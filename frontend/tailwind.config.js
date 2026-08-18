/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./components/**/*.{js,ts,jsx,tsx,mdx}",
        "./app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                void: "#050510",      // Deepest background
                nebula: "#1a1a2e",    // Secondary background
                starlight: "#e2e8f0", // Primary Text
                glass: "rgba(255, 255, 255, 0.05)",
                "glass-border": "rgba(255, 255, 255, 0.1)",
                "brand-teal": "#00f0ff",
                "brand-coral": "#ff7e67",
                // New User Theme Colors (Inferred)
                "atmosphere-dark": "#050510",
                "atmosphere-base": "#1a1a2e",
                "atmosphere-accent": "#00f0ff",
            },
            boxShadow: {
                "glass-inset": "inset 0 0 20px rgba(255, 255, 255, 0.05)",
                "glow": "0 0 20px rgba(0, 240, 255, 0.3)",
            },
            fontFamily: {
                sans: ["var(--font-inter)", "sans-serif"],
            },
            backgroundImage: {
                "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
            },
        },
    },
    plugins: [],
};
