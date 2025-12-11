/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        parchment: '#f4e5c2',
        gold: '#d4af37',
        midnight: '#0b0f19'
      },
      fontFamily: {
        display: ['"Cinzel"', 'serif'],
        body: ['"Inter"', 'sans-serif']
      },
      boxShadow: {
        glow: '0 0 20px rgba(212, 175, 55, 0.3)'
      }
    }
  },
  plugins: [],
};
