"""
Service for handling Speech-to-Text using Sarvam AI
"""

import os
import httpx
import logging
from fastapi import UploadFile, HTTPException, status

logger = logging.getLogger(__name__)

# Get the Sarvam AI key and URL from your environment variables
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_API_URL = os.getenv("SARVAM_API_URL", "https://api.sarvam.ai/v1/speech-to-text")

async def transcribe_audio_to_english(file: UploadFile) -> str:
    """
    Transcribes audio using Sarvam AI. It auto-detects the language
    and provides the transcription in English.
    """
    if not SARVAM_API_KEY:
        logger.error("SARVAM_API_KEY is not configured in the environment variables.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The speech-to-text service is not configured on the server."
        )

    headers = {
        "Authorization": f"Bearer {SARVAM_API_KEY}"
    }

    # NOTE: These parameters are based on your request and common API patterns.
    # You may need to adjust them based on Sarvam AI's official documentation.
    params = {
        "model": "indic-speech-v3",  # Example model for Indian languages
        "language": "auto-detect",   # Auto-detects the spoken language
        "task": "translate_to_english" # Translates the transcription to English
    }

    try:
        audio_content = await file.read()
        files = {'file': (file.filename, audio_content, file.content_type)}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info("Sending audio to Sarvam AI for transcription...")
            response = await client.post(SARVAM_API_URL, headers=headers, params=params, files=files)
        
        response.raise_for_status()
        
        result = response.json()
        
        if "text" in result and result["text"]:
            transcribed_text = result["text"]
            logger.info(f"Successfully transcribed audio. Text: '{transcribed_text}'")
            return transcribed_text
        else:
            logger.error(f"Sarvam AI returned an empty transcription. Response: {result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get a valid transcription from the speech service."
            )

    except httpx.HTTPStatusError as e:
        error_message = f"Error from Sarvam AI API: {e.response.status_code} - {e.response.text}"
        logger.error(error_message)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error communicating with the speech service."
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred during transcription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the audio."
        )