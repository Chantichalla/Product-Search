'use client';

import React from 'react';
import { ProgressStep } from '../types';

interface AgentProgressProps {
    steps: ProgressStep[];
    isActive: boolean;
}

/**
 * "Working Hard" Skeleton UI
 * 
 * Displays an expanding checklist of LangGraph node progress events
 * followed by animated skeleton cards that mimic product results.
 */
const AgentProgress: React.FC<AgentProgressProps> = ({ steps, isActive }) => {
    if (steps.length === 0 && !isActive) return null;

    return (
        <div className="agent-progress">
            {/* ── Expanding Checklist ── */}
            <div className="progress-checklist">
                {steps.map((step, index) => (
                    <div
                        key={step.node}
                        className={`progress-step ${step.status}`}
                        style={{ animationDelay: `${index * 0.1}s` }}
                    >
                        <span className="step-icon">
                            {step.status === 'done' && '✓'}
                            {step.status === 'active' && (
                                <span className="spinner" />
                            )}
                            {step.status === 'pending' && '○'}
                        </span>
                        <span className="step-label">{step.label}</span>
                    </div>
                ))}
            </div>

            {/* ── Skeleton Product Cards (shown while actively processing) ── */}
            {isActive && (
                <div className="skeleton-cards">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="skeleton-card" style={{ animationDelay: `${i * 0.15}s` }}>
                            <div className="skeleton-image pulse" />
                            <div className="skeleton-lines">
                                <div className="skeleton-line wide pulse" />
                                <div className="skeleton-line medium pulse" />
                                <div className="skeleton-line narrow pulse" />
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <style jsx>{`
                .agent-progress {
                    padding: 16px 0;
                }

                /* ── Checklist ── */
                .progress-checklist {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                    margin-bottom: 16px;
                }

                .progress-step {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    padding: 6px 12px;
                    border-radius: 8px;
                    font-size: 14px;
                    animation: slideIn 0.3s ease-out both;
                    transition: all 0.3s ease;
                }

                .progress-step.done {
                    color: #4ade80;
                    opacity: 0.7;
                }

                .progress-step.active {
                    color: #60a5fa;
                    background: rgba(96, 165, 250, 0.08);
                    font-weight: 500;
                }

                .progress-step.pending {
                    color: rgba(255, 255, 255, 0.3);
                }

                .step-icon {
                    width: 18px;
                    height: 18px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 13px;
                    flex-shrink: 0;
                }

                .spinner {
                    width: 14px;
                    height: 14px;
                    border: 2px solid rgba(96, 165, 250, 0.3);
                    border-top-color: #60a5fa;
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                }

                /* ── Skeleton Cards ── */
                .skeleton-cards {
                    display: flex;
                    gap: 12px;
                    overflow: hidden;
                    padding: 4px 0;
                }

                .skeleton-card {
                    flex: 0 0 180px;
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.06);
                    border-radius: 12px;
                    padding: 12px;
                    animation: fadeIn 0.4s ease-out both;
                }

                .skeleton-image {
                    width: 100%;
                    height: 100px;
                    border-radius: 8px;
                    background: rgba(255, 255, 255, 0.06);
                    margin-bottom: 10px;
                }

                .skeleton-lines {
                    display: flex;
                    flex-direction: column;
                    gap: 6px;
                }

                .skeleton-line {
                    height: 10px;
                    border-radius: 4px;
                    background: rgba(255, 255, 255, 0.06);
                }

                .skeleton-line.wide { width: 90%; }
                .skeleton-line.medium { width: 65%; }
                .skeleton-line.narrow { width: 40%; }

                /* ── Animations ── */
                .pulse {
                    animation: pulse 1.5s ease-in-out infinite;
                }

                @keyframes pulse {
                    0%, 100% { opacity: 0.4; }
                    50% { opacity: 0.8; }
                }

                @keyframes spin {
                    to { transform: rotate(360deg); }
                }

                @keyframes slideIn {
                    from { 
                        opacity: 0; 
                        transform: translateX(-8px); 
                    }
                    to { 
                        opacity: 1; 
                        transform: translateX(0); 
                    }
                }

                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(4px); }
                    to { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </div>
    );
};

export default AgentProgress;
