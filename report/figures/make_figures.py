"""Figures and summary statistics for the report.

  python report/figures/make_figures.py        (from the Project folder; needs matplotlib + z3)

Reads only results/ and avalon/; writes report/figures/fig_*.pdf|png and stats.json.

Colour semantics, identical in every figure (validated with the dataviz palette checker, CVD-safe):
  CLAY  = the solver is involved (our verifier, extraction + Z3, CEGAR)
  BLUE  = the language model on its own
  GREY  = reference values and baselines (always also told apart by line style / marker / direct label)
"""
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
PROJ = HERE.parents[1]
sys.path.insert(0, str(PROJ / 'avalon'))

# ---------------------------------------------------------------- style
FONTS = Path('C:/Windows/Fonts')           # Times New Roman, same as the draw.io overview figure (fig_overview)
for f in ('times.ttf', 'timesbd.ttf', 'timesi.ttf', 'timesbi.ttf'):
    if (FONTS / f).exists():
        font_manager.fontManager.addfont(str(FONTS / f))
INK, INK2, INK3, GRID = '#141413', '#5e5d59', '#87867f', '#e8e6dc'
CLAY, CLAY_L = '#d97757', '#f0c4b0'
BLUE, BLUE_L = '#3f7cc0', '#b5cde9'
GREY = '#6b6a65'
plt.rcParams.update({
    'font.family': 'Times New Roman', 'font.size': 8, 'mathtext.fontset': 'custom',
    'mathtext.rm': 'Times New Roman', 'mathtext.it': 'Times New Roman:italic',
    'axes.titlesize': 8.5, 'axes.titleweight': 'bold', 'axes.labelsize': 8,
    'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5, 'legend.fontsize': 7.5,
    'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'ytick.major.width': 0.6,
    'xtick.major.size': 0, 'ytick.major.size': 0, 'xtick.major.pad': 3, 'ytick.major.pad': 3,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
    'axes.edgecolor': INK3, 'xtick.color': INK2, 'ytick.color': INK2, 'axes.labelcolor': INK2,
    'text.color': INK, 'pdf.fonttype': 42, 'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03,
    'figure.dpi': 200, 'axes.titlepad': 6, 'axes.titlelocation': 'left',
})
SEQ = LinearSegmentedColormap.from_list('clay', ['#faf9f5', '#f6e6dc', '#efcbb7', '#e5a98c', '#d9875f', '#c56a42', '#a8532f'])
W = 4.8           # LNCS text width (inches)
H2 = 2.05         # height of every two-panel figure


def grid(ax, axis='y'):
    ax.grid(axis=axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def save(fig, name):
    fig.savefig(HERE / f'{name}.pdf')
    fig.savefig(HERE / f'{name}.png', dpi=220)
    plt.close(fig)


def heat(ax, M, fmt=lambda v: f'{100 * v:.0f}'):
    ax.imshow(M, cmap=SEQ, vmin=0, vmax=1, aspect='auto')
    for i, row in enumerate(M):
        for j, v in enumerate(row):
            ax.text(j, i, fmt(v), ha='center', va='center', fontsize=7.2, color='white' if v > 0.6 else INK)
    for x in range(len(M[0]) + 1):
        ax.axvline(x - 0.5, color='white', lw=1.5)
    for y in range(len(M) + 1):
        ax.axhline(y - 0.5, color='white', lw=1.5)
    for s in ax.spines.values():
        s.set_visible(False)


def jl(p):
    return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines() if x.strip()]


