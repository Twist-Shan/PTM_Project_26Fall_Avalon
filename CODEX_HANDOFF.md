# 执行说明：阿瓦隆实验（给 Codex）

项目目录：本文件所在的 `Project` 文件夹。旧的航空政策方案在 `_archive_tau2/`，**不要修改、移动或删除其中任何文件**。整个过程中不要删除任何文件。

## 约束

- 不修改规则语义：`avalon/oracle.py`、`avalon/cases.py`、`RULES.md` 是参照，不改。
- 不修改实验协议：`avalon/llm_run.py` 中的提示词、生成参数、评分方式，以及 `avalon/llm_tasks.py` 的配额和随机种子都不改。
- 不按结果调整任何东西，也不为了“改进结果”重跑模型。
- 发生任何意外时，记录下来并在最后的报告里说明。

## 第 1 步：本地验收 Z3 编码

在 `Project` 目录的 PowerShell 中运行：

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe avalon\selfcheck.py --quick --out results\selfcheck_local
```

预期最后一行是 `ALL CHECKS PASSED`，并且 `results\selfcheck_local\summary.json` 中 `"z3_available": true`。

如果失败：
1. 查看 `summary.json` 和 `mismatches.json`。
2. 独立穷举（`oracle.py`）和手写用例（`cases.py`）是参照。只允许修正 `avalon/smt.py` 中与它们不一致的**实现错误**，例如 z3py 的 API 用法、索引、类型转换。
3. 每处修改都记入 `CHANGES_BY_CODEX.md`：问题、原因、改动摘要、修复后的重新运行结果。
4. 如果分歧涉及规则本身的含义，例如两种实现都“合理”但结论不同，就停止，不要继续第 2 步以后的内容，并在回复中说明。

验收通过后，再运行完整版（可能需要几十分钟）：

```powershell
.venv\Scripts\python.exe avalon\selfcheck.py --out results\selfcheck_local_full
```

## 第 2 步：重新生成 notebook

只要第 1 步改过任何代码，就运行：

```powershell
.venv\Scripts\python.exe avalon\build_colab.py
```

## 第 3 步：在 Colab A100 上运行

1. 打开 https://colab.research.google.com/ ，使用之前跑实验的账号，上传 `colab_avalon.ipynb`。
2. 在“更改运行时类型”中选择 A100（notebook 会检查 GPU 型号）。
3. 从上到下依次运行全部单元：
   - 不需要挂载 Google Drive。
   - 数据集 avalonlogs 在 Colab 内用 `git clone` 获取。它的文件名含冒号，**不要**下载到 Windows。
   - “4 Z3 与独立穷举交叉验证”如果断言失败，立即停止，不要加载模型，把完整输出带回来。
   - 5a–5d 是模型运行与评分。中断后重新运行同一单元会从断点续跑，不要改单元内容。
   - “6 真实对局分析”只用 CPU。如果运行时可能被回收，先运行第 7 节下载已有结果，再回来跑第 6 节，最后再下载一次。
   - 第 7 节会下载 `avalon_results.zip` 和 `avalon_data_llm.zip`。放到 `Project\results\colab_run\` 下并解压。
4. 确认下载完整后，断开并删除运行时。

预计用时：A100 上 1.5–2.5 小时，其中 thinking 条件最慢。

## 第 4 步：写运行报告

在 `Project\RUN_REPORT.md` 中写：

- Colab notebook 链接、实际 GPU 型号、运行日期；
- 第 1 步结果：`summary.json` 的关键字段；如果有修改，指向 `CHANGES_BY_CODEX.md`；
- `results/audit/audit_summary.json` 的要点：解析局数、投票字段的判定、座位方向、规则违例统计、真实身份不一致统计、avalonlogs commit；
- `data/llm/manifest.json`：题数、标签分布、`tasks_sha256`；
- `results/llm/metrics.json` 的主表：各条件的 accuracy、macro_f1、premature_certainty、false_uncertainty、missed_inconsistency、parse_failures，以及 reveal、verification_pipeline、paired_bootstrap；
- 第 6 节是否完成，以及 `results/analysis/meta.json` 的内容；
- 所有报错、中断、重跑及处理方式。

完成后在对话里回复“阿瓦隆实验已完成”，并附上 `RUN_REPORT.md` 的要点。
