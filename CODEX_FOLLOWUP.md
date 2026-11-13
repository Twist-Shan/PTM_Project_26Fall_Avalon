# 执行说明：阿瓦隆后续实验（给 Codex）

项目目录：本文件所在的 `Project` 文件夹。第一次实验已完成（见 `RUN_REPORT.md`）。这次在**同一套冻结题集和第一次运行的原始输出**上补做后续实验，不重建题集、不重跑已有条件。

## 为什么要补

第一次运行暴露了三个问题，这次针对它们各补一组实验：

| 问题 | 本次做法 |
|---|---|
| thinking 预算 3072 太小：206/510 条被截断，201 条解析失败，无法判断 thinking 本身的效果 | 把被截断的思考**接着续写**到 8192、再到 16384 个新 token；每个预算下仍未结束的，再做一次“强制作答”（补上 `</think>` 让模型直接给结论）。得到 3072/8192/16384 三档的准确率曲线 |
| `revise_evidence` 96.86% 按标准答案挑题、证据也来自正确的形式化，只能算上限 | 新增**不读标准答案**的真实流水线 `verify_*`：只在直接回答与“模型自己的抽取 + Z3”结论不一致时重问，反馈也由模型自己的抽取生成 |
| 抽取 + 求解有 25 次误报“矛盾”，主要是角色配置抽错（多算一名爪牙） | 新增 `extract_repair`：Z3 判定抽取结果无解时，把冲突条款反馈给模型，让它核对一次转写（Logic-LM 式自我修正）；再在修复后的抽取上跑 `verify_evidence_repaired` |

续写之所以等价于“直接用更大预算跑”：采样只是从同一个前缀继续进行，所以续写结果就是大预算下的一次采样；本来就在 3072 以内结束的输出，在更大预算下也完全一样。

## 本次代码改动（由 Claude 完成，Codex 不需要再改）

- `avalon/llm_run.py`：`Runner.run` 增加可选的 `prefix`（拼在生成提示之后，用于续写和强制作答）和 `batch_size` 参数。没有这两个字段的任务，行为与第一次运行完全一致。提示词、生成参数、评分函数都没有改。
- 新增 `avalon/followup.py`：任务构造、续写和强制作答、真实验证流水线、抽取修复、评分，以及本地 `--selftest` 和 `--score`。
- 新增 `avalon/build_followup_colab.py`：生成 `colab_avalon_followup.ipynb` 和输入包 `avalon_followup_inputs.zip`（冻结题集 + 第一次运行的记录，sha256 已写进 notebook）。

Claude 已在本地验证：第一次运行的提示词逐字节复现（job 摘要一致），第一次运行的准确率能精确复现（0.5 / 0.4784 / 0.9196），并用假模型把整个 notebook 从头到尾模拟跑通。

## 约束

- 不修改任何代码、提示词、预算、批大小规则、随机种子和评分方式。不按结果调整任何东西，不为了“改进结果”重跑。
- 不删除任何文件；不修改、移动 `_archive_tau2/` 和 `results/colab_run/`（第一次运行的结果，只读）。
- 运行报告里**不要写 Google 账号邮箱**。
- 发生任何意外都记下来，写进最后的报告。如果某一步失败且原因涉及实验设计（而不是网络、配额这类环境问题），停下来在回复里说明，不要自行改代码绕过。

