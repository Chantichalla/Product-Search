
import React from 'react';
import { PriceHistoryData } from '../types';
import { TrendingDown, TrendingUp, Minus, ExternalLink, ShoppingCart, Clock } from 'lucide-react';

interface PriceHistoryCardProps {
    data: PriceHistoryData;
}

/**
 * Format a price in INR with comma separators.
 */
function formatPrice(price: number | null): string {
    if (price === null || price === undefined) return '—';
    return `₹${price.toLocaleString('en-IN')}`;
}

/**
 * Get the recommendation badge styling.
 */
function getRecBadge(rec: string): { bg: string; text: string; label: string; icon: React.ReactNode } {
    switch (rec) {
        case 'STRONG_BUY':
            return {
                bg: 'bg-emerald-500/20 border-emerald-500/30',
                text: 'text-emerald-400',
                label: '🔥 Strong Buy',
                icon: <ShoppingCart size={14} />,
            };
        case 'BUY':
            return {
                bg: 'bg-green-500/15 border-green-500/25',
                text: 'text-green-400',
                label: '✅ Good to Buy',
                icon: <ShoppingCart size={14} />,
            };
        case 'WAIT':
            return {
                bg: 'bg-amber-500/15 border-amber-500/25',
                text: 'text-amber-400',
                label: '⏳ Wait for Drop',
                icon: <Clock size={14} />,
            };
        default:
            return {
                bg: 'bg-white/5 border-white/10',
                text: 'text-white/60',
                label: '— Neutral',
                icon: <Minus size={14} />,
            };
    }
}

/**
 * Get the trend icon component.
 */
function TrendIcon({ trend }: { trend: string }) {
    switch (trend) {
        case 'declining':
            return <TrendingDown size={16} className="text-green-400" />;
        case 'rising':
            return <TrendingUp size={16} className="text-red-400" />;
        default:
            return <Minus size={16} className="text-white/40" />;
    }
}

export const PriceHistoryCard: React.FC<PriceHistoryCardProps> = ({ data }) => {
    const badge = getRecBadge(data.recommendation);

    return (
        <div className="mt-4 rounded-2xl overflow-hidden border border-white/[0.08] bg-gradient-to-br from-white/[0.04] to-white/[0.01] backdrop-blur-xl shadow-2xl">
            {/* Header */}
            <div className="px-5 pt-4 pb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-white/30">
                        📊 Price History
                    </span>
                    <TrendIcon trend={data.trend} />
                </div>
                {data.sourceUrl && (
                    <a
                        href={data.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 text-[11px] text-white/25 hover:text-white/50 transition-colors"
                    >
                        <span>pricehistory.app</span>
                        <ExternalLink size={10} />
                    </a>
                )}
            </div>

            {/* Price Stats Grid */}
            <div className="px-5 grid grid-cols-4 gap-3 pb-4">
                <PriceStat label="Lowest" value={data.lowestPrice} accent="text-emerald-400" />
                <PriceStat label="Average" value={data.averagePrice} accent="text-blue-400" />
                <PriceStat label="Highest" value={data.highestPrice} accent="text-red-400/70" />
                <PriceStat label="Current" value={data.currentPrice} accent="text-white" highlight />
            </div>

            {/* View Full Chart Link */}
            {data.sourceUrl && (
                <div className="px-5 pb-4">
                    <a
                        href={data.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl border border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.06] transition-all text-xs text-white/40 hover:text-white/60"
                    >
                        <ExternalLink size={12} />
                        <span>View Full Price Chart on pricehistory.app</span>
                    </a>
                </div>
            )}

            {/* Recommendation Banner */}
            <div className={`mx-5 mb-4 px-4 py-3 rounded-xl border ${badge.bg} flex items-start gap-3`}>
                <span className={`mt-0.5 ${badge.text}`}>{badge.icon}</span>
                <div className="flex-1 min-w-0">
                    <span className={`text-sm font-semibold ${badge.text}`}>{badge.label}</span>
                    {data.recommendationReason && (
                        <p className="text-xs text-white/40 mt-1 leading-relaxed">
                            {data.recommendationReason}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
};

/**
 * Individual price stat cell.
 */
function PriceStat({
    label,
    value,
    accent,
    highlight = false,
}: {
    label: string;
    value: number | null;
    accent: string;
    highlight?: boolean;
}) {
    return (
        <div
            className={`
                rounded-xl px-3 py-2.5 text-center
                ${highlight
                    ? 'bg-white/[0.06] border border-white/[0.08]'
                    : 'bg-white/[0.02]'
                }
            `}
        >
            <div className="text-[10px] uppercase tracking-wider text-white/30 mb-1">{label}</div>
            <div className={`text-sm font-semibold ${accent} tabular-nums`}>
                {formatPrice(value)}
            </div>
        </div>
    );
}
