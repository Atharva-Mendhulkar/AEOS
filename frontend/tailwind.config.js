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
        background: "#030712",
        panel: "#0b1528",
        borderGlow: "#1e293b",
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
        glow: "0 0 15px rgba(59, 130, 246, 0.5)",
        glowGreen: "0 0 15px rgba(16, 185, 129, 0.5)",
        glowOrange: "0 0 15px rgba(245, 158, 11, 0.5)",
        glowRed: "0 0 15px rgba(244, 63, 94, 0.5)",
      },
    },
  },
  plugins: [],
};
