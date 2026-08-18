
"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { ChatInput } from '@/components/ChatInput';
import { ChatMessage } from '@/components/ChatMessage';
import { SidebarState, Message, ChatSession } from '@/types';
import { api } from '@/services/api'; // Use real API
import { Sparkles } from 'lucide-react';
import { useSearchParams } from 'next/navigation';

export default function ChatPage() {
    const [sidebarState, setSidebarState] = useState<SidebarState>(SidebarState.Expanded);
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [history, setHistory] = useState<ChatSession[]>([]);

    const bottomRef = useRef<HTMLDivElement>(null);
    const searchParams = useSearchParams();
    const initialQuery = searchParams.get('q');
    const hasInitialized = useRef(false);

    // Load History on Mount
    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            const sessions = await api.getHistory();
            setHistory(sessions);
            if (sessions.length > 0 && !activeSessionId && !initialQuery) {
                // Load the most recent session if no initial query
                setActiveSessionId(sessions[0].id);
            }
        } catch (e) {
            console.error("Failed to load history", e);
        }
    };

    // Handle Selection of Session
    useEffect(() => {
        if (activeSessionId) {
            loadSessionMessages(activeSessionId);
        }
    }, [activeSessionId]);

    const loadSessionMessages = async (sessionId: string) => {
        setIsLoading(true);
        try {
            const msgs = await api.getSessionMessages(sessionId);
            setMessages(msgs);
        } catch (e) {
            console.error("Failed to load messages", e);
        } finally {
            setIsLoading(false);
        }
    };

    // Handle Initial Landing Page Query
    useEffect(() => {
        if (initialQuery && !hasInitialized.current) {
            hasInitialized.current = true;
            startNewChatWithQuery(initialQuery);
        }
    }, [initialQuery]);

    const startNewChatWithQuery = async (query: string) => {
        setIsLoading(true);
        try {
            const session = await api.createSession();
            setHistory(prev => [session, ...prev]);
            setActiveSessionId(session.id);
            setMessages([]); // Clear previous messages

            // Send the initial message immediately
            await handleSendMessage(query, session.id);
        } catch (e) {
            console.error("Failed to start chat from landing", e);
            setIsLoading(false);
        }
    };

    const toggleSidebar = () => {
        setSidebarState(prev => prev === SidebarState.Expanded ? SidebarState.Collapsed : SidebarState.Expanded);
    };

    const handleSend = async (text: string) => {
        if (!activeSessionId) {
            // If no session, create one first
            try {
                const session = await api.createSession();
                setHistory(prev => [session, ...prev]);
                setActiveSessionId(session.id);
                await handleSendMessage(text, session.id);
            } catch (e) {
                console.error("Failed to create session on send", e);
            }
        } else {
            await handleSendMessage(text, activeSessionId);
        }
    };

    const handleSendMessage = async (text: string, sessionId: string) => {
        // Optimistic Update
        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: text,
            timestamp: new Date(),
        };

        setMessages(prev => [...prev, userMsg]);
        setIsLoading(true);

        try {
            // Extract URL from message text (if user pasted a product link)
            const urlMatch = text.match(/https?:\/\/[^\s)\]}>]+/);
            const providedUrl = urlMatch ? urlMatch[0] : undefined;

            const { response: responseText, priceHistory } = await api.askAgent(sessionId, text, messages, providedUrl);

            const modelMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'model',
                content: responseText,
                timestamp: new Date(),
                priceHistory: priceHistory,
            };

            setMessages(prev => [...prev, modelMsg]);

            // Refresh history to update timestamps/titles if needed
            if (messages.length < 2) {
                loadHistory();
            }

        } catch (error) {
            console.error(error);
            const errorMsg: Message = {
                id: (Date.now() + 1).toString(),
                role: 'model',
                content: "I'm having trouble connecting to the network through the fog. Please try again.",
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMsg]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleNewChat = async () => {
        try {
            const session = await api.createSession();
            setHistory(prev => [session, ...prev]);
            setActiveSessionId(session.id);
            setMessages([{ id: '0', role: 'model', content: 'Ready for a new inquiry.', timestamp: new Date() }]);
        } catch (e) {
            console.error("Failed to create new chat", e);
        }
    };

    // Scroll to bottom on new message
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const sidebarWidth = sidebarState === SidebarState.Expanded ? 'ml-[260px]' : 'ml-[60px]';

    return (
        <div className="relative h-screen w-full bg-atmosphere-dark text-white overflow-hidden">
            {/* Background Ambience */}
            <div className="absolute inset-0 bg-gradient-to-br from-atmosphere-dark via-[#131614] to-black z-0" />
            <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-atmosphere-base/20 rounded-full blur-[120px] pointer-events-none animate-pulse opacity-50" />

            {/* Fixed Sidebar Layer */}
            <Sidebar
                state={sidebarState}
                onToggle={toggleSidebar}
                history={history}
                activeSessionId={activeSessionId}
                onSelectSession={setActiveSessionId}
                onNewChat={handleNewChat}
            />

            {/* Main Content Shell - Moves when sidebar expands/collapses */}
            <main
                className={`
            relative z-10 h-full flex flex-col 
            ${sidebarWidth} 
            transition-all duration-500 ease-[cubic-bezier(0.25,0.1,0.25,1)]
        `}
            >

                {/* Fixed Header */}
                <header className="absolute top-0 left-0 right-0 h-16 z-30 flex items-center justify-between px-6 bg-gradient-to-b from-atmosphere-dark via-atmosphere-dark/80 to-transparent backdrop-blur-[2px]">
                    <div className="flex items-center gap-2">
                        <Sparkles size={16} className="text-atmosphere-accent/70" />
                        <span className="text-sm font-medium tracking-wide text-white/80">Aether Advisor</span>
                    </div>
                </header>

                {/* Scrollable Message Area */}
                <div className="flex-1 overflow-y-auto no-scrollbar">
                    <div className="w-full h-full">
                        <div className={`max-w-3xl mx-auto flex flex-col pt-24 pb-32 px-4 transition-all duration-500`}>
                            {messages.map(msg => (
                                <ChatMessage key={msg.id} message={msg} />
                            ))}
                            <div ref={bottomRef} />
                        </div>
                    </div>
                </div>

                {/* Sticky Input Area - Floating above bottom */}
                <div className="absolute bottom-0 left-0 right-0 p-6 z-40 pointer-events-none bg-gradient-to-t from-atmosphere-dark via-atmosphere-dark/90 to-transparent h-32 flex items-end justify-center">
                    <div className="w-full max-w-3xl pointer-events-auto mb-2">
                        <ChatInput onSend={handleSend} isLoading={isLoading} />
                    </div>
                </div>

            </main>
        </div>
    );
}