def boot_ci(v, seed=271, reps=2000):
    rng, n = random.Random(seed), len(v)
    ms = sorted(sum(v[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return sum(v) / n, ms[int(0.025 * reps)], ms[int(0.975 * reps) - 1]


stats = {}
R1 = PROJ / 'results/colab_run/results'

# ================================================================ real games
a12 = json.loads((R1 / 'analysis/A1_A2_deducibility.json').read_text())
order = ['minion', 'morgana', 'mordred', 'merlin', 'oberon', 'percival', 'servant', 'observer']
label = {'minion': 'Minion of Mordred', 'morgana': 'Morgana', 'mordred': 'Mordred', 'merlin': 'Merlin',
         'oberon': 'Oberon', 'percival': 'Percival', 'servant': 'Loyal Servant', 'observer': 'Public observer'}
tab = {(r['variant'], r['perspective'], r['after_quest']): r for r in a12}
fig, axes = plt.subplots(1, 2, figsize=(W, 2.3), sharey=True, gridspec_kw={'wspace': 0.06})
for ax, var, title in zip(axes, ('fails_public', 'result_only'),
                          ('a   Fail-card counts announced', 'b   Only success / fail announced')):
    heat(ax, [[tab[(var, p, k)]['mean_fraction_fixed'] for k in range(1, 6)] for p in order])
    ax.set_xticks(range(5), [str(k) for k in range(1, 6)])
    ax.set_xlabel('after quest')
    ax.set_title(title)
axes[0].set_yticks(range(len(order)), [label[p] for p in order])
save(fig, 'fig_deducibility')
stats['deducibility'] = {f'{v}/{p}/{k}': tab[(v, p, k)]['mean_fraction_fixed'] for (v, p, k) in tab}

a3 = json.loads((R1 / 'analysis/A3_assassination.json').read_text())
a4 = json.loads((R1 / 'analysis/A4_completion.json').read_text())
ns = list(range(5, 11))
byn = defaultdict(list)
for g in a3['games']:
    byn[g['n']].append(g)
hit = [sum(g['hit'] for g in byn[n]) / len(byn[n]) for n in ns]
base = [sum(1 / g['merlin_candidates'] for g in byn[n]) / len(byn[n]) for n in ns]
cnt = [len(byn[n]) for n in ns]
st4 = defaultdict(list)
for s in a4['states']:
    st4[s['n']].append(s)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(W, H2), gridspec_kw={'wspace': 0.36})
ax1.plot(ns, hit, color=BLUE, lw=1.8, marker='o', ms=4.2)
ax1.plot(ns, base, color=GREY, lw=1.4, ls=(0, (4, 2)), marker='s', ms=3.4)
ax1.text(5.0, 0.49, 'human assassins', color=BLUE, fontsize=7.2)
ax1.text(5.0, 0.03, 'random pick among the\nlogically possible Merlins', color=GREY, fontsize=7.2)
ax1.set_ylim(0, 0.55)
ax1.set_xticks(ns, [f'{n}\n({c})' for n, c in zip(ns, cnt)])
ax1.set_xlabel('players (games)')
ax1.set_ylabel('share of shots that hit Merlin')
ax1.set_title('a   The rules never single out Merlin')
grid(ax1)
cg = [sum(s['cegar_s'] for s in st4[n]) / len(st4[n]) for n in ns]
nv_n = [n for n in ns if any('naive_s' in s for s in st4[n])]
nv = [sum(s['naive_s'] for s in st4[n] if 'naive_s' in s) / sum('naive_s' in s for s in st4[n]) for n in nv_n]
ad = [sum(s['adaptive_s'] for s in st4[n] if 'adaptive_s' in s) / sum('adaptive_s' in s for s in st4[n]) for n in nv_n]
ax2.plot(ns, cg, color=CLAY, lw=1.8, marker='o', ms=4.2)
ax2.plot(nv_n, nv, color=GREY, lw=1.4, marker='s', ms=3.4)
ax2.plot(nv_n, ad, color=GREY, lw=1.4, ls=(0, (4, 2)), marker='^', ms=3.8)
ax2.set_yscale('log')
ax2.set_xticks(ns, [str(n) for n in ns])
ax2.set_xlim(4.7, 11.8)
ax2.text(7.3, ad[-1], 'adaptive\n(minimax)', color=GREY, fontsize=7.2, va='center')
ax2.text(7.3, nv[-1] * 1.35, 'subset\nenumeration', color=GREY, fontsize=7.2, va='center')
ax2.text(10.3, cg[-1], 'CEGAR', color=CLAY, fontsize=7.2, va='center', fontweight='bold')
ax2.set_xlabel('players')
ax2.set_ylabel('seconds per end-of-game state')
ax2.set_title('b   Minimum reveal set: solve time')
grid(ax2)
save(fig, 'fig_realgames')
stats['a3'] = {'by_n': {n: {'games': c, 'hit': h, 'baseline': b} for n, c, h, b in zip(ns, cnt, hit, base)},
               'overall_baseline': sum(1 / g['merlin_candidates'] for g in a3['games']) / len(a3['games']),
               **a3['summary']}
stats['a4'] = {n: {'states': len(st4[n]), 'mean_size': sum(s['cegar_size'] for s in st4[n]) / len(st4[n]),
                   'mean_cegar_calls': sum(s['cegar_calls'] for s in st4[n]) / len(st4[n]),
                   'mean_cegar_s': c, 'mean_naive_s': (nv[nv_n.index(n)] if n in nv_n else None),
                   'mean_naive_checks': (sum(s['naive_checks'] for s in st4[n] if 'naive_checks' in s)
                                         / max(1, sum('naive_checks' in s for s in st4[n]))),
                   'mean_adaptive_s': (ad[nv_n.index(n)] if n in nv_n else None),
                   'adaptive_eq_oneshot': sum(1 for s in st4[n] if s.get('adaptive_depth') == s['cegar_size']),
                   'with_adaptive': sum(1 for s in st4[n] if 'adaptive_depth' in s),
                   'naive_eq_cegar': sum(1 for s in st4[n] if 'naive_size' in s and s['naive_size'] == s['cegar_size'])}
               for n, c in zip(ns, cg)}

# ================================================================ LLM conditions
from followup import load_base, load_new, blind, by_item, formalise_all, think_traces, parse_think, BUDGETS
from llm_run import parse_label, parse_extraction
from smt import SMT
smt = SMT()
items, base_recs, meta, original = load_base(PROJ / 'results/colab_run')
new = load_new(PROJ / 'results/followup_run/results_followup/llm')
gold = {it['id']: it['gold'] for it in items}
ids = [it['id'] for it in items]
direct, extract = by_item(base_recs['initial'], 'direct'), by_item(base_recs['initial'], 'extract')
forms = formalise_all(blind(items), extract, smt)
traces, forced = think_traces(base_recs['think'], new)
pred = {'direct': {i: parse_label(direct[i]['raw'])[0] for i in ids}}
for B in BUDGETS:
    pred[f'think{B}'] = {i: parse_think(traces[B][i]['raw'])[0] for i in ids}
    pred[f'think{B}_forced'] = {i: (parse_think(forced[B][i])[0] if i in forced[B] else pred[f'think{B}'][i])
                                for i in ids}
pred['extract_solve'] = {i: forms[i].get('label', 'parse_failure') for i in ids}
for name in ('verify_flag', 'verify_evidence'):
    r = by_item(new[name])
    pred[name] = {i: (parse_label(r[i]['raw'])[0] if i in r else pred['direct'][i]) for i in ids}
for name in ('revise_flag', 'revise_evidence'):
    r = by_item(jl(R1 / f'llm/{name}_records.jsonl'))
    pred[name] = {i: (parse_label(r[i]['raw'])[0] if i in r else pred['direct'][i]) for i in ids}
acc = {k: boot_ci([int(v[i] == gold[i]) for i in ids]) for k, v in pred.items()}
stats['llm_acc_ci'] = acc

# ---- main accuracy figure: (a) dot plot with CIs, (b) recall per gold label
rows = [('Direct answer', 'direct', 'llm'),
        ('Thinking, 3,072-token budget', 'think3072', 'llm'),
        ('Thinking, 16,384-token budget', 'think16384', 'llm'),
        ('Verify, then revise (flag)', 'verify_flag', 'pipe'),
        ('Verify, then revise (evidence)', 'verify_evidence', 'pipe'),
        ('LLM translates, Z3 decides', 'extract_solve', 'pipe'),
        ('Gold-selected revise (flag)', 'revise_flag', 'oracle'),
        ('Gold-selected revise (evidence)', 'revise_evidence', 'oracle')]
fig, ax = plt.subplots(figsize=(W, 2.3))
ys = [9, 8, 7, 5.3, 4.3, 3.3, 1.4, 0.4]
for y, (lab, key, kind) in zip(ys, rows):
    m, lo, hi = acc[key]
    col = {'llm': BLUE, 'pipe': CLAY, 'oracle': INK3}[kind]
    ax.plot([lo, hi], [y, y], color=col, lw=2.0, solid_capstyle='round', alpha=0.45 if kind != 'oracle' else 0.6)
    ax.plot(m, y, 'o', ms=5.6, color=col if kind != 'oracle' else 'white', mec=col, mew=1.4)
    ax.text(hi + 0.014, y, f'{100 * m:.1f}%', va='center', fontsize=7.4,
            fontweight='bold' if key == 'extract_solve' else 'normal')
for y, txt, col in ((9.75, 'the model alone', BLUE), (6.05, 'the solver in the loop (no gold labels used)', CLAY),
                    (2.15, 'upper bounds: items to re-ask chosen with gold labels', INK3)):
    ax.text(0.205, y, txt, fontsize=7, color=col, fontweight='bold', va='center')
ax.set_yticks(ys, [r[0] for r in rows])
ax.set_ylim(0, 10.2)
ax.set_xlim(0.2, 1.06)
ax.set_xticks([0.25, 0.5, 0.75, 1.0], ['25%', '50%', '75%', '100%'])
ax.set_xlabel('accuracy on the 510 frozen items, with 95% bootstrap interval')
grid(ax, 'x')
save(fig, 'fig_llm_accuracy')

LAB = ['entailed', 'contradicted', 'undetermined', 'inconsistent']
cond = [('Direct answer', 'direct'), ('Thinking, 16k', 'think16384'), ('Verify + evidence', 'verify_evidence'),
        ('LLM translates, Z3 decides', 'extract_solve')]
M = [[sum(pred[k][i] == g for i in ids if gold[i] == g) / sum(gold[i] == g for i in ids) for g in LAB] for _, k in cond]
fig, ax = plt.subplots(figsize=(W * 0.78, 1.45))
heat(ax, M)
ax.set_xticks(range(4), ['entailed\n150 items', 'contradicted\n150 items', 'undetermined\n150 items',
                         'inconsistent\n60 items'])
ax.set_yticks(range(len(cond)), [c[0] for c in cond])
ax.xaxis.tick_top()
save(fig, 'fig_llm_recall')
stats['recall'] = {c[0]: dict(zip(LAB, row)) for c, row in zip(cond, M)}
stats['confusion'] = {k: {g: dict(Counter(pred[k][i] for i in ids if gold[i] == g)) for g in LAB}
                      for k in ('direct', 'think16384', 'extract_solve', 'verify_evidence')}

# ---- thinking budget
t16 = traces[16384]
trunc = [i for i in ids if traces[3072][i]['hit_limit']]
fin = [i for i in ids if not traces[3072][i]['hit_limit']]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(W, H2), gridspec_kw={'wspace': 0.36})
xs = list(BUDGETS)
s_acc = [acc[f'think{B}'][0] for B in BUDGETS]
f_acc = [acc[f'think{B}_forced'][0] for B in BUDGETS]
unf = [sum(traces[B][i]['hit_limit'] for i in ids) for B in BUDGETS]
ax1.axhline(acc['extract_solve'][0], color=CLAY, lw=1.4, ls=(0, (4, 2)))
ax1.text(2750, acc['extract_solve'][0] + 0.012, 'LLM translates, Z3 decides (92.0%)', color=CLAY, fontsize=7.2,
         fontweight='bold')
ax1.plot(xs, s_acc, color=BLUE, lw=1.8, marker='o', ms=4.2)
ax1.plot(xs, f_acc, color=BLUE, lw=1.4, ls=(0, (1.5, 1.5)), marker='s', ms=3.4, mfc='white')
ax1.text(3900, 0.505, 'unfinished trace\ncounts as no answer', color=BLUE, fontsize=7.2)
ax1.text(3900, 0.705, 'unfinished trace forced\nto give a verdict', color=BLUE, fontsize=7.2)
ax1.set_xscale('log', base=2)
ax1.set_xticks(xs, [f'{x:,}' for x in xs])
ax1.minorticks_off()
ax1.set_ylim(0.4, 1.0)
ax1.set_xlim(2650, 20000)
ax1.set_yticks([0.4, 0.6, 0.8, 1.0], ['40%', '60%', '80%', '100%'])
ax1.set_xlabel('thinking budget (new tokens)')
ax1.set_ylabel('accuracy')
ax1.set_title('a   Accuracy vs. thinking budget')
grid(ax1)
bk = [(0, 2048, '<2k'), (2048, 3072, '2–3k'), (3072, 4096, '3–4k'), (4096, 6144, '4–6k'), (6144, 1e9, '6k+')]
accs, ns_b = [], []
for lo, hi, _ in bk:
    sel = [i for i in ids if lo <= t16[i]['tokens'] < hi]
    ns_b.append(len(sel))
    accs.append(sum(pred['think16384'][i] == gold[i] for i in sel) / len(sel))
ax2.bar(range(len(bk)), accs, width=0.6, color=BLUE)
for j, (a, n) in enumerate(zip(accs, ns_b)):
    ax2.text(j, a + 0.025, f'{100 * a:.0f}%', ha='center', fontsize=7.2)
ax2.set_xticks(range(len(bk)), [f'{b[2]}\nn={n}' for b, n in zip(bk, ns_b)])
ax2.set_ylim(0.4, 1.0)
ax2.set_ylim(0, 1.0)
ax2.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0], ['0%', '20%', '40%', '60%', '80%', '100%'])
ax2.set_xlabel('length of the finished trace (tokens)')
ax2.set_title('b   Accuracy vs. trace length')
grid(ax2)
save(fig, 'fig_thinking')
f3 = {i: parse_think(forced[3072][i])[0] for i in trunc}
stats['thinking'] = {
    'budget': {B: {'strict': acc[f'think{B}'][0], 'forced': acc[f'think{B}_forced'][0], 'unfinished': u,
                   'parse_fail_strict': sum(pred[f'think{B}'][i] == 'parse_failure' for i in ids)}
               for B, u in zip(BUDGETS, unf)},
    'truncated_n': len(trunc), 'finished_n': len(fin),
    'truncated_forced3072_acc': sum(f3[i] == gold[i] for i in trunc) / len(trunc),
    'truncated_completed_acc': sum(pred['think16384'][i] == gold[i] for i in trunc) / len(trunc),
    'truncated_same_label': sum(f3[i] == pred['think16384'][i] for i in trunc),
    'finished_acc': sum(pred['think3072'][i] == gold[i] for i in fin) / len(fin),
    'length_buckets': {b[2]: {'n': n, 'acc': a} for b, n, a in zip(bk, ns_b, accs)},
    'gold_truncated': dict(Counter(gold[i] for i in trunc)),
    'mean_tokens_16384': sum(t16[i]['tokens'] for i in ids) / len(ids),
}

