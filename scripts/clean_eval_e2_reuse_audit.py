"""Existing metadata only. Does not extract ROI, align audio or run models."""
import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from clean_eval_audit import DATA, OUT


def main():
    sources = []
    def read(p):
        raw = p.read_bytes()
        sources.append({'path': str(p), 'sha256': hashlib.sha256(raw).hexdigest()})
        return json.loads(raw.decode('utf-8-sig'))
    def norm(s):
        return ''.join(re.findall('[가-힣]', s))
    root = DATA / 'e2_538'
    meta = read(root/'manifest-meta.json')
    cohort = read(root/'cohort-acquired.json')
    lines = (root/'manifest.tsv').read_text(encoding='utf-8').splitlines()
    texts = {Path(a[0]).stem:a[2] for line in lines if len(a:=line.split('\t'))==3}
    sources.append({'path': str(root/'manifest.tsv'), 'sha256': hashlib.sha256((root/'manifest.tsv').read_bytes()).hexdigest()})
    st = read(DATA/'train538/state.json')
    train_person = {spk:r['person'] for spk,r in st['done'].items()}
    uses = {}
    for stage in ('explore','confirm'):
        p = OUT.parent/('e2-'+stage)/'clips.jsonl'
        raw = p.read_bytes()
        sources.append({'path':str(p),'sha256':hashlib.sha256(raw).hexdigest()})
        for line in raw.decode('utf-8').splitlines():
            r=json.loads(line); uses[r['clip']]=stage
    packs = {}
    for name, rel in [('B33','run_base'),('K1_K2','run_k')]:
        p=DATA/'roi-kmsav'/rel/'prep.json'; d=read(p)
        tr=d['meta']['train_spk']; val=d['meta']['val_spk']
        pack_person={train_person[s] for s in tr}
        texts_train={norm(c['text']) for c in d['clips'] if c['role']=='train' and c.get('text')}
        packs[name]={'person_train':pack_person,'person_val':{train_person[s] for s in val},
                     'texts_train':texts_train, 'clips':d['clips']}
    rows=[]
    for person in sorted({m['person'] for m in meta}):
        rs=[r for r in meta if r['person']==person];spk=rs[0]['spk']
        rows.append({'person':person,'spk':spk,'half':rs[0]['half'],'clips':len(rs),
                     'unique_texts':len({norm(texts[r['clip']]) for r in rs}),
                     'words':sum(len(texts[r['clip']].split()) for r in rs),
                     'duration_sec':round(sum(r['duration'] for r in rs),3),
                     'e2_uses':';'.join(sorted({uses.get(r['clip'],'not in saved E2 outcomes') for r in rs})),
                     'overlap_train538_any':person in set(train_person.values()),
                     'overlap_B33_train':person in packs['B33']['person_train'],
                     'overlap_K1_K2_538_train':person in packs['K1_K2']['person_train'],
                     'overlap_KMSAV_person_identity':'unknown: no common person namespace',
                     'B33_exact_train_text_matches':sum(norm(texts[r['clip']]) in packs['B33']['texts_train'] for r in rs),
                     'K_exact_train_text_matches':sum(norm(texts[r['clip']]) in packs['K1_K2']['texts_train'] for r in rs),
                     'R2_training_overlap':'unknown', 'lipread_eval_history':'not found in inspected V1/ROI registered cohorts'})
    for r in rows:
        union_texts = packs['B33']['texts_train'] | packs['K1_K2']['texts_train']
        person_clips = [c for c in meta if c['person'] == r['person']]
        r['union_exact_train_text_matches'] = sum(norm(texts[c['clip']]) in union_texts for c in person_clips)
        r['retained_nonshared_clips'] = r['clips'] - r['union_exact_train_text_matches']
        r['eligible_at_min3'] = r['retained_nonshared_clips'] >= 3
    with (OUT/'e2-reuse-person.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    names={r['clip'] for r in meta}
    disk={p.stem for p in (root/'clips').glob('*.mp4')}
    e2people={r['person'] for r in meta}
    result={'clips':len(meta),'persons':len(rows),'halves_persons':dict(collections.Counter(r['half'] for r in rows)),
            'halves_clips':dict(collections.Counter(r['half'] for r in meta)),
            'clips_per_person':dict(collections.Counter(r['clips'] for r in rows)),
            'unique_texts':len({norm(t) for t in texts.values()}),'text_rows':len(texts),
            'word_tokens':sum(len(t.split()) for t in texts.values()),
            'total_duration_sec':sum(r['duration'] for r in meta),
            'mp4_bytes':sum(p.stat().st_size for p in (root/'clips').glob('*.mp4')),
            'wav_bytes':sum(p.stat().st_size for p in (root/'clips').glob('*.wav')),
            'missing_mp4':sorted(names-disk),'unmanifested_mp4':sorted(disk-names),
            'missing_wav':[n for n in sorted(names) if not (root/'clips'/(n+'.wav')).exists()],
            'non_front_names':[n for n in names if not re.search(r'_[CE]\d+_A_\d+_s\d+$',n)],
            'cohort_person_match':e2people=={r['person'] for r in cohort},
            'overlap_train538':sorted(e2people & set(train_person.values())),
            'overlap_B33':sorted(e2people & packs['B33']['person_train']),
            'overlap_K1_K2_538':sorted(e2people & packs['K1_K2']['person_train']),
            'B33_shared_text_clips':sum(r['B33_exact_train_text_matches'] for r in rows),
            'K_shared_text_clips':sum(r['K_exact_train_text_matches'] for r in rows),
            'union_shared_text_clips':sum(r['union_exact_train_text_matches'] for r in rows),
            'after_min3_persons':sum(r['eligible_at_min3'] for r in rows),
            'after_min3_halves':dict(collections.Counter(r['half'] for r in rows if r['eligible_at_min3'])),
            'after_min3_clips':sum(r['retained_nonshared_clips'] for r in rows if r['eligible_at_min3']),
            'min3_excluded_persons':[{'person':r['person'],'spk':r['spk'],'half':r['half'],'clips':r['retained_nonshared_clips']} for r in rows if not r['eligible_at_min3']],
            'known_E2_use_clips':sum(n in uses for n in names),
            'new_inference':0,'network_requests':0,'sources':sources}
    (OUT/'e2-reuse-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},ensure_ascii=False))


if __name__=='__main__':
    main()
