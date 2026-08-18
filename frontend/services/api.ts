
import { ChatSession, Message, ProgressStep, PriceHistoryData } from '../types';

const API_BASE_URL = 'http://localhost:8000';

export const api = {
    // Create a new chat session
    createSession: async (): Promise<ChatSession> => {
        const response = await fetch(`${API_BASE_URL}/chat/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!response.ok) throw new Error('Failed to create session');
        return response.json();
    },

    // Send a message and get the AI response (non-streaming)
    askAgent: async (
        sessionId: string,
        text: string,
        history: Message[],
        providedUrl?: string,
        providedImageB64?: string,
    ): Promise<{ response: string; priceHistory?: PriceHistoryData }> => {
        const response = await fetch(`${API_BASE_URL}/chat/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                session_id: sessionId,
                provided_url: providedUrl || null,
                provided_image_b64: providedImageB64 || null,
            })
        });

        if (!response.ok) throw new Error('Failed to get response');
        const data = await response.json();

        // Map snake_case backend response to camelCase frontend type
        let priceHistory: PriceHistoryData | undefined;
        if (data.price_history) {
            const ph = data.price_history;
            priceHistory = {
                productName: ph.product_name,
                lowestPrice: ph.lowest_price,
                highestPrice: ph.highest_price,
                averagePrice: ph.average_price,
                currentPrice: ph.current_price,
                trend: ph.trend,
                recommendation: ph.recommendation,
                recommendationReason: ph.recommendation_reason,
                chartImageUrl: ph.chart_image_url,
                sourceUrl: ph.source_url,
            };
        }

        return { response: data.response, priceHistory };
    },

    // SSE Streaming: Send a message and receive progress events in real-time
    askAgentStream: async function* (
        sessionId: string,
        text: string,
        providedUrl?: string,
        providedImageB64?: string,
    ): AsyncGenerator<{ type: string; node?: string; label?: string; answer?: string; thumbnail_url?: string; done: boolean }> {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                session_id: sessionId,
                provided_url: providedUrl || null,
                provided_image_b64: providedImageB64 || null,
            })
        });

        if (!response.ok) throw new Error('Failed to start stream');
        if (!response.body) throw new Error('No response body');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events from buffer
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // Keep incomplete line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const event = JSON.parse(line.slice(6));
                        yield event;
                    } catch {
                        // Skip malformed JSON
                    }
                }
            }
        }
    },

    // Get all chat sessions for the sidebar
    getHistory: async (): Promise<ChatSession[]> => {
        const response = await fetch(`${API_BASE_URL}/chat/history`);
        if (!response.ok) throw new Error('Failed to fetch history');
        const data = await response.json();
        return data.sessions;
    },

    // Get messages for a specific session
    getSessionMessages: async (sessionId: string): Promise<Message[]> => {
        const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`);
        if (!response.ok) return [];

        const data = await response.json();

        // Transform backend Message -> Frontend Message
        return data.messages.map((m: any) => ({
            id: m.id.toString(),
            role: m.role,
            content: m.content,
            timestamp: new Date(m.timestamp)
        }));
    }
};
