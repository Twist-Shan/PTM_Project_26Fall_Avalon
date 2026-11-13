# 阿瓦隆后续实验运行报告

状态：已完成。日期：2026-11-13（Asia/Singapore）。三个阶段ZIP均已下载并校验，最终结果已解压；本地重新评分与Colab JSON完全一致。运行时已断开并删除，页面确认“重新连接 G4”。未修改代码或实验参数，未重建题集或重跑首次条件。

## 结论

510道冻结题上，thinking严格准确率随预算从3072的47.65%提高到16384的67.06%，最终所有思考均结束，但仍有13条答案解析失败。3072处强制作答已经达到67.06%；本次更长续写没有超过该条件的总体准确率，逐题输出不必相同。

真实证据验证准确率89.22%，高于直接回答50.00%，低于直接采用模型抽取后求解结论的91.96%。抽取修复触发85次，形式化结果改变0次，未改善准确率。修复后证据验证为89.02%，比修复前少答对1题；差异原因未查明，不能解释为抽取质量下降。

## 设置与验收

Notebook：https://colab.research.google.com/drive/1GXYhyOVl-42PSx6sqSbEtDcfZEg_NMBj?authuser=1

GPU申请H100，Colab提示该型号不可用并分配NVIDIA RTX PRO 6000 Blackwell Server Edition（G4），95.0 GiB，BF16及显存≥40GiB断言通过。模型Qwen/Qwen3-8B，revision b968826d9c46dd6066d109eabc6255188de91218。Python3.13.16、torch2.14.1+cu130、transformers4.57.6、bfloat16。默认batch_size16；8192阶段32，16384阶段18，完全由原批大小规则决定。模型seed42；thinking采样temperature0.6、top_p0.95、top_k20，关闭thinking时greedy。runner代码SHA256为47a9adcf9414a7923a3794967920ddf6a5bd4f95b538fca37667f7c2165315a0。

输入包SHA256：30c050dcf072bfc9d9495a58c5bd5c2a77ba8ba6ad8dbb21bb52cda414580d85。
题集SHA256：256fefe30df81be9bcfde152fe4cf0cb1229b0675a7ad6929b983c7a1dbe59c0。
本地selftest退出码0，SELFTEST OK；自检假模型输出不计作实验。远程第3节15秒通过：输入、题集、旧提示词检查及首次评分精确复现。3b显示无需恢复。未重新生成notebook。

本次只延续首次冻结输出并增加指定条件，未训练模型或改变数据划分。验证触发与反馈构造不读取gold，gold仅用于事后评分。续写使用同一前缀及既定采样参数；本次不额外检验其与从头生成更长输出的逐token一致性。

## thinking预算

strict只解析`</think>`后的答案；首次报告宽松解析曾从未结束的思考里识别答案词，因此3072 strict的47.65%略低于首次47.84%。forced只对预算处未结束的输出追加指定强制作答。mean_tokens为每题累计生成token的既定统计。说明性示例：思考尚未结束但含“成立”一词，strict不会将它当成最终答案。

| 预算 | unfinished | mean_tokens | strict_accuracy | strict_parse_failures | forced_accuracy |
|---|---:|---:|---:|---:|---:|
| 3072 | 206 | 2352.466667 | 0.476471 | 207 | 0.670588 |
| 8192 | 2 | 2856.325490 | 0.668627 | 15 | 0.672549 |
| 16384 | 0 | 2858.972549 | 0.670588 | 13 | 0.670588 |

## 主指标

所有条件n=510。premature_certainty分母150（信息不足题），false_uncertainty分母300（确定题），missed_inconsistency分母60（矛盾题），false_inconsistency分母450（非矛盾题）。解析失败单列并按原评分处理。

