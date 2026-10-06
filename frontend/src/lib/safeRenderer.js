// 3D 캔버스의 렌더러(WebGL 컨텍스트) 생성 실패를 잡는다.
// 시험용 컨텍스트(AvatarVRM의 detectWebGL)가 만들어져도 실제 렌더러 생성은 실패할 수 있다(GPU 차단 목록, 드라이버 오류,
// 성능 저하 경고 속성 등). @react-three/fiber 9는 렌더러를 비동기 configure 안에서 만들고 그 실패를 오류 경계로 넘기지 않아,
// 예전에는 2D 입모양 대신 빈 캔버스(검은 상자)만 남았다. Canvas의 gl 속성에 이 함수가 돌려준 생성기를 넘기면
// 생성이 실패한 순간 onFail(error)이 불리고, 화면은 그 신호로 2D로 바꾼다. 오류는 다시 던져 R3F가 더 진행하지 않게 한다.
export function guardRendererFactory(create, onFail) {
  return (props) => {
    let renderer
    try {
      renderer = create(props)
      if (!renderer) throw new Error('WebGL 렌더러를 만들지 못했다')
    } catch (error) {
      try { onFail(error) } catch { /* 알림 실패는 무시하고 원래 오류를 던진다 */ }
      throw error
    }
    return renderer
  }
}
