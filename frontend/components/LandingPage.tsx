
import React from 'react';
import { ArrowRight, Sparkles } from 'lucide-react';
import { LANDING_BG_IMAGE } from '../constants';
import { GlassCard } from '../components/GlassCard';

interface LandingPageProps {
    onEnterApp: (query?: string) => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onEnterApp }) => {
    return (
        <div className="relative w-full h-screen overflow-hidden bg-black text-white selection:bg-atmosphere-accent/30">
            {/* Background Layer - Full Viewport */}
            <div
                className="absolute inset-0 z-0"
                style={{
                    backgroundImage: `url(${LANDING_BG_IMAGE})`,
                    backgroundSize: 'cover',
                    backgroundPosition: 'center 30%', // Focused on the sky/monolith area
                }}
            >
                {/* Subtle overlay to ensure text legibility at the very bottom, but keep top clear */}
                <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/80" />
            </div>

            {/* Main Layout Container - Bottom Heavy */}
            <div className="relative z-10 w-full h-full flex flex-col justify-end pb-12 px-6 md:px-12">

                {/* Content Deck */}
                <div className="w-full max-w-6xl mx-auto flex flex-col items-center animate-in fade-in slide-in-from-bottom-10 duration-1000">

                    {/* Headline - Floating above the card */}
                    <div className="mb-8 text-center space-y-4">
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 backdrop-blur-sm">
                            <Sparkles size={12} className="text-atmosphere-accent" />
                            <span className="text-[10px] font-semibold tracking-[0.2em] uppercase text-white/50">System V 2.0</span>
                        </div>
                        <h1 className="text-5xl md:text-8xl font-thin tracking-tight text-white drop-shadow-2xl">
                            Thinking in <span className="font-normal text-transparent bg-clip-text bg-gradient-to-r from-white via-white to-white/60">Glass</span>
                        </h1>
                    </div>

                    {/* Glass Interaction Pill */}
                    <GlassCard intensity="medium" className="w-full max-w-2xl p-2 rounded-full flex items-center gap-2 mt-8 py-3 pl-6 pr-3 bg-white/5 border-white/10 hover:border-atmosphere-accent/30 transition-all duration-300 group focus-within:border-atmosphere-accent/50 focus-within:shadow-glow">
                        <Sparkles className="w-5 h-5 text-atmosphere-accent animate-pulse" />
                        <input
                            type="text"
                            placeholder="Ask the Advisor..."
                            className="flex-1 bg-transparent border-none outline-none text-white/90 placeholder:text-white/30 font-light"
                            onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                    onEnterApp(e.currentTarget.value);
                                }
                            }}
                        />
                        <button
                            onClick={(e) => {
                                const input = e.currentTarget.parentElement?.querySelector('input') as HTMLInputElement;
                                onEnterApp(input.value);
                            }}
                            className="bg-white/10 hover:bg-white/20 text-white p-3 rounded-full transition-colors"
                        >
                            <ArrowRight className="w-4 h-4" />
                        </button>
                    </GlassCard>

                    {/* Control Deck - Wide Pill */}
                    <GlassCard intensity="medium" className="w-full max-w-4xl rounded-full p-2 pl-8 pr-2 flex flex-col md:flex-row items-center justify-between gap-6 md:gap-12 mt-12">

                        {/* Left: Description */}
                        <div className="flex-1 py-4 md:py-0 text-center md:text-left">
                            <p className="text-sm md:text-base text-white/70 font-light leading-relaxed">
                                Experience an intelligent advisor designed for clarity. <br className="hidden md:block" />
                                Atmospheric context, calm reasoning, and high-fidelity thought.
                            </p>
                        </div>

                        {/* Right: Actions */}
                        <div className="flex items-center gap-2 shrink-0 w-full md:w-auto">
                            <button className="flex-1 md:flex-none px-6 py-3 rounded-full text-sm font-medium text-white/60 hover:text-white transition-colors hover:bg-white/5">
                                Login
                            </button>
                            <button
                                onClick={() => onEnterApp()}
                                className="
                  flex-1 md:flex-none group relative px-8 py-4 bg-white text-black font-semibold rounded-full
                  shadow-[0_0_20px_-5px_rgba(255,255,255,0.3)] hover:shadow-[0_0_30px_-5px_rgba(255,255,255,0.5)]
                  transition-all duration-300 transform hover:scale-105 active:scale-95
                  flex items-center justify-center gap-2
                "
                            >
                                <span>Try Advisor</span>
                                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                            </button>
                        </div>

                    </GlassCard>

                    {/* Footer Metadata */}
                    <div className="mt-8 text-white/20 text-[10px] uppercase tracking-[0.2em] font-medium">
                        Designed for Deep Thought &bull; Aether Interface
                    </div>

                </div>
            </div>
        </div>
    );
};
