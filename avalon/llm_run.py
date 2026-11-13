"""LLM experiment on frozen Avalon tasks (runs on a Colab A100).

Conditions (same items, same rule card):
  direct    : Qwen3-8B, thinking off, greedy, one-word verdict
  think     : Qwen3-8B, thinking on (sampling as recommended for thinking mode)
  extract   : the model only translates the text into the formal JSON; Z3 decides
  revise_*  : wrong direct answers get solver feedback and one more turn
              flag     = "your answer is not supported" only
              evidence = plus two consistent worlds or the minimal conflicting rules
  reveal    : for undetermined items, the model proposes Lady-of-the-Lake checks;
              scored for sufficiency (two-world test) and minimality
"""
import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from game import ZH_ROLE, ROLES, EVIL_ROLES, TEAM_SIZE, fails_required, player_label, team_label

MODEL = 'Qwen/Qwen3-8B'
REVISION = 'b968826d9c46dd6066d109eabc6255188de91218'
LABELS = ('entailed', 'contradicted', 'undetermined', 'inconsistent')
WORD = {'entailed': '成立', 'contradicted': '不成立', 'undetermined': '不确定', 'inconsistent': '矛盾'}
FROM_WORD = {v: k for k, v in WORD.items()}

RULE_CARD = '''你在分析一局《阿瓦隆》（The Resistance: Avalon）。只能依据下列规则和给出的记录做严格的逻辑推理；发言、投票倾向、"像不像"之类的策略性推测都不算证据。

【阵营与人数】好人阵营：梅林、派西维尔、亚瑟的忠臣。坏人阵营：莫甘娜、莫德雷德、奥伯伦、莫德雷德的爪牙。坏人人数：5人局2名，6人局2名，7人局3名，8人局3名，9人局3名，10人局4名。本局使用的角色在记录开头给出，每人一张。
【开局信息】每个人知道自己的角色。除奥伯伦外的坏人互相认识，他们看不到奥伯伦，奥伯伦也看不到他们。梅林能看到除莫德雷德以外的所有坏人（包括奥伯伦）。派西维尔能看到梅林和莫甘娜，但分不清谁是谁。亚瑟的忠臣和奥伯伦开局得不到任何信息。
【组队与投票】队长提名队伍，所有人公开投票，赞成票严格过半才通过（平票算否决）。每次提案后队长按座位顺序交给下一位。同一轮连续5次否决则坏人直接获胜。投票可以随意投，规则上与身份无关。各轮出队人数：5人局2,3,2,3,3；6人局2,3,4,3,4；7人局2,3,3,4,4；8至10人局3,4,4,5,5。
【执行任务】每名队员出一张任务牌：好人必须出成功；坏人可以出成功，也可以出失败。牌洗混后翻开，所有人知道失败票的张数，但不知道是谁出的。出现1张失败票任务就失败；例外：7人及以上的第4个任务需要至少2张失败票才失败。
【结束】三个任务失败则坏人获胜。三个任务成功后刺客刺杀一人：刺中梅林则坏人获胜，否则好人获胜。
【湖中仙女】持有者查验一名玩家，得知其阵营（好人或坏人），结果只有持有者本人知道。'''

TASK = '''判断给定"说法"相对于规则和记录（以及你的视角信息）的地位，只能回答一个词：
成立：在所有符合规则与记录的身份分配中，说法都为真；
不成立：在所有这样的身份分配中，说法都为假；
不确定：有的身份分配下为真，有的为假；
矛盾：记录或你的视角信息本身违反规则，不存在任何符合的身份分配。'''

ANSWER = '只输出 成立、不成立、不确定、矛盾 中的一个词，不要解释。'

