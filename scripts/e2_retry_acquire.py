"""E2 538 선택 수신: 조각 연결, 완결 멤버만 보존, 인증 실패 즉시 중단."""
import collections, hashlib, io, json, os, random, re, shutil, subprocess, sys, tarfile, tempfile, time, zlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(r'D:\work\hq\projects\liplab-lab\data\e2_538')
REPO=Path(__file__).resolve().parents[1]
KEY=Path(r'D:\work\hq\projects\liplab-lab\.aihub.key')
EXHASH='a826028983d56eab1a3d9017ee647dc875854fdfb607bdb4ed3beccf9f2a233f'
class AuthFailure(Exception): pass
class Stream:
    def __init__(self, r, cap):
        self.r=r; self.cap=cap; self.n=0; self.t=time.time()
        fd,self.header=tempfile.mkstemp(dir=ROOT,suffix='.header');os.close(fd)
        self.response=self.header+'.response'
        key=KEY.read_text(encoding='utf-8-sig').strip()
        if not key or len(key.splitlines())!=1: raise ValueError('single key required')
        Path(self.header).write_text('apikey:'+key,encoding='utf-8'); del key
        self.p=subprocess.Popen(['curl.exe','-sS','-L','--connect-timeout','30','--max-time','900','-H','@'+self.header,'-D',self.response,'https://api.aihub.or.kr/down/0.6/538.do?fileSn='+r['video_fileSn']],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.first=True
    def read(self,n=-1):
        n=min(n if n>=0 else 1024*1024,self.cap-self.n)
        if n<=0:return b''
        b=self.p.stdout.read(n);self.n+=len(b)
        if self.first:
            self.first=False
            if '인증실패'.encode() in b or '인증실패'.encode('cp949') in b:
                (ROOT/'AUTH_STOP').write_text('Authentication failure: do not retry.');raise AuthFailure('authentication failed; stopped')
            headers=Path(self.response).read_text(errors='replace')
            codes=re.findall(r'HTTP/\S+\s+(\d+)',headers)
            if not codes or codes[-1]!='200': raise RuntimeError('download HTTP '+str(codes[-1:] or 'unknown'))
        return b
    def close(self):
        self.p.terminate();self.p.stdout.close();self.p.wait()
        Path(self.header).unlink(missing_ok=True);Path(self.response).unlink(missing_ok=True)
        with (ROOT/'transfers.jsonl').open('a') as f:f.write(json.dumps({'file':self.r['video_file'],'bytes':self.n,'seconds':round(time.time()-self.t,3),'cap':self.cap})+'\n')
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
def extract_target(stream,target,dest):
    """잘린 마지막 멤버와 ReadError는 버리고 완결 목표 파일만 반환한다."""
    last=None
    try:
        with tarfile.open(fileobj=stream,mode='r|') as outer:
            with tarfile.open(fileobj=JoinedParts(outer),mode='r|') as inner:
                for m in inner:
                    if not m.isfile():continue
                    last={'name':m.name,'offset':m.offset,'size':m.size}
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
    while counts.get(r['video_file'],0)<2:
        prior=counts.get(r['video_file'],0)
        cap=(4 if prior else 2)*2**30
        if last and Path(last['name']).name==r['Video_info']['video_Name']:
            cap=min(8*2**30,last['offset']+last['size']+2**20)
        counts[r['video_file']]=prior+1
        attempts_path.write_text(json.dumps(counts,indent=2))
        s=Stream(r,cap)
        try:source,last=extract_target(s,r['Video_info']['video_Name'],dest)
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
    manifest=(ROOT/'manifest.tsv').read_text(encoding='utf-8').splitlines()
    details=json.loads((ROOT/'manifest-meta.json').read_text(encoding='utf-8'))
    done={d['spk'] for d in details};failures=[]
    for r in plan:
        if r['spk'] in done:continue
        assert r['spk'] not in ex and r['person'] not in ex and r['half']==zlib.crc32(r['spk'].encode())%2
        base=Path(r['Video_info']['video_Name']).stem
        assert re.search(r'_[CE]\d+_A_\d+$',base)
        rows=sorted(parse_sentences.sentences(r),key=lambda x:f'{base}_s{x[0]:03d}')
        random.Random(0).shuffle(rows);rows=rows[:12]
        try:
            source=video(r)
            def cut(row):
                idx,sid,rs,re_,start,dur,tx=row;name=f'{base}_s{idx:03d}';mp4=ROOT/'clips'/(name+'.mp4');wav=mp4.with_suffix('.wav')
                # 완결 MP4만 사용하고 출력 탐색으로 시각을 고정한다.
                cmd=[ff,'-v','error','-y','-i',str(source),'-ss',start,'-t',dur,'-map','0:v:0','-map','0:a:0','-vf','scale=640:-2','-r','30','-c:v','libx264','-preset','ultrafast','-crf','23','-threads','2','-c:a','aac','-ac','1',str(mp4),'-ss',start,'-t',dur,'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)]
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
            failures.append({'spk':r['spk'],'error':str(e)[:300]});print('VIDEO_ERROR',r['spk'],type(e).__name__,str(e)[:180],flush=True)
        (ROOT/'acquire-failures.json').write_text(json.dumps(failures,indent=2))
    print('ACQUIRE_DONE',len(done),flush=True)
if __name__=='__main__':acquire()
