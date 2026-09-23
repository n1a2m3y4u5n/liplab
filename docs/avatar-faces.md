# 화자별 아바타 얼굴 추가(H-5·H-6, F-4)

다자 대화는 화자마다 다른 얼굴을 쓸 수 있다. `frontend/public/models/faces/faces.json`에 등록된 GLB를 화자 순서(A, B, C, D)대로
배정하고, 목록이 비었거나 모자라면 기본 얼굴(`/models/realistic_face.glb`)을 쓴다. 목록에 있는 파일만 불러오므로 파일을 넣기 전에
목록을 먼저 고치면 안 된다.

## 1. 기본 얼굴의 규격(새 얼굴도 같아야 한다)

`realistic_face.glb`(2.5MB)를 읽어 확인한 값이다.

- Character Creator 두상, 메시 6개, 모프 229개.
- ARKit 52 블렌드셰이프(`jawOpen`, `mouthPucker`, `mouthFunnel`, `mouthClose`, `eyeBlinkLeft` 등)와 CC 혀 모프(`T01_Tongue_Up`~`T10_Tongue_Bulge_Left` 등).
- 턱 뼈 `CC_Base_JawRoot`. 이 모델은 `jawOpen` 모프가 피부를 거의 움직이지 않아, 입 벌림은 이 뼈 회전으로 만든다(`AvatarVRM.jsx`).
- 확장: `EXT_meshopt_compression`, `EXT_texture_webp`, `KHR_materials_specular`, `KHR_mesh_quantization`.

카메라 위치와 기호 위치(입꼬리 옆)는 이 두상 비율에 맞춰져 있다. 같은 CC 기본 두상에서 얼굴만 바꾼 모델이면 그대로 맞는다.

## 2. 만드는 순서

1. Character Creator 5에서 기본 두상을 열고 얼굴을 바꾼다(Headshot 3로 사진에서 만들 수도 있다). 실제 인물 사진을 쓰려면 그 사람의 동의를 먼저 받는다.
2. 내보내기에서 ARKit 표정(블렌드셰이프)과 혀 모프를 포함하고, 뼈대를 함께 내보낸다.
3. 크기를 줄인다(예: `gltfpack -cc -tc`로 meshopt 압축과 텍스처 압축). 기본 얼굴처럼 3MB 안팎이 적당하다.
   압축 뒤 오프셋이 어긋나 로드가 안 되면 `scripts/repair_meshopt_glb.py`로 고친다(9/21 기본 얼굴에서 있었던 문제).
4. `frontend/public/models/faces/`에 넣고 `faces.json`에 등록한다.

```json
{
  "faces": [
    { "url": "/models/faces/speaker_b.glb", "label": "화자 B 얼굴" },
    { "url": "/models/faces/speaker_c.glb", "label": "화자 C 얼굴" }
  ]
}
```

첫 항목이 화자 A, 둘째가 화자 B에 들어간다. 화자 A를 기본 얼굴로 두려면 첫 항목에 `/models/realistic_face.glb`를 넣는다.

## 3. 확인

- 다자 대화(`/learn/conversation-multi?speakers=4`)에서 네 얼굴이 모두 보이고 말하는 사람만 입이 움직이는지 본다.
- 브라우저 콘솔에 GLB 로드 오류가 없는지 본다. 로드에 실패한 얼굴은 2D 입모양으로 대신 보인다.
- 한 화면의 3D 캔버스가 4개이므로 저사양 기기에서 첫 렌더가 느릴 수 있다(9/23 측정: 첫 렌더 약 2.4초).
