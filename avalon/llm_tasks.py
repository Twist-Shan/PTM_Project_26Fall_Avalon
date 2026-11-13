"""Build the frozen LLM evaluation set from real (or simulated) game states.

Each item = one game state (record prefix + perspective) + one claim, with the
gold verdict computed by the solver.  Inconsistent items are made by
introducing one rule violation that is visible in the text.  Votes are kept in
the narrative on purpose: no rule links votes to roles, so they are logically
irrelevant distractors.

  python llm_tasks.py --parsed ../results/audit/parsed_games.jsonl --out ../data/llm
"""
import argparse
import copy
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle as O
from game import (EVIL_ROLES, EVIL_COUNT, TEAM_SIZE, ZH_ROLE, render_record, render_view,
                  player_label, team_label, fails_required)
from sim import true_view, prefix
from search import min_reveal_cegar, candidates

ROOT = Path(__file__).resolve().parents[1]
LABELS = ('entailed', 'contradicted', 'undetermined', 'inconsistent')
ZH_LABEL = {'entailed': '成立', 'contradicted': '不成立', 'undetermined': '不确定', 'inconsistent': '矛盾'}
QUOTA = {'entailed': 150, 'contradicted': 150, 'undetermined': 150, 'inconsistent': 60}


def render_claim(c):
    t = c['t']
    if t == 'evil':
        return f'{player_label(c["p"])}一定是坏人。'
    if t == 'good':
        return f'{player_label(c["p"])}一定是好人。'
    if t == 'role':
        return f'{player_label(c["p"])}一定是{ZH_ROLE[c["r"]]}。'
    if t == 'not' and c['a']['t'] == 'role':
        return f'{player_label(c["a"]["p"])}一定不是{ZH_ROLE[c["a"]["r"]]}。'
    if t == 'atleast':
        return f'{team_label(c["ps"])}中至少有{c["k"]}名坏人。'
    if t == 'exactly':
        return f'{team_label(c["ps"])}中恰好有{c["k"]}名坏人。'
    if t == 'same':
        a, b = c['ps']
        return f'{player_label(a)}和{player_label(b)}一定属于同一阵营。'
    if t == 'evil_set':
        return f'本局的坏人恰好是{team_label(c["ps"])}。'
    raise ValueError(t)


def claim_pool(rng, inst, roles):
    rec, view = inst['rec'], inst.get('view')
    n = rec['n']
    me = view['player'] if view else None
    others = [j for j in range(n) if j != me]
    pool = []
    for j in others:
        pool += [{'t': 'evil', 'p': j}, {'t': 'good', 'p': j}]
    for j in rng.sample(others, min(3, len(others))):
        pool.append({'t': 'role', 'p': j, 'r': 'merlin'})
        pool.append({'t': 'not', 'a': {'t': 'role', 'p': j, 'r': 'merlin'}})
    for qd in rec['quests']:
        if qd.get('result') is None:
            continue
        team = qd['team']
        for k in (1, 2):
            if k <= len(team):
                pool.append({'t': 'atleast', 'ps': team, 'k': k})
        pool.append({'t': 'exactly', 'ps': team, 'k': 1})
    for _ in range(3):
        a, b = rng.sample(others, 2)
        pool.append({'t': 'same', 'ps': sorted([a, b])})
    evil = [i for i, r in enumerate(roles) if r in EVIL_ROLES]
    pool.append({'t': 'evil_set', 'ps': evil})
    wrong = sorted(rng.sample(range(n), len(evil)))
    if wrong != evil:
        pool.append({'t': 'evil_set', 'ps': wrong})
    rng.shuffle(pool)
    return pool


def corrupt_visible(rng, inst, roles):
    """One textual rule violation; returns (inst, kind) or None."""
    rec = copy.deepcopy(inst['rec'])
    n = rec['n']
    done = [qd for qd in rec['quests'] if qd.get('result') is not None]
    reasoning = ['two_fail', 'evil_overflow', 'self_fail', 'percival_three']
    obvious = ['fails_over_team', 'team_size']
    rng.shuffle(reasoning)
    rng.shuffle(obvious)
    kinds = reasoning + obvious if rng.random() < 0.7 else obvious + reasoning
    view = inst.get('view')
    for kind in kinds:
        if kind == 'self_fail' and view and view['role'] not in EVIL_ROLES:
            mine = [qd for qd in done if view['player'] in qd['team']]
            if mine:
                qd = rng.choice(mine)
                qd['fails'] = len(qd['team'])
                qd['result'] = 'fail' if qd['fails'] >= fails_required(n, qd['q']) else 'success'
                return {**inst, 'rec': rec}, kind
        if kind == 'percival_three' and not (view and view['role'] == 'percival'):
            continue
        if kind == 'fails_over_team' and done:
            qd = rng.choice(done)
            qd['fails'] = len(qd['team']) + 1
            qd['result'] = 'fail'
            return {**inst, 'rec': rec}, kind
        if kind == 'two_fail' and n >= 7 and len(done) >= 4:
            qd = done[3]
            qd['fails'], qd['result'] = 1, 'fail'
            return {**inst, 'rec': rec}, kind
        if kind == 'evil_overflow' and len(done) >= 2:
            a, b = done[0], done[1]
            if not set(a['team']) & set(b['team']):
                a['fails'], b['fails'] = len(a['team']), len(b['team'])
                if a['fails'] + b['fails'] > EVIL_COUNT[n]:
                    a['result'] = 'fail' if a['fails'] >= fails_required(n, a['q']) else 'success'
                    b['result'] = 'fail' if b['fails'] >= fails_required(n, b['q']) else 'success'
                    return {**inst, 'rec': rec}, kind
        if kind == 'team_size' and done:
            qd = rng.choice(done)
            extra = [i for i in range(n) if i not in qd['team']]
            qd['team'] = sorted(qd['team'] + extra[:1])
            if qd['proposals']:
                qd['proposals'][-1]['team'] = list(qd['team'])
            return {**inst, 'rec': rec}, kind
        if kind == 'percival_three':
            v = copy.deepcopy(inst['view'])
            extra = [j for j in range(n) if j != v['player'] and j not in v['seen']]
            v['seen'] = sorted(v['seen'] + extra[:1])
            return {**inst, 'view': v}, kind
    return None


