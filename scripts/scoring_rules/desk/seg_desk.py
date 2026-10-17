"""데스크탑(Windows) 자르기: run_sr.sh confirm의 'seg c27b2' 단계와 같은 일(speak_asr_pod_run.cut_608, b675975판, large-v3 fp16 GPU).

    vseg\\Scripts\\python.exe seg_desk.py W SCRIPTS_DIR      W = .../c27b2 (s608/meta.json 필요), SCRIPTS_DIR = b675975판 scripts 폴더

파드와 다른 점: CUDA 11 cuBLAS·cuDNN 8 DLL을 pip nvidia-* 휠의 bin 폴더에서 찾도록 DLL 경로를 더한다(리눅스는 LD_LIBRARY_PATH).
"""
import glob
import os
import sys

W, SCRIPTS = os.path.abspath(sys.argv[1]).replace("\\", "/"), sys.argv[2]
try:
    import nvidia
    for base in nvidia.__path__:
        for d in glob.glob(os.path.join(base, "*", "bin")):
            os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
except ImportError:
    pass
sys.path.insert(0, SCRIPTS)
import speak_asr_pod_run as m  # noqa: E402

m.W, m.OUT = W, W + "/out"
os.makedirs(m.OUT, exist_ok=True)
os.makedirs(W + "/cuts", exist_ok=True)
m.cut_608()
print("SEG DONE", flush=True)
# 10/17: Windows에서 ctranslate2(CUDA)가 인터프리터 종료 때 0xC0000409로 죽는다(cuts608.json은 이미 다 씀). 정리 없이 끝낸다.
os._exit(0)
