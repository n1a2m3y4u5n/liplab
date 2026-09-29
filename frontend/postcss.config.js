import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import fontSizeRem from './postcss-font-rem.js'

// tailwind가 만든 text-[Npx]까지 바꿔야 하므로 font-size 변환은 tailwind 다음에 둔다
export default {
  plugins: [
    tailwindcss(),
    fontSizeRem(),
    autoprefixer(),
  ],
}
