"""Follow-up experiments on the frozen Avalon task set (protocol: CODEX_FOLLOWUP.md).

Re-uses the first run's records (direct / extract / think@3072) unchanged and adds:

  think budget    Every thinking trace cut off at 3072 new tokens is *continued* from its own
                  text up to 8192, then (if still unfinished) 16384 new tokens in total.
                  Sampling just carries on from the same prefix, so a continued trace is a
                  sample of what one run with the larger budget would have produced; traces
                  that already finished are unchanged.  At every budget, traces that are still
                  unfinished are additionally budget-forced (close </think>, ask for the verdict).
  verify_*        The realistic pipeline (no gold label is read anywhere): re-ask only when the
                  direct answer disagrees with Z3 run on the model's OWN extraction, with the
                  feedback computed from that extraction ('flag' or 'evidence').
  extract_repair  Logic-LM style: when Z3 finds the model's extraction unsatisfiable (or it
                  cannot be used), show the conflicting clauses once and ask for a re-check.
  verify_evidence_repaired   verify_evidence on top of the repaired extraction.

Job builders only ever receive blind(items): gold labels, true roles and gold reveal sets removed.

  python avalon/followup.py --selftest                  # local, no GPU: prompts, job counts, scorer
  python avalon/followup.py --score --base DIR --new DIR --out FILE
"""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from llm_run import (RULE_CARD, TASK, ANSWER, EXTRACT_SYS, EXTRACT_EXAMPLE_IN, EXTRACT_EXAMPLE_OUT, LABELS,
                     user_text, job, think_jobs, initial_jobs, parse_label, parse_extraction, feedback, render_core,
                     cls_metrics, bootstrap_diff, gold_shape, shape_of, _norm_view, _norm_claim, digest, score)

BUDGETS = (3072, 8192, 16384)
FORCE = '\n\n考虑到思考时间有限，我现在必须根据已有的思考直接给出最终答案。\n</think>\n\n'
FORCE_TOKENS = 16
HIDDEN = ('gold', 'true_roles', 'gold_reveal')
SYS = RULE_CARD + '\n\n' + TASK
KV_GIB_PER_TOKEN = 2 * 36 * 8 * 128 * 2 / 2 ** 30   # Qwen3-8B: 36 layers, 8 KV heads, dim 128, bf16


def blind(items):
    return [{k: v for k, v in it.items() if k not in HIDDEN} for it in items]


def by_item(records, task=None):
    return {r['item']: r for r in records if task is None or r['task'] == task}


def read_jsonl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines() if x.strip()]


def batch_size_for(mem_gib, max_context):
    """Largest safe batch for long thinking continuations (KV cache + 18 GiB for weights/overhead)."""
    per_seq = max_context * KV_GIB_PER_TOKEN
    return max(1, min(32, int(0.6 * (mem_gib - 18) / per_seq)))


# ---------------------------------------------------------------------------
# frozen prompts
# ---------------------------------------------------------------------------
def extract_messages(it):
    """Identical to the 'extract' job of llm_run.initial_jobs (checked in check_frozen)."""
    return [{'role': 'system', 'content': EXTRACT_SYS},
            {'role': 'user', 'content': EXTRACT_EXAMPLE_IN},
            {'role': 'assistant', 'content': EXTRACT_EXAMPLE_OUT},
            {'role': 'user', 'content': user_text(it)}]


def check_frozen(items, initial_meta, think_meta):
    """The first run's prompts are reproduced byte for byte (same job digests)."""
    ij = initial_jobs(items)
    assert digest(ij) == initial_meta['jobs_sha256'], 'initial prompts differ from the first run'
    assert digest(think_jobs(items, budget=3072)) == think_meta['jobs_sha256'], 'thinking prompts differ'
    em = {j['item']: j['messages'] for j in ij if j['task'] == 'extract'}
    assert all(extract_messages(it) == em[it['id']] for it in blind(items))
    return True


# ---------------------------------------------------------------------------
# the model's own formalisation
# ---------------------------------------------------------------------------
def formalise(raw, smt):
    """Extraction text -> {'inst', 'claim', 'label'}; 'label' is missing when Z3 cannot use it."""
    try:
        inst, claim = parse_extraction(raw)
    except Exception as e:
        return {'error': 'parse:' + type(e).__name__}
    try:
        return {'inst': inst, 'claim': claim, 'label': smt.classify(inst, claim)['label']}
    except Exception as e:
        return {'inst': inst, 'claim': claim, 'error': 'solver:' + type(e).__name__}


