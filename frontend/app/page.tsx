
"use client";

import { LandingPage } from "@/components/LandingPage";
import { useRouter } from "next/navigation";

export default function Home() {
    const router = useRouter();

    const handleEnterApp = (query?: string) => {
        if (query) {
            router.push(`/chat?q=${encodeURIComponent(query)}`);
        } else {
            router.push('/chat');
        }
    };
    return <LandingPage onEnterApp={handleEnterApp} />;
}