EXTRACT_SYS = '''把一段《阿瓦隆》局面描述逐字转换成JSON，不做任何推理。格式：
{"n": 人数,
 "config": {角色英文名: 数量, ...}（只列出现的角色）,
 "quests": [{"q": 任务编号, "team": [座位号], "fails": 失败票张数, "result": "success"或"fail"}]（只列已执行的任务；提案和投票不需要）,
 "view": null 或 {"player": 座位号, "role": 角色英文名, "seen": [开局看到的座位号], "lady": [[被查验的座位号, 是坏人则true否则false]]},
 "claim": 说法的JSON}
说法的写法：X号一定是坏人 → {"t":"evil","p":X}；X号一定是好人 → {"t":"good","p":X}；X号一定是梅林 → {"t":"role","p":X,"r":"merlin"}；X号一定不是梅林 → {"t":"not","a":{"t":"role","p":X,"r":"merlin"}}；某些人中至少有k名坏人 → {"t":"atleast","ps":[座位号],"k":k}；某些人中恰好有k名坏人 → {"t":"exactly","ps":[座位号],"k":k}；X号和Y号一定属于同一阵营 → {"t":"same","ps":[X,Y]}；本局的坏人恰好是某些人 → {"t":"evil_set","ps":[座位号]}。
角色英文名：梅林 merlin，派西维尔 percival，亚瑟的忠臣 servant，莫甘娜 morgana，莫德雷德 mordred，奥伯伦 oberon，莫德雷德的爪牙 minion。座位号使用文字中的号码（从1开始）。旁观者视角时 view 为 null。只输出一个JSON对象，不要解释，不要Markdown。'''

EXTRACT_EXAMPLE_IN = '''6人局，角色为：梅林、派西维尔、亚瑟的忠臣×2、莫甘娜、莫德雷德的爪牙（共2名坏人）。
第1轮第1次提案：队长3号提名1号、6号，赞成者为1号、3号、6号，被否决。
第1轮第2次提案：队长4号提名2号、4号，赞成者为1号、2号、4号、5号，通过。
第1个任务由2号、4号执行，翻开1张失败票，任务失败。
你是5号，身份是派西维尔。开局时你看到1号、3号（其中一人是梅林，另一人是莫甘娜，你分不清）。
说法：2号和4号中至少有1名坏人。'''
EXTRACT_EXAMPLE_OUT = ('{"n": 6, "config": {"merlin": 1, "percival": 1, "servant": 2, "morgana": 1, "minion": 1}, '
                       '"quests": [{"q": 1, "team": [2, 4], "fails": 1, "result": "fail"}], '
                       '"view": {"player": 5, "role": "percival", "seen": [1, 3], "lady": []}, '
                       '"claim": {"t": "atleast", "ps": [2, 4], "k": 1}}')

REVEAL_Q = ('现在可以用湖中仙女查验若干玩家的阵营（每查验一人，就得知他是好人还是坏人）。'
            '请一次性给出最少需要查验的玩家，使得无论查验结果如何，都一定能判断上述说法成立还是不成立。'
            '不能查验你自己。只输出座位号的JSON数组，例如 [3, 5]，不要解释。')


def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def user_text(item):
    return item['text'] + '\n\n说法：' + item['claim_text']


def job(item, task, messages, budget, thinking=False):
    return {'id': f'{task}/{item["id"]}', 'item': item['id'], 'task': task, 'messages': messages,
            'max_new_tokens': budget, 'thinking': thinking}


def initial_jobs(items):
    jobs = []
    sys_msg = RULE_CARD + '\n\n' + TASK
    for it in items:
        base = [{'role': 'system', 'content': sys_msg}, {'role': 'user', 'content': user_text(it) + '\n' + ANSWER}]
        jobs.append(job(it, 'direct', base, 16))
        jobs.append(job(it, 'extract', [{'role': 'system', 'content': EXTRACT_SYS},
                                        {'role': 'user', 'content': EXTRACT_EXAMPLE_IN},
                                        {'role': 'assistant', 'content': EXTRACT_EXAMPLE_OUT},
                                        {'role': 'user', 'content': user_text(it)}], 768))
        if it['gold'] == 'undetermined' and (it.get('gold_reveal') or {}).get('status') == 'ok':
            jobs.append(job(it, 'reveal', [{'role': 'system', 'content': RULE_CARD},
                                           {'role': 'user', 'content': user_text(it) + '\n' + REVEAL_Q}], 64))
    return jobs


def think_jobs(items, budget=3072):
    sys_msg = RULE_CARD + '\n\n' + TASK
    return [job(it, 'think', [{'role': 'system', 'content': sys_msg},
                              {'role': 'user', 'content': user_text(it) + '\n' + ANSWER}], budget, thinking=True)
            for it in items]


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def strip_think(raw):
    return raw.split('</think>')[-1] if '</think>' in raw else raw