def formalise_all(bitems, extract, smt):
    return {it['id']: formalise(extract[it['id']]['raw'], smt) for it in bitems}


def verify_jobs(bitems, direct, forms, smt, mode, task):
    """Re-ask only where the direct answer disagrees with Z3 on the model's own extraction."""
    jobs = []
    for it in bitems:
        lab, _ = parse_label(direct[it['id']]['raw'])
        f = forms[it['id']]
        if 'label' not in f or f['label'] == lab:
            continue
        fb = feedback({'inst': f['inst'], 'claim': f['claim']}, lab, smt, mode)
        msgs = [{'role': 'system', 'content': SYS},
                {'role': 'user', 'content': user_text(it) + '\n' + ANSWER},
                {'role': 'assistant', 'content': direct[it['id']]['raw'].strip() or '（无输出）'},
                {'role': 'user', 'content': fb}]
        jobs.append(job(it, task, msgs, 16))
    return jobs


EXTRA_CLAUSE = {
    'S-SIZE': '人数必须在5到10之间',
    'S-TOTAL': '角色配置的总人数必须等于玩家人数',
    'S-UNIQUE': '梅林、派西维尔、莫甘娜、莫德雷德、奥伯伦各至多一名',
    'R-ORDER': '任务必须按第1、2、3……个的顺序记录',
    'G-END': '三个任务成功或三个任务失败后游戏结束，之后不再有任务',
}
REPAIR_TAIL = ('请逐项对照原文检查你的转写：人数、角色配置、每个任务的队员、失败票张数和结果、你的视角信息、说法。'
               '如果转写有误，输出改正后的完整JSON；如果转写与原文一致（也就是原文记录本身违反规则），就原样输出同一个JSON。'
               '只输出一个JSON对象，不要解释，不要Markdown。')


def render_core_ext(tags, inst):
    item, parts = {'inst': inst}, []
    for tag in tags:
        rid, _, where = tag.partition('@')
        if rid in EXTRA_CLAUSE:
            parts.append(EXTRA_CLAUSE[rid] + (f'（{where}）' if where else ''))
            continue
        try:
            parts.append(render_core([tag], item).rstrip('。'))
        except Exception:
            parts.append(f'规则{tag}')
    return '；'.join(parts) + '。'


def repair_feedback(f, smt):
    if 'inst' not in f:
        return '你的输出无法解析为要求格式的JSON。' + REPAIR_TAIL
    if 'label' not in f:
        return '你的JSON中有约束求解器无法处理的内容（例如超出人数范围的座位号）。' + REPAIR_TAIL
    core = smt.classify(f['inst'], f['claim'], explain=True)['core']
    return ('把你的JSON交给约束求解器后，发现不存在任何符合规则的身份分配。冲突来自：'
            + render_core_ext(core, f['inst']) + '\n' + REPAIR_TAIL)


def repair_jobs(bitems, extract, forms, smt):
    jobs = []
    for it in bitems:
        f = forms[it['id']]
        if f.get('label') not in (None, 'inconsistent'):
            continue
        msgs = extract_messages(it) + [
            {'role': 'assistant', 'content': extract[it['id']]['raw'].strip() or '（无输出）'},
            {'role': 'user', 'content': repair_feedback(f, smt)}]
        jobs.append(job(it, 'extract_repair', msgs, 768))
    return jobs


def repaired_forms(bitems, forms, repair, smt):
    """A repair that does not parse as JSON keeps the original extraction (fixed in advance)."""
    out = {}
    for it in bitems:
        r = repair.get(it['id'])
        g = formalise(r['raw'], smt) if r else None
        out[it['id']] = g if g is not None and 'inst' in g else forms[it['id']]
    return out


# ---------------------------------------------------------------------------
# thinking budget: continuation and budget forcing
# ---------------------------------------------------------------------------
def initial_traces(think_records):
    return {r['item']: {'raw': r['raw'], 'tokens': r['output_tokens'], 'hit_limit': r['hit_limit']}
            for r in think_records}


def _think_messages(bitems):
    return {j['item']: j['messages'] for j in think_jobs(bitems)}


def continue_jobs(bitems, traces, budget, task):
    msgs, jobs = _think_messages(bitems), []
    for it in bitems:
        t = traces[it['id']]
        if not t['hit_limit']:
            continue
        assert t['tokens'] < budget
        j = job(it, task, msgs[it['id']], budget - t['tokens'], thinking=True)
        j['prefix'] = t['raw'].rstrip('�')   # drop a dangling partial UTF-8 character
        jobs.append(j)
    return jobs


