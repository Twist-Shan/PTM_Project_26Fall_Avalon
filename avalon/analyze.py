"""What do the rules alone let players deduce in real games?

Input : results/audit/parsed_games.jsonl (from logs.py --audit)
Output: results/analysis/*.json

A1 deducibility : after each quest, for the public observer and for every
                  player's true private view, how many other players'
                  alignments are logically fixed by the rules?
A2 variant      : the same when only quest results (not Fail counts) are public
A3 assassination: from the assassin's view before the shot, how many players
                  can still be Merlin, and was the shot among them?
A4 completion   : for the public observer at the end of the game, the minimum
                  number of loyalty reveals (Lady of the Lake checks) that
                  decide the full evil team: one-shot (CEGAR, naive) vs
                  adaptive, with solver calls and run time.

  python analyze.py --games 600 [--backend z3|oracle]
"""
import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle as O
from game import EVIL_ROLES
from sim import true_view, prefix
from search import min_reveal_cegar, min_reveal_naive, adaptive_depth, candidates

ROOT = Path(__file__).resolve().parents[1]


def get_backend(name):
    if name in ('z3', 'auto'):
        try:
            from smt import SMT
            return SMT()
        except ImportError:
            if name == 'z3':
                raise
    return O.Oracle()


def determined(backend, inst):
    if hasattr(backend, 'determined_players'):
        return backend.determined_players(inst)
    return O.determined_players(inst)


