import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        night: { DEFAULT: v("night"), 2: v("night-2"), 3: v("night-3"), line: v("night-line") },
        moon: { DEFAULT: v("moon"), 2: v("moon-2"), 3: v("moon-3") },
        paper: { DEFAULT: v("paper"), 2: v("paper-2") },
        card: v("card"),
        ink: { DEFAULT: v("ink"), 2: v("ink-2"), 3: v("ink-3") },
        line: v("line"),
        marigold: { DEFAULT: v("marigold"), ink: v("marigold-ink") },
        teal: { DEFAULT: v("teal"), ink: v("teal-ink") },
        coral: { DEFAULT: v("coral"), ink: v("coral-ink"), night: v("coral-night") },
        violet: { DEFAULT: v("violet"), ink: v("violet-ink"), night: v("violet-night") },
      },
      fontFamily: {
        sans: ["var(--font-ui)"],
      },
      borderRadius: { "4xl": "2rem" },
      boxShadow: {
        soft: "0 1px 2px rgb(var(--shadow) / 0.06), 0 8px 24px -12px rgb(var(--shadow) / 0.18)",
        lift: "0 2px 4px rgb(var(--shadow) / 0.06), 0 18px 40px -18px rgb(var(--shadow) / 0.35)",
        glow: "0 0 0 1px rgb(var(--marigold) / 0.35), 0 10px 40px -10px rgb(var(--marigold) / 0.45)",
      },
      keyframes: {
        breathe: { "0%,100%": { opacity: "0.55" }, "50%": { opacity: "1" } },
        drift: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        pulseRing: { "0%": { transform: "scale(0.6)", opacity: "0.7" }, "100%": { transform: "scale(2.4)", opacity: "0" } },
        shimmer: { from: { backgroundPosition: "-200% 0" }, to: { backgroundPosition: "200% 0" } },
      },
      animation: {
        breathe: "breathe 6s ease-in-out infinite",
        drift: "drift 38s linear infinite",
        "drift-slow": "drift 64s linear infinite",
        pulseRing: "pulseRing 2.6s cubic-bezier(0.2,0.6,0.3,1) infinite",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