def to_text(inst):
    return render_record(inst['rec'], show_votes=True) + '\n' + render_view(inst.get('view'), inst['rec']['config'])


def build(parsed_path, out_dir, seed=137, backend=None, max_states=4000):
    rng = random.Random(seed)
    games = [json.loads(x) for x in open(parsed_path, encoding='utf-8') if x.strip()]
    games = [g for g in games if not O.record_violations(g['rec'], {}) and g['rec']['quests']]
    if backend is None or backend.name == 'oracle':
        backend = backend or O.Oracle()
        games = [g for g in games if g['rec']['n'] <= 8]
    rng.shuffle(games)
    items, have = [], Counter()
    used_games = set()
    for g in games[:max_states]:
        if all(have[k] >= QUOTA[k] for k in QUOTA):
            break
        rec, roles = g['rec'], tuple(g['roles'])
        done = [k for k, qd in enumerate(rec['quests'], 1) if qd.get('result') is not None]
        if not done:
            continue
        k = rng.choice(done)
        r = prefix(rec, k)
        r['source'] = rec.get('source')
        persp = None if rng.random() < 0.3 else rng.randrange(rec['n'])
        view = None if persp is None else true_view(roles, persp)
        inst = {'rec': r, 'view': view}
        gid = (rec.get('source') or {}).get('game', str(len(items)))
        if have['inconsistent'] < QUOTA['inconsistent'] and rng.random() < 0.15:
            bad = corrupt_visible(rng, inst, roles)
            if bad:
                binst, kind = bad
                claim = rng.choice(claim_pool(rng, binst, roles))
                if backend.classify(binst, claim)['label'] == 'inconsistent':
                    items.append(make_item(binst, claim, 'inconsistent', gid, k, roles, kind))
                    have['inconsistent'] += 1
                    used_games.add(gid)
                    continue
        for claim in claim_pool(rng, inst, roles):
            lab = backend.classify(inst, claim)['label']
            if lab in QUOTA and have[lab] < QUOTA[lab]:
                item = make_item(inst, claim, lab, gid, k, roles, None)
                if lab == 'undetermined':
                    cg = min_reveal_cegar(backend, inst, claim)
                    item['gold_reveal'] = {'status': cg['status'], 'size': cg.get('size'), 'set': cg.get('set')}
                items.append(item)
                have[lab] += 1
                used_games.add(gid)
                break
    for i, it in enumerate(items):
        it['id'] = f'av{i:04d}'
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'tasks.jsonl', 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
    blob = (out / 'tasks.jsonl').read_bytes()
    manifest = {'items': len(items), 'labels': dict(Counter(it['gold'] for it in items)),
                'games': len(used_games), 'seed': seed, 'backend': backend.name,
                'n_dist': dict(Counter(it['inst']['rec']['n'] for it in items)),
                'perspective': dict(Counter(it['perspective'] for it in items)),
                'claim_types': dict(Counter(it['claim']['t'] for it in items)),
                'corruptions': dict(Counter(it['corruption'] for it in items if it['corruption'])),
                'reveal_status': dict(Counter((it.get('gold_reveal') or {}).get('status') for it in items
                                              if it['gold'] == 'undetermined')),
                'tasks_sha256': hashlib.sha256(blob).hexdigest(), 'source': str(parsed_path)}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def make_item(inst, claim, gold, gid, k, roles, corruption):
    view = inst.get('view')
    return {'game': gid, 'after_quest': k, 'perspective': 'observer' if view is None else view['role'],
            'inst': {'rec': inst['rec'], 'view': view}, 'claim': claim, 'gold': gold,
            'corruption': corruption, 'text': to_text(inst), 'claim_text': render_claim(claim),
            'true_roles': list(roles)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parsed', default=str(ROOT / 'results' / 'audit' / 'parsed_games.jsonl'))
    ap.add_argument('--out', default=str(ROOT / 'data' / 'llm'))
    ap.add_argument('--seed', type=int, default=137)
    ap.add_argument('--backend', default='auto')
    a = ap.parse_args()
    backend = None
    if a.backend in ('auto', 'z3'):
        try:
            from smt import SMT
            backend = SMT()
        except ImportError:
            if a.backend == 'z3':
                raise
    print(json.dumps(build(a.parsed, a.out, a.seed, backend), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