def parse_label(raw):
    t = strip_think(raw).strip().strip('。.`*"“”\' \n')
    if t in FROM_WORD:
        return FROM_WORD[t], 'strict'
    found = set()
    for w in ('不成立', '不确定', '矛盾'):
        if w in t:
            found.add(FROM_WORD[w])
    if '成立' in t.replace('不成立', ''):
        found.add('entailed')
    if len(found) == 1:
        return found.pop(), 'lenient'
    return 'parse_failure', None


def _json_block(raw):
    t = strip_think(raw).strip()
    t = re.sub(r'^```(?:json)?|```$', '', t.strip(), flags=re.M).strip()
    start = t.find('{') if '{' in t else t.find('[')
    if start < 0:
        raise ValueError('no json')
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(t[start:])
    return obj


def _claim_to0(c):
    c = dict(c)
    if c.get('t') in ('evil', 'good', 'role'):
        c['p'] = int(c['p']) - 1
    elif c.get('t') in ('atleast', 'exactly', 'same', 'evil_set'):
        c['ps'] = sorted(int(x) - 1 for x in c['ps'])
        if 'k' in c:
            c['k'] = int(c['k'])
    elif c.get('t') == 'not':
        c['a'] = _claim_to0(c['a'])
    else:
        raise ValueError('claim type')
    return c


def parse_extraction(raw):
    """Model JSON (1-based seats) -> (inst, claim) with 0-based seats."""
    x = _json_block(raw)
    n = int(x['n'])
    cfg = {str(k): int(v) for k, v in x['config'].items() if int(v) > 0}
    if any(k not in ROLES for k in cfg):
        raise ValueError('role name')
    quests = []
    for q in x.get('quests') or []:
        res = str(q['result']).lower()
        if res not in ('success', 'fail'):
            raise ValueError('result')
        quests.append({'q': int(q['q']), 'team': sorted(int(i) - 1 for i in q['team']),
                       'fails': None if q.get('fails') is None else int(q['fails']), 'result': res, 'proposals': []})
    v = x.get('view')
    view = None
    if v:
        view = {'player': int(v['player']) - 1, 'role': str(v['role']),
                'seen': sorted(int(i) - 1 for i in v.get('seen') or []),
                'lady': [[int(t) - 1, bool(e)] for t, e in v.get('lady') or []]}
        if view['role'] not in ROLES:
            raise ValueError('view role')
    inst = {'rec': {'n': n, 'config': cfg, 'quests': quests, 'end': None}, 'view': view}
    return inst, _claim_to0(x['claim'])


def parse_reveal(raw, cands):
    x = _json_block(raw)
    if not isinstance(x, list) or any(type(i) is not int for i in x):
        raise ValueError('not an int array')
    s = sorted(i - 1 for i in x)
    if len(set(s)) != len(s):
        raise ValueError('duplicate')
    if any(i not in cands for i in s):
        raise ValueError('not a candidate')
    return s


def gold_shape(item):
    """Extraction target: the item's formalisation without proposals."""
    rec = item['inst']['rec']
    quests = [{'q': q['q'], 'team': sorted(q['team']), 'fails': q['fails'], 'result': q['result']}
              for q in rec['quests'] if q.get('result') is not None]
    return {'n': rec['n'], 'config': {k: v for k, v in rec['config'].items() if v}, 'quests': quests,
            'view': item['inst']['view'], 'claim': item['claim']}


def shape_of(inst, claim):
    rec = inst['rec']
    return {'n': rec['n'], 'config': rec['config'],
            'quests': [{'q': q['q'], 'team': q['team'], 'fails': q['fails'], 'result': q['result']} for q in rec['quests']],
            'view': inst['view'], 'claim': claim}


def _norm_view(v):
    if v is None:
        return None
    return {'player': v['player'], 'role': v['role'], 'seen': sorted(v.get('seen') or []),
            'lady': sorted([list(map(int, x[:1])) + [bool(x[1])] for x in v.get('lady') or []])}


