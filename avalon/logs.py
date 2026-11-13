"""Parse avalonlogs (github.com/WhoaWhoa/avalonlogs) into records, and audit
the real games against the formal rules.

  python logs.py --data ../data/avalonlogs --inspect     # schema statistics
  python logs.py --data ../data/avalonlogs --audit       # parse + rule audit

Observed schema (one JSON file per game):
  players  : [{name, uid}]                       seat order (verified by the audit)
  missions : [{teamSize, failsRequired, numFails, state, team: [name],
               proposals: [{proposer, team: [name], votes: [name], state}]}]
  outcome  : {state, message, assassinated, roles: [{name, role, assassin}], ...}
Two things are not documented and are decided from the data by the audit:
whether `votes` lists approvers or rejecters, and the direction in which
leadership passes along the `players` array.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game import normalize_role, EVIL_ROLES, TEAM_SIZE, fails_required, config_ok
import oracle as O

ROOT = Path(__file__).resolve().parents[1]


def game_files(data_dir):
    d = Path(data_dir)
    base = d / 'logs' if (d / 'logs').is_dir() else d
    return sorted(p for p in base.iterdir() if p.is_file() and not p.name.startswith('.')
                  and p.suffix.lower() not in ('.md', '.py', '.txt', '.ipynb'))


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _state(s):
    s = str(s or '').upper()
    if 'SUCC' in s:
        return 'success'
    if 'FAIL' in s:
        return 'fail'
    if 'APPROV' in s:
        return 'approved'
    if 'REJECT' in s:
        return 'rejected'
    return None


def inspect(files, limit=None):
    keys, mkeys, pkeys, okeys = Counter(), Counter(), Counter(), Counter()
    mstates, pstates, ostates, roles, ns = Counter(), Counter(), Counter(), Counter(), Counter()
    bad = 0
    for path in files[:limit]:
        try:
            g = load(path)
        except Exception:
            bad += 1
            continue
        keys.update(g.keys())
        ns[len(g.get('players', []))] += 1
        for m in g.get('missions', []):
            mkeys.update(m.keys())
            mstates[str(m.get('state'))] += 1
            for p in m.get('proposals', []):
                pkeys.update(p.keys())
                pstates[str(p.get('state'))] += 1
        o = g.get('outcome') or {}
        okeys.update(o.keys())
        ostates[str(o.get('state'))] += 1
        for r in o.get('roles', []) or []:
            roles[str(r.get('role'))] += 1
    return {'files': len(files[:limit]), 'unreadable': bad, 'top_keys': dict(keys), 'mission_keys': dict(mkeys),
            'proposal_keys': dict(pkeys), 'outcome_keys': dict(okeys), 'mission_states': dict(mstates),
            'proposal_states': dict(pstates), 'outcome_states': dict(ostates), 'roles': dict(roles),
            'players': dict(ns)}


def parse(g, votes_are='approve', reverse_seats=False, game_id=None):
    """Return (record, true_roles, issues) or (None, None, issues)."""
    issues = []
    names = [p['name'] for p in g.get('players', [])]
    n = len(names)
    if not 5 <= n <= 10 or len(set(names)) != n:
        return None, None, ['players']
    seat = {name: (-i) % n if reverse_seats else i for i, name in enumerate(names)}
    o = g.get('outcome') or {}
    try:
        rmap = {r['name']: normalize_role(r['role']) for r in o.get('roles') or []}
    except ValueError as e:
        return None, None, ['role:' + str(e)]
    if set(rmap) != set(names):
        return None, None, ['roles_missing']
    roles = [None] * n
    for name, r in rmap.items():
        roles[seat[name]] = r
    config = dict(Counter(roles))
    quests = []
    for k, m in enumerate(g.get('missions') or []):
        q = k + 1
        res = _state(m.get('state'))
        res = res if res in ('success', 'fail') else None
        props = []
        for p in m.get('proposals') or []:
            st = _state(p.get('state'))
            if st not in ('approved', 'rejected'):
                continue
            try:
                team = sorted(seat[x] for x in p.get('team') or [])
                voters = {seat[x] for x in p.get('votes') or []}
            except KeyError:
                return None, None, ['unknown_name']
            approve = sorted(voters) if votes_are == 'approve' else sorted(set(range(n)) - voters)
            props.append({'leader': seat.get(p.get('proposer'), -1), 'team': team,
                          'approve': approve, 'approved': st == 'approved'})
        if res is None:
            if len(props) == 5 and not props[-1]['approved']:
                quests.append({'q': q, 'proposals': props, 'team': [], 'fails': None, 'result': None})
            break
        try:
            team = sorted(seat[x] for x in m.get('team') or [])
        except KeyError:
            return None, None, ['unknown_name']
        if m.get('failsRequired') is not None and m['failsRequired'] != fails_required(n, q):
            issues.append('platform_failsRequired')
        if m.get('teamSize') is not None and m['teamSize'] != TEAM_SIZE[n][q - 1]:
            issues.append('platform_teamSize')
        quests.append({'q': q, 'proposals': props, 'team': team,
                       'fails': m.get('numFails'), 'result': res})
    st = str(o.get('state') or '').upper()
    outcome = 'good_win' if 'GOOD' in st else ('evil_win' if 'EVIL' in st else None)
    a = o.get('assassinated')
    end = {'assassinated': seat.get(a) if a else None, 'outcome': outcome}
    assassin = [seat[r['name']] for r in o.get('roles') or [] if r.get('assassin')]
    rec = {'n': n, 'config': config, 'quests': quests, 'end': end if outcome else None,
           'source': {'dataset': 'avalonlogs', 'game': game_id,
                      'assassin': assassin[0] if assassin else None}}
    return rec, tuple(roles), issues


def vote_semantics(games):
    """Fraction of decided proposals consistent with 'votes = approvers' vs 'votes = rejecters'."""
    a = b = tot = 0
    for g in games:
        n = len(g.get('players', []))
        for m in g.get('missions') or []:
            for p in m.get('proposals') or []:
                st = _state(p.get('state'))
                if st not in ('approved', 'rejected'):
                    continue
                k = len(set(p.get('votes') or []))
                tot += 1
                a += (2 * k > n) == (st == 'approved')
                b += (2 * (n - k) > n) == (st == 'approved')
    return {'proposals': tot, 'votes_are_approvers': a, 'votes_are_rejecters': b}


def leader_direction(games):
    plus = minus = other = 0
    for g in games:
        names = [p['name'] for p in g.get('players', [])]
        n = len(names)
        idx = {x: i for i, x in enumerate(names)}
        seq = [idx.get(p.get('proposer')) for m in g.get('missions') or [] for p in m.get('proposals') or []
               if _state(p.get('state')) in ('approved', 'rejected')]
        for x, y in zip(seq, seq[1:]):
            if x is None or y is None:
                other += 1
            elif y == (x + 1) % n:
                plus += 1
            elif y == (x - 1) % n:
                minus += 1
            else:
                other += 1
    return {'next_in_array': plus, 'previous_in_array': minus, 'other': other}


def audit(data_dir, out_dir, limit=None):
    files = game_files(data_dir)[:limit]
    games, ids = [], []
    for f in files:
        try:
            games.append(load(f))
            ids.append(f.name)
        except Exception:
            pass
    vs = vote_semantics(games)
    ld = leader_direction(games)
    votes_are = 'approve' if vs['votes_are_approvers'] >= vs['votes_are_rejecters'] else 'reject'
    reverse = ld['previous_in_array'] > ld['next_in_array']
    parsed, skipped, viol, truth_bad, platform = [], Counter(), Counter(), Counter(), Counter()
    per_game = []
    for g, gid in zip(games, ids):
        rec, roles, issues = parse(g, votes_are, reverse, gid)
        platform.update(i for i in issues if i.startswith('platform'))
        if rec is None:
            skipped[issues[0]] += 1
            continue
        if config_ok(rec['n'], rec['config']):
            skipped['config:' + ','.join(config_ok(rec['n'], rec['config']))] += 1
            continue
        v = O.record_violations(rec, {})
        viol.update(v)
        truth = O.world_ok(roles, rec, None, [], {}) if not v else None
        if truth is False:
            truth_bad['public_record'] += 1
        for p in range(rec['n']):
            from sim import true_view
            if not v and not O.world_ok(roles, rec, true_view(roles, p), [], {}):
                truth_bad['view_' + roles[p]] += 1
        per_game.append({'game': gid, 'n': rec['n'], 'violations': v, 'truth_consistent': truth})
        parsed.append({'rec': rec, 'roles': list(roles)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        'files': len(files), 'loaded': len(games), 'parsed': len(parsed), 'skipped': dict(skipped),
        'vote_semantics': vs, 'votes_interpreted_as': votes_are,
        'leader_direction': ld, 'seats_reversed': reverse,
        'platform_table_mismatch': dict(platform),
        'games_with_rule_violations': sum(1 for x in per_game if x['violations']),
        'violations_by_rule': dict(viol),
        'true_roles_inconsistent': dict(truth_bad),
        'players': dict(Counter(x['n'] for x in per_game)),
        'configs': dict(Counter(json.dumps(p['rec']['config'], sort_keys=True) for p in parsed).most_common(15)),
    }
    (out / 'audit_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'audit_games.jsonl').write_text('\n'.join(json.dumps(x) for x in per_game), encoding='utf-8')
    with open(out / 'parsed_games.jsonl', 'w', encoding='utf-8') as f:
        for p in parsed:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(ROOT / 'data' / 'avalonlogs'))
    ap.add_argument('--out', default=str(ROOT / 'results' / 'audit'))
    ap.add_argument('--inspect', action='store_true')
    ap.add_argument('--audit', action='store_true')
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    files = game_files(a.data)
    if a.inspect:
        print(json.dumps(inspect(files, a.limit), ensure_ascii=False, indent=2))
    if a.audit:
        print(json.dumps(audit(a.data, a.out, a.limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
