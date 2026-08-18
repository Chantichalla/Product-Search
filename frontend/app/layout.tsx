
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
    title: "Aether Advisor | Thinking in Glass",
    description: "An intelligent advisor designed for clarity.",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body className={cn(inter.variable, "bg-black text-white font-sans antialiased selection:bg-brand-teal/30")}>
                {children}
            </body>
        </html>
    );
}
