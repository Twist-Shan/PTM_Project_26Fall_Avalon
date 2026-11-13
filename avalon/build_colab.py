"""Build the self-contained Colab notebook (A100) for the Avalon study.

  python avalon/build_colab.py        ->  colab_avalon.ipynb  (+ results/notebook_assets.json)

All project code is embedded; the notebook clones avalonlogs inside Colab
(its file names contain ':' and cannot be checked out on Windows), audits it,
freezes the LLM task set, cross-checks Z3 against the independent oracle,
then runs Qwen3-8B and scores everything.  No Google Drive access is needed.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ['avalon/game.py', 'avalon/oracle.py', 'avalon/smt.py', 'avalon/search.py', 'avalon/sim.py',
         'avalon/cases.py', 'avalon/selfcheck.py', 'avalon/logs.py', 'avalon/analyze.py',
         'avalon/llm_tasks.py', 'avalon/llm_run.py', 'RULES.md']

cells = []


def md(s):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': s.strip().splitlines(True)})


def code(s):
    ast.parse(s)
    cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
                  'source': s.strip().splitlines(True)})


def main():
    assets = {n: (ROOT / n).read_text(encoding='utf-8') for n in FILES}
    md('''
# 阿瓦隆：约束求解验证 × Qwen3-8B（Colab A100）

按顺序运行全部单元。流程：
1. 克隆 avalonlogs 真实对局，记录 commit；
2. 审计日志是否符合形式化规则；
3. 冻结 LLM 评测集；
4. Z3 与独立穷举交叉验证，不通过则停止；
5. 依次运行 Qwen3-8B 的五种条件并评分；
6. 真实对局分析（仅用 CPU）；
7. 打包下载。

全部原始输出逐批落盘，中断后重新运行同一单元会从断点续跑。不需要授权 Google Drive。完成并下载 ZIP 后，请断开并删除运行时。
''')
    code('''
import subprocess, sys
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'z3-solver==4.16.0.0',
                       'transformers==4.57.6', 'safetensors>=0.4.3'])
import torch
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')
assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(), '请选择支持 BF16 的 CUDA GPU'
''')
    code('''
import json, sys, os, hashlib
from pathlib import Path
ROOT = Path('/content/avalon_project')
ROOT.mkdir(exist_ok=True)
ASSETS = json.loads(''' + repr(json.dumps(assets, ensure_ascii=False)) + ''')
for name, content in ASSETS.items():
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
sys.path.insert(0, str(ROOT / 'avalon'))
os.chdir(ROOT)
print('assets:', len(ASSETS))
''')
    md('## 1–3 数据：克隆、审计、冻结评测集')
    code('''
import subprocess
DATA = ROOT / 'data' / 'avalonlogs'
if not DATA.exists():
    subprocess.check_call(['git', 'clone', '--quiet', 'https://github.com/WhoaWhoa/avalonlogs', str(DATA)])
COMMIT = subprocess.check_output(['git', '-C', str(DATA), 'rev-parse', 'HEAD'], text=True).strip()
print('avalonlogs commit', COMMIT)
subprocess.check_call([sys.executable, 'avalon/logs.py', '--data', str(DATA), '--inspect', '--audit',
                       '--out', 'results/audit'])
audit = json.loads((ROOT / 'results/audit/audit_summary.json').read_text())
audit['avalonlogs_commit'] = COMMIT
(ROOT / 'results/audit/audit_summary.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
''')
    code('''
TASKS = ROOT / 'data/llm/tasks.jsonl'
if not TASKS.exists():
    subprocess.check_call([sys.executable, 'avalon/llm_tasks.py', '--parsed', 'results/audit/parsed_games.jsonl',
                           '--out', 'data/llm', '--backend', 'z3', '--seed', '137'])
manifest = json.loads((ROOT / 'data/llm/manifest.json').read_text())
assert manifest['tasks_sha256'] == hashlib.sha256(TASKS.read_bytes()).hexdigest()
manifest['avalonlogs_commit'] = COMMIT
(ROOT / 'data/llm/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
items = [json.loads(x) for x in TASKS.read_text(encoding='utf-8').splitlines() if x.strip()]
print(json.dumps(manifest, ensure_ascii=False, indent=1))
''')
    md('## 4 Z3 与独立穷举交叉验证（不调用模型）')
    code('''
r = subprocess.run([sys.executable, 'avalon/selfcheck.py', '--quick', '--out', 'results/selfcheck_colab'],
                   capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-2000:])
assert 'ALL CHECKS PASSED' in r.stdout, 'Z3 与穷举不一致：停止，不要运行模型'
import oracle as O
from smt import SMT
smt = SMT()
small = [it for it in items if it['inst']['rec']['n'] <= 8]
bad = [it['id'] for it in small if O.Oracle().classify(it['inst'], it['claim'])['label'] != it['gold']]
print('gold re-checked by oracle on', len(small), 'items; mismatches:', bad)
assert not bad
''')
    md('## 5 加载固定 revision 的 Qwen3-8B')
    code('''
from llm_run import *
runner = Runner('results/llm')
print(json.dumps(runner.meta, indent=1))
''')
    md('### 5a 直接判断、事实提取、湖中仙女查验（关闭 thinking，greedy）')
    code('''
recs = {}
init = runner.run(initial_jobs(items), 'initial')
for t in ('direct', 'extract', 'reveal'):
    recs[t] = [r for r in init if r['task'] == t]
print({k: len(v) for k, v in recs.items()})
''')
    md('### 5b 开启 thinking（按 Qwen 推荐的采样参数）')
    code('''
recs['think'] = runner.run(think_jobs(items, budget=3072), 'think')
''')
    md('### 5c 求解器反馈后修正（仅对直接判断答错的题）')
    code('''
for mode in ('flag', 'evidence'):
    recs['revise_' + mode] = runner.run(revise_jobs(items, recs['direct'], smt, mode), 'revise_' + mode)
''')
    md('### 5d 评分')
    code('''
metrics = score(items, recs, smt)
metrics['manifest'] = manifest
(ROOT / 'results/llm/metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
print(json.dumps({k: {kk: v[kk] for kk in ('accuracy', 'macro_f1', 'premature_certainty', 'false_uncertainty',
                                           'missed_inconsistency', 'parse_failures') if kk in v}
                  for k, v in metrics.items() if isinstance(v, dict) and 'accuracy' in v}, ensure_ascii=False, indent=1))
print(json.dumps({k: metrics.get(k) for k in ('reveal', 'verification_pipeline', 'paired_bootstrap')}, indent=1))
''')
    md('## 6 真实对局分析（仅 CPU，约 20–40 分钟；可以在下载第 5 步结果之后再运行）')
    code('''
r = subprocess.run([sys.executable, 'avalon/analyze.py', '--parsed', 'results/audit/parsed_games.jsonl',
                    '--out', 'results/analysis', '--games', '600', '--completion-games', '150', '--backend', 'z3'],
                   capture_output=True, text=True)
print(r.stdout[-4000:], r.stderr[-2000:])
''')
    md('## 7 打包下载，然后断开并删除运行时')
    code('''
import shutil
from google.colab import files
(ROOT / 'results/COMPLETED.json').write_text(json.dumps({
    'avalonlogs_commit': COMMIT, 'tasks_sha256': manifest['tasks_sha256'],
    'records': {k: len(v) for k, v in recs.items()},
    'analysis_done': (ROOT / 'results/analysis/meta.json').exists()}, indent=2))
for big in ['results/audit/parsed_games.jsonl']:
    p = ROOT / big
    if p.exists():
        shutil.make_archive(str(ROOT / 'results/audit/parsed_games'), 'zip', p.parent, p.name)
archive = shutil.make_archive('/content/avalon_results', 'zip', ROOT, 'results')
shutil.make_archive('/content/avalon_data_llm', 'zip', ROOT, 'data/llm')
print(archive)
files.download(archive)
files.download('/content/avalon_data_llm.zip')
''')
    for i, c in enumerate(cells):
        c['id'] = f'avalon-{i:02d}'
    nb = {'nbformat': 4, 'nbformat_minor': 5,
          'metadata': {'colab': {'name': 'colab_avalon.ipynb', 'provenance': []}, 'accelerator': 'GPU',
                       'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}},
          'cells': cells}
    (ROOT / 'colab_avalon.ipynb').write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding='utf-8')
    (ROOT / 'results').mkdir(exist_ok=True)
    (ROOT / 'results' / 'notebook_assets.json').write_text(
        json.dumps({n: hashlib.sha256(x.encode()).hexdigest() for n, x in assets.items()}, indent=2), encoding='utf-8')
    print('notebook cells:', len(cells))


if __name__ == '__main__':
    main()
