/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  safelist: [
    'bg-mac-bg',
    'bg-mac-accent',
    'bg-mac-accent-dark',
    'text-mac-accent',
    'shadow-mac',
    'font-mac',
    'backdrop-blur-md',
    'rounded-xl',
    'rounded-2xl',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        }
      }
    },
  },
  plugins: [],
}
