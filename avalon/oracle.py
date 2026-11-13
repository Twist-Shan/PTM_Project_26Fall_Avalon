"""Independent executable reading of the Avalon rules (no solver).

Enumerates every assignment of the configured role multiset to the seats and
keeps those consistent with the record, the private view and the reveals.
It shares no rule code with smt.py: the tables are typed again here, the
quest rule is checked as an inequality (#Fail cards <= #evil on the team)
instead of per-card variables, and record legality is checked imperatively.
selfcheck.py compares the two implementations instance by instance.
"""
from itertools import combinations

O_EVIL = {'morgana', 'mordred', 'oberon', 'minion'}
O_ORDER = ('merlin', 'percival', 'servant', 'morgana', 'mordred', 'oberon', 'minion')
O_EVIL_COUNT = {5: 2, 6: 2, 7: 3, 8: 3, 9: 3, 10: 4}
O_SIZES = {5: [2, 3, 2, 3, 3], 6: [2, 3, 4, 3, 4], 7: [2, 3, 3, 4, 4],
           8: [3, 4, 4, 5, 5], 9: [3, 4, 4, 5, 5], 10: [3, 4, 4, 5, 5]}


def o_need(n, q):
    if q == 4 and n >= 7:
        return 2
    return 1


def role_assignments(n, config):
    left = {r: config.get(r, 0) for r in O_ORDER}
    seats = [None] * n

    def go(i):
        if i == n:
            yield tuple(seats)
            return
        for r in O_ORDER:
            if left[r]:
                left[r] -= 1
                seats[i] = r
                yield from go(i + 1)
                left[r] += 1
    if sum(left.values()) == n:
        yield from go(0)


def record_violations(rec, variant):
    """Role-independent legality of the record; returns violated rule ids."""
    n, cfg, bad = rec['n'], rec['config'], []
    if n not in O_EVIL_COUNT:
        return ['S-SIZE']
    if sum(cfg.values()) != n:
        bad.append('S-TOTAL')
    if sum(v for r, v in cfg.items() if r in O_EVIL) != O_EVIL_COUNT[n]:
        bad.append('S-COUNT')
    if any(cfg.get(r, 0) > 1 for r in ('merlin', 'percival', 'morgana', 'mordred', 'oberon')):
        bad.append('S-UNIQUE')
    wins = losses = 0
    last_leader = None
    quests = rec.get('quests', [])
    for pos, qd in enumerate(quests):
        q = qd['q']
        if q != pos + 1:
            bad.append('R-ORDER')
            continue
        if wins >= 3 or losses >= 3:
            bad.append('G-END')
        size = O_SIZES[n][q - 1]
        props = qd.get('proposals', [])
        if len(props) > 5:
            bad.append('T-HAMMER')
        for k, p in enumerate(props):
            team = p['team']
            if len(team) != size:
                bad.append('T-SIZE')
            if len(set(team)) != len(team) or any(not 0 <= x < n for x in team):
                bad.append('T-DISTINCT')
            if p.get('approve') is not None:
                yes = len(set(p['approve']))
                if (2 * yes > n) != bool(p['approved']):
                    bad.append('T-VOTE')
            if variant.get('check_leader', True) and last_leader is not None:
                if p['leader'] != (last_leader + 1) % n:
                    bad.append('T-LEADER')
            last_leader = p['leader']
            if p['approved'] and k != len(props) - 1:
                bad.append('T-LAST')
        if qd.get('result') is not None:
            if not props or not props[-1]['approved'] or sorted(props[-1]['team']) != sorted(qd['team']):
                if props:
                    bad.append('T-LAST')
            if len(qd['team']) != size or len(set(qd['team'])) != size:
                bad.append('Q-SIZE')
            f = qd.get('fails')
            if variant.get('fail_count_public', True) and f is not None:
                if f < 0 or f > len(qd['team']):
                    bad.append('Q-COUNT')
                if (f >= o_need(n, q)) != (qd['result'] == 'fail'):
                    bad.append('Q-RESULT')
            if qd['result'] == 'success':
                wins += 1
            else:
                losses += 1
        elif len(props) == 5 and not props[-1]['approved']:
            # fifth rejection: game over, evil wins (T-HAMMER)
            if pos != len(quests) - 1:
                bad.append('T-HAMMER')
            end = rec.get('end')
            if end and end.get('outcome') not in (None, 'evil_win'):
                bad.append('T-HAMMER')
    # Lady of the Lake (optional rule): public part of each use
    resolved = {qd['q'] for qd in quests if qd.get('result') is not None}
    holders, prev_q = [], 0
    for k, use in enumerate(rec.get('lady') or []):
        if use['q'] not in (2, 3, 4) or use['q'] <= prev_q or use['q'] not in resolved:
            bad.append('L-WHEN')
        prev_q = use['q']
        if k == 0:
            first = quests[0]['proposals'][0]['leader'] if quests and quests[0].get('proposals') else None
            if first is not None and use['holder'] != (first - 1) % n:
                bad.append('L-FIRST')
        elif use['holder'] != rec['lady'][k - 1]['target']:
            bad.append('L-CHAIN')
        holders.append(use['holder'])
        if use['target'] in holders or not 0 <= use['target'] < n:
            bad.append('L-PREV')
    end = rec.get('end')
    if end and end.get('outcome') is not None:
        if losses >= 3 and end['outcome'] != 'evil_win':
            bad.append('G-OUTCOME')
        if end.get('assassinated') is not None and wins < 3:
            bad.append('G-ASSASSIN')
    return sorted(set(bad))


