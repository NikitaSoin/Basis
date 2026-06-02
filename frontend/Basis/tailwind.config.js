/** @type {import('tailwindcss').Config} */

// Colours map to the CSS custom properties defined in src/styles/tokens.css.
// Using <alpha-value> would require channel-only vars; tokens here are full
// colours, so we reference them directly. This lets new components be written
// with classes (bg-bg-elevated, text-text-primary, text-accent...) while the
// single source of truth stays the token file (themed via .dark).
module.exports = {
  darkMode: "class",
  // PREFIX is mandatory here: src/styles.css already hand-implements ~249
  // utility-like classes (.flex, .grid, .p-2, .rounded-lg, .bg-slate-900 ...).
  // Without a prefix Tailwind would regenerate those names with its own values
  // and (loaded last) override the entire existing UI. `tw-` isolates new
  // utilities so Phase 2 primitives can use them WITHOUT touching legacy code.
  prefix: "tw-",
  // No preflight: Tailwind's global reset would clobber the hand-written CSS.
  corePlugins: { preflight: false },
  content: ["./src/**/*.{js,jsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "var(--bg-base)",
          elevated: "var(--bg-elevated)",
          overlay: "var(--bg-overlay-srf)",
          hover: "var(--bg-hover)",
        },
        border: {
          subtle: "var(--border-subtle)",
          strong: "var(--border-strong)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          soft: "var(--accent-soft)",
        },
        success: {
          DEFAULT: "var(--success)",
          soft: "var(--success-soft)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          soft: "var(--danger-soft)",
        },
        warning: {
          DEFAULT: "var(--warning)",
          soft: "var(--warning-soft)",
        },
        info: {
          DEFAULT: "var(--info)",
          soft: "var(--info-soft)",
        },
        "on-accent": "var(--on-accent)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        display: ["Inter Display", "Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      // 8pt grid (with 4pt sub-grid) from the constitution.
      spacing: {
        0.5: "2px",
        1: "4px",
        1.5: "6px",
        2: "8px",
        3: "12px",
        4: "16px",
        5: "20px",
        6: "24px",
        8: "32px",
        10: "40px",
        12: "48px",
        16: "64px",
        20: "80px",
        24: "96px",
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        xl: "16px",
        pill: "9999px",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        xl: "var(--shadow-xl)",
        focus: "0 0 0 3px var(--accent-soft)",
      },
    },
  },
  plugins: [],
};