def _norm_claim(c):
    c = dict(c)
    if 'ps' in c:
        c['ps'] = sorted(c['ps'])
    if c.get('t') == 'not':
        c['a'] = _norm_claim(c['a'])
    return c


# ---------------------------------------------------------------------------
# solver feedback
# ---------------------------------------------------------------------------
def render_world(roles):
    return '，'.join(f'{player_label(i)}{ZH_ROLE[r]}' for i, r in enumerate(roles))


def render_core(tags, item):
    rec = item['inst']['rec']
    cfg, n = rec['config'], rec['n']
    out = []
    for tag in tags:
        rid, _, where = tag.partition('@')
        if rid.startswith('S-DEAL'):
            r = rid[rid.index('[') + 1:-1]
            out.append(f'本局{ZH_ROLE[r]}共{cfg.get(r, 0)}名')
        elif rid == 'Q-COUNT':
            q = int(where[1:])
            f = next(x['fails'] for x in rec['quests'] if x['q'] == q)
            out.append(f'第{q}个任务翻开了{f}张失败票')
        elif rid == 'Q-GOOD':
            q, i = where[1:].split(':')
            out.append(f'好人必须出成功票（第{q}个任务中的{int(i) + 1}号）')
        elif rid == 'Q-RESULT':
            q = int(where[1:])
            out.append(f'第{q}个任务需要至少{fails_required(n, q)}张失败票才算失败')
        elif rid == 'Q-SIZE':
            q = int(where[1:])
            out.append(f'第{q}个任务应由{TEAM_SIZE[n][q - 1]}人执行')
        elif rid == 'V-SELF':
            out.append('你自己的身份')
        elif rid in ('K-MERLIN', 'K-PERCIVAL', 'K-EVIL', 'K-NONE'):
            who = {'K-MERLIN': '梅林', 'K-PERCIVAL': '派西维尔', 'K-EVIL': '坏人', 'K-NONE': '该身份'}[rid]
            out.append(f'{who}的开局视野（关于{int(where) + 1}号）')
        elif rid == 'K-SELF':
            out.append('开局视野不包括自己')
        elif rid == 'K-LADY':
            out.append(f'湖中仙女对{int(where) + 1}号的查验结果')
        elif rid == 'S-COUNT':
            out.append('角色配置中的坏人数量必须符合人数表')
        else:
            out.append(f'规则{rid}' + (f'（{where}）' if where else ''))
    return '；'.join(out) + '。'


def feedback(item, answer_label, smt, mode):
    head = f'约束求解器检查了你的回答“{WORD.get(answer_label, answer_label)}”，发现它不被规则与记录支持。'
    if mode == 'flag':
        return head + '请重新判断。' + ANSWER
    res = smt.classify(item['inst'], item['claim'], explain=True)
    g = res['label']
    if g == 'undetermined':
        ev = ('下面两种身份分配都符合规则与记录：\n情形一（说法为真）：' + render_world(res['positive'])
              + '\n情形二（说法为假）：' + render_world(res['negative']))
    elif g == 'inconsistent':
        ev = '记录本身违反规则，冲突来自：' + render_core(res['core'], item)
    else:
        w = res['positive'] or res['negative']
        ev = ('存在符合规则与记录的身份分配，例如：' + render_world(w) + '\n') if answer_label == 'inconsistent' else ''
        ev += ('不存在使说法为假的身份分配' if g == 'entailed' else '不存在使说法为真的身份分配')
        ev += '，推理所需的规则与记录：' + render_core(res['core'], item)
    return head + '\n' + ev + '\n请重新判断。' + ANSWER


def revise_jobs(items, direct_records, smt, mode):
    by = {r['item']: r for r in direct_records}
    jobs = []
    sys_msg = RULE_CARD + '\n\n' + TASK
    for it in items:
        r = by[it['id']]
        lab, _ = parse_label(r['raw'])
        if lab == it['gold']:
            continue
        msgs = [{'role': 'system', 'content': sys_msg},
                {'role': 'user', 'content': user_text(it) + '\n' + ANSWER},
                {'role': 'assistant', 'content': r['raw'].strip() or '（无输出）'},
                {'role': 'user', 'content': feedback(it, lab, smt, mode)}]
        jobs.append(job(it, 'revise_' + mode, msgs, 16))
    return jobs


