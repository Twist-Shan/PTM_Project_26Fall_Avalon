"""Build the follow-up Colab notebook and its input package (protocol: CODEX_FOLLOWUP.md).

  python avalon/build_followup_colab.py
    -> colab_avalon_followup.ipynb          (code embedded; small)
    -> avalon_followup_inputs.zip           (frozen tasks + first-run records; upload to Colab)

The notebook does not clone avalonlogs and does not rebuild the task set: it reuses the
frozen tasks.jsonl (sha256 checked against the manifest) and the first run's records.
"""
import ast
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ['avalon/game.py', 'avalon/smt.py', 'avalon/search.py', 'avalon/oracle.py', 'avalon/llm_run.py',
        'avalon/followup.py']
BASE = ROOT / 'results/colab_run'
INPUTS = ['data/llm/tasks.jsonl', 'data/llm/manifest.json',
          'results/llm/initial_records.jsonl', 'results/llm/initial_metadata.json',
          'results/llm/think_records.jsonl', 'results/llm/think_metadata.json', 'results/llm/metrics.json']
INPUT_ZIP = ROOT / 'avalon_followup_inputs.zip'

cells = []


def md(s):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': s.strip().splitlines(True)})


def code(s):
    ast.parse(s)
    cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
                  'source': s.strip().splitlines(True)})


