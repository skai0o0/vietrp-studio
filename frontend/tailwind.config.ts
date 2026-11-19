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
        surface: {
          DEFAULT: token("surface"),
          2: token("surface-2"),
          3: token("surface-3"),
        },
        field: token("field-bg"),
        hover: token("hover"),
        border: {
          DEFAULT: token("border"),
          subtle: token("border-subtle"),
          strong: token("border-strong"),
        },
        fg: token("text"),
        muted: token("text-muted"),
        accent: {
          DEFAULT: token("accent"),
          2: token("accent-2"),
          fg: token("accent-fg"),
          text: token("accent-text"),
        },
        danger: {
          DEFAULT: token("danger"),
          fg: token("danger-fg"),
          text: token("danger-text"),
        },
        success: token("success"),
        warning: token("warning"),
        focus: token("focus"),
        scrim: "rgb(var(--scrim))",
      },
      fontFamily: {
        sans: "var(--font-sans)",
        content: "var(--font-content)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        popover: "var(--shadow-popover)",
        dialog: "var(--shadow-dialog)",
        glow: "var(--glow)",
      },
      transitionDuration: {
        press: "var(--dur-press)",
        fast: "var(--dur-fast)",
        base: "var(--dur-base)",
        panel: "var(--dur-panel)",
        exit: "var(--dur-exit)",
      },
      transitionTimingFunction: {
        ui: "var(--ease-ui)",
        enter: "var(--ease-enter)",
        exit: "var(--ease-exit)",
      },
      zIndex: {
        sticky: "20",
        popover: "40",
        modal: "50",
        tooltip: "60",
        toast: "70",
        skip: "100",
      },
      spacing: {
        "safe-top": "env(safe-area-inset-top, 0px)",
        "safe-bottom": "env(safe-area-inset-bottom, 0px)",
        "safe-left": "env(safe-area-inset-left, 0px)",
        "safe-right": "env(safe-area-inset-right, 0px)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
