"""Minimal information completion for Avalon claims (backend-agnostic).

A *reveal* tells the alignment (good/evil) of one player, exactly what a Lady
of the Lake check gives its holder.  For an undetermined claim C we ask:

  one-shot   : the smallest set S of players whose alignments, whatever they
               turn out to be, always decide C.  S is sufficient iff no two
               consistent worlds agree on the alignments in S but disagree on C
               (two-world test, backend.find_pair).
               - naive : enumerate subsets by increasing size
               - cegar : counterexample-guided implicit hitting sets
  adaptive   : the minimax number of sequential reveals, where each next
               player is chosen after seeing earlier answers (a game against
               an adversarial world; answers must stay consistent).

Backends implement classify(inst, claim) and find_pair(inst, claim, agree).
"""
import time
from itertools import combinations

EVIL = {'morgana', 'mordred', 'oberon', 'minion'}
DECIDED = ('entailed', 'contradicted')


def _ev(roles, j):
    return roles[j] in EVIL


def min_hitting_set(sets, costs):
    best = [float('inf'), None]
    sets = [frozenset(s) for s in sets]
    if any(not s for s in sets):
        return None

    def rec(chosen, cost):
        if cost >= best[0]:
            return
        unhit = None
        for s in sets:
            if not (s & chosen) and (unhit is None or len(s) < len(unhit)):
                unhit = s
        if unhit is None:
            best[0], best[1] = cost, chosen
            return
        for f in sorted(unhit, key=lambda x: (costs[x], x)):
            rec(chosen | {f}, cost + costs[f])
    rec(frozenset(), 0)
    return None if best[1] is None else sorted(best[1])


def candidates(inst):
    known = {t for t, _ in inst.get('reveals') or []}
    view = inst.get('view')
    if view is not None:
        known.add(view['player'])
        known |= {t for t, _ in view.get('lady') or []}
    return [j for j in range(inst['rec']['n']) if j not in known]


def min_reveal_naive(backend, inst, claim, cands=None, deadline=None):
    cands = candidates(inst) if cands is None else cands
    checks, t0 = 0, time.perf_counter()
    for k in range(len(cands) + 1):
        found = []
        for S in combinations(cands, k):
            if deadline and time.perf_counter() - t0 > deadline:
                return {'status': 'timeout', 'checks': checks, 'size_reached': k}
            checks += 1
            if backend.find_pair(inst, claim, list(S)) is None:
                found.append(list(S))
        if found:
            return {'status': 'ok', 'sets': found, 'size': k, 'checks': checks}
    return {'status': 'none', 'checks': checks}


def min_reveal_cegar(backend, inst, claim, cands=None, costs=None, generalize=True):
    cands = candidates(inst) if cands is None else cands
    costs = costs or {j: 1 for j in cands}
    D, calls, rounds = [], 0, 0
    while True:
        rounds += 1
        H = min_hitting_set(D, costs)
        if H is None:
            return {'status': 'none', 'calls': calls, 'rounds': rounds}
        pair = backend.find_pair(inst, claim, H)
        calls += 1
        if pair is None:
            return {'status': 'ok', 'set': H, 'size': len(H), 'calls': calls, 'rounds': rounds,
                    'cuts': [sorted(d) for d in D]}
        x, y = pair
        diff = [j for j in cands if j not in H and _ev(x, j) != _ev(y, j)]
        if generalize:
            agree = list(H)
            for j in list(diff):
                if j not in diff:
                    continue
                trial = backend.find_pair(inst, claim, agree + [j])
                calls += 1
                if trial is not None:
                    agree.append(j)
                    x, y = trial
                    diff = [g for g in cands if g not in agree and _ev(x, g) != _ev(y, g)]
        if not diff:
            return {'status': 'none', 'calls': calls, 'rounds': rounds}
        D.append(frozenset(diff))


def adaptive_depth(backend, inst, claim, cands=None, limit=None):
    """Worst-case number of sequential reveals needed to decide the claim.

    Returns (depth, first_choice); depth is None if no reveal strategy over
    `cands` can decide the claim."""
    cands = candidates(inst) if cands is None else cands
    memo = {}
    base = list(inst.get('reveals') or [])

    def label(extra):
        return backend.classify({**inst, 'reveals': base + list(extra)}, claim)['label']

    def solve(extra):
        key = frozenset(extra)
        if key in memo:
            return memo[key]
        lab = label(extra)
        if lab in DECIDED or lab == 'inconsistent':
            memo[key] = (0, None)
            return memo[key]
        used = {t for t, _ in extra}
        best = (None, None)
        for j in cands:
            if j in used:
                continue
            worst = 0
            for v in (False, True):
                nxt = tuple(sorted(extra + ((j, v),)))
                if label(nxt) == 'inconsistent':
                    continue
                d, _ = solve(nxt)
                if d is None:
                    worst = None
                    break
                worst = max(worst, d + 1)
            if worst is not None and (best[0] is None or worst < best[0]):
                best = (worst, j)
                if limit is not None and worst <= 1:
                    break
        memo[key] = best
        return best

    return solve(tuple())
