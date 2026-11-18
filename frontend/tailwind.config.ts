import animate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

// Every color resolves to a theme CSS variable (space-separated RGB channels) so that
// opacity modifiers such as `bg-accent/15` work in both themes.
const token = (name: string): string => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"),
        surface: { DEFAULT: token("surface"), 2: token("surface-2") },
        border: token("border"),
        fg: token("text"),
        muted: token("text-muted"),
        accent: { DEFAULT: token("accent"), 2: token("accent-2"), fg: token("accent-fg") },
        danger: token("danger"),
        focus: token("focus"),
      },
      fontFamily: {
        sans: "var(--font-sans)",
        content: "var(--font-content)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        glow: "var(--glow)",
      },
      spacing: {
        "safe-top": "env(safe-area-inset-top, 0px)",
        "safe-bottom": "env(safe-area-inset-bottom, 0px)",
        "safe-left": "env(safe-area-inset-left, 0px)",
        "safe-right": "env(safe-area-inset-right, 0px)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
    },
  },
  plugins: [animate],
} satisfies Config;
