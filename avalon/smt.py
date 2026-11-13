"""Z3 encoding of the Avalon rules (see RULES.md for the clause table).

Every rule instance is a tracked constraint whose tag starts with the clause
id (e.g. 'Q-GOOD@q3:5' = "good players play Success", quest 3, seat 5), so
unsatisfiable cores read as lists of rule instances and recorded facts.
Each quest card is a Boolean variable (True = Fail); this is a different
formulation from oracle.py, which checks #Fail <= #evil on the team directly.
"""
import z3
from game import (ROLES, EVIL_ROLES, SPECIAL, EVIL_COUNT, TEAM_SIZE, DEFAULT_VARIANT,
                  fails_required)

CODE = {r: i for i, r in enumerate(ROLES)}


class SolverUnknown(RuntimeError):
    pass


def _g(b):
    return z3.BoolVal(bool(b))


class SMT:
    name = 'z3'

    def __init__(self, timeout_ms=60000):
        self.timeout = timeout_ms
        self.calls = 0

    # ------------------------------------------------------------------ encoding
    def encode(self, inst, suffix=''):
        rec, view = inst['rec'], inst.get('view')
        reveals = inst.get('reveals') or []
        variant = {**DEFAULT_VARIANT, 'check_leader': True, **inst.get('variant', {})}
        n, cfg = rec['n'], rec['config']
        R = [z3.Int(f'role{suffix}_{i}') for i in range(n)]
        E = [z3.Or([x == CODE[r] for r in EVIL_ROLES]) for x in R]
        bg = [z3.And(x >= 0, x < len(ROLES)) for x in R]
        tr = []

        def add(tag, expr):
            tr.append((tag, expr))

        add('S-SIZE', _g(n in EVIL_COUNT))
        if n not in EVIL_COUNT:
            return bg, tr, R, E
        add('S-TOTAL', _g(sum(cfg.values()) == n))
        add('S-COUNT', _g(sum(cfg.get(r, 0) for r in EVIL_ROLES) == EVIL_COUNT[n]))
        add('S-UNIQUE', _g(all(cfg.get(r, 0) <= 1 for r in SPECIAL)))
        for r in ROLES:
            add(f'S-DEAL[{r}]', z3.Sum([z3.If(x == CODE[r], 1, 0) for x in R]) == cfg.get(r, 0))

        quests = rec.get('quests', [])
        end = rec.get('end')
        wins = losses = 0
        last_leader = None
        for pos, qd in enumerate(quests):
            q = qd['q']
            add(f'R-ORDER@{pos + 1}', _g(q == pos + 1))
            if q != pos + 1:
                continue
            add(f'G-END@q{q}', _g(wins < 3 and losses < 3))
            size = TEAM_SIZE[n][q - 1]
            props = qd.get('proposals', [])
            add(f'T-HAMMER@q{q}', _g(len(props) <= 5))
            for k, p in enumerate(props):
                tag = f'q{q}.{k + 1}'
                team = p['team']
                add(f'T-SIZE@{tag}', _g(len(team) == size))
                add(f'T-DISTINCT@{tag}', _g(len(set(team)) == len(team) and all(0 <= x < n for x in team)))
                if p.get('approve') is not None:
                    add(f'T-VOTE@{tag}', _g((2 * len(set(p['approve'])) > n) == bool(p['approved'])))
                if variant['check_leader'] and last_leader is not None:
                    add(f'T-LEADER@{tag}', _g(p['leader'] == (last_leader + 1) % n))
                last_leader = p['leader']
                if p['approved'] and k != len(props) - 1:
                    add(f'T-LAST@{tag}', _g(False))
            if qd.get('result') is not None:
                team = qd['team']
                if props:
                    add(f'T-LAST@q{q}', _g(props[-1]['approved'] and sorted(props[-1]['team']) == sorted(team)))
                add(f'Q-SIZE@q{q}', _g(len(team) == size and len(set(team)) == size))
                cards = {i: z3.Bool(f'card{suffix}_{q}_{i}') for i in sorted(set(team)) if 0 <= i < n}
                for i, c in cards.items():
                    add(f'Q-GOOD@q{q}:{i}', z3.Implies(z3.Not(E[i]), z3.Not(c)))
                nf = z3.Sum([z3.If(c, 1, 0) for c in cards.values()]) if cards else z3.IntVal(0)
                f, need, failed = qd.get('fails'), fails_required(n, q), qd['result'] == 'fail'
                if variant['fail_count_public'] and f is not None:
                    add(f'Q-COUNT@q{q}', nf == f)
                    add(f'Q-RESULT@q{q}', _g((f >= need) == failed))
                else:
                    add(f'Q-RESULT@q{q}', (nf >= need) == failed)
                if failed:
                    losses += 1
                else:
                    wins += 1
            elif len(props) == 5 and not props[-1]['approved']:
                ok = pos == len(quests) - 1 and not (end and end.get('outcome') not in (None, 'evil_win'))
                add(f'T-HAMMER@q{q}:end', _g(ok))

        resolved = {qd['q'] for qd in quests if qd.get('result') is not None}
        holders, prev_q = [], 0
        for k, use in enumerate(rec.get('lady') or []):
            add(f'L-WHEN@{k + 1}', _g(use['q'] in (2, 3, 4) and use['q'] > prev_q and use['q'] in resolved))
            prev_q = use['q']
            if k == 0:
                first = quests[0]['proposals'][0]['leader'] if quests and quests[0].get('proposals') else None
                if first is not None:
                    add('L-FIRST', _g(use['holder'] == (first - 1) % n))
            else:
                add(f'L-CHAIN@{k + 1}', _g(use['holder'] == rec['lady'][k - 1]['target']))
            holders.append(use['holder'])
            add(f'L-PREV@{k + 1}', _g(use['target'] not in holders and 0 <= use['target'] < n))

        if end and end.get('outcome') is not None:
            add('G-OUTCOME', _g(not (losses >= 3 and end['outcome'] != 'evil_win')))
            a = end.get('assassinated')
            if a is not None:
                add('G-ASSASSIN', _g(wins >= 3))
                if 0 <= a < n:
                    add('G-MERLIN-HIT', (R[a] == CODE['merlin']) == _g(end['outcome'] == 'evil_win'))

        if view is not None:
            p, r = view['player'], view['role']
            seen = set(view.get('seen') or [])
            add('V-SELF', R[p] == CODE[r])
            add('K-SELF', _g(p not in seen and all(0 <= j < n for j in seen)))
            for j in range(n):
                if j == p:
                    continue
                inS = _g(j in seen)
                if r == 'merlin':
                    vis = z3.And(E[j], R[j] != CODE['mordred'])
                    if not variant['merlin_sees_oberon']:
                        vis = z3.And(vis, R[j] != CODE['oberon'])
                    add(f'K-MERLIN@{j}', vis == inS)
                elif r == 'percival':
                    add(f'K-PERCIVAL@{j}', z3.Or(R[j] == CODE['merlin'], R[j] == CODE['morgana']) == inS)
                elif r in EVIL_ROLES and r != 'oberon':
                    add(f'K-EVIL@{j}', z3.And(E[j], R[j] != CODE['oberon']) == inS)
                else:
                    add(f'K-NONE@{j}', _g(j not in seen))
            for t, ev in view.get('lady') or []:
                add(f'K-LADY@{t}', E[t] == _g(ev))
        for t, ev in reveals:
            add(f'X-REVEAL@{t}', E[t] == _g(ev))
        return bg, tr, R, E

    def claim(self, c, R, E, rec):
        t = c['t']
        cnt = lambda ps: z3.Sum([z3.If(E[i], 1, 0) for i in ps]) if ps else z3.IntVal(0)
        if t == 'evil':
            return E[c['p']]
        if t == 'good':
            return z3.Not(E[c['p']])
        if t == 'role':
            return R[c['p']] == CODE[c['r']]
        if t == 'atleast':
            return cnt(c['ps']) >= c['k']
        if t == 'exactly':
            return cnt(c['ps']) == c['k']
        if t == 'same':
            a, b = c['ps']
            return E[a] == E[b]
        if t == 'evil_set':
            S = set(c['ps'])
            return z3.And([E[i] == _g(i in S) for i in range(len(R))])
        if t == 'not':
            return z3.Not(self.claim(c['a'], R, E, rec))
        if t == 'and':
            return z3.And([self.claim(x, R, E, rec) for x in c['as']])
        if t == 'or':
            return z3.Or([self.claim(x, R, E, rec) for x in c['as']])
        if t == 'fail_by':
            return _g(c['f'] >= fails_required(rec['n'], c['q']))
        if t == 'vote_pass':
            return _g(2 * c['yes'] > rec['n'])
        if t == 'team_size':
            return _g(TEAM_SIZE[rec['n']][c['q'] - 1] == c['k'])
        raise ValueError(t)

    # ------------------------------------------------------------------ solving
    def _solver(self):
        s = z3.Solver()
        s.set(timeout=self.timeout)
        return s

    def _check(self, s, *assume):
        self.calls += 1
        r = s.check(*assume)
        if r == z3.unknown:
            raise SolverUnknown(s.reason_unknown())
        return r

    @staticmethod
    def _decode(m, R):
        return tuple(ROLES[m.eval(x, model_completion=True).as_long()] for x in R)

    def classify(self, inst, claim, explain=False):
        bg, tr, R, E = self.encode(inst)
        s = self._solver()
        s.add(*bg)
        s.add(*[e for _, e in tr])
        if self._check(s) == z3.unsat:
            out = {'label': 'inconsistent', 'positive': None, 'negative': None}
            if explain:
                out['core'] = self.core(bg, tr)
            return out
        cz = self.claim(claim, R, E, inst['rec'])
        wit = []
        for side in (cz, z3.Not(cz)):
            s.push()
            s.add(side)
            wit.append(self._decode(s.model(), R) if self._check(s) == z3.sat else None)
            s.pop()
        pos, neg = wit
        label = 'undetermined' if pos and neg else ('entailed' if pos else 'contradicted')
        out = {'label': label, 'positive': pos, 'negative': neg}
        if explain and label == 'entailed':
            out['core'] = self.core(bg, tr, z3.Not(cz))
        if explain and label == 'contradicted':
            out['core'] = self.core(bg, tr, cz)
        return out

    def core(self, bg, tr, extra=None):
        """Subset-minimal set of tracked rule instances (deletion-based)."""
        s = self._solver()
        s.add(*bg)
        if extra is not None:
            s.add(extra)
        lits = [z3.Bool(f'__t{i}') for i in range(len(tr))]
        for lit, (_, e) in zip(lits, tr):
            s.add(z3.Implies(lit, e))
        if self._check(s, *lits) != z3.unsat:
            raise AssertionError('core of a satisfiable query')
        index = {str(l): i for i, l in enumerate(lits)}
        cur = sorted(index[str(x)] for x in s.unsat_core())
        i = 0
        while i < len(cur):
            trial = cur[:i] + cur[i + 1:]
            if self._check(s, *[lits[j] for j in trial]) == z3.unsat:
                cur = trial
            else:
                i += 1
        return [tr[j][0] for j in cur]

    def find_pair(self, inst, claim, agree):
        bga, tra, Ra, Ea = self.encode(inst, '_a')
        bgb, trb, Rb, Eb = self.encode(inst, '_b')
        s = self._solver()
        s.add(*bga, *bgb, *[e for _, e in tra], *[e for _, e in trb])
        s.add(self.claim(claim, Ra, Ea, inst['rec']) != self.claim(claim, Rb, Eb, inst['rec']))
        s.add(*[Ea[j] == Eb[j] for j in agree])
        if self._check(s) == z3.unsat:
            return None
        m = s.model()
        return self._decode(m, Ra), self._decode(m, Rb)

    def determined_players(self, inst):
        """For each seat: 'evil' / 'good' / 'unknown' (or None if inconsistent)."""
        bg, tr, R, E = self.encode(inst)
        s = self._solver()
        s.add(*bg, *[e for _, e in tr])
        if self._check(s) == z3.unsat:
            return None
        out = []
        for e in E:
            s.push(); s.add(e); can_evil = self._check(s) == z3.sat; s.pop()
            s.push(); s.add(z3.Not(e)); can_good = self._check(s) == z3.sat; s.pop()
            out.append('unknown' if can_evil and can_good else ('evil' if can_evil else 'good'))
        return out

    def possible_roles(self, inst, p):
        bg, tr, R, E = self.encode(inst)
        s = self._solver()
        s.add(*bg, *[e for _, e in tr])
        out = []
        for r in ROLES:
            s.push()
            s.add(R[p] == CODE[r])
            if self._check(s) == z3.sat:
                out.append(r)
            s.pop()
        return out
