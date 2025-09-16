"""
Revival Medical System Chat API Routes
API endpoints for medical chat and query functionality with role-based access control
"""

import logging
import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from agents import MedicalLangChainAgent
from auth.auth import get_current_user, UserContext, get_authorized_patient_id, require_patient_access
import os

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api/chat", tags=["chat"])

# Global variables
session_agents = {}  # Dictionary to store agent instances per session

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    sessionId: Optional[str] = None
    patient_id: Optional[int] = None  # For medical staff to query specific patients

class QueryResponse(BaseModel):
    response: str
    sessionId: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    user_context: Optional[Dict[str, Any]] = None

def get_or_create_session_agent(session_id: Optional[str] = None, openai_api_key: Optional[str] = None) -> tuple:
    """Get existing session agent or create new one"""
    global session_agents
    
    # Generate new session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Get existing agent or create new one
    if session_id not in session_agents:
        try:
            session_agents[session_id] = MedicalLangChainAgent(openai_api_key=openai_api_key or '')
            logger.info(f"✅ Created new session agent for session: {session_id[:8]}...")
        except Exception as e:
            logger.error(f"❌ Failed to create session agent: {e}")
            return None, session_id
    
    return session_agents[session_id], session_id

@router.post("/query", response_model=QueryResponse)
async def handle_query(
    request: QueryRequest, 
    current_user: UserContext = Depends(get_current_user)
):
    """Handle medical queries with LangChain agent, session management, and role-based access control"""
    logger.info(f"🔍 Received medical query from user {current_user.user_id} (Role: {current_user.role_name}): {request.query[:100]}...")
    
    try:
        query = request.query.strip()
        session_id = request.sessionId
        requested_patient_id = request.patient_id
        
        if not query:
            logger.warning("❌ Empty query received")
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        # Authorize patient access
        authorized_patient_id = get_authorized_patient_id(requested_patient_id, current_user)
        
        # For patients, modify the query to include context about their identity
        if current_user.role_id == 1:  # Patient role
            # Add patient context to the query
            query_with_context = f"[Patient Query - User ID: {current_user.user_id}] {query}"
        else:
            # For medical staff, include the authorized patient context if specified
            if authorized_patient_id:
                query_with_context = f"[Medical Staff Query - For Patient ID: {authorized_patient_id}] {query}"
            else:
                query_with_context = f"[Medical Staff Query - General] {query}"
        
        logger.info(f"📝 Processing medical query from {current_user.role_name}: '{query[:50]}{'...' if len(query) > 50 else ''}' | Session: {session_id[:8] + '...' if session_id else 'NEW'}")
        
        # Get or create session-specific agent
        session_agent, session_id = get_or_create_session_agent(session_id, os.getenv("OPENAI_API_KEY"))
        
        try:
            # Add user context to the agent if it doesn't have it
            if hasattr(session_agent, 'set_user_context'):
                session_agent.set_user_context({
                    'user_id': current_user.user_id,
                    'role_id': current_user.role_id,
                    'role_name': current_user.role_name,
                    'can_access_all_patients': current_user.can_access_all_patients,
                    'authorized_patient_id': authorized_patient_id
                })
            
            result = await session_agent.chat(query_with_context)
            logger.info(f"✅ Medical agent response generated successfully for user {current_user.user_id}")
            
            # Add session info and user context to metadata
            result_metadata = result.get("metadata", {})
            result_metadata["session_id"] = session_id
            result_metadata["conversation_length"] = len(session_agent.get_conversation_history())
            result_metadata["user_role"] = current_user.role_name
            result_metadata["authorized_patient_id"] = authorized_patient_id
            
            return QueryResponse(
                response=result["message"],
                sessionId=session_id,
                metadata=result_metadata,
                user_context={
                    "user_id": current_user.user_id,
                    "role_name": current_user.role_name,
                    "can_access_all_patients": current_user.can_access_all_patients,
                    "authorized_patient_id": authorized_patient_id
                }
            )
        except Exception as e:
            logger.error(f"❌ Medical session agent failed: {e}")
            raise HTTPException(status_code=500, detail=f"Medical agent error: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Medical query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Revival Medical System API",
        "version": "1.0.0",
        "features": [
            "Medical Data Analysis",
            "LangChain Agent",
            "Conversation Memory",
            "Patient Health Records"
        ],
        "endpoints": ["/api/chat/query", "/api/chat/sessions"],
        "status": "active"
    }

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Revival Medical System API",
        "version": "1.0.0"
    }

@router.get("/sessions")
async def get_active_sessions():
    """Get information about active sessions"""
    return {
        "active_sessions": len(session_agents),
        "session_ids": [session_id[:8] + "..." for session_id in session_agents.keys()]
    }
