"""Hand-written test scenarios: natural-language situation, formalisation,
a claimed conclusion, the expected verdict (derived by hand from the
rulebook) and the clauses exercised.  Seats are written 1-based in the text
and 0-based in the formalisation (helper S).

Verdicts: entailed = the claim must hold (correct answer), contradicted =
the claim cannot hold (wrong answer), undetermined = the record does not
settle it (unsupported answer), inconsistent = the record itself breaks the
rules.
"""

C5 = {'merlin': 1, 'servant': 2, 'minion': 2}
C6 = {'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'minion': 1}
C7 = {'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'mordred': 1, 'minion': 1}
C7O = {'merlin': 1, 'percival': 1, 'servant': 2, 'morgana': 1, 'oberon': 1, 'minion': 1}
C8 = {'merlin': 1, 'percival': 1, 'servant': 3, 'morgana': 1, 'mordred': 1, 'minion': 1}
C10 = {'merlin': 1, 'percival': 1, 'servant': 4, 'morgana': 1, 'mordred': 1, 'oberon': 1, 'minion': 1}


def S(*seats):
    return [s - 1 for s in seats]


def Q(q, team, fails, result=None, leader=None, n=None, proposals=None):
    """A completed quest; result defaults to the rulebook outcome."""
    from game import fails_required
    if result is None:
        result = 'fail' if fails is not None and fails >= fails_required(n, q) else 'success'
    d = {'q': q, 'team': S(*team), 'fails': fails, 'result': result}
    if proposals is not None:
        d['proposals'] = proposals
    elif leader is not None:
        d['proposals'] = [{'leader': leader - 1, 'team': S(*team), 'approved': True, 'approve': None}]
    else:
        d['proposals'] = []
    return d


def P(leader, team, approved, approve=None):
    return {'leader': leader - 1, 'team': S(*team), 'approved': approved,
            'approve': None if approve is None else S(*approve)}


def rec(n, cfg, quests=(), end=None, lady=None):
    r = {'n': n, 'config': cfg, 'quests': list(quests), 'end': end}
    if lady:
        r['lady'] = [{'q': q, 'holder': h - 1, 'target': t - 1} for q, h, t in lady]
    return r


def view(seat, role, seen=(), lady=()):
    return {'player': seat - 1, 'role': role, 'seen': S(*seen),
            'lady': [[t - 1, ev] for t, ev in lady]}


EVIL = lambda s: {'t': 'evil', 'p': s - 1}
GOOD = lambda s: {'t': 'good', 'p': s - 1}
ROLE = lambda s, r: {'t': 'role', 'p': s - 1, 'r': r}
AND = lambda *a: {'t': 'and', 'as': list(a)}
NOT = lambda a: {'t': 'not', 'a': a}
ATLEAST = lambda seats, k: {'t': 'atleast', 'ps': S(*seats), 'k': k}
EXACTLY = lambda seats, k: {'t': 'exactly', 'ps': S(*seats), 'k': k}
EVILSET = lambda *seats: {'t': 'evil_set', 'ps': S(*seats)}

ALL7 = (1, 2, 3, 4, 5, 6, 7)

CASES = [
    # ---------------- setup tables ----------------
    dict(id='T01', cat='simple', rules=['S-COUNT', 'S-DEAL'],
         text='7人局，角色为梅林、派西维尔、忠臣×2、莫甘娜、莫德雷德、爪牙。问：本局有几名坏人？答：3名。',
         inst={'rec': rec(7, C7)}, claim=EXACTLY(ALL7, 3), expect='entailed'),
    dict(id='T02', cat='simple', rules=['S-COUNT', 'S-DEAL'],
         text='同上。答：2名坏人。', inst={'rec': rec(7, C7)}, claim=EXACTLY(ALL7, 2), expect='contradicted'),
    dict(id='T03', cat='inconsistent', rules=['S-COUNT'],
         text='6人局却配置了莫甘娜、莫德雷德、爪牙三名坏人。问：1号是好人吗？答：是。',
         inst={'rec': rec(6, {'merlin': 1, 'servant': 2, 'morgana': 1, 'mordred': 1, 'minion': 1})},
         claim=GOOD(1), expect='inconsistent'),
    dict(id='T04', cat='simple', rules=['T-SIZE'],
         text='8人局第1个任务需要几人出队？答：3人。', inst={'rec': rec(8, C8)},
         claim={'t': 'team_size', 'q': 1, 'k': 3}, expect='entailed'),
    dict(id='T05', cat='boundary', rules=['T-SIZE'],
         text='5人局第3个任务需要几人出队？答：3人。', inst={'rec': rec(5, C5)},
         claim={'t': 'team_size', 'q': 3, 'k': 3}, expect='contradicted'),
    dict(id='T06', cat='inconsistent', rules=['Q-SIZE'],
         text='5人局第1个任务由1、2、3号三人执行，0张失败票。问：4号是好人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2, 3), 0, n=5)])}, claim=GOOD(4), expect='inconsistent'),
    # ---------------- two-fail rule ----------------
    dict(id='T07', cat='boundary', rules=['Q-TWOFAIL'],
         text='7人局第4个任务翻开1张失败票。问：任务失败了吗？答：失败。', inst={'rec': rec(7, C7)},
         claim={'t': 'fail_by', 'q': 4, 'f': 1}, expect='contradicted'),
    dict(id='T08', cat='boundary', rules=['Q-TWOFAIL'],
         text='6人局第4个任务翻开1张失败票。问：任务失败了吗？答：失败。', inst={'rec': rec(6, C6)},
         claim={'t': 'fail_by', 'q': 4, 'f': 1}, expect='entailed'),
    dict(id='T09', cat='boundary', rules=['Q-TWOFAIL'],
         text='7人局第4个任务翻开2张失败票。问：任务失败了吗？答：失败。', inst={'rec': rec(7, C7)},
         claim={'t': 'fail_by', 'q': 4, 'f': 2}, expect='entailed'),
    dict(id='T10', cat='boundary', rules=['Q-TWOFAIL'],
         text='7人局第3个任务翻开1张失败票。问：任务失败了吗？答：失败。', inst={'rec': rec(7, C7)},
         claim={'t': 'fail_by', 'q': 3, 'f': 1}, expect='entailed'),
    dict(id='T11', cat='inconsistent', rules=['Q-RESULT', 'Q-TWOFAIL'],
         text='7人局记录：前三个任务正常，第4个任务4人出队、1张失败票，却被记为失败。问：1号是坏人吗？答：是。',
         inst={'rec': rec(7, C7, [Q(1, (1, 2), 0, n=7), Q(2, (1, 2, 3), 0, n=7), Q(3, (1, 2, 4), 1, n=7),
                                   Q(4, (1, 2, 3, 4), 1, result='fail', n=7)])},
         claim=EVIL(1), expect='inconsistent'),
    # ---------------- voting ----------------
    dict(id='T12', cat='boundary', rules=['T-VOTE'],
         text='6人局，提案得到3票赞成。问：提案通过了吗？答：通过。', inst={'rec': rec(6, C6)},
         claim={'t': 'vote_pass', 'yes': 3}, expect='contradicted'),
    dict(id='T13', cat='boundary', rules=['T-VOTE'],
         text='7人局，提案得到4票赞成。问：提案通过了吗？答：通过。', inst={'rec': rec(7, C7)},
         claim={'t': 'vote_pass', 'yes': 4}, expect='entailed'),
    dict(id='T14', cat='inconsistent', rules=['T-VOTE'],
         text='8人局第1轮：队长1号提名1、2、3号，赞成者为1、2、3、4号，记为通过。问：5号是好人吗？答：是。',
         inst={'rec': rec(8, C8, [{'q': 1, 'team': S(1, 2, 3), 'fails': 0, 'result': 'success',
                                    'proposals': [P(1, (1, 2, 3), True, approve=(1, 2, 3, 4))]}])},
         claim=GOOD(5), expect='inconsistent'),
    dict(id='T15', cat='inconsistent', rules=['T-HAMMER'],
         text='5人局第1轮连续5次提案都被否决，但随后第2轮仍继续进行。问：1号是好人吗？答：是。',
         inst={'rec': rec(5, C5, [{'q': 1, 'team': [], 'fails': None, 'result': None,
                                    'proposals': [P(k, (k, k % 5 + 1), False) for k in range(1, 6)]},
                                   {'q': 2, 'team': S(1, 2, 3), 'fails': 0, 'result': 'success',
                                    'proposals': [P(1, (1, 2, 3), True)]}])},
         claim=GOOD(1), expect='inconsistent'),
    dict(id='T16', cat='inconsistent', rules=['T-LEADER'],
         text='6人局第1轮：1号提案被否决后，下一次提案的队长是3号。问：1号是好人吗？答：是。',
         inst={'rec': rec(6, C6, [{'q': 1, 'team': S(3, 4), 'fails': 0, 'result': 'success',
                                    'proposals': [P(1, (1, 2), False), P(3, (3, 4), True)]}])},
         claim=GOOD(1), expect='inconsistent'),
    # ---------------- deductions from quests ----------------
    dict(id='T17', cat='simple', rules=['Q-GOOD', 'Q-COUNT'],
         text='5人局第1个任务由1、2号执行，翻开2张失败票。问：1号和2号都是坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 2, n=5)])}, claim=AND(EVIL(1), EVIL(2)), expect='entailed'),
    dict(id='T18', cat='combination', rules=['Q-GOOD', 'Q-COUNT', 'S-COUNT'],
         text='同上。问：3号是好人吗？答：是（坏人只有2名，已全部在队中）。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 2, n=5)])}, claim=GOOD(3), expect='entailed'),
    dict(id='T19', cat='simple', rules=['Q-GOOD', 'Q-COUNT'],
         text='5人局第1个任务由1、2号执行，翻开1张失败票。问：队里恰好有一个坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 1, n=5)])}, claim=EXACTLY((1, 2), 1), expect='undetermined'),
    dict(id='T20', cat='simple', rules=['Q-GOOD', 'Q-COUNT'],
         text='同上。问：队里至少有一个坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 1, n=5)])}, claim=ATLEAST((1, 2), 1), expect='entailed'),
    dict(id='T21', cat='simple', rules=['Q-GOOD'],
         text='5人局第1个任务由1、2号执行，0张失败票，任务成功。问：1号和2号都是好人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 0, n=5)])}, claim=AND(GOOD(1), GOOD(2)), expect='undetermined'),
    dict(id='T22', cat='combination', rules=['Q-COUNT', 'S-COUNT'],
         text='7人局第2个任务由1、2、3号执行，翻开3张失败票。问：4到7号都是好人吗？答：是。',
         inst={'rec': rec(7, C7, [Q(1, (4, 5), 0, n=7), Q(2, (1, 2, 3), 3, n=7)])},
         claim=AND(*[GOOD(s) for s in (4, 5, 6, 7)]), expect='entailed'),
    dict(id='T23', cat='combination', rules=['Q-COUNT', 'S-COUNT'],
         text='6人局：第1个任务（1、2号）1张失败票；第2个任务（3、4、5号）1张失败票。问：6号是好人吗？答：是。',
         inst={'rec': rec(6, C6, [Q(1, (1, 2), 1, n=6), Q(2, (3, 4, 5), 1, n=6)])},
         claim=GOOD(6), expect='entailed'),
    dict(id='T24', cat='combination', rules=['Q-COUNT', 'S-COUNT'],
         text='同上。问：1号是坏人吗？答：是。',
         inst={'rec': rec(6, C6, [Q(1, (1, 2), 1, n=6), Q(2, (3, 4, 5), 1, n=6)])},
         claim=EVIL(1), expect='undetermined'),
    dict(id='T25', cat='inconsistent', rules=['Q-COUNT', 'S-COUNT'],
         text='6人局：第1个任务（1、2号）2张失败票；第2个任务（3、4、5号）1张失败票。问：6号是好人吗？答：是。',
         inst={'rec': rec(6, C6, [Q(1, (1, 2), 2, n=6), Q(2, (3, 4, 5), 1, n=6)])},
         claim=GOOD(6), expect='inconsistent'),
    # ---------------- private knowledge ----------------
    dict(id='T26', cat='perspective', rules=['K-MERLIN', 'S-DEAL'],
         text='7人局（含莫德雷德）。你是1号梅林，开局看到3号、5号是坏人。问：坏人就是3号和5号吗？答：是。',
         inst={'rec': rec(7, C7), 'view': view(1, 'merlin', (3, 5))}, claim=EVILSET(3, 5), expect='contradicted'),
    dict(id='T27', cat='perspective', rules=['K-MERLIN', 'S-COUNT'],
         text='同上。问：2、4、6、7号中恰好还有一名坏人吗？答：是（莫德雷德对梅林隐藏）。',
         inst={'rec': rec(7, C7), 'view': view(1, 'merlin', (3, 5))}, claim=EXACTLY((2, 4, 6, 7), 1), expect='entailed'),
    dict(id='T28', cat='combination', rules=['K-MERLIN', 'Q-COUNT', 'S-COUNT'],
         text='同上，另外第1个任务由2、4号执行，翻开1张失败票。问：6号和7号都是好人吗？答：是。',
         inst={'rec': rec(7, C7, [Q(1, (2, 4), 1, n=7)]), 'view': view(1, 'merlin', (3, 5))},
         claim=AND(GOOD(6), GOOD(7)), expect='entailed'),
    dict(id='T29', cat='perspective', rules=['K-PERCIVAL'],
         text='7人局。你是2号派西维尔，开局看到4号和6号（梅林与莫甘娜）。问：4号是梅林吗？答：是。',
         inst={'rec': rec(7, C7), 'view': view(2, 'percival', (4, 6))}, claim=ROLE(4, 'merlin'), expect='undetermined'),
    dict(id='T30', cat='combination', rules=['K-PERCIVAL', 'Q-COUNT'],
         text='同上，另外第1个任务由4、7号执行，翻开2张失败票。问：6号是梅林吗？答：是。',
         inst={'rec': rec(7, C7, [Q(1, (4, 7), 2, n=7)]), 'view': view(2, 'percival', (4, 6))},
         claim=ROLE(6, 'merlin'), expect='entailed'),
    dict(id='T31', cat='perspective', rules=['K-EVIL', 'S-COUNT'],
         text='7人局（含奥伯伦）。你是3号爪牙，开局只看到5号一名同伴。问：坏人只有你和5号吗？答：是。',
         inst={'rec': rec(7, C7O), 'view': view(3, 'minion', (5,))}, claim=EVILSET(3, 5), expect='contradicted'),
    dict(id='T32', cat='perspective', rules=['K-EVIL'],
         text='同上。问：1号是好人吗？答：是。',
         inst={'rec': rec(7, C7O), 'view': view(3, 'minion', (5,))}, claim=GOOD(1), expect='undetermined'),
    dict(id='T33', cat='combination', rules=['V-SELF', 'Q-COUNT', 'S-COUNT'],
         text='5人局。你是1号忠臣。第1个任务由2、3号执行，翻开2张失败票。问：4号和5号都是好人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (2, 3), 2, n=5)]), 'view': view(1, 'servant')},
         claim=AND(GOOD(4), GOOD(5)), expect='entailed'),
    dict(id='T34', cat='inconsistent', rules=['K-PERCIVAL'],
         text='7人局。你是2号派西维尔，开局看到了3号、4号、6号三个人。问：3号是梅林吗？答：是。',
         inst={'rec': rec(7, C7), 'view': view(2, 'percival', (3, 4, 6))}, claim=ROLE(3, 'merlin'),
         expect='inconsistent'),
    dict(id='T35', cat='inconsistent', rules=['V-SELF', 'Q-GOOD', 'Q-COUNT'],
         text='5人局。你是1号忠臣，和2号一起执行第1个任务，翻开2张失败票。问：2号是坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 2, n=5)]), 'view': view(1, 'servant')},
         claim=EVIL(2), expect='inconsistent'),
    # ---------------- end of game ----------------
    dict(id='T36', cat='simple', rules=['G-MERLIN-HIT'],
         text='5人局，前三个任务成功；刺客刺杀4号后好人获胜。问：4号不是梅林吗？答：不是梅林。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 0, n=5), Q(2, (1, 2, 3), 0, n=5), Q(3, (1, 3), 0, n=5)],
                          end={'assassinated': 3, 'outcome': 'good_win'})},
         claim=NOT(ROLE(4, 'merlin')), expect='entailed'),
    dict(id='T37', cat='simple', rules=['G-MERLIN-HIT'],
         text='同样的任务结果，但刺杀4号后坏人获胜。问：4号是梅林吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 0, n=5), Q(2, (1, 2, 3), 0, n=5), Q(3, (1, 3), 0, n=5)],
                          end={'assassinated': 3, 'outcome': 'evil_win'})},
         claim=ROLE(4, 'merlin'), expect='entailed'),
    dict(id='T38', cat='inconsistent', rules=['G-ASSASSIN'],
         text='5人局只成功了两个任务，刺客就开始刺杀。问：4号是梅林吗？答：否。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 0, n=5), Q(2, (1, 2, 3), 0, n=5)],
                          end={'assassinated': 3, 'outcome': 'good_win'})},
         claim=NOT(ROLE(4, 'merlin')), expect='inconsistent'),
    dict(id='T39', cat='inconsistent', rules=['G-END'],
         text='5人局前三个任务都失败后，记录里还有第4个任务。问：1号是坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 1, n=5), Q(2, (1, 2, 3), 1, n=5), Q(3, (1, 3), 1, n=5),
                                   Q(4, (1, 2, 3), 0, n=5)])},
         claim=EVIL(1), expect='inconsistent'),
    # ---------------- Lady of the Lake ----------------
    dict(id='T40', cat='perspective', rules=['K-LADY'],
         text='8人局。你是1号忠臣，用湖中仙女查验4号，结果为好人。问：4号是好人吗？答：是。',
         inst={'rec': rec(8, C8), 'view': view(1, 'servant', (), lady=((4, False),))}, claim=GOOD(4),
         expect='entailed'),
    dict(id='T41', cat='inconsistent', rules=['L-PREV', 'L-CHAIN'],
         text='8人局首位队长1号，湖中仙女在8号手中。第2轮后8号查验3号；第3轮后3号又查验8号。问：3号是好人吗？答：是。',
         inst={'rec': rec(8, C8, [Q(1, (1, 2, 3), 0, leader=1, n=8), Q(2, (1, 2, 3, 4), 0, leader=2, n=8),
                                   Q(3, (1, 2, 3, 5), 0, leader=3, n=8)],
                          lady=[(2, 8, 3), (3, 3, 8)])},
         claim=GOOD(3), expect='inconsistent'),
    # ---------------- encoding variants ----------------
    dict(id='T42', cat='variant', rules=['Q-COUNT', 'V-FAILCOUNT'],
         text='（只公开任务结果、不公开失败票数的读法）5人局第1个任务由1、2号执行并失败。问：1号和2号都是坏人吗？答：是。',
         inst={'rec': rec(5, C5, [Q(1, (1, 2), 2, n=5)]), 'variant': {'fail_count_public': False}},
         claim=AND(EVIL(1), EVIL(2)), expect='undetermined'),
    dict(id='T43', cat='variant', rules=['K-MERLIN', 'V-OBERON'],
         text='10人局（含莫德雷德、奥伯伦）。你是1号梅林，开局看到3、5、7号三名坏人。问：2、4、6、8、9、10号中恰好还有一名坏人吗？答：是。',
         inst={'rec': rec(10, C10), 'view': view(1, 'merlin', (3, 5, 7))},
         claim=EXACTLY((2, 4, 6, 8, 9, 10), 1), expect='entailed'),
    dict(id='T44', cat='variant', rules=['K-MERLIN', 'V-OBERON'],
         text='同上，但按“奥伯伦不向梅林显示”的读法。答：是。',
         inst={'rec': rec(10, C10), 'view': view(1, 'merlin', (3, 5, 7)), 'variant': {'merlin_sees_oberon': False}},
         claim=EXACTLY((2, 4, 6, 8, 9, 10), 1), expect='inconsistent'),
]
