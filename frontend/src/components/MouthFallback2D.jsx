/**
 * 2D 입모양 폴백
 * WebGL 미지원(구형·저사양 기기)이나 3D 모델 로드 실패 시,
 * 현재 viseme의 입모양 SVG를 대신 보여줘 학습이 끊기지 않게 한다.
 */
export default function MouthFallback2D({ visemeId = 15 }) {
  const id = visemeId >= 1 && visemeId <= 15 ? visemeId : 15
  return (
    <div className="w-full h-full flex items-center justify-center bg-gradient-to-b from-slate-100 to-slate-200">
      <img
        src={`/visemes/${id}.svg`}
        alt={`입모양 ${id}`}
        className="w-full h-full object-contain p-4"
        draggable={false}
      />
    </div>
  )
}
