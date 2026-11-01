// Builds src/tkd_scorer/infra/static/admin/tailwind.css (run `make css`).
// The CSS is committed so the admin panel and TV scoreboard work on a LAN without internet.
module.exports = {
  content: ["../src/tkd_scorer/infra/templates/**/*.html"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Nunito Sans", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#ecfeff",
          100: "#cffafe",
          200: "#a5f3fc",
          300: "#67e8f9",
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
          700: "#0e7490",
          800: "#155e75",
          900: "#164e63",
        },
      },
      boxShadow: {
        panel: "0 14px 36px rgba(8, 47, 73, 0.12)",
      },
    },
  },
  plugins: [require("@tailwindcss/forms"), require("@tailwindcss/typography")],
};
