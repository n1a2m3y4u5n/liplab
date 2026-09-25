/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // 디자인 토큰 — Figma 변수(get_variable_defs) + Figma 화면에 반복되는 고정 hex.
      // 같은 값은 index.css :root의 CSS 변수로도 있다(인라인 style·SVG용). 임의 hex를 새로 쓰지 말고 여기서 고른다.
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
          light: '#a78bfa',  // 보라 그라데이션 시작색(137:17 특별 과제·199:22 오답 복습·243:34 로그인 헤더)
          line: '#d9ccf7',   // 보라 카드 위 흰 버튼 테두리(199:22)
          faint: '#d6c9f6',  // 가이드 독화 요령 번호 01~06(370:84)
        },
        // 글자 — text/primary, text/secondary + Figma 보조 회색(라벨·캡션·그룹 머리)
        ink: {
          DEFAULT: '#1a1a2e',  // text/primary
          muted: '#5a5a6e',    // text/secondary
          soft: '#7a7a8c',     // 스탯 카드 라벨(93:22)
          faint: '#8a8a9b',    // 캡션·힌트(130:19, 178:23)
          ghost: '#a8a8b8',    // 축 눈금·보조 숫자
          hint: '#a4a4b4',     // 가이드 모달 그룹 머리(338:57)
          pale: '#b9b9c8',     // 가이드 독화 요령 '사과'의 뒷글자(370:142)
        },
        line: {
          DEFAULT: '#e2e2e8',  // border/default
          strong: '#d4d4de',   // 어두운 딤 위 흰 버튼 테두리(313:230 배지 모달 닫기)
        },
        page: '#f3f3f3',       // surface/background — 모바일 페이지·레슨 배경
        surface: {
          DEFAULT: '#ffffff',  // surface/card
          muted: '#fafafc',    // 카드 안 무대(3D 아바타 자리)
          nav: '#f7f7fa',      // 가이드 모달 왼쪽 목차
          sunken: '#f3f3f7',   // 칩·비활성 난이도 칩
          hover: '#e9e9f0',
        },
        fill: {
          DEFAULT: '#ededf3',  // 진행바 트랙·빈 요일 원(138:69, 102:41)
          strong: '#e4e4ec',   // 레슨 진행바 트랙·비활성 경로 연결선(91:16, 233:48)
        },
        overlay: {
          DEFAULT: '#0f0a1f',  // 모달 딤(50%)
          deep: '#0d081c',     // 배지 상세 딤(80% + 블러, 313:33)
        },
        // 트랙 색(§3.1) — index.css의 --track 변수. data-track="speak" 안에서는 분홍으로 바뀐다.
        // CSS 변수라 /투명도 수식어(bg-track/50)는 쓸 수 없다.
        track: {
          DEFAULT: 'var(--track)',
          dark: 'var(--track-dark)',
          tint: 'var(--track-tint)',
          hover: 'var(--track-hover)',
        },
        speak: { DEFAULT: '#ec4899', dark: '#be185d', tint: '#ffe4e9', hover: '#db2777' },  // 발화 트랙(171:38)
        bookmark: { DEFAULT: '#2563eb', dark: '#1d4ed8', light: '#60a5fa', line: '#c3dafb' },  // §3.1 북마크 고정색(199:29)
        // 점수·피드백(§3.2) — 94:98 정답 / 94:140 오답 / 182:92 음소 칩
        good: { DEFAULT: '#16a34a', dark: '#0f7a36', text: '#15803d', tint: '#e7f8ef', line: '#cde7d7' },
        warn: { DEFAULT: '#f59e0b', strong: '#d97706', text: '#b45309', tint: '#fef3c7' },
        bad: { DEFAULT: '#dc2626', dark: '#991b1b', text: '#b91c1c', tint: '#feecec', line: '#f3c8c8' },
        // 스탯 칩 고정색(§3.1) — 불꽃·별(XP)·레벨·정확도
        stat: { streak: '#b45309', xp: '#5f3ab8', level: '#0369a1', accuracy: '#047857' },
        // 비활성 버튼(130:20 "확인 (비활성)")
        inactive: { DEFAULT: '#e4e4ec', line: '#d2d2de', text: '#a0a0b0', bg: '#f1f1f5', glyph: '#c2c2ce' },  // bg·glyph = 잠긴 배지(313:130)
        placeholder: '#c9c9d6',   // 입력칸 안내 문구(227:59·243:52 로그인, 입력 화면 공통)
        // 파스텔 바탕 — 연습 탭 카드 아이콘 칩(96:120)·수어 칸(226:161)·획득 배지 원(313:130)
        pastel: { sky: '#e0f2fe', pink: '#ffe4e9', amber: '#fff3d6', mint: '#dff7ec', indigo: '#e0e7ff', violet: '#ede9fe' },
        // 분석 탭 정확도 추이(96:66) — 선·점 초록, 마지막 주가 아닌 수치 글자. 어두운 딤 위 강조 초록(313:33 희귀도)
        chart: { accuracy: '#10b981', label: '#7a9a8c', onDark: '#6ee7b7' },
        // 활동 캘린더 5단계(207:29) — 0 = 기록 없음
        heat: { 0: '#ededf3', 1: '#ddd3f7', 2: '#b49bec', 3: '#8b5cf6', 4: '#5f3ab8' },
        // 랜딩(9:12) 그림에만 나오는 고정색 — 단계 막대(54:8·54:9·54:10), 출석 칸(54:18·54:21), 기기 테두리(19:37)
        landing: { step2: '#c9b8f2', step3: '#b49bec', step4: '#9e7ce6', day: '#fce8b8', done: '#f7b733', device: '#dbdbe5' },
        // 엔드리스 학습(연습 탭 인디고 카드) — 히어로 그라데이션·3D 테두리·버튼, 유형 막대(낮음 분홍 · 높음 앰버)
        endless: {
          DEFAULT: '#4f46e5', light: '#818cf8', dark: '#3730a3', line: '#cbd2fa',
          low: '#f472a0', high: '#fbbf24',
        },
      },
      fontFamily: {
        // 본문·UI = Noto Sans KR, 로고·디스플레이 = Rowdies (index.css에서 Google Fonts 로드)
        sans: ['"Noto Sans KR"', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Rowdies', '"Noto Sans KR"', 'sans-serif'],
      },
      // Figma 글자 상자의 "leading normal" — Noto Sans KR에서 글자 크기의 1.2배(16px→19, 30px→36).
      // 브라우저의 line-height: normal(≈1.45)과 달라서 토큰으로 둔다.
      lineHeight: { figma: '1.2' },
      borderWidth: { 1.5: '1.5px', 5: '5px', 6: '6px' },  // Figma 구분선 1.5 / 3D 하단테두리 5·6
      // Figma 반경 — rounded-14(버튼·칩) 16(주 버튼) 18(정보 카드) 20(카드) 22(모달) 24(가이드 모달)
      borderRadius: {
        '2xl': '1rem', '10': '10px', '13': '13px', '14': '14px', '15': '15px', '16': '16px',
        '18': '18px', '20': '20px', '22': '22px', '24': '24px',
      },
      boxShadow: {
        card: '0 2px 12px -2px rgba(26,13,64,0.06)',
        modal: '0px 18px 44px -6px rgba(13,5,31,0.32)',
        sheet: '0px -4px 16px -2px rgba(26,13,64,0.12)',  // 모바일 레슨 시트(233:61)
        art: '0px 14px 30px -4px rgba(26,13,64,0.14)',    // 랜딩 섹션 그림 카드(54:6·54:17)
        device: '0px 18px 40px -4px rgba(26,13,64,0.22)', // 랜딩 히어로 기기(19:37)
      },
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
