#!/usr/bin/env python3
"""V7b 받은 뒤 고르기 준비(맥, 측정 전). liplab-lab/data/v18/v7b_dl2를 한 뿌리로 만든다.
  - spk407(3.1절, 대본 001~008을 10/9에 이미 받음)의 클립을 data/v18/v7b_dl에서 복제(cp -c)하고 manifest 행을 더한다(한 번만).
  - 화자별 계획 v7b_plan2.json: 3.1절 7명과 탐색 절반 8명은 10/9 계획(v7b_plan.json)의 인물, 새 배치는 영상 첫 mp4의 인물
    (data/v18/v7b_dl2/state/<spk>.video.json)의 계획(v7b_plan2_persons.json). 그다음 v7b_read_spont.py select를 부른다.
  python3 scripts/newdata_c27/v7b_prepare.py
"""
import json
import os
import subprocess
import sys

LAB = os.path.expanduser("~/Downloads/liplab-lab")
V18 = f"{LAB}/data/v18"
OLD, NEW = f"{V18}/v7b_dl", f"{V18}/v7b_dl2"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    old_plan = json.load(open(f"{V18}/v7b_plan.json"))
    persons = json.load(open(f"{V18}/v7b_plan2_persons.json"))
    have = set()
    if os.path.exists(f"{NEW}/manifest.tsv"):
        have = {l.split("\t")[1] for l in open(f"{NEW}/manifest.tsv", encoding="utf-8")}
    if "spk407" not in have:
        sc = set(old_plan["spk407"]["read"] + old_plan["spk407"]["spont"])
        rows = [l.rstrip("\n").split("\t") for l in open(f"{OLD}/manifest.tsv", encoding="utf-8")]
        rows = [r for r in rows if r[1] == "spk407" and r[0][:-4].rsplit("_", 2)[1] in sc]
        os.makedirs(f"{NEW}/clips", exist_ok=True)
        with open(f"{NEW}/manifest.tsv", "a", encoding="utf-8") as f:
            for r in rows:
                b = r[0][:-4]
                for e in (".mp4", ".wav"):
                    if not os.path.exists(f"{NEW}/clips/{b}{e}"):
                        subprocess.run(["cp", "-c", f"{OLD}/clips/{b}{e}", f"{NEW}/clips/{b}{e}"], check=True)
                f.write("\t".join(r) + "\n")
        print("SPK407_COPIED", len(rows))
    plan = {}
    for spk, p in old_plan.items():
        plan[spk] = p
    for fn in os.listdir(f"{NEW}/state"):
        if not fn.endswith(".video.json"):
            continue
        v = json.load(open(f"{NEW}/state/{fn}"))
        spk = v["spk"]
        if spk in plan or not v["got"]:
            continue
        p = persons[spk][v["person"]]
        plan[spk] = {"person": v["person"], "half": p["half"], "rows": p["rows"], "read": p["read"], "spont": p["spont"],
                     "max_script": p["max_script"]}
    json.dump(plan, open(f"{V18}/v7b_plan2.json", "w"), ensure_ascii=False, indent=1)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "v7b_read_spont.py"), "select", "--root", NEW,
                    "--pool", f"{V18}/tl_survey.jsonl", "--plan", f"{V18}/v7b_plan2.json", "--out", f"{V18}/v7b_sel2.json",
                    "--list", f"{V18}/v7b_list2.txt"], check=True)


if __name__ == "__main__":
    main()
