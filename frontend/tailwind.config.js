/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#f8fafc",
        panel: "#ffffff",
        borderGlow: "#e2e8f0",
        glowEmerald: "#10b981",
        glowAmber: "#f59e0b",
        glowRose: "#f43f5e",
        glowBlue: "#3b82f6",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      boxShadow: {
        glow: "0 4px 20px rgba(0, 0, 0, 0.04)",
        glowGreen: "0 4px 20px rgba(16, 185, 129, 0.15)",
        glowOrange: "0 4px 20px rgba(245, 158, 11, 0.15)",
        glowRed: "0 4px 20px rgba(244, 63, 94, 0.15)",
      },
    },
  },
  plugins: [],
};