| 条件 | accuracy | macro_f1 | premature_certainty | false_uncertainty | missed_inconsistency | false_inconsistency | parse_failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| direct | 0.500000 | 0.369917 | 28/150 | 152/300 | 60/60 | 0/450 | 0 |
| think16384_strict | 0.670588 | 0.612398 | 25/150 | 71/300 | 49/60 | 1/450 | 13 |
| think16384_forced | 0.670588 | 0.612398 | 25/150 | 71/300 | 49/60 | 1/450 | 13 |
| extract_solve | 0.919608 | 0.907874 | 2/150 | 2/300 | 0/60 | 25/450 | 0 |
| extract_repair | 0.919608 | 0.907874 | 2/150 | 2/300 | 0/60 | 25/450 | 0 |
| solver_final | 0.919608 | 0.907874 | 2/150 | 2/300 | 0/60 | 25/450 | 0 |
| verify_flag | 0.652941 | 0.506255 | 12/150 | 27/300 | 60/60 | 0/450 | 0 |
| verify_evidence | 0.892157 | 0.879963 | 2/150 | 13/300 | 3/60 | 25/450 | 0 |
| verify_evidence_repaired | 0.890196 | 0.877091 | 2/150 | 13/300 | 4/60 | 25/450 | 0 |

## 抽取修复

triggered=85，changed=0；triggered_gold为inconsistent60、undetermined10、entailed5、contradicted10。修复前后25次误报矛盾均保留。下表数字为510题中字段正确或有效的数量。

| extraction字段 | extract_solve | extract_repair |
|---|---:|---:|
| valid_json | 510 | 510 |
| n_ok | 510 | 510 |
| config_ok | 483 | 483 |
| quests_ok | 510 | 510 |
| view_ok | 509 | 509 |
| claim_ok | 482 | 482 |
| exact | 455 | 455 |

## 真实验证流水线

solver_final直接输出模型抽取后的求解结论，不追加LLM调用；它复用已有抽取，因此此处“无LLM”仅指最终决策阶段。以下计数仅针对触发重问的题目；fixed为错改对，broken为对改错。

| 条件 | reasked | fixed | broken | followed_solver | kept_own_answer | solver_right | followed_when_solver_right | solver_wrong | followed_when_solver_wrong |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| verify_flag | 276 | 101 | 23 | 103 | 0 | 237 | 95 | 39 | 8 |
| verify_evidence | 276 | 223 | 23 | 259 | 0 | 237 | 222 | 39 | 37 |
| verify_evidence_repaired | 276 | 222 | 23 | 258 | 0 | 237 | 221 | 39 | 37 |

solver_final没有重问，其reasked/fixed/broken等交互统计不适用。证据流水线在求解器正确的237题中跟随222题，在求解器错误的39题中跟随37题，表明模型也会采纳错误形式化产生的证据。

## paired_bootstrap全表

差值单位为百分点，按原实现配对重采样；区间不涵盖跨seed变化。本次仅一次既定采样运行。

| 比较 | 准确率差值 | 95%区间 |
|---|---:|---:|
| think16384_forced_minus_direct | 17.0588 | [12.1569, 21.9608] |
| think16384_strict_minus_direct | 17.0588 | [12.1569, 21.9608] |
| think16384_strict_minus_think3072_strict | 19.4118 | [16.0784, 22.9412] |
| extract_solve_minus_think16384_forced | 24.9020 | [20.1961, 30.0000] |
| extract_repair_minus_extract_solve | 0.0000 | [0.0000, 0.0000] |
| verify_flag_minus_direct | 15.2941 | [11.3725, 19.4118] |
| verify_evidence_minus_direct | 39.2157 | [34.1176, 44.1176] |
| verify_evidence_repaired_minus_direct | 39.0196 | [33.9216, 44.1176] |
| verify_evidence_minus_extract_solve | -2.7451 | [-4.3137, -1.3725] |
| verify_evidence_repaired_minus_extract_repair | -2.9412 | [-4.5098, -1.3725] |

## 阶段耗时、记录数与归档

以下为各任务record中batch_seconds/batch_size求和所得生成时间，避免同批每条记录重复计时；不包含CPU求解、加载、打包、等待检查和传输时间。浏览器连接恢复后显示的单元耗时曾与逐批日志不一致，故以原始批次计时为依据。

| 任务 | STATUS记录数 | 生成秒数 |
|---|---:|---:|
| verify_flag | 276 | 26.82 |
| verify_evidence | 276 | 24.73 |
| extract_repair | 85 | 87.01 |
| verify_evidence_repaired | 276 | 24.78 |
| think_force3072 | 206 | 93.77 |
| think_cont8192 | 206 | 7570.73 |
| think_force8192 | 2 | 2.08 |
| think_cont16384 | 2 | 70.35 |
| think_force16384 | 0 | 0.00 |

