# Report plan (LNCS, XeLaTeX, English) — handoff for writing main.tex

**Title.** What Do the Rules Prove? Verifying Claims in *The Resistance: Avalon* with a Constraint Solver

**Core thesis (one sentence).** A rulebook can be compiled into a verifier that says what a game record proves, why, and which single check would settle the rest; a language model is most useful as the *translator* into that verifier — not as the reasoner, and not as the judge of the solver.

**Style.** Anthropic-research-post voice: lead with the finding, plain words, takeaway-style headings and captions. Figure colours: clay = solver involved, blue = LLM alone, grey = reference. Fonts in figures: Segoe UI.

## Figures (all in `report/figures/`, regenerate with `make_figures.py`; Fig. 1 with `make_overview_drawio.py` + draw.io export)
| Fig | File | Takeaway caption |
|---|---|---|
| 1 | fig_overview.pdf (editable: fig_overview.drawio) | What we built and what we found |
| 2 | fig_deducibility.pdf | Rules settle little for the good side; hiding Fail counts erases most of it |
| 3 | fig_realgames.pdf | Rules never single out Merlin (0/387); humans beat rules-only guess 38.5% vs 25.3%; CEGAR scales, enumeration/adaptive don't |
| 4 | fig_llm_accuracy.pdf (+ fig_llm_recall.pdf) | Translate, don't reason: 50.0 / 67.1 / 92.0 |
| 5 | fig_thinking.pdf | More budget removes truncation, not errors |
| 6 | fig_deference.pdf | The model follows the solver even when the solver is wrong (37/39) |

Tables: `tables/cases_table.tex` (44 cases, generated, longtable — needs `longtable`, `booktabs`, `ctex[scheme=plain]`).

