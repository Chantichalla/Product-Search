
import React from "react";
import { cn } from "@/lib/utils";

interface Props extends React.HTMLAttributes<HTMLDivElement> {}

export function GlassCard({ className, children, ...props }: Props) {
  return (
    <div 
      className={cn(
        "rounded-2xl backdrop-blur-md bg-white/5 border border-white/10 shadow-2xl transition-all hover:bg-white/10", 
        className
      )} 
      {...props}
    >
      {children}
    </div>
  );
}