def possible_roles(backend, inst, p):
    if hasattr(backend, 'possible_roles'):
        return backend.possible_roles(inst, p)
    return O.possible_roles(inst, p)


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parsed', default=str(ROOT / 'results' / 'audit' / 'parsed_games.jsonl'))
    ap.add_argument('--out', default=str(ROOT / 'results' / 'analysis'))
    ap.add_argument('--games', type=int, default=600)
    ap.add_argument('--completion-games', type=int, default=150)
    ap.add_argument('--backend', default='auto')
    ap.add_argument('--seed', type=int, default=271)
    a = ap.parse_args()
    backend = get_backend(a.backend)
    rng = random.Random(a.seed)
    games = [json.loads(x) for x in open(a.parsed, encoding='utf-8') if x.strip()]
    games = [g for g in games if not O.record_violations(g['rec'], {})]
    if backend.name == 'oracle':
        games = [g for g in games if g['rec']['n'] <= 8]
    rng.shuffle(games)
    sample = games[: a.games]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    # ---------------- A1 / A2 ----------------
    acc = defaultdict(list)
    full = defaultdict(list)
    rows = []
    for gi, g in enumerate(sample):
        rec, roles = g['rec'], tuple(g['roles'])
        n = rec['n']
        done = [k for k, qd in enumerate(rec['quests'], 1) if qd.get('result') is not None]
        for k in done:
            r = prefix(rec, k)
            for persp in [None] + list(range(n)):
                view = None if persp is None else true_view(roles, persp)
                who = 'observer' if persp is None else roles[persp]
                for variant_name, variant in (('fails_public', {}), ('result_only', {'fail_count_public': False})):
                    det = determined(backend, {'rec': r, 'view': view, 'variant': variant})
                    if det is None:
                        continue
                    others = [j for j in range(n) if j != persp]
                    fixed = sum(det[j] != 'unknown' for j in others)
                    key = (variant_name, who, k)
                    acc[key].append(fixed / len(others))
                    full[key].append(all(det[j] != 'unknown' for j in others))
                    if variant_name == 'fails_public':
                        rows.append({'game': rec['source']['game'], 'n': n, 'quest': k, 'perspective': who,
                                     'fixed': fixed, 'others': len(others)})
        if gi % 50 == 0:
            print(f'A1 {gi}/{len(sample)} {time.perf_counter() - t0:.0f}s', flush=True)
    a1 = [{'variant': v, 'perspective': w, 'after_quest': k, 'states': len(xs),
           'mean_fraction_fixed': round(mean(xs), 4), 'all_fixed_rate': round(mean(full[(v, w, k)]), 4)}
          for (v, w, k), xs in sorted(acc.items())]
    (out / 'A1_A2_deducibility.json').write_text(json.dumps(a1, ensure_ascii=False, indent=1), encoding='utf-8')
    with open(out / 'A1_states.jsonl', 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')

    # ---------------- A3 ----------------
    a3 = []
    for g in sample:
        rec, roles = g['rec'], tuple(g['roles'])
        end = rec.get('end') or {}
        assassin = rec['source'].get('assassin')
        if end.get('assassinated') is None or assassin is None:
            continue
        r = {**rec, 'end': None}
        view = true_view(roles, assassin)
        cands = [p for p in range(rec['n']) if 'merlin' in possible_roles(backend, {'rec': r, 'view': view}, p)]
        a3.append({'game': rec['source']['game'], 'n': rec['n'], 'merlin_candidates': len(cands),
                   'shot_in_candidates': end['assassinated'] in cands,
                   'hit': roles[end['assassinated']] == 'merlin'})
    a3s = {'games': len(a3), 'mean_candidates': mean([x['merlin_candidates'] for x in a3]),
           'unique_candidate_rate': mean([x['merlin_candidates'] == 1 for x in a3]),
           'shot_outside_candidates': sum(not x['shot_in_candidates'] for x in a3),
           'hit_rate': mean([x['hit'] for x in a3]),
           'by_n': {n: {'games': len(v), 'mean_candidates': mean([x['merlin_candidates'] for x in v]),
                        'hit_rate': mean([x['hit'] for x in v])}
                    for n, v in sorted(group(a3, 'n').items())}}
    (out / 'A3_assassination.json').write_text(json.dumps({'summary': a3s, 'games': a3}, indent=1), encoding='utf-8')

    # ---------------- A4 ----------------
    a4 = []
    for g in sample[: a.completion_games]:
        rec, roles = g['rec'], tuple(g['roles'])
        r = {**rec, 'end': None}
        evil = [i for i, x in enumerate(roles) if x in EVIL_ROLES]
        inst = {'rec': r}
        claim = {'t': 'evil_set', 'ps': evil}
        if backend.classify(inst, claim)['label'] != 'undetermined':
            continue
        row = {'game': rec['source']['game'], 'n': rec['n'], 'quests': len(rec['quests'])}
        c0 = getattr(backend, 'calls', 0)
        t = time.perf_counter()
        cg = min_reveal_cegar(backend, inst, claim)
        row.update(cegar_size=cg.get('size'), cegar_calls=cg['calls'], cegar_s=round(time.perf_counter() - t, 3))
        if rec['n'] <= 7:
            t = time.perf_counter()
            nv = min_reveal_naive(backend, inst, claim, deadline=60)
            row.update(naive_size=nv.get('size'), naive_checks=nv['checks'], naive_s=round(time.perf_counter() - t, 3),
                       naive_status=nv['status'], n_optimal_sets=len(nv.get('sets', [])))
            t = time.perf_counter()
            d, first = adaptive_depth(backend, inst, claim)
            row.update(adaptive_depth=d, adaptive_s=round(time.perf_counter() - t, 3))
        row['backend_calls'] = getattr(backend, 'calls', 0) - c0
        a4.append(row)
    a4s = {'states': len(a4),
           'by_n': {n: {'states': len(v), 'mean_cegar_size': mean([x['cegar_size'] for x in v if x['cegar_size'] is not None]),
                        'mean_cegar_s': mean([x['cegar_s'] for x in v]),
                        'mean_naive_s': mean([x['naive_s'] for x in v if 'naive_s' in x]),
                        'adaptive_lt_oneshot': sum(1 for x in v if x.get('adaptive_depth') is not None
                                                   and x['cegar_size'] is not None and x['adaptive_depth'] < x['cegar_size']),
                        'with_adaptive': sum(1 for x in v if x.get('adaptive_depth') is not None)}
                    for n, v in sorted(group(a4, 'n').items())}}
    (out / 'A4_completion.json').write_text(json.dumps({'summary': a4s, 'states': a4}, indent=1), encoding='utf-8')

    meta = {'backend': backend.name, 'games_available': len(games), 'games_sampled': len(sample),
            'seed': a.seed, 'seconds': round(time.perf_counter() - t0, 1)}
    (out / 'meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps({'meta': meta, 'A3': a3s, 'A4': a4s}, indent=2))


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


if __name__ == '__main__':
    main()