# ---- deference to the solver
fig, ax = plt.subplots(figsize=(W, 1.3))
segs = [('solver right · model follows', CLAY), ('solver right · model refuses', CLAY_L),
        ('solver wrong · model follows', GREY), ('solver wrong · model refuses', '#d3d1c7')]
defer = {}
for y, (lab, name) in zip([1, 0], [('told only “not supported”', 'verify_flag'),
                                   ('shown the solver’s evidence', 'verify_evidence')]):
    r = by_item(new[name])
    c = Counter()
    for i in r:
        v = forms[i]['label']
        p = parse_label(r[i]['raw'])[0]
        c[('solver right' if v == gold[i] else 'solver wrong') + (' · model follows' if p == v else ' · model refuses')] += 1
    defer[name] = dict(c)
    left = 0
    for seg, col in segs:
        w = c[seg]
        ax.barh(y, w, left=left, height=0.58, color=col, edgecolor='white', linewidth=1.2)
        if w >= 7:
            ax.text(left + w / 2, y, str(w), ha='center', va='center', fontsize=7.2,
                    color='white' if col in (CLAY, GREY) else INK)
        left += w
ax.set_yticks([1, 0], ['told only “not supported”', 'shown the solver’s evidence'])
ax.set_xlim(0, 276)
ax.set_xticks([0, 50, 100, 150, 200, 250, 276])
ax.set_xlabel('re-asked items: direct answer disagreed with Z3 on the model’s own extraction')
ax.legend(handles=[Patch(color=c, label=s) for s, c in segs], ncol=2, frameon=False, loc='lower left',
          bbox_to_anchor=(-0.01, 1.0), handlelength=0.9, columnspacing=1.2, fontsize=7.2)
