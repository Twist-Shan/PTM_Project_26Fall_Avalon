"""Acceptance checks.  Runs everything that does not need Z3 with the oracle
alone; when z3 is importable it also cross-checks the SMT encoding.

  python selfcheck.py [--quick] [--out ../results/selfcheck]
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import game
import oracle as O
from cases import CASES
from search import min_reveal_naive, min_reveal_cegar, adaptive_depth, candidates
from sim import play, true_view, prefix, random_claim, corrupt

try:
    from smt import SMT
    HAVE_Z3 = True
except ImportError:
    HAVE_Z3 = False


def tables_agree():
    ok = game.EVIL_COUNT == O.O_EVIL_COUNT
    ok &= all(list(game.TEAM_SIZE[n]) == O.O_SIZES[n] for n in game.TEAM_SIZE)
    ok &= all(game.fails_required(n, q) == O.o_need(n, q) for n in range(5, 11) for q in range(1, 6))
    ok &= set(game.EVIL_ROLES) == O.O_EVIL
    return bool(ok)


def run_cases(backends):
    rows = []
    for c in CASES:
        row = {'id': c['id'], 'cat': c['cat'], 'expect': c['expect'], 'rules': c['rules']}
        for name, b in backends.items():
            res = b.classify(c['inst'], c['claim'], explain=True) if name == 'z3' else b.classify(c['inst'], c['claim'])
            row[name] = res['label']
            if 'core' in res:
                row['core'] = res['core']
            if res.get('positive'):
                row[name + '_pos'] = res['positive']
            if res.get('negative'):
                row[name + '_neg'] = res['negative']
        row['pass'] = all(row[name] == c['expect'] for name in backends)
        rows.append(row)
    return rows


def sample_instances(rng, n_games, max_n=8):
    insts = []
    for g in range(n_games):
        n = rng.choice([5, 5, 6, 6, 7, 7, 8] + ([9, 10] if max_n >= 10 else []))
        rec, roles = play(rng, n=n, p_approve=0.6, lady=(n >= 7 and rng.random() < 0.5))
        done = len(rec['quests'])
        for k in sorted({rng.randint(1, done), done}):
            r = prefix(rec, k) if k < done else rec
            for persp in (None, rng.randrange(n)):
                view = None if persp is None else true_view(roles, persp, rec=r)
                variant = rng.choice([{}, {}, {'fail_count_public': False}, {'merlin_sees_oberon': False}])
                if variant.get('merlin_sees_oberon') is False and view is not None:
                    view = true_view(roles, persp, variant, rec=r)
                insts.append(({'rec': r, 'view': view, 'variant': variant}, roles, f'g{g}k{k}p{persp}'))
    return insts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--seed', type=int, default=20261112)
    ap.add_argument('--out', default=str(Path(__file__).resolve().parents[1] / 'results' / 'selfcheck'))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    t0 = time.perf_counter()
    oracle = O.Oracle()
    backends = {'oracle': oracle}
    if HAVE_Z3:
        backends['z3'] = SMT()
    summary = {'z3_available': HAVE_Z3, 'seed': args.seed, 'tables_agree': tables_agree()}

    # 1. hand-written cases
    rows = run_cases(backends)
    summary['cases'] = {'n': len(rows), 'pass': sum(r['pass'] for r in rows),
                        'by_expect': {k: sum(r['expect'] == k for r in rows)
                                      for k in ('entailed', 'contradicted', 'undetermined', 'inconsistent')},
                        'failed': [r['id'] for r in rows if not r['pass']]}
    (out / 'cases.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')

    # 2. random instances: soundness w.r.t. the true roles, and oracle vs z3
    insts = sample_instances(rng, 25 if args.quick else 120, max_n=8 if args.quick else 10)
    agree = sound = total = 0
    mismatches = []
    for inst, roles, tag in insts:
        for _ in range(3):
            claim = random_claim(rng, inst['rec']['n'])
            a = oracle.classify(inst, claim)['label']
            truth = O.claim_holds(claim, roles, inst['rec'])
            total += 1
            sound += (a == 'entailed' and truth) or (a == 'contradicted' and not truth) or a == 'undetermined'
            if HAVE_Z3:
                b = backends['z3'].classify(inst, claim)['label']
                agree += a == b
                if a != b:
                    mismatches.append({'tag': tag, 'claim': claim, 'oracle': a, 'z3': b, 'inst': inst})
    summary['random'] = {'instances': len(insts), 'claims': total, 'sound_wrt_truth': sound,
                         'oracle_z3_agree': agree if HAVE_Z3 else None}

    # 3. corrupted records must be inconsistent for both backends
    bad_ok = bad_total = 0
    for inst, roles, tag in insts[:60]:
        r, kind = corrupt(rng, inst['rec'])
        ci = {**inst, 'rec': r, 'variant': {}}  # violations of the fail count are visible only in the default reading
        labels = {name: b.classify(ci, {'t': 'evil', 'p': 0})['label'] for name, b in backends.items()}
        bad_total += 1
        bad_ok += all(v == 'inconsistent' for v in labels.values())
        if not all(v == 'inconsistent' for v in labels.values()):
            mismatches.append({'tag': tag + ':corrupt:' + kind, 'labels': labels, 'inst': ci})
    summary['corrupted'] = {'n': bad_total, 'all_inconsistent': bad_ok}

    # 4. minimum reveal sets: brute force vs naive vs CEGAR (oracle backend), and z3 CEGAR
    mr = {'n': 0, 'naive_eq': 0, 'cegar_eq': 0, 'z3_cegar_eq': 0 if HAVE_Z3 else None, 'adaptive_le_oneshot': 0}
    for inst, roles, tag in insts[: (15 if args.quick else 80)]:
        if inst['rec']['n'] > 8:
            continue
        claim = random_claim(rng, inst['rec']['n'])
        if oracle.classify(inst, claim)['label'] != 'undetermined':
            continue
        cands = candidates(inst)
        brute = oracle.min_reveal_sets(inst, claim, cands)
        size = len(brute[0]) if brute else None  # [] = no sufficient set exists
        nv = min_reveal_naive(oracle, inst, claim, cands)
        cg = min_reveal_cegar(oracle, inst, claim, cands)
        mr['n'] += 1
        mr['naive_eq'] += (nv.get('size') == size and sorted(map(sorted, nv.get('sets', []))) == sorted(map(sorted, brute or [])))
        mr['cegar_eq'] += cg.get('size') == size and (cg.get('set') is None or sorted(cg['set']) in [sorted(s) for s in brute])
        if HAVE_Z3:
            zc = min_reveal_cegar(backends['z3'], inst, claim, cands)
            mr['z3_cegar_eq'] += zc.get('size') == size
        d, _ = adaptive_depth(oracle, inst, claim, cands)
        # no reveal strategy exists  <=>  no one-shot set exists; otherwise adaptive <= one-shot
        mr['adaptive_le_oneshot'] += (d is None and size is None) or (d is not None and size is not None and d <= size)
        mr.setdefault('adaptive_lt_oneshot', 0)
        mr['adaptive_lt_oneshot'] += d is not None and size is not None and d < size
        mr.setdefault('no_reveal_set', 0)
        mr['no_reveal_set'] += size is None
    summary['min_reveal'] = mr

    # 5. votes carry no logical information about roles (rule-level property)
    vp = {'n': 0, 'same': 0}
    for inst, roles, tag in insts[:40]:
        stripped = {**inst, 'rec': {**inst['rec'], 'quests': [
            {**qd, 'proposals': [{**p, 'approve': None} for p in qd.get('proposals', [])]}
            for qd in inst['rec']['quests']]}}
        for p in range(inst['rec']['n']):
            c = {'t': 'evil', 'p': p}
            vp['n'] += 1
            vp['same'] += oracle.classify(inst, c)['label'] == oracle.classify(stripped, c)['label']
    summary['votes_uninformative'] = vp

    summary['seconds'] = round(time.perf_counter() - t0, 2)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'mismatches.json').write_text(json.dumps(mismatches[:50], ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    ok = (summary['tables_agree'] and not summary['cases']['failed'] and sound == total
          and bad_ok == bad_total and (not HAVE_Z3 or agree == total)
          and mr['naive_eq'] == mr['n'] and mr['cegar_eq'] == mr['n'] and mr['adaptive_le_oneshot'] == mr['n']
          and (not HAVE_Z3 or mr['z3_cegar_eq'] == mr['n']) and vp['same'] == vp['n'])
    print('ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