# ---------------------------------------------------------------------------
# model runner
# ---------------------------------------------------------------------------
class Runner:
    def __init__(self, out_dir, batch_size=None):
        import torch
        import transformers
        import platform
        from transformers import AutoTokenizer, AutoModelForCausalLM
        assert torch.cuda.is_available() and torch.cuda.is_bf16_supported(), 'Need a BF16-capable CUDA GPU runtime'
        self.torch = torch
        mem = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
        self.batch = batch_size or (16 if mem > 60 else 8)
        self.tok = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, padding_side='left')
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(MODEL, revision=REVISION, torch_dtype=torch.bfloat16,
                                                          attn_implementation='sdpa').to('cuda').eval()
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.meta = {'model': MODEL, 'revision': REVISION, 'gpu': torch.cuda.get_device_name(0),
                     'gpu_mem_gib': round(mem, 1), 'python': platform.python_version(), 'torch': torch.__version__,
                     'transformers': transformers.__version__, 'dtype': 'bfloat16', 'batch_size': self.batch,
                     'greedy_when_thinking_off': True,
                     'thinking_sampling': {'temperature': 0.6, 'top_p': 0.95, 'top_k': 20},
                     'seed': 42, 'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (self.out / 'runner_metadata.json').write_text(json.dumps(self.meta, indent=2), encoding='utf-8')

    def run(self, jobs, name, batch_size=None):
        """A job may carry 'prefix': text appended after the chat template's generation prompt
        (used by followup.py to continue or budget-force a thinking trace)."""
        meta = {'jobs_sha256': digest(jobs), 'n': len(jobs)}
        mp, rp = self.out / f'{name}_metadata.json', self.out / f'{name}_records.jsonl'
        if mp.exists():
            assert json.loads(mp.read_text()) == meta, 'resume mismatch: use a new name'
        else:
            mp.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        (self.out / f'{name}_jobs.json').write_text(json.dumps(jobs, ensure_ascii=False), encoding='utf-8')
        records = [json.loads(x) for x in rp.read_text(encoding='utf-8').splitlines() if x.strip()] if rp.exists() else []
        done = {r['id'] for r in records}
        groups = sorted({(j['max_new_tokens'], j['thinking']) for j in jobs})
        for budget, thinking in groups:
            todo = [j for j in jobs if j['id'] not in done and j['max_new_tokens'] == budget and j['thinking'] == thinking]
            bs = batch_size or (self.batch if budget <= 1024 else max(4, self.batch))
            for b0 in range(0, len(todo), bs):
                batch = todo[b0:b0 + bs]
                texts = [self.tok.apply_chat_template(j['messages'], tokenize=False, add_generation_prompt=True,
                                                      enable_thinking=thinking) + j.get('prefix', '') for j in batch]
                enc = self.tok(texts, return_tensors='pt', padding=True).to('cuda')
                kw = dict(max_new_tokens=budget, pad_token_id=self.tok.pad_token_id)
                if thinking:
                    self.torch.manual_seed(42 + b0)
                    kw.update(do_sample=True, temperature=0.6, top_p=0.95, top_k=20)
                else:
                    kw.update(do_sample=False)
                self.torch.cuda.synchronize()
                t0 = time.perf_counter()
                with self.torch.inference_mode():
                    out = self.model.generate(**enc, **kw)
                self.torch.cuda.synchronize()
                sec = time.perf_counter() - t0
                gen = out[:, enc.input_ids.shape[1]:]
                dec = self.tok.batch_decode(gen, skip_special_tokens=True)
                with rp.open('a', encoding='utf-8') as f:
                    for j, raw, ids in zip(batch, dec, gen):
                        ids = ids.tolist()
                        eos = self.tok.eos_token_id
                        row = {'id': j['id'], 'item': j['item'], 'task': j['task'], 'raw': raw,
                               'output_tokens': ids.index(eos) + 1 if eos in ids else len(ids),
                               'hit_limit': eos not in ids, 'batch_seconds': sec, 'batch_size': len(batch),
                               'input_tokens': int(enc.input_ids.shape[1])}
                        f.write(json.dumps(row, ensure_ascii=False) + '\n')
                        records.append(row)
                print(f'{name} budget={budget} think={thinking}: {b0 + len(batch)}/{len(todo)} {sec:.1f}s', flush=True)
        assert len({r['id'] for r in records}) == len(jobs)
        return records


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def cls_metrics(rows):
    n = len(rows)
    conf = {g: Counter() for g in LABELS}
    for r in rows:
        conf[r['gold']][r['pred']] += 1
    f1 = []
    for k in LABELS:
        tp = conf[k][k]
        fp = sum(conf[g][k] for g in LABELS if g != k)
        fn = sum(v for p, v in conf[k].items() if p != k)
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    und = [r for r in rows if r['gold'] == 'undetermined']
    dec = [r for r in rows if r['gold'] in ('entailed', 'contradicted')]
    inc = [r for r in rows if r['gold'] == 'inconsistent']
    return {'n': n, 'accuracy': sum(r['gold'] == r['pred'] for r in rows) / n if n else None,
            'macro_f1': sum(f1) / 4, 'f1': dict(zip(LABELS, f1)),
            'confusion': {g: dict(c) for g, c in conf.items()},
            'premature_certainty': [sum(r['pred'] in ('entailed', 'contradicted') for r in und), len(und)],
            'false_uncertainty': [sum(r['pred'] == 'undetermined' for r in dec), len(dec)],
            'missed_inconsistency': [sum(r['pred'] != 'inconsistent' for r in inc), len(inc)],
            'false_inconsistency': [sum(r['pred'] == 'inconsistent' for r in rows if r['gold'] != 'inconsistent'),
                                    sum(r['gold'] != 'inconsistent' for r in rows)],
            'parse_failures': sum(r['pred'] == 'parse_failure' for r in rows)}


def bootstrap_diff(a, b, seed=271, reps=2000):
    """Paired bootstrap over items of mean(b) - mean(a); a, b are 0/1 lists."""
    rng = random.Random(seed)
    n = len(a)
    diffs = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(b[i] - a[i] for i in idx) / n)
    diffs.sort()
    return {'diff': sum(b[i] - a[i] for i in range(n)) / n, 'ci95': [diffs[int(0.025 * reps)], diffs[int(0.975 * reps) - 1]]}


