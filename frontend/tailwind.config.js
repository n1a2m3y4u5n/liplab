/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 브랜드 주색 — Figma 디자인 토큰(brand/primary #7d53de) 기반 보라 팔레트.
        // 기존 primary-* 사용부(하늘색)가 이 리맵으로 전부 보라로 전환된다.
        primary: {
          50: '#f6f3fe',
          100: '#efe9fc',  // brand/primary-tint
          200: '#ddd3f7',
          300: '#c4b5fd',
          400: '#a689ee',
          500: '#7d53de',  // brand/primary
          600: '#6d3fc4',
          700: '#5f3ab8',  // brand/primary-dark
          800: '#4c2e93',
          900: '#3b246f',
        },
        // 의미 토큰(Figma) — 텍스트·보더. 정답/오답/소리는 emerald/rose/pink 유틸리티 사용.
        ink: { DEFAULT: '#1a1a2e', muted: '#5a5a6e' },  // text/primary, text/secondary
        line: '#e2e2e8',                                 // border/default
      },
      fontFamily: {
        // 본문·UI = Noto Sans KR, 로고·디스플레이 = Rowdies (index.css에서 Google Fonts 로드)
        sans: ['"Noto Sans KR"', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Rowdies', '"Noto Sans KR"', 'sans-serif'],
      },
      borderWidth: { 5: '5px', 6: '6px' },  // Figma 3D 하단테두리(카드·버튼)
      borderRadius: { '2xl': '1rem', '20': '20px' },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.4s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
