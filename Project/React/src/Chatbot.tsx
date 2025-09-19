import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

// Extend Window interface for potential browser APIs
declare global {
    interface Window {
        SpeechRecognition: any;
        webkitSpeechRecognition: any;
    }
}

/**
 * Chatbot component for the Revival365 web application.
 *
 * This component implements both text and voice interactions.  In addition
 * to the upstream functionality it introduces a microphone button that
 * offers two voice modes: 'Regional' and 'International'.  When the user
 * selects one of these modes the component records audio using the
 * MediaRecorder API, encodes the recording as a base64 data URL and sends
 * it to the backend `/api/chat/voice` endpoint along with the selected
 * language hint.  The server transcribes and translates the audio as
 * necessary before generating a response from the LangChain agent.
 */
const Chatbot: React.FC = () => {
    // Toggle chatbot visibility
    const [isOpen, setIsOpen] = useState<boolean>(false);
    // User's text input
    const [userQuery, setUserQuery] = useState<string>("");
    // Chat history (user and bot messages)
    const [chatHistory, setChatHistory] = useState<
        { role: "user" | "bot"; message: string; metadata?: any }[]
    >([
        {
            role: "bot",
            message:
                "Hello! I am your Revival365 AI Assistant. How can I help you today? You want know your records, CGM values,  medication schedules with dates ",
        },
    ]);
    // Loading state for API requests
    const [isLoading, setIsLoading] = useState<boolean>(false);
    // Session ID to persist conversation context
    const [sessionId, setSessionId] = useState<string>("");

    // Voice recording state
    const [showMicOptions, setShowMicOptions] = useState<boolean>(false);
    const [isRecording, setIsRecording] = useState<boolean>(false);
    const [selectedLanguage, setSelectedLanguage] = useState<"regional" | "international" | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    const chatEndRef = useRef<HTMLDivElement | null>(null);

    // 🔊 Audio / silence detection refs (NEW)
    const streamRef = useRef<MediaStream | null>(null);
    const audioCtxRef = useRef<AudioContext | null>(null);
    const analyserRef = useRef<AnalyserNode | null>(null);
    const silenceTimerRef = useRef<number | null>(null);
    const recordingStartedAtRef = useRef<number>(0);
    const lastSpeechAtRef = useRef<number>(0);
    const speechDetectedRef = useRef<boolean>(false);

    // Silence/VAD tuning (NEW)
    const SILENCE_THRESHOLD = 0.02;            // lower = more sensitive
    const INITIAL_SILENCE_TIMEOUT_MS = 5000;   // stop if no speech for first 5s
    const SILENCE_AFTER_SPEECH_MS = 1200;      // stop ~1.2s after speaker finishes
    const ANALYZE_INTERVAL_MS = 100;           // check 10x/second

    // Generate a pseudo-random session ID (8 digits)
    const generateSessionId = () => {
        return Math.floor(Math.random() * 99999999).toString();
    };

    // Initialize session ID on mount
    useEffect(() => {
        let storedSessionId = sessionStorage.getItem("chatbot_session_id");
        if (!storedSessionId) {
            storedSessionId = generateSessionId();
            sessionStorage.setItem("chatbot_session_id", storedSessionId);
        }
        setSessionId(storedSessionId);
    }, []);

    // Cleanup audio graph on unmount (NEW)
    useEffect(() => {
        return () => {
            cleanupAudioGraph();
            stopStreamTracks();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const predefinedQuestions = [
        "Steps to Pair the CGM Device on Linx Application",
        "Steps to Pair the CGM Device on iOS ",
        "Steps to Pair the CGM Device on iOS",
        "How to Pair the Wrist Band Device on IOS",
        "Steps to Pair the CGM Device on Android",
        "Steps to Pair the Band on Android",
    ];

    // Custom components for ReactMarkdown to style various Markdown elements
    const markdownComponents = {
        h1: ({ children }: any) => <h1 className="text-2xl font-bold mt-4 mb-3">{children}</h1>,
        h2: ({ children }: any) => <h2 className="text-xl font-bold mt-4 mb-3">{children}</h2>,
        h3: ({ children }: any) => <h3 className="text-lg font-bold mt-4 mb-2 border-b border-blue-200 pb-1">{children}</h3>,
        p: ({ children }: any) => <p className="mt-6 mb-2">{children}</p>,
        ul: ({ children }: any) => <ul className="list-disc pl-4 list-outside mb-2 ml-2">{children}</ul>,
        ol: ({ children }: any) => <ol className="list-decimal pl-4 list-outside mb-2 ml-2">{children}</ol>,
        li: ({ children }: any) => <li className="mb-1">{children}</li>,
        strong: ({ children }: any) => <strong className="font-bold">{children}</strong>,
        em: ({ children }: any) => <em className="italic">{children}</em>,
        img: ({ src, alt }: any) => (
            <div className="my-3">
                <img
                    src={src}
                    alt={alt}
                    className="max-w-full h-auto rounded-lg shadow-md border"
                    style={{ maxHeight: "300px", objectFit: "contain" }}
                    onError={(e: any) => {
                        e.target.style.display = "none";
                        e.target.nextElementSibling.style.display = "block";
                    }}
                />
                <div className="text-sm text-gray-500 italic mt-1 hidden">Image failed to load: {alt}</div>
            </div>
        ),
        code: ({ children, className }: any) => {
            const isInline = !className;
            if (isInline) {
                return <code className="bg-gray-100 px-1 py-0.5 rounded text-sm">{children}</code>;
            }
            return (
                <pre className="bg-gray-100 p-3 rounded-lg overflow-x-auto mb-2">
                    <code className="text-sm">{children}</code>
                </pre>
            );
        },
        blockquote: ({ children }: any) => (
            <blockquote className="border-l-4 border-blue-300 pl-4 my-2 italic text-gray-600">{children}</blockquote>
        ),
    };

    // Auto-scroll to last message when chatHistory changes
    useEffect(() => {
        if (chatEndRef.current) {
            chatEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [chatHistory, isLoading]);

    /**
     * Send a text query to the server and update the chat history.
     */
    const handleSendMessage = async (message?: string) => {
        const query = message || userQuery;
        if (!query.trim()) {
            return; // Do not send empty messages
        }
        setUserQuery(""); // Clear input field immediately

        // Add user's message to chat history
        setChatHistory((prev) => [...prev, { role: "user", message: query }]);
        setIsLoading(true);

        try {
            const response = await fetch("/api/chat/query", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    // Use doctor token for now; in a real app this should come from auth context
                    Authorization: `Bearer testtt`,
                },
                body: JSON.stringify({
                    query: query,
                    sessionId: sessionId,
                }),
            });
            if (!response.ok) {
                throw new Error("Failed to fetch response from the server.");
            }
            const data = await response.json();
            const botMessage = data.response;
            const metadata = data.metadata;
            setChatHistory((prev) => [
                ...prev,
                {
                    role: "bot",
                    message: botMessage,
                    metadata: metadata,
                },
            ]);
        } catch (error) {
            console.error("Error:", error);
            setChatHistory((prev) => [
                ...prev,
                { role: "bot", message: "Something went wrong. Please try again." },
            ]);
        } finally {
            setIsLoading(false);
            setUserQuery(""); // Clear input field
        }
    };

    /**
     * Toggle the microphone button behaviour.  When not recording this will
     * display the language selection menu.  When recording it will stop
     * the current recording.
     */
    const handleMicButtonClick = () => {
        if (isRecording) {
            stopRecording(); // manual stop
        } else {
            setShowMicOptions((prev) => !prev);
        }
    };

    /**
     * Start recording audio and set the selected language.  Hides the
     * language selection menu and begins capturing microphone input.
     * Adds silence detection to auto-stop.
     */
    const startRecording = async (language: "regional" | "international") => {
        setSelectedLanguage(language);
        setShowMicOptions(false);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            audioChunksRef.current = [];
            mediaRecorder.ondataavailable = (event: BlobEvent) => {
                if (event.data && event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };
            mediaRecorder.onstop = async () => {
                try {
                    const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
                    const reader = new FileReader();
                    reader.onloadend = async () => {
                        const base64String = reader.result?.toString() || "";
                        await sendVoiceMessage(base64String, language);
                    };
                    reader.readAsDataURL(audioBlob);
                } catch (e) {
                    console.error("Finalize voice error:", e);
                    setChatHistory((prev) => [
                        ...prev,
                        { role: "bot", message: "Something went wrong. Please try again." },
                    ]);
                } finally {
                    stopStreamTracks();
                }
            };

            mediaRecorder.start();
            setIsRecording(true);

            // Start silence detection (NEW)
            startSilenceDetection(stream);
        } catch (error) {
            console.error("Error accessing microphone:", error);
        }
    };

    /**
     * Stop the current recording if one is in progress.
     */
    const stopRecording = () => {
        try {
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
                mediaRecorderRef.current.stop();
            }
        } catch {}
        setIsRecording(false);
        cleanupAudioGraph(); // stop silence detection & close AudioContext (NEW)
    };

    const stopStreamTracks = () => {
        try {
            streamRef.current?.getTracks().forEach((t) => t.stop());
        } catch {}
        streamRef.current = null;
    };

    // ---- Silence Detection (NEW) ----
    const startSilenceDetection = (stream: MediaStream) => {
        cleanupAudioGraph();

        const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;

        source.connect(analyser);

        audioCtxRef.current = audioCtx;
        analyserRef.current = analyser;

        recordingStartedAtRef.current = Date.now();
        lastSpeechAtRef.current = Date.now();
        speechDetectedRef.current = false;

        const buffer = new Float32Array(analyser.fftSize);

        const check = () => {
            if (!analyserRef.current) return;

            analyserRef.current.getFloatTimeDomainData(buffer);
            // Compute RMS
            let sum = 0;
            for (let i = 0; i < buffer.length; i++) {
                const x = buffer[i];
                sum += x * x;
            }
            const rms = Math.sqrt(sum / buffer.length);

            const now = Date.now();

            if (rms > SILENCE_THRESHOLD) {
                // speech present
                speechDetectedRef.current = true;
                lastSpeechAtRef.current = now;
            }

            // Initial no-speech timeout
            if (!speechDetectedRef.current) {
                if (now - recordingStartedAtRef.current > INITIAL_SILENCE_TIMEOUT_MS) {
                    stopRecording();
                    return;
                }
            } else {
                // After speech, stop when silent for SILENCE_AFTER_SPEECH_MS
                if (now - lastSpeechAtRef.current > SILENCE_AFTER_SPEECH_MS) {
                    stopRecording();
                    return;
                }
            }
        };

        silenceTimerRef.current = window.setInterval(check, ANALYZE_INTERVAL_MS);
    };

    const cleanupAudioGraph = () => {
        if (silenceTimerRef.current) {
            window.clearInterval(silenceTimerRef.current);
            silenceTimerRef.current = null;
        }
        try {
            audioCtxRef.current?.close();
        } catch {}
        audioCtxRef.current = null;
        analyserRef.current = null;
    };
    // ---- End Silence Detection ----

    // Helper to decide which text to show as the user's question after voice
    function pickDisplayedTranscript(
        data: any,
        lang: "regional" | "international" | null
    ): string {
        const meta = data?.metadata || {};
        const candidates: string[] = [
            data?.translatedTranscript,
            data?.translation,
            meta?.translatedTranscript,
            meta?.translation,
        ].filter(Boolean);

        if (lang === "international") {
            const translated = candidates.find(Boolean);
            if (translated && typeof translated === "string") return translated.trim();
            return (data?.transcript || meta?.transcript || "").trim();
        }

        return (
            (candidates.find(Boolean) as string | undefined) ||
            data?.transcript ||
            meta?.transcript ||
            ""
        ).trim();
    }

    /**
     * Send a voice message to the backend API.  The message is represented as
     * a base64-encoded audio string (no data URL prefix) plus a language hint.
     * UI: show loader, then add transcribed/translated question as user bubble, then bot reply.
     */
    const sendVoiceMessage = async (base64Audio: string, language: "regional" | "international") => {
        setIsLoading(true);

        try {
            // Strip "data:audio/...;base64," prefix if present
            const audioBase64 = base64Audio.includes(",") ? base64Audio.split(",")[1] : base64Audio;

            const response = await fetch("/api/chat/voice", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer testtt`,
                },
                body: JSON.stringify({
                    audioBase64,                // expected key
                    language,                   // "regional" | "international"
                    sessionId: sessionId ?? "", // keep session continuity
                }),
            });

            if (!response.ok) {
                const errText = await response.text().catch(() => "");
                throw new Error(`Failed to fetch voice response from the server. ${errText}`);
            }

            const data = await response.json();
            const botMessage = data.response;
            const metadata = data.metadata;

            // Show the (translated, if available) question first
            const displayedQuestion = pickDisplayedTranscript(data, language);
            if (displayedQuestion) {
                setChatHistory((prev) => [...prev, { role: "user", message: displayedQuestion }]);
            }

            // Then, show the bot's answer
            setChatHistory((prev) => [
                ...prev,
                {
                    role: "bot",
                    message: botMessage,
                    metadata: metadata,
                },
            ]);
        } catch (error) {
            console.error(error);
            setChatHistory((prev) => [...prev, { role: "bot", message: "Something went wrong. Please try again." }]);
        } finally {
            setIsLoading(false);
        }
    };

    /**
     * Handle keyboard events on the text input (e.g. press Enter to send).
     */
    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter" && !isLoading) {
            handleSendMessage();
        }
    };

    return (
        <>
            {/* Chatbot Toggle Button */}
            <div
                onClick={() => setIsOpen(!isOpen)}
                className="fixed bottom-5 right-5 flex h-16 w-16 cursor-pointer items-center justify-center rounded-full bg-blue-500 text-white shadow-lg hover:bg-blue-600 transition-colors"
            >
                <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
            </div>

            {/* Chatbot Window */}
            {isOpen && (
                <div className="fixed top-0 bottom-0 right-0 z-999 flex max-h-dvh w-[35%] flex-col overflow-hidden rounded-lg border border-gray-300 bg-white shadow-lg">
                    {/* Header */}
                    <div className="flex items-center justify-between relative bg-blue-500 p-3 text-center font-bold text-white">
                        <span>Chatbot</span>
                        <button onClick={() => setIsOpen(false)} className="text-white hover:text-gray-200">
                            <svg
                                width="20"
                                height="20"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            >
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                    </div>

                    {/* Chat History */}
                    <div className="min-h-90 flex-1 overflow-y-auto bg-gray-100">
                        <div className="p-3">
                            {chatHistory.map((chat, index) => (
                                <div key={index} className={`flex ${chat.role === "user" ? "justify-end" : "justify-start"} mb-3`}>
                                    <div
                                        className={`max-w-[85%] rounded-lg p-3 shadow ${
                                            chat.role === "user" ? "bg-blue-500 text-white" : "bg-gray-200 text-black"
                                        }`}
                                    >
                                        <strong>{chat.role === "user" ? "You" : "Bot"}:</strong>{" "}
                                        <div className="mt-2">
                                            {chat.role === "bot" ? (
                                                <ReactMarkdown components={markdownComponents}>{chat.message}</ReactMarkdown>
                                            ) : (
                                                <span>{chat.message}</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {/* Loading indicator */}
                            {isLoading && (
                                <div className="flex justify-start mb-3">
                                    <div className="max-w-[85%] rounded-lg p-3 shadow bg-gray-200 text-black flex items-center">
                                        <svg
                                            className="animate-spin mr-2"
                                            width="20"
                                            height="20"
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="2"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        >
                                            <circle cx="12" cy="12" r="10" strokeOpacity="0.2" />
                                            <path d="M12 2a10 10 0 0 1 10 10" />
                                        </svg>
                                        <span>Processing...</span>
                                    </div>
                                </div>
                            )}
                            <div ref={chatEndRef} />
                        </div>
                        {/* Predefined Questions */}
                        {!isLoading && (
                            <div className="flex flex-wrap gap-2 border-t border-gray-300 bg-gray-50 p-3">
                                {predefinedQuestions.map((question, index) => (
                                    <button
                                        key={index}
                                        onClick={() => handleSendMessage(question)}
                                        className="rounded bg-blue-100 px-3 py-1 text-sm text-blue-700 hover:bg-blue-200"
                                    >
                                        {question}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Input Area */}
                    <div className="flex border-t border-gray-300 bg-white p-3 relative">
                        <input
                            type="text"
                            value={userQuery}
                            onChange={(e) => setUserQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Type your question or use the microphone..."
                            className="rounded pr-20 flex-1 border border-gray-300 p-2 focus:outline-none focus:ring focus:ring-blue-300"
                            disabled={isLoading || isRecording}
                        />
                        {/* Microphone Options Menu */}
                        {showMicOptions && !isRecording && (
                            <div className="absolute bottom-14 right-20 z-50 bg-white border border-gray-300 rounded shadow-lg">
                                <button
                                    onClick={() => startRecording("regional")}
                                    className="block w-full px-4 py-2 text-left hover:bg-gray-100"
                                >
                                    Regional
                                </button>
                                <button
                                    onClick={() => startRecording("international")}
                                    className="block w-full px-4 py-2 text-left hover:bg-gray-100"
                                >
                                    International
                                </button>
                            </div>
                        )}
                        {/* Microphone Button */}
                        <button
                            onClick={handleMicButtonClick}
                            className={`rounded -ml-16 pr-2 py-2 ${
                                isRecording ? "text-red-500 hover:text-red-600" : "text-gray-600 hover:text-gray-800"
                            } disabled:text-gray-400`}
                            disabled={isLoading}
                            title={isRecording ? "Stop recording" : "Start voice input"}
                        >
                            {isRecording ? (
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="inline-block">
                                    <circle cx="12" cy="12" r="8" opacity="0.3">
                                        <animate attributeName="r" values="8;12;8" dur="1.5s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" values="0.3;0.1;0.3" dur="1.5s" repeatCount="indefinite" />
                                    </circle>
                                    <circle cx="12" cy="12" r="6" opacity="0.5">
                                        <animate attributeName="r" values="6;9;6" dur="1s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" values="0.5;0.2;0.5" dur="1s" repeatCount="indefinite" />
                                    </circle>
                                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c1.66 0 3 1.34 3 3z" />
                                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                                </svg>
                            ) : (
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="inline-block">
                                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                                </svg>
                            )}
                        </button>
                        <button
                            onClick={() => handleSendMessage()}
                            className="rounded rounded-l-none bg-blue-500 px-3 py-2 text-white hover:bg-blue-600 disabled:bg-gray-400 flex items-center justify-center"
                            disabled={isLoading}
                            title="Send"
                        >
                            <svg
                                width="22"
                                height="22"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            >
                                <line x1="22" y1="2" x2="11" y2="13" />
                                <polygon points="22 2 15 22 11 13 2 9 22 2" />
                            </svg>
                        </button>
                    </div>
                </div>
            )}
        </>
    );
};

export default Chatbot;
