# Codex 执行变更

## 2026-11-12：保留打包前的解析文件

- 问题：`avalon/build_colab.py` 第7节在压缩 `results/audit/parsed_games.jsonl` 后执行 `p.unlink()`，与用户要求不删除任何文件冲突。
- 授权：用户明确允许仅移除删除语句。
- 改动：仅移除 `p.unlink()`，保留原始解析文件及压缩副本；重新生成 `colab_avalon.ipynb`。
- 不涉及规则、提示词、配额、生成参数、评分方式或随机种子。Z3 实现暂未修改。
- 验证结果与运行状态见 `RUN_REPORT.md`。

## 2026-11-12：用户授权改用其他GPU

- A100两次不可用后，用户要求“换个别的卡，把实验跑了”。
- 仅将 `build_colab.py` 环境单元及 `llm_run.py` Runner 的A100型号断言改为CUDA可用且支持BF16；重新生成notebook。优先申请H100。
- 保留BF16、SDPA、已有按显存决定batch的逻辑、全部提示词、生成参数、评分、配额及种子。GPU实际型号将由Runner元数据记录。
