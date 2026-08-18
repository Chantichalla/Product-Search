import React from 'react';

interface GlassCardProps {
    children: React.ReactNode;
    className?: string;
    intensity?: 'low' | 'medium' | 'high';
}

export const GlassCard: React.FC<GlassCardProps> = ({
    children,
    className = '',
    intensity = 'medium'
}) => {
    // Updated base styles for a thinner, cleaner glass look
    const baseStyles = "backdrop-blur-md border border-white/10 shadow-glass-inset transition-all duration-300";

    const intensityStyles = {
        low: "bg-black/10",
        medium: "bg-black/20",
        high: "bg-black/40",
    };

    return (
        <div className={`${baseStyles} ${intensityStyles[intensity]} ${className}`}>
            {children}
        </div>
    );
};
