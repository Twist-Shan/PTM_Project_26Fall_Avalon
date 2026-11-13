"""Vocabulary, tables and record format for The Resistance: Avalon.

A *record* is the public history of one game (JSON-compatible dict):

  {"n": 7,
   "config": {"merlin": 1, "percival": 1, "servant": 2, "morgana": 1, "minion": 2},
   "quests": [
      {"q": 1,
       "proposals": [{"leader": 0, "team": [2, 4], "approve": [0, 2, 3, 4], "approved": true}],
       "team": [2, 4], "fails": 0, "result": "success"},
      ...],
   "end": {"assassinated": 4, "outcome": "good_win"}}      # or null while the game runs

Players are 0..n-1 in seating (clockwise) order; they are shown to people as 1..n.
`approve` lists the players who voted to approve (null if unknown).  `fails` is
the number of Fail cards revealed (null if only the result is known).

A *view* is the private information of one player:
  {"player": 3, "role": "percival", "seen": [0, 6], "lady": [[5, false]]}
`seen` is what the setup reveal showed that player (meaning depends on the
role, see RULES.md K-*); `lady` lists Lady-of-the-Lake checks made by that player
as [target, target_is_evil].

*Reveals* are extra alignment facts used by the information-completion
analysis: [[player, is_evil], ...].
"""
import json

ROLES = ('merlin', 'percival', 'servant', 'morgana', 'mordred', 'oberon', 'minion')
GOOD_ROLES = ('merlin', 'percival', 'servant')
EVIL_ROLES = ('morgana', 'mordred', 'oberon', 'minion')
SPECIAL = ('merlin', 'percival', 'morgana', 'mordred', 'oberon')

# Rulebook tables (RULES.md S-COUNT, T-SIZE, Q-TWOFAIL)
EVIL_COUNT = {5: 2, 6: 2, 7: 3, 8: 3, 9: 3, 10: 4}
TEAM_SIZE = {5: (2, 3, 2, 3, 3), 6: (2, 3, 4, 3, 4), 7: (2, 3, 3, 4, 4),
             8: (3, 4, 4, 5, 5), 9: (3, 4, 4, 5, 5), 10: (3, 4, 4, 5, 5)}


def fails_required(n, q):
    return 2 if q == 4 and n >= 7 else 1


ZH_ROLE = {'merlin': '梅林', 'percival': '派西维尔', 'servant': '亚瑟的忠臣', 'morgana': '莫甘娜',
           'mordred': '莫德雷德', 'oberon': '奥伯伦', 'minion': '莫德雷德的爪牙'}

DEFAULT_VARIANT = {
    'fail_count_public': True,   # revealed Quest cards show how many Fails were played
    'merlin_sees_oberon': True,  # Oberon raises his thumb in the Merlin step
}


def player_label(i):
    return f'{i + 1}号'


def team_label(team):
    return '、'.join(player_label(i) for i in sorted(team))


def normalize_role(text):
    t = str(text).lower()
    for key, role in (('merlin', 'merlin'), ('percival', 'percival'), ('morgana', 'morgana'),
                      ('mordred', 'mordred'), ('oberon', 'oberon'), ('minion', 'minion'),
                      ('assassin', 'minion'), ('loyal', 'servant'), ('servant', 'servant'),
                      ('follower', 'servant'), ('resistance', 'servant'), ('spy', 'minion')):
        if key in t:
            return role
    raise ValueError(f'unknown role {text!r}')


def config_ok(n, config):
    """Static setup check (S-COUNT, S-UNIQUE); returns list of violated rule ids."""
    bad = []
    if n not in EVIL_COUNT:
        bad.append('S-SIZE')
        return bad
    if sum(config.values()) != n:
        bad.append('S-TOTAL')
    if sum(config.get(r, 0) for r in EVIL_ROLES) != EVIL_COUNT[n]:
        bad.append('S-COUNT')
    if any(config.get(r, 0) > 1 for r in SPECIAL):
        bad.append('S-UNIQUE')
    if any(r not in ROLES for r in config):
        bad.append('S-ROLE')
    return bad


def dumps(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# Chinese rendering (used for test cases and LLM inputs)
# ---------------------------------------------------------------------------
def render_config(n, config):
    parts = []
    for r in ROLES:
        c = config.get(r, 0)
        if c:
            parts.append(ZH_ROLE[r] + (f'×{c}' if c > 1 else ''))
    return f'{n}人局，角色为：' + '、'.join(parts) + f'（共{EVIL_COUNT.get(n, "?")}名坏人）。'


def render_record(rec, show_votes=False):
    lines = [render_config(rec['n'], rec['config'])]
    for qd in rec.get('quests', []):
        q = qd['q']
        if show_votes:
            for k, p in enumerate(qd.get('proposals', [])):
                s = f'第{q}轮第{k + 1}次提案：队长{player_label(p["leader"])}提名{team_label(p["team"])}'
                if p.get('approve') is not None:
                    s += f'，赞成者为{team_label(p["approve"]) or "无"}'
                s += '，通过。' if p['approved'] else '，被否决。'
                lines.append(s)
        if qd.get('result') is None:
            continue
        s = f'第{q}个任务由{team_label(qd["team"])}执行'
        if qd.get('fails') is not None:
            s += f'，翻开{qd["fails"]}张失败票'
        s += '，任务' + ('成功。' if qd['result'] == 'success' else '失败。')
        lines.append(s)
    end = rec.get('end')
    if end and end.get('assassinated') is not None:
        lines.append(f'三个任务成功后，刺客刺杀了{player_label(end["assassinated"])}，'
                     + ('好人获胜。' if end['outcome'] == 'good_win' else '坏人获胜。'))
    return '\n'.join(lines)


def render_view(view, config):
    if view is None:
        return '你是旁观者，只知道公开信息。'
    p, role = view['player'], view['role']
    s = f'你是{player_label(p)}，身份是{ZH_ROLE[role]}。'
    seen = view.get('seen') or []
    if role == 'merlin':
        s += f'开局时你看到的坏人是：{team_label(seen) or "无人"}。'
    elif role == 'percival':
        s += f'开局时你看到{team_label(seen)}' + ('（其中一人是梅林，另一人是莫甘娜，你分不清）。' if len(seen) == 2 else '是梅林。')
    elif role in EVIL_ROLES and role != 'oberon':
        s += f'开局时你看到的同伴是：{team_label(seen) or "无人"}。'
    for t, ev in view.get('lady') or []:
        s += f'你用湖中仙女查验了{player_label(t)}，其阵营为{"坏人" if ev else "好人"}。'
    return s
