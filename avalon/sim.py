"""Random legal Avalon games (for cross-checking and synthetic tasks)."""
import random
from game import EVIL_ROLES, EVIL_COUNT, TEAM_SIZE, fails_required

CONFIGS = {
    5: [{'merlin': 1, 'servant': 2, 'minion': 2},
        {'merlin': 1, 'percival': 1, 'servant': 1, 'morgana': 1, 'minion': 1}],
    6: [{'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'minion': 1},
        {'merlin': 1, 'servant': 3, 'minion': 2}],
    7: [{'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'mordred': 1, 'minion': 1},
        {'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'oberon': 1, 'minion': 1}],
    8: [{'merlin': 1, 'percival': 1, 'servant': 3, 'morgana': 1, 'mordred': 1, 'minion': 1}],
    9: [{'merlin': 1, 'percival': 1, 'servant': 4, 'morgana': 1, 'mordred': 1, 'minion': 1}],
    10: [{'merlin': 1, 'percival': 1, 'servant': 4, 'morgana': 1, 'mordred': 1, 'oberon': 1, 'minion': 1}],
}


def deal(rng, config):
    roles = [r for r, c in config.items() for _ in range(c)]
    rng.shuffle(roles)
    return tuple(roles)


def play(rng, n=None, config=None, p_fail=0.65, p_approve=0.5, lady=None):
    n = n or rng.choice(sorted(CONFIGS))
    config = config or rng.choice(CONFIGS[n])
    roles = deal(rng, config)
    evil = [r in EVIL_ROLES for r in roles]
    leader = rng.randrange(n)
    first_leader = leader
    quests, wins, losses = [], 0, 0
    end = None
    for q in range(1, 6):
        size = TEAM_SIZE[n][q - 1]
        props = []
        team = None
        for k in range(5):
            t = sorted(rng.sample(range(n), size))
            approve = sorted(i for i in range(n) if rng.random() < p_approve)
            ok = 2 * len(approve) > n
            if k == 4 and not ok:
                pass
            props.append({'leader': leader, 'team': t, 'approve': approve, 'approved': ok})
            leader = (leader + 1) % n
            if ok:
                team = t
                break
        if team is None:  # five rejections: evil wins
            quests.append({'q': q, 'proposals': props, 'team': [], 'fails': None, 'result': None})
            end = {'assassinated': None, 'outcome': 'evil_win'}
            break
        fails = sum(1 for i in team if evil[i] and rng.random() < p_fail)
        failed = fails >= fails_required(n, q)
        quests.append({'q': q, 'proposals': props, 'team': team, 'fails': fails,
                       'result': 'fail' if failed else 'success'})
        losses += failed
        wins += not failed
        if losses == 3:
            end = {'assassinated': None, 'outcome': 'evil_win'}
            break
        if wins == 3:
            target = rng.choice([i for i in range(n) if not evil[i]])
            end = {'assassinated': target,
                   'outcome': 'evil_win' if roles[target] == 'merlin' else 'good_win'}
            break
    rec = {'n': n, 'config': dict(config), 'quests': quests, 'end': end}
    if lady:
        holder = (first_leader - 1) % n
        used, uses = {holder}, []
        for qd in quests:
            if qd['q'] in (2, 3, 4) and qd.get('result') is not None:
                choices = [i for i in range(n) if i not in used]
                t = rng.choice(choices)
                uses.append({'q': qd['q'], 'holder': holder, 'target': t})
                used.add(t)
                holder = t
        rec['lady'] = uses
    return rec, roles


def true_view(roles, p, variant=None, rec=None):
    variant = variant or {}
    n, r = len(roles), roles[p]
    if r == 'merlin':
        seen = [j for j in range(n) if j != p and roles[j] in EVIL_ROLES and roles[j] != 'mordred'
                and (variant.get('merlin_sees_oberon', True) or roles[j] != 'oberon')]
    elif r == 'percival':
        seen = [j for j in range(n) if j != p and roles[j] in ('merlin', 'morgana')]
    elif r in EVIL_ROLES and r != 'oberon':
        seen = [j for j in range(n) if j != p and roles[j] in EVIL_ROLES and roles[j] != 'oberon']
    else:
        seen = []
    lady = []
    if rec is not None:
        for use in rec.get('lady') or []:
            if use['holder'] == p:
                lady.append([use['target'], roles[use['target']] in EVIL_ROLES])
    return {'player': p, 'role': r, 'seen': seen, 'lady': lady}


def prefix(rec, k):
    """Public record after the first k quests (no end information)."""
    return {**rec, 'quests': rec['quests'][:k], 'end': None,
            'lady': [u for u in rec.get('lady') or [] if u['q'] <= k] if 'lady' in rec else None}


def random_claim(rng, n):
    kind = rng.choice(['evil', 'good', 'role', 'atleast', 'exactly', 'same', 'and', 'not'])
    p = rng.randrange(n)
    if kind in ('evil', 'good'):
        return {'t': kind, 'p': p}
    if kind == 'role':
        return {'t': 'role', 'p': p, 'r': rng.choice(['merlin', 'percival', 'morgana', 'mordred', 'servant', 'minion', 'oberon'])}
    if kind in ('atleast', 'exactly'):
        ps = sorted(rng.sample(range(n), rng.randint(2, min(4, n))))
        return {'t': kind, 'ps': ps, 'k': rng.randint(0, len(ps))}
    if kind == 'same':
        a, b = rng.sample(range(n), 2)
        return {'t': 'same', 'ps': [a, b]}
    if kind == 'and':
        a, b = rng.sample(range(n), 2)
        return {'t': 'and', 'as': [{'t': 'evil', 'p': a}, {'t': 'good', 'p': b}]}
    return {'t': 'not', 'a': {'t': 'role', 'p': p, 'r': 'merlin'}}


def corrupt(rng, rec):
    """Introduce one rule violation (for inconsistent-record tests)."""
    import copy
    r = copy.deepcopy(rec)
    done = [qd for qd in r['quests'] if qd.get('result') is not None]
    if not done:
        r['config'] = {**r['config'], 'minion': r['config'].get('minion', 0) + 1}
        return r, 'S-TOTAL'
    qd = rng.choice(done)
    kind = rng.choice(['fails_over', 'size', 'result', 'vote'])
    if kind == 'fails_over':
        qd['fails'] = len(qd['team']) + 1
        return r, 'Q-COUNT'
    if kind == 'size':
        extra = [i for i in range(r['n']) if i not in qd['team']]
        qd['team'] = sorted(qd['team'] + extra[:1])
        if qd['proposals']:
            qd['proposals'][-1]['team'] = list(qd['team'])
        return r, 'Q-SIZE'
    if kind == 'result':
        qd['result'] = 'success' if qd['result'] == 'fail' else 'fail'
        return r, 'Q-RESULT'
    p = qd['proposals'][-1]
    p['approve'] = p['approve'][: r['n'] // 2]
    return r, 'T-VOTE'
