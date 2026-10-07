"""파드: 렌더 작업 목록(JSON) → 작업마다 <out>/<id>.mp4(H.264 640×360 30fps)와 <id>.sched.json(재생 일정).

하네스(scripts/v2_render, vite build 결과 폴더)를 로컬 HTTP로 띄우고, 작업자마다 헤드리스 Chromium(Playwright) 하나를 연다.
작업자는 작업 번호 % 작업자 수로 나눠 가지며, 이미 있는 결과는 건너뛴다(끊겨도 다시 돌리면 이어서 한다).

  python render_jobs.py --harness DIR --jobs jobs_text.json [--jobs jobs_raw.json] --out DIR --workers 12 --gl swiftshader
  python render_jobs.py --harness DIR --jobs jobs_text.json --bench --gl swiftshader      # 작업 하나로 속도·렌더러 확인
표식: RJ_OK id n 초, RJ_FAIL id 오류, RJ_DONE ok fail skip
"""
import argparse
import base64
import functools
import http.server
import json
import multiprocessing as mp
import os
import subprocess
import sys
import threading
import time

GL_ARGS = {
    "swiftshader": ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
    "egl": ["--use-gl=angle", "--use-angle=gl-egl", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"],
    "vulkan": ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist"],
}


def serve(root, port):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def write_mp4(images, path):
    tmp = path + ".part.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", "30", "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30", tmp],
                         stdin=subprocess.PIPE)
    for im in images:
        p.stdin.write(base64.b64decode(im.split(",", 1)[1]))
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg 실패")
    os.replace(tmp, path)


def open_page(pw, a, port):
    br = pw.chromium.launch(headless=True, args=GL_ARGS[a.gl] + ["--no-sandbox", "--disable-dev-shm-usage"])
    pg = br.new_page(viewport={"width": 700, "height": 400})
    pg.goto(f"http://127.0.0.1:{port}/index.html")
    pg.wait_for_function("window.__v2ready === true", timeout=60000)
    cam = [float(x) for x in a.cam.split(",")]
    tgt = [float(x) for x in a.target.split(",")]
    info = pg.evaluate("(c) => window.__v2.init(c)", {"w": 640, "h": 360, "fov": a.fov, "camPos": cam, "target": tgt,
                                                      "glb": a.glb or None})
    return br, pg, info


def run_job(pg, j, tables=None):
    if j["kind"] == "text":
        # V15: table(후보 입모양 표 이름, --tables 파일의 키)이 있으면 그 표로 렌더한다. 없으면 하네스에 빌드된 앱 표.
        tbl = (tables or {}).get(j["table"]) if j.get("table") else None
        if j.get("table") and tbl is None:
            raise KeyError("table " + j["table"])
        r = pg.evaluate("(j) => window.__v2.renderText(j)",
                        {"frames": j["frames"], "talker": j["talker"], "seed": 0, "speed": j["speed"], "leadMs": 400, "tailMs": 400,
                         "table": tbl})
        sched = {"id": j["id"], "schedule": r["schedule"], "speech": r["speech"], "fps": r["fps"], "talker": j["talker"], "speed": j["speed"],
                 "table": j.get("table")}
    elif j["kind"] == "poses":
        r = pg.evaluate("(j) => window.__v2.renderPoses(j)", {"poses": j["poses"], "hold": j.get("hold", 3)})
        sched = {"id": j["id"], "poses": len(j["poses"]), "hold": r["hold"], "fps": r["fps"]}
    else:
        r = pg.evaluate("(j) => window.__v2.renderRaw(j)", {"names": j["names"], "frames": j["frames"], "fps": j.get("fps", 30),
                                                             "rawMap": j.get("rawMap")})
        sched = {"id": j["id"], "raw": True, "fps": r["fps"], "n_in": len(j["frames"]), "rawMap": bool(j.get("rawMap"))}
    return r["images"], sched