def extend(traces, records):
    out = dict(traces)
    for r in records:
        t = traces[r['item']]
        out[r['item']] = {'raw': t['raw'].rstrip('�') + r['raw'], 'tokens': t['tokens'] + r['output_tokens'],
                          'hit_limit': r['hit_limit']}
    return out


def force_prefix(raw):
    raw = raw.rstrip('�')
    return raw if '</think>' in raw else raw + FORCE


def force_jobs(bitems, traces, task):
    msgs, jobs = _think_messages(bitems), []
    for it in bitems:
        t = traces[it['id']]
        if not t['hit_limit']:
            continue
        j = job(it, task, msgs[it['id']], FORCE_TOKENS, thinking=True)
        j['prefix'] = force_prefix(t['raw'])
        jobs.append(j)
    return jobs


def parse_think(raw):
    """Thinking-mode verdict: only text after </think> counts (an unfinished trace is a parse failure)."""
    if '</think>' not in raw:
        return 'parse_failure', None
    return parse_label(raw)


def think_traces(base_think, new):
    """traces[B] and forced[B] (item -> full forced text) for every budget."""
    traces = {BUDGETS[0]: initial_traces(base_think)}
    for prev, b in zip(BUDGETS, BUDGETS[1:]):
        traces[b] = extend(traces[prev], new.get(f'think_cont{b}', []))
    forced = {}
    for b in BUDGETS:
        forced[b] = {r['item']: force_prefix(traces[b][r['item']]['raw']) + r['raw']
                     for r in new.get(f'think_force{b}', [])}
    return traces, forced


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def extraction_quality(items, forms):
    q = Counter()
    for it in items:
        f = forms[it['id']]
        if 'inst' not in f:
            continue
        gs, ps = gold_shape(it), shape_of(f['inst'], f['claim'])
        ok = {'n_ok': gs['n'] == ps['n'], 'config_ok': gs['config'] == ps['config'],
              'quests_ok': gs['quests'] == ps['quests'],
              'view_ok': _norm_view(gs['view']) == _norm_view(ps['view']),
              'claim_ok': _norm_claim(gs['claim']) == _norm_claim(ps['claim'])}
        q['valid_json'] += 1
        for k, v in ok.items():
            q[k] += v
        q['exact'] += all(ok.values())
    return dict(q)


def _verify_condition(items, direct, forms, recs):
    rows, s = [], Counter()
    for it in items:
        d, _ = parse_label(direct[it['id']]['raw'])
        pred = d
        if it['id'] in recs:
            v = forms[it['id']]['label']
            pred, _ = parse_label(recs[it['id']]['raw'])
            s['reasked'] += 1
            s['fixed'] += d != it['gold'] and pred == it['gold']
            s['broken'] += d == it['gold'] and pred != it['gold']
            s['followed_solver'] += pred == v
            s['kept_own_answer'] += pred == d
            key = 'solver_right' if v == it['gold'] else 'solver_wrong'
            s[key] += 1
            s['followed_when_' + key] += pred == v
        rows.append({'id': it['id'], 'gold': it['gold'], 'pred': pred})
    m = cls_metrics(rows)
    m.update({k: s[k] for k in ('reasked', 'fixed', 'broken', 'followed_solver', 'kept_own_answer', 'solver_right',
                                'followed_when_solver_right', 'solver_wrong', 'followed_when_solver_wrong')})
    return m, rows


