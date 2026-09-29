// 글자 크기 px → rem 변환(빌드 시). '글자 크게' 접근성 옵션은 <html> 글자 크기를 118%로 올리는데,
// 화면 대부분이 text-[13px] 같은 고정 px라 rem만 커지고 레슨 화면 글자는 그대로였다(9/29 점검: 823/1,240).
// font-size 선언의 px만 루트 16px 기준 rem으로 바꿔 기본 화면은 픽셀 단위로 같고, 옵션을 켜면 전부 1.18배가 된다.
// 12px 미만(8~11.5px)은 읽기 어려워 최소 12px(0.75rem)로 올린다.
// 여백·높이·줄 간격 등 다른 속성은 건드리지 않는다(줄 간격은 대부분 배수라 글자를 따라 커진다).
const PX = /(-?\d*\.?\d+)px\b/g

export function pxToRem(value, { base = 16, minPx = 12 } = {}) {
  return value.replace(PX, (_, n) => {
    const px = Math.max(parseFloat(n), minPx)
    return `${+(px / base).toFixed(5)}rem`
  })
}

export default function fontSizeRem(opts = {}) {
  return {
    postcssPlugin: 'liplab-font-size-rem',
    Declaration: {
      'font-size'(decl) {
        if (decl.value.includes('px')) decl.value = pxToRem(decl.value, opts)
      },
    },
  }
}
fontSizeRem.postcss = true