def build_inputs():
    manifest = json.loads((BASE / 'data/llm/manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((BASE / 'data/llm/tasks.jsonl').read_bytes()).hexdigest() == manifest['tasks_sha256']
    with zipfile.ZipFile(INPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in INPUTS:
            info = zipfile.ZipInfo('base/' + rel, date_time=(2026, 11, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, (BASE / rel).read_bytes())
    return hashlib.sha256(INPUT_ZIP.read_bytes()).hexdigest(), manifest['tasks_sha256']


def main():
    inputs_sha, tasks_sha = build_inputs()
    assets = {n: (ROOT / n).read_text(encoding='utf-8') for n in CODE}
    md('''
# 阿瓦隆后续实验：thinking 预算、真实验证流水线、抽取修复（Qwen3-8B）

按顺序运行全部单元。说明见项目里的 `CODEX_FOLLOWUP.md`。

- 不克隆 avalonlogs，不重建题集：复用冻结的 510 题和第一次运行的 direct / extract / think 原始输出。
- 第 3 节需要上传 `avalon_followup_inputs.zip`（如果左侧文件面板里还没有）。
- 第 5 节（便宜，约 15 分钟）结束、第 6 节结束、全部结束时各打包一次；每次都尽量下载，自动下载失败就从文件面板手动下载。
- 模型输出逐批落盘。同一运行时内中断后，从第 2 节开始重新运行即可续跑，已完成的批次不会重算。
''')
    md('## 1 环境与 GPU')
    code('''
import subprocess, sys
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'z3-solver==4.16.0.0',
                       'transformers==4.57.6', 'safetensors>=0.4.3'])
import torch
assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(), '请选择支持 BF16 的 CUDA GPU'
MEM = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
print(torch.cuda.get_device_name(0), round(MEM, 1), 'GiB')
assert MEM >= 40, '显存不足 40 GiB：请换 A100 80GB / H100 / RTX PRO 6000 等大显存的卡'
''')
    md('## 2 写入代码')
    code('''
import json, os, hashlib, zipfile, shutil
from pathlib import Path
ROOT = Path('/content/avalon_followup')
ROOT.mkdir(exist_ok=True)
ASSETS = json.loads(''' + repr(json.dumps(assets, ensure_ascii=False)) + ''')
for name, content in ASSETS.items():
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
sys.path.insert(0, str(ROOT / 'avalon'))
os.chdir(ROOT)
print('code files:', len(ASSETS))
''')
    md('## 3 输入包：校验、冻结提示词检查、复现第一次运行的评分（不调用模型）')
    code('''
INPUTS_SHA = ''' + repr(inputs_sha) + '''
TASKS_SHA = ''' + repr(tasks_sha) + '''
zp = Path('/content/avalon_followup_inputs.zip')
if not zp.exists():
    from google.colab import files
    up = files.upload()   # 选择 avalon_followup_inputs.zip
    zp.write_bytes(next(iter(up.values())))
assert hashlib.sha256(zp.read_bytes()).hexdigest() == INPUTS_SHA, '输入包校验失败：请上传本次生成的 avalon_followup_inputs.zip'
with zipfile.ZipFile(zp) as z:
    z.extractall(ROOT)
assert hashlib.sha256((ROOT / 'base/data/llm/tasks.jsonl').read_bytes()).hexdigest() == TASKS_SHA
from followup import *
from smt import SMT
smt = SMT()
items, base, meta, original = load_base(ROOT / 'base')
assert check_frozen(items, meta['initial'], meta['think'])
b = blind(items)
direct, extract = by_item(base['initial'], 'direct'), by_item(base['initial'], 'extract')
traces = initial_traces(base['think'])
dry = score_followup(items, base, {}, smt, original)   # asserts the first run's accuracies are reproduced
print(json.dumps(dry['reproduced_first_run'], indent=1))
print('items', len(items), '| thinking traces cut at 3072:', sum(t['hit_limit'] for t in traces.values()),
      '| solver_final accuracy:', round(dry['solver_final']['accuracy'], 4))
''')
    md('''
## 3b 仅在运行时被回收后使用：从已下载的阶段结果续跑

正常流程直接运行即可（会显示“无需恢复”）。如果运行时被回收，在新运行时里先把最近一次下载的
`avalon_followup_stage*.zip` 上传到 `/content`，再从第 1 节依次运行；已完成的阶段不会重算。
''')
    code('''
RES = ROOT / 'results_followup'
_cands = sorted(Path('/content').glob('avalon_followup_stage*.zip'))
if not RES.exists() and _cands:
    with zipfile.ZipFile(_cands[-1]) as z:
        z.extractall(ROOT)
    print('restored from', _cands[-1], sorted(p.name for p in (RES / 'llm').glob('*_records.jsonl')))
else:
    print('无需恢复')
''')
    md('## 4 加载同一 revision 的 Qwen3-8B')
    code('''
from llm_run import Runner
runner = Runner('results_followup/llm')
_t = runner.tok.apply_chat_template([{'role': 'user', 'content': 'x'}], tokenize=False,
                                    add_generation_prompt=True, enable_thinking=True)
assert _t.endswith('<|im_start|>assistant\\n'), repr(_t[-80:])
NEW = {}
def run(jobs, name, **kw):
    NEW[name] = runner.run(jobs, name, **kw)
    print(name, ':', len(jobs), 'jobs done', flush=True)

def pack(tag):
    from google.colab import files
    out = ROOT / 'results_followup'
    m = score_followup(items, base, NEW, smt, original)
    (out / 'metrics_followup.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'STATUS.json').write_text(json.dumps({'stage': tag, 'inputs_sha256': INPUTS_SHA, 'tasks_sha256': TASKS_SHA,
                                                 'records': {k: len(v) for k, v in NEW.items()}}, indent=2))
    print(json.dumps(main_table(m), ensure_ascii=False, indent=1))
    print(json.dumps(m['think_budget_table'], indent=1))
    archive = Path(f'/content/avalon_followup_{tag}.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file() and not p.name.endswith('_jobs.json'):   # jobs are rebuilt deterministically
                z.write(p, p.relative_to(ROOT))
    print(archive, archive.stat().st_size, 'bytes, sha256', hashlib.sha256(archive.read_bytes()).hexdigest())
    try:
        files.download(str(archive))
    except Exception as e:
        print('自动下载失败，请从左侧文件面板手动下载', archive, e)
print(json.dumps(runner.meta, indent=1))
''')
    md('## 5 真实验证流水线与抽取修复（关闭 thinking，greedy；约 15 分钟）')
    code('''
forms = formalise_all(b, extract, smt)
run(verify_jobs(b, direct, forms, smt, 'flag', 'verify_flag'), 'verify_flag')
run(verify_jobs(b, direct, forms, smt, 'evidence', 'verify_evidence'), 'verify_evidence')
run(repair_jobs(b, extract, forms, smt), 'extract_repair')
forms_r = repaired_forms(b, forms, by_item(NEW['extract_repair']), smt)
run(verify_jobs(b, direct, forms_r, smt, 'evidence', 'verify_evidence_repaired'), 'verify_evidence_repaired')
pack('stage1')
''')
    md('## 6 thinking：3072 处强制作答，续写到 8192 并强制作答（约 1–2 小时）')
    code('''
BS8 = batch_size_for(MEM, 1800 + 8192 + 64)
BS16 = batch_size_for(MEM, 1800 + 16384 + 64)
print('batch sizes: 8192 ->', BS8, '| 16384 ->', BS16)
run(force_jobs(b, traces, 'think_force3072'), 'think_force3072', batch_size=BS8)
run(continue_jobs(b, traces, 8192, 'think_cont8192'), 'think_cont8192', batch_size=BS8)
tr8 = extend(traces, NEW['think_cont8192'])
run(force_jobs(b, tr8, 'think_force8192'), 'think_force8192', batch_size=BS8)
print('unfinished at 8192:', sum(t['hit_limit'] for t in tr8.values()))
pack('stage2')
''')
    md('## 7 thinking：仍未结束的续写到 16384 并强制作答（时长取决于剩余条数）')
    code('''
run(continue_jobs(b, tr8, 16384, 'think_cont16384'), 'think_cont16384', batch_size=BS16)
tr16 = extend(tr8, NEW['think_cont16384'])
run(force_jobs(b, tr16, 'think_force16384'), 'think_force16384', batch_size=BS16)
print('unfinished at 16384:', sum(t['hit_limit'] for t in tr16.values()))
''')
    md('## 8 最终评分与打包（下载后断开并删除运行时）')
    code('''
pack('final')
''')
    for i, c in enumerate(cells):
        c['id'] = f'followup-{i:02d}'
    nb = {'nbformat': 4, 'nbformat_minor': 5,
          'metadata': {'colab': {'name': 'colab_avalon_followup.ipynb', 'provenance': []}, 'accelerator': 'GPU',
                       'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}},
          'cells': cells}
    out = ROOT / 'colab_avalon_followup.ipynb'
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding='utf-8')
    print('notebook:', out.name, len(cells), 'cells,', out.stat().st_size, 'bytes')
    print('inputs:', INPUT_ZIP.name, INPUT_ZIP.stat().st_size, 'bytes, sha256', inputs_sha)


if __name__ == '__main__':
    main()
