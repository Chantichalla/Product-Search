
import React from 'react';
import { cn } from "@/lib/utils";
import Link from 'next/link';
import { Ghost, Menu, MessageSquarePlus } from 'lucide-react';

export function Sidebar() {
    return (
        <div className="w-[260px] h-screen bg-[#050510]/80 backdrop-blur-xl border-r border-white/5 flex flex-col fixed left-0 top-0 z-50">

            {/* Header Area */}
            <div className="h-16 flex items-center px-4 border-b border-white/5">
                <Link href="/" className="flex items-center gap-2 text-starlight font-semibold">
                    <Ghost className="w-5 h-5 text-brand-teal" />
                    <span>Aether</span>
                </Link>
            </div>

            {/* New Chat Button (Pinned) */}
            <div className="p-4">
                <button className="w-full flex items-center gap-2 bg-white/5 hover:bg-white/10 text-starlight/90 px-4 py-3 rounded-lg border border-white/10 transition-all text-sm font-medium group">
                    <MessageSquarePlus className="w-4 h-4 text-brand-teal group-hover:scale-110 transition-transform" />
                    <span>New Chat</span>
                </button>
            </div>

            {/* Scrollable List */}
            <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1">
                <div className="text-xs text-white/40 font-medium mb-2 uppercase tracking-wider pl-2">Recent</div>

                {/* Mock Items */}
                {["Quantum Physics Logic", "React Architecture Plan", "Poetry Analysis", "Landing Page Copy"].map((item, i) => (
                    <button key={i} className="w-full text-left px-3 py-2 text-sm text-starlight/60 hover:text-white hover:bg-white/5 rounded-md transition-colors truncate">
                        {item}
                    </button>
                ))}
            </div>

            {/* Footer Area */}
            <div className="p-4 border-t border-white/5">
                <div className="flex items-center gap-3 px-2">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-brand-teal to-blue-600"></div>
                    <div className="text-sm">
                        <div className="text-starlight font-medium">Guest User</div>
                        <div className="text-xs text-white/40">Free Plan</div>
                    </div>
                </div>
            </div>
        </div>
    );
}
