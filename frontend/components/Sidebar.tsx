
import React from 'react';
import { MessageSquare, Settings, PanelLeftClose, PanelLeftOpen, Plus } from 'lucide-react';
import { SidebarState, ChatSession } from '../types';

interface SidebarProps {
    state: SidebarState;
    onToggle: () => void;
    history: ChatSession[];
    activeSessionId: string | null;
    onSelectSession: (id: string) => void;
    onNewChat: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
    state,
    onToggle,
    history,
    activeSessionId,
    onSelectSession,
    onNewChat
}) => {
    const isCollapsed = state === SidebarState.Collapsed;
    const widthClass = isCollapsed ? 'w-[60px]' : 'w-[260px]';

    return (
        <div
            className={`
        fixed top-0 left-0 bottom-0
        flex flex-col transition-all duration-500 ease-[cubic-bezier(0.25,0.1,0.25,1)]
        ${widthClass}
        backdrop-blur-xl bg-black/40 border-r border-white/5
        z-50
      `}
        >
            {/* Header (Fixed) */}
            <div className={`shrink-0 flex ${isCollapsed ? 'flex-col gap-4 py-4 items-center' : 'flex-row items-center justify-between p-4 h-20'}`}>
                <button
                    onClick={onNewChat}
                    className={`
                flex items-center justify-center transition-all shadow-glass-inset group
                ${isCollapsed
                            ? 'w-10 h-10 rounded-full bg-white/5 hover:bg-white/10 text-atmosphere-accent'
                            : 'gap-2 text-sm font-medium text-white/90 bg-white/5 hover:bg-white/10 border border-white/5 px-3 py-2.5 rounded-lg w-full mr-2'}
            `}
                    title="New Chat"
                >
                    <Plus size={isCollapsed ? 20 : 16} className={isCollapsed ? "group-hover:rotate-90 transition-transform duration-300" : ""} />
                    {!isCollapsed && <span>New Chat</span>}
                </button>

                <button
                    onClick={onToggle}
                    className={`text-white/50 hover:text-white transition-colors p-1 ${isCollapsed ? 'mt-2' : ''}`}
                >
                    {isCollapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
                </button>
            </div>

            {/* Navigation Links (Scrollable) */}
            <div className="flex-1 overflow-y-auto py-2 space-y-1 no-scrollbar">
                {!isCollapsed && <div className="px-4 text-[10px] font-semibold text-white/20 uppercase tracking-widest mb-3 mt-2">History</div>}

                {history.map((session) => (
                    <button
                        key={session.id}
                        onClick={() => onSelectSession(session.id)}
                        className={`
              group w-full flex items-center gap-3 px-4 py-3 transition-all duration-200
              relative
              ${isCollapsed ? 'justify-center' : ''}
              ${activeSessionId === session.id ? 'bg-white/5' : 'hover:bg-white/5'}
            `}
                        title={isCollapsed ? session.title : undefined}
                    >
                        {/* Active Indicator Line */}
                        {activeSessionId === session.id && (
                            <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-atmosphere-accent shadow-[0_0_10px_currentColor]" />
                        )}

                        <MessageSquare
                            size={18}
                            className={`${activeSessionId === session.id ? 'text-atmosphere-accent' : 'text-white/40 group-hover:text-white/80'} transition-colors shrink-0`}
                        />

                        {!isCollapsed && (
                            <span className={`text-sm truncate ${activeSessionId === session.id ? 'text-white font-medium' : 'text-white/60 group-hover:text-white/90'}`}>
                                {session.title}
                            </span>
                        )}
                    </button>
                ))}
            </div>

            {/* Footer / User (Fixed) */}
            <div className="shrink-0 p-4 border-t border-white/5 bg-black/10">
                <button className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} text-white/60 hover:text-white transition-colors`}>
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-atmosphere-accent to-slate-600 flex items-center justify-center text-atmosphere-base font-bold text-xs shadow-glow shrink-0">
                        US
                    </div>
                    {!isCollapsed && (
                        <div className="text-left flex-1 truncate">
                            <div className="text-xs font-medium text-white/90">User</div>
                            <div className="text-[10px] text-white/40">Free Plan</div>
                        </div>
                    )}
                    {!isCollapsed && <Settings size={14} />}
                </button>
            </div>
        </div>
    );
};
