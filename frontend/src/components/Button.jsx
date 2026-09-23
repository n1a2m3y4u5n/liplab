/**
 * 공통 버튼 (Figma "Button / Primary" 75:23 계열) — index.css의 .btn-* 클래스를 조합하는 얇은 래퍼.
 * 클래스를 직접 써도 된다: className="btn-primary btn-lg w-full".
 *
 * variant: 'primary'(트랙색, 기본) | 'secondary'(흰 바탕·회색 글자) | 'good'(초록) | 'bad'(빨강)
 * size:    'base'(r14·b5, 기본) | 'lg'(75:23: r16·b6, 32/18, 20px) | 'md'(59:43: 18/14, 17px)
 *          | 'bar'(130:20 레슨 하단 바: 40/15, 17px)
 * accent:  secondary 글자를 트랙색으로(227:69 "둘러보기", 93:12 "커리큘럼으로 돌아가기").
 * track:   'read' | 'speak' — AppShell 안(data-track이 이미 있음)에서는 생략. 레슨처럼 셸 밖에서
 *          분홍이 필요하면 'speak'. 페이지 전체를 분홍으로 하려면 루트에 data-track="speak"를 단다.
 * block:   w-full.
 * 나머지 props는 <button>에 그대로 간다(type 기본 'button').
 */
const VARIANT = { primary: 'btn-primary', secondary: 'btn-secondary', good: 'btn-good', bad: 'btn-bad' }
const SIZE = { base: '', lg: 'btn-lg', md: 'btn-md', bar: 'btn-bar' }

export default function Button({ variant = 'primary', size = 'base', accent = false, track, block = false, className = '', type = 'button', ...rest }) {
  const cls = [VARIANT[variant] || VARIANT.primary, SIZE[size] || '', accent ? 'text-track' : '', block ? 'w-full' : '', className]
    .filter(Boolean).join(' ')
  return <button type={type} className={cls} data-track={track || undefined} {...rest} />
}
