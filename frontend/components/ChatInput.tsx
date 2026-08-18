
import React, { useState, useRef, useEffect } from 'react';
import { Send, Sparkles } from 'lucide-react';

interface ChatInputProps {
    onSend: (message: string) => void;
    isLoading: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, isLoading }) => {
    const [input, setInput] = useState('');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleSubmit = () => {
        if (!input.trim() || isLoading) return;
        onSend(input);
        setInput('');
    };

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
        }
    }, [input]);

    return (
        <div className="relative w-full max-w-3xl mx-auto">
            <div className={`
        relative flex items-end gap-2 p-2 rounded-[24px]
        bg-black/40 backdrop-blur-xl border border-white/10
        shadow-[0_8px_32px_rgba(0,0,0,0.3)]
        transition-all duration-300 focus-within:border-white/20 focus-within:bg-black/50
      `}>
                <div className="pl-4 pb-3 text-white/30">
                    <Sparkles size={18} />
                </div>

                <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask the Advisor..."
                    disabled={isLoading}
                    rows={1}
                    className="
            flex-1 bg-transparent border-none outline-none 
            text-white placeholder-white/30 resize-none
            py-3 max-h-[120px] overflow-y-auto font-light leading-relaxed
          "
                    style={{ minHeight: '44px' }}
                />

                <button
                    onClick={handleSubmit}
                    disabled={!input.trim() || isLoading}
                    className={`
            mb-1 p-2 rounded-full flex items-center justify-center transition-all duration-300
            ${input.trim() && !isLoading
                            ? 'bg-white text-atmosphere-base shadow-[0_0_15px_rgba(255,255,255,0.3)] scale-100 opacity-100'
                            : 'bg-white/5 text-white/20 scale-90 opacity-50'}
          `}
                >
                    {isLoading ? (
                        <div className="w-5 h-5 border-2 border-atmosphere-base/30 border-t-atmosphere-base rounded-full animate-spin" />
                    ) : (
                        <Send size={18} className={input.trim() ? "animate-pulse" : ""} />
                    )}
                </button>
            </div>

            <div className="text-center mt-3 text-xs text-white/20 font-light">
                AI can make mistakes. Check important info.
            </div>
        </div>
    );
};