def score_followup(items, base, new, smt, original_metrics=None):
    """base: {'initial': records, 'think': records} from the first run; new: task -> records."""
    b = blind(items)
    direct, extract = by_item(base['initial'], 'direct'), by_item(base['initial'], 'extract')
    out, correct = {}, {}

    def put(name, rows, extra=None):
        m = cls_metrics(rows)
        m.update(extra or {})
        out[name] = m
        correct[name] = [int(r['gold'] == r['pred']) for r in rows]

    # reproduction of the first run (same scorer)
    rep = score(items, {'direct': list(direct.values()), 'think': base['think'], 'extract': list(extract.values())},
                smt)
    out['reproduced_first_run'] = {k: {'accuracy': rep[k]['accuracy'], 'macro_f1': rep[k]['macro_f1']}
                                   for k in ('direct', 'think', 'extract_solve')}
    if original_metrics:
        for k, v in out['reproduced_first_run'].items():
            assert abs(v['accuracy'] - original_metrics[k]['accuracy']) < 1e-12, k
    put('direct', [{'id': it['id'], 'gold': it['gold'], 'pred': parse_label(direct[it['id']]['raw'])[0]}
                   for it in items])

    # thinking at three budgets, strict and budget-forced
    traces, forced = think_traces(base['think'], new)
    budget_table = {}
    for B in BUDGETS:
        tr = traces[B]
        strict = [{'id': it['id'], 'gold': it['gold'], 'pred': parse_think(tr[it['id']]['raw'])[0]} for it in items]
        put(f'think{B}_strict', strict)
        unfinished = [it['id'] for it in items if tr[it['id']]['hit_limit']]
        info = {'unfinished': len(unfinished), 'mean_tokens': sum(tr[i]['tokens'] for i in tr) / len(tr)}
        if all(i in forced[B] for i in unfinished):
            rows = [{'id': r['id'], 'gold': r['gold'],
                     'pred': parse_think(forced[B][r['id']])[0] if r['id'] in forced[B] else r['pred']}
                    for r in strict]
            put(f'think{B}_forced', rows, {'forced': len(unfinished)})
            info['forced_accuracy'] = out[f'think{B}_forced']['accuracy']
        else:
            info['forced_accuracy'] = None   # stage not run yet
        info['strict_accuracy'] = out[f'think{B}_strict']['accuracy']
        info['strict_parse_failures'] = out[f'think{B}_strict']['parse_failures']
        budget_table[B] = info
    out['think_budget_table'] = budget_table

    # extraction + Z3, before and after one repair round
    forms = formalise_all(b, extract, smt)
    put('extract_solve', [{'id': it['id'], 'gold': it['gold'], 'pred': forms[it['id']].get('label', 'parse_failure')}
                          for it in items], {'extraction': extraction_quality(items, forms)})
    if 'extract_repair' in new:
        rep_recs = by_item(new['extract_repair'])
        forms_r = repaired_forms(b, forms, rep_recs, smt)
        changed = sum(_norm_claim(forms_r[i].get('claim') or {}) != _norm_claim(forms[i].get('claim') or {})
                      or shape_of(forms_r[i]['inst'], {}) != shape_of(forms[i]['inst'], {})
                      for i in rep_recs if 'inst' in forms_r[i] and 'inst' in forms[i])
        put('extract_repair', [{'id': it['id'], 'gold': it['gold'],
                                'pred': forms_r[it['id']].get('label', 'parse_failure')} for it in items],
            {'triggered': len(rep_recs), 'changed': changed,
             'triggered_gold': dict(Counter(it['gold'] for it in items if it['id'] in rep_recs)),
             'extraction': extraction_quality(items, forms_r)})
    else:
        forms_r = None

    # no LLM in the loop: answer with Z3's verdict whenever the extraction is usable
    put('solver_final', [{'id': it['id'], 'gold': it['gold'],
                          'pred': forms[it['id']].get('label') or parse_label(direct[it['id']]['raw'])[0]}
                         for it in items])

    # realistic verify-and-revise
    for name, fm in (('verify_flag', forms), ('verify_evidence', forms), ('verify_evidence_repaired', forms_r)):
        if name in new and fm is not None:
            m, rows = _verify_condition(items, direct, fm, by_item(new[name]))
            out[name] = m
            correct[name] = [int(r['gold'] == r['pred']) for r in rows]

    comps = {}
    pairs = [('direct', 'think16384_forced'), ('direct', 'think16384_strict'), ('think3072_strict', 'think16384_strict'),
             ('think16384_forced', 'extract_solve'), ('extract_solve', 'extract_repair'),
             ('direct', 'verify_flag'), ('direct', 'verify_evidence'), ('direct', 'verify_evidence_repaired'),
             ('extract_solve', 'verify_evidence'), ('extract_repair', 'verify_evidence_repaired')]
    for a, c in pairs:
        if a in correct and c in correct:
            comps[f'{c}_minus_{a}'] = bootstrap_diff(correct[a], correct[c])
    out['paired_bootstrap'] = comps
    return out


MAIN_KEYS = ('accuracy', 'macro_f1', 'premature_certainty', 'false_uncertainty', 'missed_inconsistency',
             'false_inconsistency', 'parse_failures')


