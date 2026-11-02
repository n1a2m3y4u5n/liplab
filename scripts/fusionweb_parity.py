"""합성 입력만 사용. 원본 AST의 순수 함수만 실행하여 외부 import/자료 접근을 차단한다."""
import argparse
import ast
import json
import math
from pathlib import Path
import struct
import subprocess

SOURCE = Path(r'D:\work\hq\projects\liplab-lab\data\nextreg_2026-11\code\tools\extract_blendshapes.py')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'normalize_lips']
    scope = {'math': math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
    idx = [61,146,91,181,84,17,314,405,321,375,291,409,270,269,267,0,37,39,40,185,
           78,95,88,178,87,14,317,402,318,324,308,415,310,311,312,13,82,81,80,191]
    cases, expected = [], []
    for W, H in [(640,360), (360,640), (1920,1080)]:
        for angle in [-0.52, 0, 0.31]:
            for mirror in [False, True]:
                c, s = math.cos(angle), math.sin(angle)
                def image(x, y):
                    if mirror:
                        x = -x
                    return {'x': (330 + 120*(c*x-s*y))/W, 'y': (205+120*(s*x+c*y))/H}
                lm = [image(0,0) for _ in range(478)]
                for p, i in enumerate(idx):
                    lm[i] = image(-(.3 if p < 20 else .2)*math.cos(2*math.pi*p/20)+.003*(p%3),
                                  (.12 if p < 20 else .05)*math.sin(2*math.pi*p/20))
                lm[33], lm[263] = image(-.5,-1.2), image(.5,-1.2)
                pts = [(lm[i]['x']*W, lm[i]['y']*H) for i in idx]
                ref = scope['normalize_lips'](pts, (lm[33]['x']*W,lm[33]['y']*H), (lm[263]['x']*W,lm[263]['y']*H))
                expected.append([round(v,4) for v in ref])
                cases.append({'landmarks':lm, 'W':W, 'H':H})
    cases.append({'landmarks':[{'x':.5,'y':.5}]*478, 'W':640,'H':360})
    expected.append(None)
    frames = [{'t':t,'lips':v} for t,v in [(0,expected[0]),(1,expected[1]),(67,None),(100,expected[2]),(167,None)]]
    rounds = [0.00005,0.00015,0.00025,-0.00005,1.23445,1.23455,0.06255,-0.06255]
    result = subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))], input=json.dumps({'cases':cases,'frames':frames,'rounds':rounds}),
                            capture_output=True, text=True, check=True)
    got = json.loads(result.stdout)
    worst = max(abs(a-b) for x,y in zip(expected,got['results']) if x for a,b in zip(x,y))
    assert worst <= 0.000100000001, worst  # 양자화 경계에서 1 LSB 허용, 보통 0.
    assert got['results'][-1] is None
    assert got['rounds'] == [round(v,4) for v in rounds]
    f32 = lambda v: struct.unpack('f',struct.pack('f',v))[0]
    grid = [expected[1],None,None,expected[2],None,None]
    packed = []
    for i in range(6):
        a,b = (0,3) if i < 3 else (3,3)
        row = [f32(f32(grid[a][k])+(f32(grid[b][k])-f32(grid[a][k]))*((i-a)/(b-a))) if a!=b else f32(grid[a][k]) for k in range(80)]
        assert row == got['lips'][i]
        packed.append(row)
    pad = 75-len(packed)
    flattened = sum([packed[0]]*(pad//2)+packed+[packed[-1]]*(pad-pad//2), [])
    assert flattened == got['packed'] and got['T']==75
    report = {'status':'passed','cases':len(cases),'max_abs_error':worst,'quantized_tolerance':0.000100000001,
              'rounding_ties':'CPython exact double rounding, exact match','pack_float32':'exact match',
              'source':str(SOURCE),'source_function_lines':[nodes[0].lineno,nodes[0].end_lineno],
              'data':'synthetic landmarks only; no images/audio/evaluation data'}
    Path(args.out).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