def worker(wid, a, port, jobs, q):
    ok = fail = skip = 0
    try:
        _worker(wid, a, port, jobs, q, [0, 0, 0])
    except Exception as e:
        print(f"RJ_WORKER_FAIL {wid} {type(e).__name__}: {str(e)[:300]}", flush=True)
        q.put((0, 0, 0))


def _worker(wid, a, port, jobs, q, _cnt):
    from playwright.sync_api import sync_playwright
    ok = fail = skip = 0
    with sync_playwright() as pw:
        br, pg, info = open_page(pw, a, port)
        if wid == 0:
            print("RJ_GL", json.dumps(info, ensure_ascii=False), flush=True)
        for k, j in enumerate(jobs):
            if k % a.workers != wid:
                continue
            mp4 = os.path.join(a.out, j["id"] + ".mp4")
            sj = os.path.join(a.out, j["id"] + ".sched.json")
            if os.path.exists(mp4) and os.path.exists(sj):
                skip += 1
                continue
            t0 = time.time()
            try:
                images, sched = run_job(pg, j, a.tables_obj)
                write_mp4(images, mp4)
                json.dump(sched, open(sj + ".tmp", "w"), ensure_ascii=False)
                os.replace(sj + ".tmp", sj)
                ok += 1
                print(f"RJ_OK {j['id']} {len(images)} {time.time() - t0:.1f}", flush=True)
            except Exception as e:
                fail += 1
                print(f"RJ_FAIL {j['id']} {type(e).__name__}: {str(e)[:200]}", flush=True)
                try:   # 페이지가 망가졌을 수 있어 다시 연다
                    br.close()
                except Exception:
                    pass
                br, pg, _ = open_page(pw, a, port)
        br.close()
    q.put((ok, fail, skip))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True)
    ap.add_argument("--jobs", action="append", required=True)
    ap.add_argument("--out", default="renders")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--gl", choices=sorted(GL_ARGS), default="swiftshader")
    ap.add_argument("--cam", default="0,1.66,1.8")
    ap.add_argument("--target", default="0,1.66,0")
    ap.add_argument("--fov", type=float, default=16)
    ap.add_argument("--port", type=int, default=5196)
    ap.add_argument("--only", default="", help="id 접두어로 거르기(쉼표)")
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--glb", default="", help="하네스 폴더 기준 다른 GLB(리그 측정용 원본 GLB)")
    ap.add_argument("--tables", default="", help="V15 후보 입모양 표 JSON({이름: {입모양: {모프: 가중치}}})")
    a = ap.parse_args()
    a.tables_obj = json.load(open(a.tables, encoding="utf-8")) if a.tables else None
    os.makedirs(a.out, exist_ok=True)
    jobs = []
    for p in a.jobs:
        jobs += json.load(open(p, encoding="utf-8"))
    if a.only:
        pre = tuple(a.only.split(","))
        jobs = [j for j in jobs if j["id"].startswith(pre)]
    srv = serve(os.path.abspath(a.harness), a.port)
    if a.bench:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br, pg, info = open_page(pw, a, a.port)
            t0 = time.time()
            images, _ = run_job(pg, jobs[0], a.tables_obj)
            dt = time.time() - t0
            write_mp4(images, os.path.join(a.out, "_bench_" + a.gl + ".mp4"))
            print("RJ_BENCH", a.gl, json.dumps(info), f"frames={len(images)} sec={dt:.1f} fps={len(images) / dt:.1f}", flush=True)
            br.close()
        srv.shutdown()
        return
    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(w, a, a.port, jobs, q)) for w in range(a.workers)]
    for p in ps:
        p.start()
    tot = [0, 0, 0]
    for _ in ps:
        r = q.get()
        tot = [x + y for x, y in zip(tot, r)]
    for p in ps:
        p.join()
    srv.shutdown()
    print(f"RJ_DONE ok={tot[0]} fail={tot[1]} skip={tot[2]}", flush=True)


if __name__ == "__main__":
    main()