stage1生成合计：163.34秒。

stage2生成合计：7666.58秒。

stage3生成合计：70.35秒。

环境单元9秒、代码写入2秒、输入校验成功单元15秒、恢复检查0秒、模型加载54秒；最终评分打包为短CPU阶段，未获得可靠独立耗时。

| 归档 | 字节 | SHA256 |
|---|---:|---|
| avalon_followup_final.zip | 196904 | 2e0081c4c24ef5dab953a0079c8f69596d32e2b07c1d4cf74faa2f1416e1063d |
| avalon_followup_stage1.zip | 15832 | b678e39d4f779722c82dde5c73facd213326a50008ed2633434bbc97a655f479 |
| avalon_followup_stage2.zip | 195239 | 132075a689cd5d59d2a3c680af377255c9e1e423bb225ed0226871e69dcdd8c7 |

三个ZIP均CRC通过，远端显示哈希与本地一致。stage1含前4项记录；stage2增加force3072、cont8192、force8192；final包含全部9项。最终每类记录数及ID唯一性已检查，与STATUS.json一致。final解压到results/followup_run/results_followup/。

执行原命令`followup.py --score --new results/followup_run/results_followup/llm --out results/followup_run/metrics_followup_local.json`退出码0；本地与远端metrics对象精确相等。核验摘要保存在results/followup_run/verification.json。所有记录的源文件哈希与运行前一致。

## 异常及处理

1. 内嵌上传控件两次等待文件选择事件超时；改用Colab左侧文件面板上传成功。取消仍等待的内嵌上传产生StopIteration。输入包就绪后仅重运行第3节，哈希和评分断言全部通过；属于上传交互恢复，没有改代码或重复模型计算。
2. H100不可用，Colab自动分配95GiB G4；环境要求满足，未再次换卡。
3. 8192阶段界面多次显示“正在连接/正在恢复执行”，批次日志持续增加；未重启、重跑或修改单元。最终恢复正常连接。原因未查明。
4. 长阶段每30分钟检查；用户中途打断等待并询问进度时读取当前状态。没有创建持久自动任务。检查间隔导致阶段完成到启动下一阶段存在等待，不计入模型生成时间。
5. 全部阶段自动下载成功，无需手动传输或添加传输代码。确认最终ZIP完整后，已执行断开并删除运行时，截图runtime_released.png保留。此为用户明确要求的运行时释放；本地及归档文件未删除。
6. 未修改代码、提示词、预算、批大小规则、种子或评分。没有按结果重跑，首次结果results/colab_run/及_archive_tau2/保持只读。报告不包含账号邮箱。早期状态保留在FOLLOWUP_RUN_REPORT_execution_history.md。

## 补充（Claude，2026-11-13）：提示词重建

notebook 的打包步骤没有保存 `*_jobs.json`（只在 `*_metadata.json` 里留了 jobs_sha256）。`verify_*` 和 `extract_repair` 的反馈里有 Z3 给出的见证身份分配和最小冲突条款；这类对象往往有多个同样正确的选择，Z3 返回哪一个取决于同一进程中此前的求解历史。因此提示词只有按 notebook 的原顺序重放才能逐字复原。

已用 `avalon/followup.py --reconstruct` 按原顺序（第 3 节空评分，然后第 5、6、7 节依次构造）在本地重建全部 9 组提示词，保存在 `results/followup_run/reconstructed_jobs/`；每组的 sha256 都与运行记录一致（见该目录 `manifest.json`），所以就是本次实验实际使用的提示词。

这也解释了 `verify_evidence` 与 `verify_evidence_repaired` 相差 1 题的原因：两者的抽取完全相同（修复改动为 0），但构造反馈时求解历史不同，有一部分题目展示的见证或冲突条款不同。用前一种方法在同一进程里连续构造两遍，276 条中有 45 条不同（28 条见证、17 条冲突条款），每一条都是正确的反馈。
