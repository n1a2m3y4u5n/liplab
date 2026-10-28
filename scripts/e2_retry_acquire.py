"""E2 538 선택 수신: 조각 연결, 완결 멤버만 보존, 인증 실패 즉시 중단."""
import collections, hashlib, io, json, os, random, re, shutil, subprocess, sys, tarfile, tempfile, time, zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(r'D:\work\hq\projects\liplab-lab\data\e2_538')
REPO=Path(__file__).resolve().parents[1]
KEY=Path(r'D:\work\hq\projects\liplab-lab\.aihub.key')
EXHASH='a826028983d56eab1a3d9017ee647dc875854fdfb607bdb4ed3beccf9f2a233f'
class AuthFailure(Exception): pass
class SlowStop(AuthFailure): pass   # 인증 실패와 같은 길로 즉시 멈추되 AUTH_STOP은 남기지 않는다
class Stream:
    def __init__(self, r, cap):
        self.r=r; self.cap=cap; self.n=0; self.t=time.time()
        fd,self.header=tempfile.mkstemp(dir=ROOT,suffix='.header');os.close(fd)
        self.response=self.header+'.response'
        key=KEY.read_text(encoding='utf-8-sig').strip()
        if not key or len(key.splitlines())!=1: raise ValueError('single key required')
        Path(self.header).write_text('apikey:'+key,encoding='utf-8'); del key
        self.p=subprocess.Popen(['curl.exe','-sS','-L','--connect-timeout','30','--max-time',str(max(900,cap//(2*2**20))),   # 10/28: 4GiB 이상은 900초 안에 못 닿아 잘렸다(2MB/s 아래면 시간 초과)
            '-H','@'+self.header,'-D',self.response,'https://api.aihub.or.kr/down/0.6/538.do?fileSn='+r['video_fileSn']],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.first=True
    def read(self,n=-1):
        n=min(n if n>=0 else 1024*1024,self.cap-self.n)
        if n<=0:return b''
        b=self.p.stdout.read(n);self.n+=len(b)
        el=time.time()-self.t
        if el>180 and self.n/el<512*1024:   # 10/27 오후 서버가 100KB/s로 느려져 요청만 날렸다. 느리면 전체를 멈춘다
            (ROOT/'SLOW_STOP').write_text(time.strftime('%Y-%m-%dT%H:%M:%S')+' '+self.r['video_file']+' '+str(self.n));raise SlowStop('server too slow; stopped')
        if self.first:
            self.first=False
            if '인증실패'.encode() in b or '인증실패'.encode('cp949') in b:
                (ROOT/'AUTH_STOP').write_text('Authentication failure: do not retry.');raise AuthFailure('authentication failed; stopped')
            headers=Path(self.response).read_text(errors='replace')
            codes=re.findall(r'HTTP/\S+\s+(\d+)',headers)
            if codes and codes[-1] in ('401','403','502'):   # 502는 키 오류에서도 나므로 즉시 멈춘다(10/27 지시)
                (ROOT/'AUTH_STOP').write_text('Authentication HTTP failure: do not retry.');raise AuthFailure('authentication failed; stopped')
            if not codes or codes[-1]!='200': raise RuntimeError('download HTTP '+str(codes[-1:] or 'unknown'))
        return b
    def close(self):
        rc=self.p.poll();self.p.terminate();self.p.stdout.close();self.p.wait();self.p.returncode=rc if rc is not None else 'killed'
        Path(self.header).unlink(missing_ok=True);Path(self.response).unlink(missing_ok=True)
        with (ROOT/'transfers.jsonl').open('a') as f:f.write(json.dumps({'file':self.r['video_file'],'bytes':self.n,'seconds':round(time.time()-self.t,3),'cap':self.cap,'curl_rc':self.p.returncode})+'\n')   # 10/28: 서버가 일찍 끊는지(18·56) 남긴다
class JoinedParts:
    """외부 tar의 .partN을 이어 내부 tar의 1GiB 경계 절단을 없앤다."""
    def __init__(self, outer):self.outer=outer;self.current=None;self.eof=False
    def read(self,n):
        chunks=[];remaining=n
        if self.eof:return b''
        while remaining:
            if self.current is None:
                m=self.outer.next()
                if m is None:self.eof=True;break
                if not m.isfile():continue
                print('PART',m.name,m.size,flush=True)
                self.current=self.outer.extractfile(m)
            b=self.current.read(min(remaining,1024*1024))
            if not b:self.current=None;continue
            chunks.append(b);remaining-=len(b)
        return b''.join(chunks)
def extract_target(stream,target,dest,front_only=False):
    """잘린 마지막 멤버와 ReadError는 버리고 완결 목표 파일만 반환한다."""
    last=None
    try:
        with tarfile.open(fileobj=stream,mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer),mode='r|') as inner:
                for m in inner:
                    if not m.isfile():continue
                    last={'name':m.name,'offset':m.offset,'size':m.size}
                    if front_only and m.name.endswith('.mp4') and Path(m.name.replace('\\','/')).name!=target:
                        return None,last
                    if Path(m.name.replace('\\','/')).name!=target:continue
                    tmp=dest.with_suffix('.partial')
                    try:
                        with tmp.open('wb') as f:shutil.copyfileobj(inner.extractfile(m),f,1024*1024)
                        if tmp.stat().st_size!=m.size:return None,last
                        tmp.replace(dest);return dest,last
                    finally:tmp.unlink(missing_ok=True)
    except (tarfile.ReadError,EOFError):pass
    return None,last
def video(r):
    attempts_path=ROOT/'request-counts.json'
    counts=json.loads(attempts_path.read_text()) if attempts_path.exists() else {'TS131.tar':1}
    dest=ROOT/'source.mp4';last=None
    while counts.get(r['video_file'],0)<r.get('max_requests',2):
        prior=counts.get(r['video_file'],0)
        cap=(4 if prior else 2)*2**30
        if 'source_cap' in r:cap=r['source_cap'] if r.get('deep_retry') else min(cap,r['source_cap'])   # 10/27 12GiB 재시도만 4GiB를 넘긴다
        if r.get('selection_basis','').startswith('skipped first header') and not r.get('deep_retry') and prior>=2:
            # 10/28: 정면 A가 tar 깊숙이 있어 4GiB 앞부분으론 못 닿았다. 남은 한 번은 tar 끝까지 흘려 읽는다(디스크에 tar를 두지 않음)
            m=re.search(re.escape(r['video_file'])+r'\s*\|\s*([\d,]+)\s*(GB|MB|KB|B)',(REPO/'out/aihub538-filetree-retry.txt').read_text(encoding='utf-8'))
            if m:cap=int(m[1].replace(',',''))*{'MB':2**20,'GB':2**30,'KB':1024,'B':1}[m[2]]+2**30
        if 'source_offset' in r:
            cap=r['source_offset']+r['source_bytes']+2**20
        if last and Path(last['name']).name==r['Video_info']['video_Name']:
            cap=min(8*2**30,last['offset']+last['size']+2**20)
        counts[r['video_file']]=prior+1
        attempts_path.write_text(json.dumps(counts,indent=2))
        s=Stream(r,cap)
        try:source,last=extract_target(s,r['Video_info']['video_Name'],dest,r.get('front_only',False))
        except AuthFailure:raise
        except Exception as error:
            print('TAR_ERROR',r['video_file'],type(error).__name__,str(error)[:180],flush=True)
            source=None
        finally:s.close()
        print('STREAM',r['spk'],s.n,'last',last,flush=True)
        if source:return source
    raise ValueError('bounded requests exhausted: '+r['video_file'])
def acquire():
    import imageio_ffmpeg
    sys.path.insert(0,r'D:\work\hq\projects\liplab-lab\tools');import parse_sentences
    if (ROOT/'AUTH_STOP').exists():raise AuthFailure('previous authentication failure; stopped')
    excluded=REPO/'docs/e2-excluded-speakers-2026-10-27.txt'
    assert hashlib.sha256(excluded.read_bytes()).hexdigest()==EXHASH
    ex=set(excluded.read_text().splitlines());ff=imageio_ffmpeg.get_ffmpeg_exe()
    plan=json.loads((ROOT/'plan.json').read_text(encoding='utf-8'))
    frozen=json.loads((ROOT/'cohort-frozen.json').read_text(encoding='utf-8'))
    if frozen.get('rule_commit'):
        assert frozen['plan_sha256']==hashlib.sha256((ROOT/'plan.json').read_bytes()).hexdigest()
    manifest=(ROOT/'manifest.tsv').read_text(encoding='utf-8').splitlines()
    details=json.loads((ROOT/'manifest-meta.json').read_text(encoding='utf-8'))
    done={d['spk'] for d in details}
    failure_path=ROOT/'acquire-failures.json'
    failures=json.loads(failure_path.read_text(encoding='utf-8')) if failure_path.exists() else []
    for r in plan:
        if r['spk'] in done:continue
        if all(sum(zlib.crc32(s.encode())%2==h for s in done)>=20 for h in (0,1)):break
        if sum(zlib.crc32(s.encode())%2==r['half'] for s in done)>=20:continue
        assert r['spk'] not in ex and r['person'] not in ex and r['half']==zlib.crc32(r['spk'].encode())%2
        base=Path(r['Video_info']['video_Name']).stem
        assert re.search(r'_[CE]\d+_A_\d+$',base)
        rows=sorted(parse_sentences.sentences(r),key=lambda x:f'{base}_s{x[0]:03d}')
        random.Random(0).shuffle(rows);rows=rows[:12]
        if len(rows)!=12:raise ValueError('insufficient metadata sentences: '+r['spk'])
        try:
            source=video(r)
            def cut(row):
                idx,sid,rs,re_,start,dur,tx=row;name=f'{base}_s{idx:03d}';mp4=ROOT/'clips'/(name+'.mp4');wav=mp4.with_suffix('.wav')
                # 잘린 MP4는 버렸으므로 완결 입력에 한해 빠른 입력 탐색을 쓴다.
                cmd=[ff,'-v','error','-y','-ss',start,'-i',str(source),'-t',dur,'-map','0:v:0','-map','0:a:0','-vf','scale=640:-2','-r','30','-c:v','libx264','-preset','ultrafast','-crf','23','-threads','2','-c:a','aac','-ac','1',str(mp4),'-t',dur,'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)]
                subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                return name,tx,{'clip':name,'spk':r['spk'],'person':r['person'],'half':r['half'],'start':float(start),'duration':float(dur),'sentence_ID':sid}
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(cut,rows))
            finally:source.unlink(missing_ok=True)
            for name,tx,meta in results:manifest.append(f'{name}.mp4\t{r["spk"]}\t{tx}');details.append(meta)
            (ROOT/'manifest.tsv').write_text('\n'.join(sorted(manifest))+'\n',encoding='utf-8')
            (ROOT/'manifest-meta.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
            done.add(r['spk'])
            print('VIDEO_DONE',r['spk'],'speakers',len(done),'halves',[sum(zlib.crc32(s.encode())%2==h for s in done) for h in (0,1)],flush=True)
        except AuthFailure:raise
        except Exception as e:
            failures=[f for f in failures if f['spk']!=r['spk']]
            failures.append({'spk':r['spk'],'file':r['video_file'],'error':str(e)[:300]});print('VIDEO_ERROR',r['spk'],type(e).__name__,str(e)[:180],flush=True)
        (ROOT/'acquire-failures.json').write_text(json.dumps(failures,indent=2))
    print('ACQUIRE_DONE',len(done),flush=True)
if __name__=='__main__':acquire()