save(fig, 'fig_deference')
stats['deference'] = defer

# ---- extraction error pattern
pat, tot = Counter(), Counter()
for it in items:
    inst, _ = parse_extraction(extract[it['id']]['raw'])
    g = {k: v for k, v in it['inst']['rec']['config'].items() if v}
    key = 'oberon+1minion,n>=7' if (g.get('oberon') and g.get('minion', 0) == 1 and it['inst']['rec']['n'] >= 7) else 'other'
    tot[key] += 1
    pat[key] += inst['rec']['config'] != g
stats['config_errors'] = {k: [pat[k], tot[k]] for k in tot}

# ---- bookkeeping for the text
stats['selfcheck_full'] = json.loads((PROJ / 'results/selfcheck_local_full/summary.json').read_text())
from cases import CASES
stats['cases'] = {'by_cat': dict(Counter(c['cat'] for c in CASES)), 'by_expect': dict(Counter(c['expect'] for c in CASES))}
stats['audit'] = json.loads((R1 / 'audit/audit_summary.json').read_text())
stats['llm_metrics_first'] = {k: v for k, v in json.loads((R1 / 'llm/metrics.json').read_text()).items()
                              if k in ('reveal', 'verification_pipeline')}
(HERE / 'stats.json').write_text(json.dumps(stats, indent=1, default=str), encoding='utf-8')
print('figures written to', HERE)