def _team_evil(roles, team):
    return sum(1 for i in team if roles[i] in O_EVIL)


def world_ok(roles, rec, view, reveals, variant):
    n = rec['n']
    for qd in rec.get('quests', []):
        if qd.get('result') is None:
            continue
        ev = _team_evil(roles, qd['team'])
        f = qd.get('fails')
        if variant.get('fail_count_public', True) and f is not None:
            if f > ev:
                return False
        elif qd['result'] == 'fail' and ev < o_need(rec['n'], qd['q']):
            return False
    end = rec.get('end')
    if end and end.get('assassinated') is not None:
        hit = roles[end['assassinated']] == 'merlin'
        if (end['outcome'] == 'evil_win') != hit:
            return False
    if view is not None:
        p, r = view['player'], view['role']
        if roles[p] != r:
            return False
        seen = set(view.get('seen') or [])
        if r == 'merlin':
            exp = set()
            for j in range(n):
                if j == p or roles[j] not in O_EVIL or roles[j] == 'mordred':
                    continue
                if roles[j] == 'oberon' and not variant.get('merlin_sees_oberon', True):
                    continue
                exp.add(j)
        elif r == 'percival':
            exp = {j for j in range(n) if j != p and roles[j] in ('merlin', 'morgana')}
        elif r in O_EVIL and r != 'oberon':
            exp = {j for j in range(n) if j != p and roles[j] in O_EVIL and roles[j] != 'oberon'}
        else:
            exp = set()  # servants and Oberon learn nothing at setup
        if exp != seen:
            return False
        for t, is_evil in view.get('lady') or []:
            if (roles[t] in O_EVIL) != bool(is_evil):
                return False
    for t, is_evil in reveals or []:
        if (roles[t] in O_EVIL) != bool(is_evil):
            return False
    return True


def claim_holds(c, roles, rec):
    t = c['t']
    if t == 'evil':
        return roles[c['p']] in O_EVIL
    if t == 'good':
        return roles[c['p']] not in O_EVIL
    if t == 'role':
        return roles[c['p']] == c['r']
    if t == 'atleast':
        return _team_evil(roles, c['ps']) >= c['k']
    if t == 'exactly':
        return _team_evil(roles, c['ps']) == c['k']
    if t == 'same':
        a, b = c['ps']
        return (roles[a] in O_EVIL) == (roles[b] in O_EVIL)
    if t == 'evil_set':
        return {i for i, r in enumerate(roles) if r in O_EVIL} == set(c['ps'])
    if t == 'not':
        return not claim_holds(c['a'], roles, rec)
    if t == 'and':
        return all(claim_holds(x, roles, rec) for x in c['as'])
    if t == 'or':
        return any(claim_holds(x, roles, rec) for x in c['as'])
    if t == 'fail_by':
        return c['f'] >= o_need(rec['n'], c['q'])
    if t == 'vote_pass':
        return 2 * c['yes'] > rec['n']
    if t == 'team_size':
        return O_SIZES[rec['n']][c['q'] - 1] == c['k']
    raise ValueError(t)


def worlds(inst):
    rec, view = inst['rec'], inst.get('view')
    variant = inst.get('variant', {})
    if record_violations(rec, variant):
        return
    for roles in role_assignments(rec['n'], rec['config']):
        if world_ok(roles, rec, view, inst.get('reveals'), variant):
            yield roles


class Oracle:
    name = 'oracle'

    def classify(self, inst, claim):
        pos = neg = None
        for roles in worlds(inst):
            if claim_holds(claim, roles, inst['rec']):
                pos = pos or roles
            else:
                neg = neg or roles
            if pos and neg:
                break
        if pos is None and neg is None:
            return {'label': 'inconsistent', 'positive': None, 'negative': None}
        label = 'undetermined' if pos and neg else ('entailed' if pos else 'contradicted')
        return {'label': label, 'positive': pos, 'negative': neg}

    def find_pair(self, inst, claim, agree):
        seen = {}
        for roles in worlds(inst):
            key = tuple(roles[j] in O_EVIL for j in agree)
            v = claim_holds(claim, roles, inst['rec'])
            bucket = seen.setdefault(key, {})
            if (not v) in bucket:
                return bucket[not v], roles
            bucket.setdefault(v, roles)
        return None

    def min_reveal_sets(self, inst, claim, candidates):
        ws = [(r, claim_holds(claim, r, inst['rec'])) for r in worlds(inst)]
        if not ws:
            return None
        for k in range(len(candidates) + 1):
            found = []
            for S in combinations(candidates, k):
                groups = {}
                for r, v in ws:
                    groups.setdefault(tuple(r[j] in O_EVIL for j in S), set()).add(v)
                if all(len(g) == 1 for g in groups.values()):
                    found.append(list(S))
            if found:
                return found
        return []

    def count_worlds(self, inst):
        return sum(1 for _ in worlds(inst))


def determined_players(inst):
    """Per seat: 'evil' / 'good' / 'unknown' over all consistent worlds (None if inconsistent)."""
    seen = None
    for roles in worlds(inst):
        ev = [r in O_EVIL for r in roles]
        seen = [{e} for e in ev] if seen is None else [s | {e} for s, e in zip(seen, ev)]
    if seen is None:
        return None
    return ['unknown' if len(s) == 2 else ('evil' if True in s else 'good') for s in seen]


def possible_roles(inst, p):
    return sorted({roles[p] for roles in worlds(inst)})
