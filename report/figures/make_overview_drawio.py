"""Write fig_overview.drawio (Figure 1), laid out on an exact grid.

  python report/figures/make_overview_drawio.py
  "C:/Program Files/draw.io/draw.io.exe" --export --format pdf --crop -o fig_overview.pdf fig_overview.drawio

The .drawio file stays editable in draw.io; this script is only the first layout.
Canvas is 920 px wide and is scaled to the LNCS text width (12.2 cm), so 13 px type prints at about 6.5 pt.
"""
from pathlib import Path
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
FONT = 'Times New Roman'          # system font, so draw.io export embeds it (same face as the matplotlib charts)
MONO = 'Times New Roman'
INK, INK2, INK3, RULE = '#141413', '#5E5D59', '#87867F', '#DEDCD3'
IVORY, CLAY, CLAYL, CLAYM, BLUE, TRACK = '#F5F4EE', '#D97757', '#F9ECE5', '#E49C7F', '#3F7CC0', '#ECEAE3'

cells = []


def add(value, x, y, w, h, style, edge=False, src=None, tgt=None, points=None):
    cid = f'c{len(cells) + 2}'
    if edge:
        geo = '<mxGeometry relative="1" as="geometry">'
        geo += f'<mxPoint x="{points[0][0]}" y="{points[0][1]}" as="sourcePoint"/>'
        geo += f'<mxPoint x="{points[1][0]}" y="{points[1][1]}" as="targetPoint"/></mxGeometry>'
        cells.append(f'<mxCell id="{cid}" value="" style="{style}" edge="1" parent="1">{geo}</mxCell>')
    else:
        cells.append(f'<mxCell id="{cid}" value={quoteattr(value)} style="{style}" vertex="1" parent="1">'
                     f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return cid


def base(**kw):
    s = {'html': 1, 'whiteSpace': 'wrap', 'fontFamily': FONT, 'fontSize': 14, 'fontColor': INK}
    s.update(kw)
    return ';'.join(f'{k}={v}' for k, v in s.items()) + ';'


def g(t):
    return f'<font color="{INK2}">{t}</font>'


def m(t):
    return f'<font face="{MONO}" style="font-size:14px">{t}</font>'


PANEL = dict(rounded=1, arcSize=3, strokeColor='none')
CARD = dict(rounded=1, arcSize=7, fillColor='#FFFFFF', strokeColor=RULE, strokeWidth=1, align='left',
            verticalAlign='top', spacingLeft=9, spacingRight=6, spacingTop=5)
HOT = dict(CARD, strokeColor=CLAY, strokeWidth=1.6)
HEAD = dict(text=1, align='left', verticalAlign='top', fontSize=15, fontStyle=1, fontFamily='Times New Roman',
            strokeColor='none', fillColor='none', spacing=0)
AND, NOT = '<font face="Cambria Math">∧</font>', '<font face="Cambria Math">¬</font>'
TXT = dict(text=1, align='left', verticalAlign='middle', strokeColor='none', fillColor='none', spacing=0)
ARROW = 'endArrow=blockThin;endFill=1;endSize=7;strokeColor=%s;strokeWidth=1.6;html=1;' % INK3

# ---------------------------------------------------------------- three panels (286 px, gaps 31 px)
PX = [0, 317, 634]
PW, PH = 286, 322
for x, fill, title in zip(PX, (IVORY, CLAYL, IVORY),
                          ('1&nbsp;&nbsp; What is asked', '2&nbsp;&nbsp; What the rules prove',
                           '3&nbsp;&nbsp; Why, and what to ask next')):
    add('', x, 0, PW, PH, base(fillColor=fill, **PANEL))
    add(title, x + 12, 10, PW - 24, 22, base(**HEAD))

CX = [x + 12 for x in PX]
CW, CH, ROWS = 262, 82, [40, 132, 224]          # equal cards, bottoms at 122, 214, 306

# ---------------------------------------------------------------- 1: the question
add(f'<b>A game record</b>&nbsp; {g("6 players, 2 of them evil")}<br>'
    f'{g("quest 1: seats 1–2 &nbsp;→&nbsp; one Fail card")}<br>{g("quest 2: seats 3–5 &nbsp;→&nbsp; one Fail card")}',
    CX[0], ROWS[0], CW, CH, base(**CARD))
add(f'<b>A point of view</b>&nbsp; {g("(optional)")}<br>'
    f'{g("“I am seat 6, Percival. At setup I")}<br>{g("saw seats 1 and 3.”")}',
    CX[0], ROWS[1], CW, CH, base(**CARD))
add('<b>A claim</b><br>C<sub>1</sub>&nbsp; seat 6 is good<br>C<sub>2</sub>&nbsp; the evil team is seats 1 and 3',
    CX[0], ROWS[2], CW, CH, base(**HOT))

# ---------------------------------------------------------------- 2: the verifier
enc = add(f'<b>Z3 model of 31 rule clauses</b><br>{g("every constraint keeps its clause id,")}<br>'
          f'{g("e.g. " + m("Q-GOOD@q1:2") + ", " + m("K-PERCIVAL@3"))}',
          CX[1], ROWS[0], CW, CH, base(**dict(CARD, align='center', spacingLeft=6)))
chk = add(f'<b>three satisfiability checks</b><br><i>B</i> ? &nbsp;&nbsp;&nbsp; <i>B</i> {AND} <i>C</i> ? &nbsp;&nbsp;&nbsp; '
          f'<i>B</i> {AND} {NOT}<i>C</i> ?',
          CX[1], 140, CW, 54, base(**dict(CARD, align='center', spacingLeft=6)))
mid = CX[1] + CW / 2
add('', 0, 0, 0, 0, ARROW, edge=True, points=[(mid, ROWS[0] + CH), (mid, 140)])
add('', 0, 0, 0, 0, ARROW, edge=True, points=[(mid, 194), (mid, 216)])
CHW, CHH = 128, 39
chip = dict(rounded=1, arcSize=10, align='center', verticalAlign='middle', fontSize=12.5, spacing=0)
add('<b>entailed</b><br>C<sub>1</sub>', CX[1], 224, CHW, CHH,
    base(**dict(chip, fillColor=CLAY, strokeColor='none', fontColor='#FFFFFF')))
add('<b>contradicted</b><br>C<sub>2</sub>, for Percival', CX[1] + CW - CHW, 224, CHW, CHH,
    base(**dict(chip, fillColor=CLAYM, strokeColor='none', fontColor='#FFFFFF')))
add('<b>undetermined</b><br>C<sub>2</sub>, for an observer', CX[1], 267, CHW, CHH,
    base(**dict(chip, fillColor='#FFFFFF', strokeColor=CLAY, strokeWidth=1.4)))
add(f'<b>inconsistent</b><br>{g("illegal record")}', CX[1] + CW - CHW, 267, CHW, CHH,
    base(**dict(chip, fillColor='#FFFFFF', strokeColor=INK2, strokeWidth=1.2, dashed=1, dashPattern='4 3')))

# ---------------------------------------------------------------- 3: evidence and the next question
add(f'<b>Proof of C<sub>1</sub></b>&nbsp; {g("a minimal clause core")}<br>'
    f'{g(m("S-DEAL") + ": only 2 of the 6 are evil")}<br>{g(m("Q-GOOD") + ": each Fail needs an evil player")}',
    CX[2], ROWS[0], CW, CH, base(**CARD))
add(f'<b>Counterexample for C<sub>2</sub></b> {g("(observer)")}<br>'
    f'{g("two complete, legal role assignments,")}<br>{g("one where C<sub>2</sub> holds, one where it fails")}',
    CX[2], ROWS[1], CW, CH, base(**CARD))
add(f'<b>Fewest checks that decide C<sub>2</sub></b><br>'
    f'{g("reveal seats 1 and 3: C<sub>2</sub> is settled")}<br>{g("whatever they are (CEGAR search)")}',
    CX[2], ROWS[2], CW, CH, base(**HOT))

# arrows between panels, at the height of the middle row
for x0 in (PW, PX[1] + PW):
    add('', 0, 0, 0, 0, ARROW, edge=True, points=[(x0 + 5, 173), (x0 + 26, 173)])

# ---------------------------------------------------------------- bottom strip: the two findings
BY, BH = 340, 126
add('', 0, BY, 452, BH, base(fillColor=IVORY, **PANEL))
add('', 468, BY, 452, BH, base(fillColor=IVORY, **PANEL))
add('Is the formal model faithful to the rulebook?', 12, BY + 10, 428, 22, base(**HEAD))
rows = [('1,296 / 1,296', 'verdicts agree with an independent brute-force oracle'),
        ('44 / 44', 'hand-written natural-language test cases pass'),
        ('12,447', 'real online games audited; 1 rule violation found')]
for k, (num, txt) in enumerate(rows):
    y = BY + 44 + 24 * k
    add(f'<b><font color="{CLAY}">{num}</font></b>', 12, y, 92, 20, base(**dict(TXT, align='right')))
    add(txt, 114, y, 330, 20, base(**TXT))
add(f'Who should do the reasoning?&nbsp; <font face="Times New Roman" color="{INK2}" style="font-size:14px;font-weight:normal">Qwen3-8B, 510 items</font>',
    480, BY + 10, 428, 22, base(**HEAD))
bars = [('answer directly', 0.500, BLUE, '50.0%'), ('think first (16k tokens)', 0.671, BLUE, '67.1%'),
        ('LLM translates, Z3 decides', 0.920, CLAY, '92.0%')]
LX, BX, BW = 480, 690, 168
for k, (lab, v, col, t) in enumerate(bars):
    y = BY + 44 + 24 * k
    add(lab, LX, y, BX - LX - 10, 20, base(**dict(TXT, align='right')))
    add('', BX, y + 4, BW, 12, base(fillColor=TRACK, strokeColor='none'))
    add('', BX, y + 4, round(BW * v, 1), 12, base(fillColor=col, strokeColor='none'))
    add(f'<b>{t}</b>', BX + BW + 8, y, 50, 20,
        base(**dict(TXT, fontColor=CLAY if col == CLAY else INK)))

xml = ('<mxfile host="generator"><diagram id="overview" name="Figure 1">'
       '<mxGraphModel dx="1000" dy="600" grid="0" gridSize="10" guides="1" tooltips="1" connect="0" arrows="1" '
       'fold="1" page="0" pageScale="1" pageWidth="920" pageHeight="470" math="0" shadow="0" background="#FFFFFF">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + ''.join(cells) + '</root></mxGraphModel></diagram></mxfile>')
(HERE / 'fig_overview.drawio').write_text(xml, encoding='utf-8')
print('wrote', HERE / 'fig_overview.drawio', len(cells), 'cells')