## 第 1 步：本地检查（PowerShell，在 `Project` 目录）

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe avalon\followup.py --selftest
```

预期最后一行是 `SELFTEST OK`（约 1–3 分钟）。不要重新生成 notebook；直接使用目录里已有的 `colab_avalon_followup.ipynb` 和 `avalon_followup_inputs.zip`（notebook 第 3 节会校验输入包的 sha256，应为 `30c050dcf072bfc9d9495a58c5bd5c2a77ba8ba6ad8dbb21bb52cda414580d85`）。

## 第 2 步：Colab

1. 使用之前跑实验的同一个账号，上传 `colab_avalon_followup.ipynb`。
2. 运行时类型选**显存至少 40 GiB、支持 BF16 的 GPU**：优先 H100 / A100 80GB / RTX PRO 6000（上次实际分到的就是 RTX PRO 6000，可以用）。L4、T4 不够，notebook 会在第 1 节报错停下。
3. 在左侧文件面板把 `avalon_followup_inputs.zip` 上传到 `/content`（如果没上传，第 3 节会弹出上传按钮）。
4. 从上到下依次运行：

| 节 | 内容 | 预计时长 | 结束时 |
|---|---|---|---|
| 1–3 | 环境、代码、输入校验、复现第一次运行的评分 | 5 分钟 | 第 3 节断言失败就停下，带着完整输出回来 |
| 3b | 运行时被回收后才用；正常显示“无需恢复” | — | — |
| 4 | 加载 Qwen3-8B（同一 revision） | 3–5 分钟 | — |
| 5 | `verify_flag` / `verify_evidence` / `extract_repair` / `verify_evidence_repaired` | 约 15 分钟 | 自动打包并下载 `avalon_followup_stage1.zip` |
| 6 | 3072 处强制作答，续写到 8192，8192 处强制作答 | 约 1–2 小时 | 下载 `avalon_followup_stage2.zip` |
| 7 | 仍未结束的续写到 16384，16384 处强制作答 | 取决于剩余条数，可能 1–3 小时 | — |
| 8 | 最终评分与打包 | 几分钟 | 下载 `avalon_followup_final.zip` |

- 长时间运行阶段每 30 分钟检查一次进度（每批会打印 `名称 budget=… : 已完成/总数 秒数`）。
- 每个阶段的 ZIP 都要设法存到 `Project\results\followup_run\` 下。自动下载失败时，从 Colab 左侧文件面板 `/content/` 手动下载；仍不行就请用户手动下载，不要绕过浏览器的安全限制。
- 同一运行时内中断：从第 2 节起重新运行即可续跑。运行时被回收：开新运行时，把最近一次下载的 `avalon_followup_stage*.zip` 上传到 `/content`，再从第 1 节依次运行，第 3b 节会自动恢复，已完成的阶段不会重算。
- 全部下载完成并确认后，断开并删除运行时。

## 第 3 步：本地复核

把 `avalon_followup_final.zip` 解压到 `Project\results\followup_run\`（解压后应有 `results\followup_run\results_followup\llm\*_records.jsonl` 和 `metrics_followup.json`），然后运行：

```powershell
.venv\Scripts\python.exe avalon\followup.py --score --new results\followup_run\results_followup\llm --out results\followup_run\metrics_followup_local.json
```

`metrics_followup_local.json` 应与 Colab 生成的 `results_followup\metrics_followup.json` 数值一致；不一致就记录在报告里。

## 第 4 步：写 `FOLLOWUP_RUN_REPORT.md`

- 运行日期、实际 GPU 型号与显存、`runner_metadata.json` 的要点、输入包 sha256、各阶段耗时与 `STATUS.json` 中的记录数；
- **thinking 预算表**（`think_budget_table`）：三档预算各自的 unfinished、mean_tokens、strict_accuracy、strict_parse_failures、forced_accuracy；再给 `think16384_strict` 与 `think16384_forced` 的主指标（accuracy、macro_f1、premature_certainty、false_uncertainty、missed_inconsistency、false_inconsistency、parse_failures）。说明：strict 只认 `</think>` 之后的答案，所以 `think3072_strict` 比第一次报告的 47.84% 略低（第一次的宽松解析从未结束的思考里捞到过答案词）；
- **抽取修复**（`extract_repair`）：triggered、triggered_gold、changed、主指标、修复前后的 `extraction` 字段对比（与 `extract_solve` 并列）；
- **真实验证流水线**（`verify_flag`、`verify_evidence`、`verify_evidence_repaired`，以及无 LLM 的 `solver_final`）：主指标，加上 reasked、fixed、broken、followed_solver、kept_own_answer、solver_right / followed_when_solver_right、solver_wrong / followed_when_solver_wrong；
- `paired_bootstrap` 全表；
- 所有报错、中断、重跑、换卡及处理方式。

完成后在对话里回复“阿瓦隆后续实验已完成”，并附上报告要点。