def main_table(metrics):
    return {k: {kk: v[kk] for kk in MAIN_KEYS if kk in v} for k, v in metrics.items()
            if isinstance(v, dict) and 'accuracy' in v}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def load_base(base_dir):
    base_dir = Path(base_dir)
    items = read_jsonl(base_dir / 'data/llm/tasks.jsonl')
    llm = base_dir / 'results/llm'
    base = {'initial': read_jsonl(llm / 'initial_records.jsonl'), 'think': read_jsonl(llm / 'think_records.jsonl')}
    meta = {k: json.loads((llm / f'{k}_metadata.json').read_text()) for k in ('initial', 'think')}
    original = json.loads((llm / 'metrics.json').read_text(encoding='utf-8'))
    return items, base, meta, original


def load_new(new_dir):
    new = {}
    for p in sorted(Path(new_dir).glob('*_records.jsonl')):
        for r in read_jsonl(p):
            new.setdefault(r['task'], []).append(r)
    return new


def selftest(base_dir):
    """Local, no GPU: frozen prompts, blindness, job counts, sample prompts, scorer on fake outputs."""
    from smt import SMT
    smt = SMT()
    items, base, meta, original = load_base(base_dir)
    assert check_frozen(items, meta['initial'], meta['think'])
    b = blind(items)
    assert not any(k in it for it in b for k in HIDDEN)
    direct, extract = by_item(base['initial'], 'direct'), by_item(base['initial'], 'extract')
    forms = formalise_all(b, extract, smt)
    vf = verify_jobs(b, direct, forms, smt, 'flag', 'verify_flag')
    ve = verify_jobs(b, direct, forms, smt, 'evidence', 'verify_evidence')
    rj = repair_jobs(b, extract, forms, smt)
    traces = initial_traces(base['think'])
    f3 = force_jobs(b, traces, 'think_force3072')
    c8 = continue_jobs(b, traces, 8192, 'think_cont8192')
    print('jobs:', {'verify_flag': len(vf), 'verify_evidence': len(ve), 'extract_repair': len(rj),
                    'think_force3072': len(f3), 'think_cont8192': len(c8)})
    print('\n--- verify_evidence sample feedback ---\n' + ve[0]['messages'][-1]['content'])
    print('\n--- extract_repair sample feedback ---\n' + rj[0]['messages'][-1]['content'])
    print('\n--- think_force3072 prefix tail ---\n' + repr(f3[0]['prefix'][-160:]))
    print('budgets:', {j['max_new_tokens'] for j in c8}, 'batch sizes (95/80/48 GiB, 8k/16k):',
          [(batch_size_for(m, 1800 + 8192 + 64), batch_size_for(m, 1800 + 16384 + 64)) for m in (95, 79, 47)])

    # fake GPU outputs to exercise every scoring path
    rng = random.Random(0)
    fake = lambda jobs, f: [{'id': j['id'], 'item': j['item'], 'task': j['task'], **f(j)} for j in jobs]
    word = ['成立', '不成立', '不确定', '矛盾']
    new = {'verify_flag': fake(vf, lambda j: {'raw': rng.choice(word)}),
           'verify_evidence': fake(ve, lambda j: {'raw': rng.choice(word)}),
           'extract_repair': fake(rj, lambda j: {'raw': extract[j['item']]['raw']}),
           'think_force3072': fake(f3, lambda j: {'raw': rng.choice(word), 'output_tokens': 3, 'hit_limit': False})}
    new['verify_evidence_repaired'] = new['verify_evidence']
    cont = lambda j: ({'raw': '……\n</think>\n\n' + rng.choice(word), 'output_tokens': 900, 'hit_limit': False}
                      if rng.random() < 0.5 else {'raw': '……', 'output_tokens': j['max_new_tokens'], 'hit_limit': True})
    new['think_cont8192'] = fake(c8, cont)
    tr8 = extend(traces, new['think_cont8192'])
    new['think_force8192'] = fake(force_jobs(b, tr8, 'think_force8192'),
                                  lambda j: {'raw': rng.choice(word), 'output_tokens': 3, 'hit_limit': False})
    c16 = continue_jobs(b, tr8, 16384, 'think_cont16384')
    assert {j['max_new_tokens'] for j in c16} == {8192}
    new['think_cont16384'] = fake(c16, cont)
    tr16 = extend(tr8, new['think_cont16384'])
    new['think_force16384'] = fake(force_jobs(b, tr16, 'think_force16384'),
                                   lambda j: {'raw': rng.choice(word), 'output_tokens': 3, 'hit_limit': False})
    m = score_followup(items, base, new, smt, original)
    print('\nreproduced first run:', json.dumps(m['reproduced_first_run']))
    print('think budget table (FAKE outputs):', json.dumps(m['think_budget_table'], indent=1))
    print('extract_repair with unchanged JSON (must equal extract_solve):',
          m['extract_repair']['accuracy'], m['extract_solve']['accuracy'], m['extract_repair']['changed'])
    assert m['extract_repair']['accuracy'] == m['extract_solve']['accuracy'] and m['extract_repair']['changed'] == 0
    assert m['think3072_strict']['parse_failures'] >= original['think']['parse_failures']
    print('solver_final accuracy:', m['solver_final']['accuracy'])
    print('SELFTEST OK')