## Sections
1. Introduction — hook (one Fail card: is seat 1 evil?), Q1–Q4, Fig. 1, key-findings box.
2. Material & scope — rulebook groups; Table 1: 31 clauses (from RULES.md: S-SIZE, S-COUNT, S-TOTAL, S-UNIQUE, S-DEAL; V-SELF, K-EVIL, K-MERLIN, K-PERCIVAL, K-NONE, K-SELF, K-LADY; T-LEADER, T-SIZE, T-DISTINCT, T-VOTE, T-HAMMER, T-LAST; Q-SIZE, Q-GOOD, Q-COUNT, Q-RESULT/TWOFAIL, R-ORDER; G-END, G-OUTCOME, G-ASSASSIN, G-MERLIN-HIT; L-WHEN, L-FIRST, L-CHAIN, L-PREV); not formalised (speech, votes — proven uninformative 246/246, Targeting); Table 2 readings V-FAILCOUNT (T17 vs T42), V-OBERON (T43 vs T44), L-FIRST, T-LEADER.
3. From rules to a verifier — variables role_i, fail_{q,i}; clause-tagged encoding; 4 verdicts via B?, B∧C?, B∧¬C? (inconsistent must be checked first, else vacuous truth); `unknown` never occurred (60 s limit); evidence = deletion-minimised core / two witness worlds (choice depends on Z3 history). Worked example box: 6 players, Q1 {1,2} 1 Fail, Q2 {3,4,5} 1 Fail. C1 "seat 6 good" entailed, core of 10 instances (S-DEAL[merlin, percival, servant], Q-GOOD×5, Q-COUNT×2). C2 "evil = {1,3}" undetermined; w+=(Morgana,Servant,Minion,Servant,Merlin,Percival), w−=(Servant,Minion,Morgana,Servant,Merlin,Percival); min reveal {1,3} (also {2,3}), CEGAR 3 rounds / 6 calls, cuts {1,2},{3,4}; as Percival seeing {1,3}: contradicted. Q1 with 2 Fails → inconsistent, same core.
4. Minimum information completion — two-world test; S sufficient ⇔ S hits every Δ(w,w′); CEGAR implicit hitting set (Algorithm 1) + generalisation; optimality argument; adaptive minimax ≤ one-shot.
5. Faithfulness — oracle (different encoding, re-typed tables); 44 cases (simple 9, boundary 7, combination 7, view 6, illegal 12, variant 3; ent 19 / con 6 / und 6 / inc 13); random 432 instances, 1,296/1,296 agree + sound; corrupted 60/60; min-reveal 44/44 (7 none); audit 12,447 games: votes = approvers (88,302/88,302), leader in array order (75,855/75,855), 1 Q-RESULT violation, 2 platform failsRequired mismatches, true roles never excluded.
6. Real games (600 sampled, seed 271) — Minion 96→98%, Merlin 62→81%, Servant 1→10% (2% if counts hidden), observer 0→8% (0%); assassination 387 games, mean 4.22 candidates, unique 0%, hit 38.5% vs 25.3%, 2 shots outside candidates; A4 150 states, CEGAR size 1.8 (5p)…4.0 (10p), 0.12→0.88 s, enumeration agrees 108/108, adaptive = one-shot 108/108.
7. LLM study (Qwen3-8B rev b968826, 510 items from 510 games, 150/150/150/60, RTX PRO 6000) —
   acc / macro-F1: direct 50.0/.370; think3072 strict 47.6/.504; think3072 forced 67.1/.617; think8192 66.9; think16384 67.1/.612; extract+Z3 92.0/.908; repair 92.0 (85 triggered = 60 inc + 25 false, 0 changed); verify-flag 65.3/.506; verify-evidence 89.2/.880; repaired 89.0; gold-selected flag 70.0/.544, evidence 96.9/.968.
   CIs: direct [45.9,54.5]; think16k [62.7,71.4]; extract [89.6,94.3]; verify-evidence [86.5,91.8]. Paired: extract−direct +42.0 [36.9,47.1]; extract−think16k +24.9 [20.2,30.0]; think16k−direct +17.1 [12.2,22.0]; verify-evidence−extract −2.7 [−4.3,−1.4].
   Direct never says inconsistent (0/60), calls 115/150 contradicted items undetermined. Thinking: 206 cut at 3,072; 2 at 8,192; 0 at 16,384; truncated items 49.0% forced vs 49.0% completed (135/206 same label); finished-early items 79.3%; by length <2k 86.5% (163), 2–3k 70.9% (141), 3–4k 52.5% (99), 4–6k 48.0% (98), ≥6k 22.2% (9); 13 answers-with-explanation → first-line parse 68.8% (sensitivity).
   Extraction: 455/510 exact; quests 510/510; config 483; claim 482. Config errors 27/31 for Oberon + exactly one Minion, n≥7, vs 0/479 otherwise (model adds a Minion — does not count Oberon as evil); every config error ⇒ inconsistent (25 false). Claim errors invisible to solver ("must be Merlin" → "is good").
   Deference: re-asked 276 (253/255 wrong + 23/255 right flagged); kept own answer 0/276; flag: followed solver 95/237 right, 8/39 wrong; evidence: 222/237 right, 37/39 wrong. LLM reveal proposals: 99/122 sufficient, 35 optimal, 2 invalid, +0.96 excess.
8. Limitations — templated text; gold from our model; one model/seed; Z3 evidence choice history-dependent (prompts reconstructed exactly, `results/followup_run/reconstructed_jobs/`); Lady absent from logs.
9. Related work — Bedrock AR checks; Logic-LM, SatLM, LINC, DTV; MUS (Liffiton & Sakallah), QuickXplain; implicit hitting sets (Davies & Bacchus), CEGAR/CEGIS; DeepRole (Serrino et al.), AvalonBench, Stepputtis et al.; s1 budget forcing; self-correction (Huang et al.), sycophancy (Sharma et al.).
10. Conclusion — "let the model translate, let the solver decide, and show people the solver's evidence."
11. **Answers to the course questions — placeholder only. The author must type this section personally; no AI text.**
Appendix A: cases_table.tex. Appendix B: rule card + extraction prompt (verbatim, Chinese). Appendix C: code map, commands, hashes, hardware.
