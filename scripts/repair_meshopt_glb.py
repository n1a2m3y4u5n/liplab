"""EXT_meshopt_compression 오프셋이 어긋난 GLB 복구 (2026-09-21 CC 두상 모델에서 발생).

증상: 로더가 `Malformed buffer data: -1`로 죽는다. 원인은 BIN 청크 배치가
  [0, IMG_END)         이미지(일반 bufferView)
  [IMG_END, STREAMS)   참조되지 않는 쓰레기 블록(이미지가 한 번 더 들어감)
  [STREAMS, END)       진짜 meshopt 스트림 — 그런데 ext.byteOffset이 STREAMS-IMG_END 만큼 앞을 가리킴
이라서다. 쓰레기 블록을 버리고 ext.byteOffset을 이미지 끝 기준으로 다시 놓는다.

사용법: python scripts/repair_meshopt_glb.py <깨진.glb> <출력.glb> <SHIFT>
  SHIFT = 스트림이 실제로 얼마나 뒤에 있는지(바이트). 첫 스트림 헤더 바이트(ATTRIBUTES 0xa0/0xa1,
  TRIANGLES 0xe0/0xe1)가 ext.byteOffset+SHIFT에 오는 값을 찾는다. 2026-09-21 파일은 768448.
복구 후에는 반드시 디코더로 모든 스트림이 풀리는지 확인한다(개발일지 N 참고).
"""
import json, struct, sys
src, dst, SHIFT = sys.argv[1], sys.argv[2], int(sys.argv[3])  # SHIFT: found by header cross-correlation, verified by decoding every view
with open(src, "rb") as f:
    magic, ver, total = struct.unpack("<4sII", f.read(12)); assert magic == b"glTF"
    clen, ctype = struct.unpack("<II", f.read(8)); js = json.loads(f.read(clen).decode("utf-8"))
    blen, btype = struct.unpack("<II", f.read(8)); bin_ = f.read(blen); assert btype == 0x004E4942
plain = [bv for bv in js["bufferViews"] if "EXT_meshopt_compression" not in (bv.get("extensions") or {})]
ext = [bv["extensions"]["EXT_meshopt_compression"] for bv in js["bufferViews"] if "EXT_meshopt_compression" in (bv.get("extensions") or {})]
IMG_END = max(bv["byteOffset"] + bv["byteLength"] for bv in plain)
decl_start = min(e["byteOffset"] for e in ext)
decl_len = max(e["byteOffset"] + e["byteLength"] for e in ext) - decl_start
shift = SHIFT
STREAMS = decl_start + shift
assert STREAMS + decl_len <= len(bin_) <= STREAMS + decl_len + 3, (STREAMS + decl_len, len(bin_))
assert IMG_END % 4 == 0 and shift > 0, (IMG_END, shift)
assert all(bv["byteOffset"] + bv["byteLength"] <= IMG_END for bv in plain)
print(f"images end={IMG_END} declared streams start={decl_start} real streams start={STREAMS} shift={shift} junk={STREAMS-IMG_END} bytes")
# junk block: is it a duplicate of the image block?
junk = bin_[IMG_END:STREAMS]
print("junk == images block?", junk[:IMG_END] == bin_[:IMG_END], "| junk head:", junk[:8].hex())
new_bin = bin_[:IMG_END] + bin_[STREAMS:]
for e in ext:
    e["byteOffset"] = e["byteOffset"] - decl_start + IMG_END
    assert e["byteOffset"] + e["byteLength"] <= len(new_bin)
# the plain byteOffset/byteLength on meshopt views are meaningless leftovers (spec: fallback buffer);
# point them at a proper fallback buffer so strict validators are happy and nothing overlaps.
fallback_len = 0
for bv in js["bufferViews"]:
    if "EXT_meshopt_compression" in (bv.get("extensions") or {}):
        bv["buffer"] = 1
        bv["byteOffset"] = fallback_len
        fallback_len += (bv["byteLength"] + 3) // 4 * 4
js["buffers"] = [{"byteLength": len(new_bin)}, {"byteLength": fallback_len, "extensions": {"EXT_meshopt_compression": {"fallback": True}}}]
assert len(new_bin) % 4 == 0
jb = json.dumps(js, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
jb += b" " * ((4 - len(jb) % 4) % 4)
out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(jb) + 8 + len(new_bin)) + struct.pack("<II", len(jb), 0x4E4F534A) + jb + struct.pack("<II", len(new_bin), 0x004E4942) + new_bin
open(dst, "wb").write(out)
print(f"wrote {dst}: {len(out)/1e6:.2f} MB (was {total/1e6:.2f} MB)")
