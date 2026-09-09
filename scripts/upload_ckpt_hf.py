#!/usr/bin/env python
"""
축 A 체크포인트를 HF private repo로 백업 — 최종 모델만.

  HF_TOKEN=hf_... python scripts/upload_ckpt_hf.py /workspace/ckpt/scorer  duadnwls/liplab-dgop-scorer
  HF_TOKEN=hf_... python scripts/upload_ckpt_hf.py /workspace/ckpt/aligner duadnwls/liplab-dgop-aligner

Pod 안에서 돌린다(체크포인트가 Network Volume에 있다). 저장소 2개와 모델 카드는
2026-09-09에 이미 만들어 뒀고 가중치만 비어 있다.

stage1_head/·stage2_full/·checkpoint-*/ 는 Trainer 옵티마이저 상태(학습 재개용)라
제외한다. 학습은 끝났고 추론·앱 연결에는 최상위 최종 모델만 필요하다(19GB → 2.5GB).

제외 패턴을 쓰지 않고 **최상위 일반 파일만 명시적으로 나열**한다 — fnmatch는 '/'도
'*'로 먹어서 "*.json" 같은 패턴이 하위 디렉터리 파일까지 잡을 수 있다.

실행: python upload_ckpt.py <로컬경로> <repo_id>
"""
import os
import sys

from huggingface_hub import HfApi


def main(local_dir: str, repo_id: str) -> int:
    api = HfApi(token=os.environ["HF_TOKEN"])

    top = sorted(f for f in os.listdir(local_dir)
                 if os.path.isfile(os.path.join(local_dir, f)))
    if not any(f.endswith(".safetensors") or f.startswith("pytorch_model") for f in top):
        print(f"[중단] {local_dir} 최상위에 모델 가중치가 없습니다: {top}", file=sys.stderr)
        return 1

    total = sum(os.path.getsize(os.path.join(local_dir, f)) for f in top)
    skipped = sorted(d for d in os.listdir(local_dir)
                     if os.path.isdir(os.path.join(local_dir, d)))
    print(f"→ {repo_id}")
    for f in top:
        print(f"   {f:26} {os.path.getsize(os.path.join(local_dir, f))/1e6:9.1f} MB")
    print(f"   합계 {total/1e9:.2f} GB | 제외한 디렉터리: {skipped or '없음'}")

    api.upload_folder(folder_path=local_dir, repo_id=repo_id, repo_type="model",
                      allow_patterns=top,
                      commit_message="축 A D-GOP 최종 모델 백업(Trainer 상태 제외)")

    # 검증 — 원격 파일 목록과 크기가 로컬과 맞는지 확인한다.
    info = api.repo_info(repo_id=repo_id, repo_type="model", files_metadata=True)
    remote = {s.rfilename: s.size for s in info.siblings}
    ok = True
    for f in top:
        want = os.path.getsize(os.path.join(local_dir, f))
        got = remote.get(f)
        if got != want:
            print(f"   [불일치] {f}: 로컬 {want} vs 원격 {got}", file=sys.stderr)
            ok = False
    extra = [f for f in remote if f not in top and f != ".gitattributes"]
    print(f"   업로드 검증: {'일치' if ok else '불일치'} | 원격 파일 {len(remote)}개"
          + (f" | 예상 외 파일 {extra}" if extra else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
