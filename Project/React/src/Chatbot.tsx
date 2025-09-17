import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

// Extend Window interface for Speech Recognition
declare global {
    interface Window {
        SpeechRecognition: any;
        webkitSpeechRecognition: any;
    }
}

const Chatbot: React.FC = () => {
    const [isOpen, setIsOpen] = useState<boolean>(false); // Toggle chatbot visibility
    const [userQuery, setUserQuery] = useState<string>(""); // User's input
    const [chatHistory, setChatHistory] = useState<{ role: "user" | "bot"; message: string; metadata?: any }[]>([
        {
            role: "bot",
            message:
                "Hello! I am your Revival365 AI Assistant. How can I help you today? You want know your records, CGM values,  medication schedules with dates ",
        },
    ]); // Chat history
    const [isLoading, setIsLoading] = useState<boolean>(false); // Loading state
    const [isListening, setIsListening] = useState<boolean>(false); // Voice recognition state
    const [sessionId, setSessionId] = useState<string>(""); // Session ID
    const recognitionRef = useRef<any>(null);
    const chatEndRef = useRef<HTMLDivElement | null>(null);

    // Generate or retrieve session ID
    const generateSessionId = () => {
        return Math.floor(Math.random() * 99999999).toString();
    };

    useEffect(() => {});

    // Initialize session ID
    useEffect(() => {
        let storedSessionId = sessionStorage.getItem("chatbot_session_id");
        if (!storedSessionId) {
            storedSessionId = generateSessionId();
            sessionStorage.setItem("chatbot_session_id", storedSessionId);
        }
        setSessionId(storedSessionId);
    }, []);

    const predefinedQuestions = [
        "Steps to Pair the CGM Device on Linx Application",
        "Steps to Pair the CGM Device on iOS ",
        "Steps to Pair the CGM Device on iOS",
        "How to Pair the Wrist Band Device on IOS",
        "Steps to Pair the CGM Device on Android",
        "Steps to Pair the Band on Android",
    ];

    // Custom components for ReactMarkdown
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

    // Initialize Speech Recognition
    useEffect(() => {
        if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = false;
            recognitionRef.current.lang = "en-US";

            recognitionRef.current.onresult = (event: any) => {
                const transcript = event.results[0][0].transcript;
                handleSendMessage(transcript);
                //setUserQuery(transcript);
                setIsListening(false);
            };

            recognitionRef.current.onerror = (event: any) => {
                console.error("Speech recognition error:", event.error);
                setIsListening(false);
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };
        }

        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
        };
    }, []);

    const startListening = () => {
        if (recognitionRef.current && !isListening) {
            setIsListening(true);
            recognitionRef.current.start();
        }
    };

    const stopListening = () => {
        if (recognitionRef.current && isListening) {
            recognitionRef.current.stop();
            setIsListening(false);
        }
    };

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
            // Call the enhanced query API
            //const response = await fetch("http://13.200.229.28:8000/api/chat/query", {
                const response = await fetch("/api/chat/query", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    // this is docter's token
                    Authorization: `Bearer testtt`, // Use environment variable for API key

                    // below is the token of patient
                    //Authorization: `Bearer cA5yeQGBJ0jtrOd9OY9cUE:APA91bHxJwsailj3LabcsYBGwCXMD3v4tp4kthlabzXn32G-WVmNHZWxs5BeN7USWHnMrlGib-mzfOSmpX4LEOlxTzJNXonfvZFerZzc4FJ9wGIkkbia1tk`, // Use environment variable for API key
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

            // Add bot's response with metadata to chat history
            const botMessage = data.response;
            const metadata = data.metadata;

            // Add visual indicators based on query type
            let messagePrefix = "";
            // if (metadata?.used_mcp) {
            //     messagePrefix = "📊 **Real-time Data**: ";
            // } else if (metadata?.query_type === "rag") {
            //     messagePrefix = "📚 **From Handbook**: ";
            // }

            setChatHistory((prev) => [
                ...prev,
                {
                    role: "bot",
                    message: messagePrefix + botMessage,
                    metadata: metadata,
                },
            ]);
        } catch (error) {
            console.error("Error:", error);
            setChatHistory((prev) => [...prev, { role: "bot", message: "Something went wrong. Please try again." }]);
        } finally {
            setIsLoading(false);
            setUserQuery(""); // Clear input field
        }
    };

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
                    <div className="flex border-t border-gray-300 bg-white p-3">
                        <input
                            type="text"
                            value={userQuery}
                            onChange={(e) => setUserQuery(e.target.value)}
                            onKeyDown={handleKeyDown} // Handle Enter key
                            placeholder="Type your question or use the microphone..."
                            className="rounded pr-20 flex-1 border border-gray-300 p-2 focus:outline-none focus:ring focus:ring-blue-300"
                            disabled={isLoading}
                        />
                        {/* Microphone Button */}
                        <button
                            onClick={isListening ? stopListening : startListening}
                            className={`rounded -ml-16 pr-2 py-2 ${
                                isListening ? "text-red-500 hover:text-red-600" : "text-gray-600 hover:text-gray-800"
                            } disabled:text-gray-400`}
                            disabled={isLoading}
                            title={isListening ? "Stop listening" : "Start voice input"}
                        >
                            {isListening ? (
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="inline-block">
                                    <circle cx="12" cy="12" r="8" opacity="0.3">
                                        <animate attributeName="r" values="8;12;8" dur="1.5s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" values="0.3;0.1;0.3" dur="1.5s" repeatCount="indefinite" />
                                    </circle>
                                    <circle cx="12" cy="12" r="6" opacity="0.5">
                                        <animate attributeName="r" values="6;9;6" dur="1s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" values="0.5;0.2;0.5" dur="1s" repeatCount="indefinite" />
                                    </circle>
                                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
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