def strata(items):
    def pkind(p):
        return 'observer' if p == 'observer' else ('evil_view' if p in EVIL_ROLES else 'good_view')
    return {it['id']: {'perspective': pkind(it['perspective']), 'claim': it['claim']['t'],
                       'n': it['inst']['rec']['n'], 'corruption': it.get('corruption') or '-'} for it in items}


def score(items, recs, smt):
    by = defaultdict(dict)
    for task, rr in recs.items():
        for r in rr:
            by[task][r['item']] = r
    st = strata(items)
    out, correct = {}, {}
    for task in ('direct', 'think'):
        if task not in by:
            continue
        rows = []
        for it in items:
            lab, mode = parse_label(by[task][it['id']]['raw'])
            rows.append({'id': it['id'], 'gold': it['gold'], 'pred': lab, 'mode': mode})
        m = cls_metrics(rows)
        m['lenient_parses'] = sum(r['mode'] == 'lenient' for r in rows)
        m['hit_token_limit'] = sum(by[task][it['id']].get('hit_limit', False) for it in items)
        m['mean_output_tokens'] = sum(by[task][it['id']]['output_tokens'] for it in items) / len(items)
        m['by'] = {k: {v: cls_metrics([r for r in rows if st[r['id']][k] == v])['accuracy']
                       for v in sorted({s[k] for s in st.values()}, key=str)} for k in ('perspective', 'claim', 'n')}
        out[task] = m
        correct[task] = [int(r['gold'] == r['pred']) for r in rows]
    # extraction + solver
    if 'extract' in by:
        rows, ex = [], Counter()
        for it in items:
            raw = by['extract'][it['id']]['raw']
            try:
                inst, claim = parse_extraction(raw)
                ex['valid_json'] += 1
                gs, ps = gold_shape(it), shape_of(inst, claim)
                ex['n_ok'] += gs['n'] == ps['n']
                ex['config_ok'] += gs['config'] == ps['config']
                ex['quests_ok'] += gs['quests'] == ps['quests']
                ex['view_ok'] += _norm_view(gs['view']) == _norm_view(ps['view'])
                ex['claim_ok'] += _norm_claim(gs['claim']) == _norm_claim(ps['claim'])
                exact = (gs['n'] == ps['n'] and gs['config'] == ps['config'] and gs['quests'] == ps['quests']
                         and _norm_view(gs['view']) == _norm_view(ps['view']) and _norm_claim(gs['claim']) == _norm_claim(ps['claim']))
                ex['exact'] += exact
                try:
                    lab = smt.classify(inst, claim)['label']
                except Exception:
                    lab = 'parse_failure'
                    ex['solver_error'] += 1
            except Exception:
                lab = 'parse_failure'
            rows.append({'id': it['id'], 'gold': it['gold'], 'pred': lab})
        m = cls_metrics(rows)
        m['extraction'] = dict(ex)
        m['by'] = {k: {v: cls_metrics([r for r in rows if st[r['id']][k] == v])['accuracy']
                       for v in sorted({s[k] for s in st.values()}, key=str)} for k in ('perspective', 'claim', 'n')}
        out['extract_solve'] = m
        correct['extract_solve'] = [int(r['gold'] == r['pred']) for r in rows]
    # revision with solver feedback (only wrong direct answers were re-asked)
    for mode in ('flag', 'evidence'):
        t = 'revise_' + mode
        if t not in by:
            continue
        rows, fixed = [], 0
        for it in items:
            lab, _ = parse_label(by['direct'][it['id']]['raw'])
            if lab != it['gold']:
                lab2, _ = parse_label(by[t][it['id']]['raw'])
                fixed += lab2 == it['gold']
                lab = lab2
            rows.append({'id': it['id'], 'gold': it['gold'], 'pred': lab})
        m = cls_metrics(rows)
        m['reasked'] = len(by[t])
        m['fixed'] = fixed
        out[t] = m
        correct[t] = [int(r['gold'] == r['pred']) for r in rows]
    # reveal selection
    if 'reveal' in by:
        from search import candidates
        rv = Counter()
        excess = []
        for it in items:
            if it['id'] not in by['reveal']:
                continue
            rv['n'] += 1
            cands = candidates(it['inst'])
            try:
                S = parse_reveal(by['reveal'][it['id']]['raw'], cands)
            except Exception:
                rv['invalid'] += 1
                continue
            suff = smt.find_pair(it['inst'], it['claim'], S) is None
            rv['sufficient'] += suff
            gsize = it['gold_reveal']['size']
            if suff:
                rv['optimal'] += len(S) == gsize
                excess.append(len(S) - gsize)
            rv['all_candidates_chosen'] += len(S) == len(cands)
        out['reveal'] = {**rv, 'mean_excess_when_sufficient': sum(excess) / len(excess) if excess else None,
                         'gold_total': sum(it['gold_reveal']['size'] for it in items if it['id'] in by['reveal'])}
    # end-to-end verification of direct answers with the model's own formalisation
    if 'direct' in by and 'extract' in by:
        flagged_wrong = flagged_right = wrong = right = 0
        for it in items:
            lab, _ = parse_label(by['direct'][it['id']]['raw'])
            try:
                inst, claim = parse_extraction(by['extract'][it['id']]['raw'])
                verdict = smt.classify(inst, claim)['label']
            except Exception:
                verdict = None
            flag = verdict is not None and verdict != lab
            if lab == it['gold']:
                right += 1
                flagged_right += flag
            else:
                wrong += 1
                flagged_wrong += flag
        out['verification_pipeline'] = {'direct_wrong': wrong, 'wrong_flagged': flagged_wrong,
                                         'direct_right': right, 'right_flagged': flagged_right}
    comps = {}
    for t in ('think', 'extract_solve', 'revise_flag', 'revise_evidence'):
        if t in correct and 'direct' in correct:
            comps[f'{t}_minus_direct'] = bootstrap_diff(correct['direct'], correct[t])
    out['paired_bootstrap'] = comps
    return out