def reconstruct(base_dir, new_dir, out_dir):
    """Rebuild every job list of the follow-up run and check it against the recorded jobs_sha256.

    Z3 may return any one of several valid witnesses / minimal cores, and which one depends on
    the solver history of the process, so the notebook's order of Z3 work is replayed exactly:
    section 3 dry scoring, then section 5 job construction.  Thinking jobs do not use Z3."""
    from smt import SMT
    smt = SMT()
    items, base, meta, original = load_base(base_dir)
    new = load_new(new_dir)
    b = blind(items)
    direct, extract = by_item(base['initial'], 'direct'), by_item(base['initial'], 'extract')
    traces = initial_traces(base['think'])
    score_followup(items, base, {}, smt, original)                        # notebook section 3
    forms = formalise_all(b, extract, smt)                                 # notebook section 5
    jobs = {'verify_flag': verify_jobs(b, direct, forms, smt, 'flag', 'verify_flag'),
            'verify_evidence': verify_jobs(b, direct, forms, smt, 'evidence', 'verify_evidence'),
            'extract_repair': repair_jobs(b, extract, forms, smt)}
    forms_r = repaired_forms(b, forms, by_item(new['extract_repair']), smt)
    jobs['verify_evidence_repaired'] = verify_jobs(b, direct, forms_r, smt, 'evidence', 'verify_evidence_repaired')
    jobs['think_force3072'] = force_jobs(b, traces, 'think_force3072')     # notebook section 6
    jobs['think_cont8192'] = continue_jobs(b, traces, 8192, 'think_cont8192')
    tr8 = extend(traces, new.get('think_cont8192', []))
    jobs['think_force8192'] = force_jobs(b, tr8, 'think_force8192')
    jobs['think_cont16384'] = continue_jobs(b, tr8, 16384, 'think_cont16384')   # notebook section 7
    tr16 = extend(tr8, new.get('think_cont16384', []))
    jobs['think_force16384'] = force_jobs(b, tr16, 'think_force16384')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, js in jobs.items():
        recorded = json.loads((Path(new_dir) / f'{name}_metadata.json').read_text())
        manifest[name] = {'n': len(js), 'jobs_sha256': digest(js),
                          'matches_run_metadata': digest(js) == recorded['jobs_sha256'] and len(js) == recorded['n']}
        (out / f'{name}_jobs.json').write_text(json.dumps(js, ensure_ascii=False), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps({
        'note': ('Rebuilt locally with avalon/followup.py --reconstruct, replaying the notebook order of Z3 work; '
                 'each file is byte-identical in content to the job list the Colab run used when its '
                 'jobs_sha256 matches the run metadata.'),
        'jobs': manifest}, indent=2), encoding='utf-8')
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--score', action='store_true')
    ap.add_argument('--reconstruct', action='store_true')
    ap.add_argument('--jobs-out', default='results/followup_run/reconstructed_jobs')
    ap.add_argument('--base', default='results/colab_run')
    ap.add_argument('--new', default='results/followup_run/results_followup/llm')
    ap.add_argument('--out', default='results/followup_run/metrics_followup_local.json')
    a = ap.parse_args()
    if a.selftest:
        selftest(a.base)
    if a.score:
        from smt import SMT
        items, base, _, original = load_base(a.base)
        m = score_followup(items, base, load_new(a.new), SMT(), original)
        Path(a.out).write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(main_table(m), ensure_ascii=False, indent=1))
        print(json.dumps(m['think_budget_table'], indent=1))
    if a.reconstruct:
        man = reconstruct(a.base, a.new, a.jobs_out)
        print(json.dumps(man, indent=1))
        assert all(v['matches_run_metadata'] for v in man.values()), 'some job lists differ from the run'
        print('ALL JOBS RECONSTRUCTED')


if __name__ == '__main__':
    main()
