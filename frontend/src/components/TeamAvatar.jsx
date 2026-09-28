import MascotAvatar from './MascotAvatar'

// 팀원 아바타. 9/28부터 사진 대신 마스코트(사람마다 색·표정·모션, config/team.js의 mascot). 가이드 11번 탭과 랜딩이 함께 쓴다.
// 순서대로 모션 시작을 조금씩 늦춰(delay) 여러 명이 나란히 있어도 똑같이 움직이지 않게 한다.
export default function TeamAvatar({ m, size = 60, index = 0 }) {
  const c = m.mascot || {}
  return <MascotAvatar palette={c.palette} face={c.face} motion={c.motion} size={size} delay={index * 0.37} />
}
