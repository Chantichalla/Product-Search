
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '../types';
import { Sparkles, User, ExternalLink, Image as ImageIcon } from 'lucide-react';
import { PriceHistoryCard } from './PriceHistoryCard';

interface ChatMessageProps {
    message: Message;
}

/**
 * Fix malformed markdown tables from LLM output.
 * LLMs sometimes output pipe-tables on a single line like:
 *   | Col1 | Col2 | |------|------| | a | b |
 * This splits them into proper multi-line tables.
 */
function fixMarkdownTables(content: string): string {
    // Split pipe-table rows that are jammed together on one line
    // Pattern: "| ... | | ..." (end of one row, start of next)
    let fixed = content.replace(/\|\s*\|(?=\s*[^|])/g, '|\n|');

    // Ensure separator rows (|---|---|) are on their own line
    fixed = fixed.replace(/(\|[^|\n]*\|)\s*(\|[-:\s|]+\|)/g, '$1\n$2');
    fixed = fixed.replace(/(\|[-:\s|]+\|)\s*(\|[^-|\n])/g, '$1\n$2');

    return fixed;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
    const isUser = message.role === 'user';

    return (
        <div className={`flex gap-4 sm:gap-6 py-6 group animate-in fade-in slide-in-from-bottom-2 duration-500`}>
            <div className={`
        flex-shrink-0 w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center shadow-lg
        ${isUser
                    ? 'bg-gradient-to-br from-white/10 to-white/5 border border-white/10'
                    : 'bg-atmosphere-accent/10 border border-atmosphere-accent/20 text-atmosphere-accent'}
      `}>
                {isUser ? <User size={18} className="text-white/70" /> : <Sparkles size={18} />}
            </div>

            <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-white/80">
                        {isUser ? 'You' : 'Advisor'}
                    </span>
                    <span className="text-xs text-white/20">
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                </div>

                {/* ── User-uploaded Image Preview ── */}
                {message.imagePreview && (
                    <div className="mb-3">
                        <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10">
                            <ImageIcon size={14} className="text-white/40" />
                            <img
                                src={message.imagePreview}
                                alt="Uploaded product"
                                className="max-h-32 rounded-md object-contain"
                            />
                        </div>
                    </div>
                )}

                {/* ── Attached URL Badge ── */}
                {message.attachedUrl && (
                    <div className="mb-3">
                        <a
                            href={message.attachedUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs hover:bg-blue-500/20 transition-colors"
                        >
                            <ExternalLink size={12} />
                            <span className="truncate max-w-[300px]">{message.attachedUrl}</span>
                        </a>
                    </div>
                )}

                {/* ── Product Thumbnail (from backend visual confirmation) ── */}
                {message.productThumbnail && (
                    <div className="mb-3 flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10">
                        <img
                            src={message.productThumbnail}
                            alt="Product"
                            className="w-16 h-16 rounded-lg object-cover"
                        />
                        <span className="text-xs text-white/40">Product identified</span>
                    </div>
                )}

                <div className={`
          prose prose-invert prose-p:leading-relaxed prose-pre:bg-black/30 prose-pre:backdrop-blur-md prose-pre:border prose-pre:border-white/5
          prose-table:border-collapse prose-th:border prose-th:border-white/10 prose-th:px-3 prose-th:py-2 prose-th:bg-white/5 prose-th:text-xs prose-th:text-white/60 prose-th:font-medium
          prose-td:border prose-td:border-white/10 prose-td:px-3 prose-td:py-2 prose-td:text-sm
          max-w-none text-white/80 font-light
        `}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {fixMarkdownTables(message.content)}
                    </ReactMarkdown>
                </div>

                {/* ── Price History Card (structured data) ── */}
                {message.priceHistory && (
                    <PriceHistoryCard data={message.priceHistory} />
                )}
            </div>
        </div>
    );
};

