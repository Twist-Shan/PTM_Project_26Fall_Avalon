# 阿瓦隆实验运行报告

状态：已完成。执行日期：2026-11-12 至 2026-11-13（Asia/Singapore）。结果已下载、校验并解压；2026-11-13检查Colab时，运行时已因空闲自动断开，管理会话显示“没有正在进行的会话”。没有重新连接或启动计算。

## 主要结论

510道题上，Qwen3-8B直接回答准确率50.00%，语言抽取后约束求解91.96%。抽取后求解提高41.96个百分点，配对bootstrap 95%区间为[36.86,47.06]个百分点。

约束证据辅助修正准确率96.86%。该条件由正确结构化题目生成反馈，并依据gold挑选直接回答错误的255题再问，其他255题保留原答案；它衡量受控纠错能力。实际依赖语言抽取的端到端方案由extract_solve及verification_pipeline单独评估。不能把96.86%直接作为完整自动验证流水线的准确率。

## 实验设置与复现

Notebook：https://colab.research.google.com/drive/1nFk9mRykGmr2EHcOMQkKjorVl30vEyqH?authuser=1

账号：[账号信息已省略]。A100不可用后，用户授权其他GPU；实际硬件为NVIDIA RTX PRO 6000 Blackwell Server Edition，95 GiB。Qwen/Qwen3-8B，revision `b968826d9c46dd6066d109eabc6255188de91218`；BF16、batch_size=16；Python3.13.16、torch2.14.1+cu130、transformers4.57.6。模型seed42，题集seed137，分析和bootstrap seed271。无训练；本次为冻结题集单次评估，未进行跨seed重复。参数、提示词、配额、规则和评分均保持原协议。

标签为entailed（必然成立）、contradicted（必然不成立）、undetermined（信息不足）、inconsistent（约束矛盾）。说明性示例：同一命题在两个合法身份分配中分别为真和假，则标签为undetermined。

数据源avalonlogs commit：`3219bbdd1a27b77da6c9e9f7b1f05f7d3969398f`。原始仓库仅在Colab克隆，未下载含冒号的原始文件到Windows。

## 本地和远程验收

使用项目.venv运行，快速版和完整版均退出码0、ALL CHECKS PASSED；z3_available=true，tables_agree=true。未发现实现错误或语义分歧，未修改smt.py。

| 检查 | 本地快速版 | 本地完整版 |
|---|---:|---:|
| 手写用例 | 44/44 | 44/44 |
| 随机实例 | 88 | 432 |
| 判断正确且Z3与穷举一致 | 264/264 | 1296/1296 |
| 损坏记录检出 | 60/60 | 60/60 |
| 最小查验算法一致 | 9/9 | 44/44 |
| 投票不提供身份逻辑信息 | 260/260 | 246/246 |
| 耗时（秒） | 267.99 | 2236.26 |

本地保留原默认seed20261112，按本次明确要求不修改。远程快速验收56.83秒通过，另455道8人及以下题与独立穷举零不一致。

## 数据审计与冻结题集

12447个文件全部成功加载和解析，无跳过。88302条提案均与votes表示赞成人员一致；其中6640条也与另一种解释相容，最终采用approve。队长轮换75855次均沿数组正方向，无反向或其他方向；seats_reversed=false。platform_failsRequired字段2处与规则表不符；1局出现Q-RESULT规则违例。true_roles_inconsistent为空，未记录真实身份不一致。

题集510题来自510个不同对局：entailed、contradicted、undetermined各150题，inconsistent60题。150道不确定题中122道存在充分查验集合，28道不存在。tasks_sha256：`256fefe30df81be9bcfde152fe4cf0cb1229b0675a7ad6929b983c7a1dbe59c0`。

## 主结果

所有主条件n=510。premature_certainty统计150道信息不足题上错误给出确定真/假的次数；false_uncertainty统计300道确定题上错误回答信息不足的次数；missed_inconsistency统计60道矛盾题的漏检。解析失败按原评分处理，单独列出，不能仅凭前两项低值判断thinking更可靠。

| 条件 | accuracy | macro_f1 | premature_certainty | false_uncertainty | missed_inconsistency | parse_failures |
|---|---:|---:|---:|---:|---:|---:|
| direct | 0.500000 | 0.369917 | 28/150 | 152/300 | 60/60 | 0 |
| think | 0.478431 | 0.502036 | 12/150 | 25/300 | 57/60 | 201 |
| extract_solve | 0.919608 | 0.907874 | 2/150 | 2/300 | 0/60 | 0 |
| revise_flag | 0.700000 | 0.544324 | 0/150 | 15/300 | 60/60 | 0 |
| revise_evidence | 0.968627 | 0.968214 | 0/150 | 10/300 | 4/60 | 0 |

thinking有201条解析失败、206条触及3072token上限；两种事件的重合数量本报告未另行计算。当前比较受输出预算和答案可解析性影响，不能据此推出普遍的推理能力排序。extract_solve有25/450条错误报矛盾；结构化抽取完全正确455/510，配置正确483/510、命题正确482/510、任务记录正确510/510、视角正确509/510。

revise_flag修正102/255个原错误；revise_evidence修正239/255个原错误。两者均只追问一次。

## 查验集合、验证流水线与配对统计

reveal：122题中99题选择的查验集合充分（81.15%），35题最优（28.69%），2题无效，选择全部候选者0题；充分时平均超出最优查验数0.9596，gold_total=170。

verification_pipeline：原回答错误255题，标记253题（99.22%）；原回答正确255题，误标记23题（9.02%）。这体现实际抽取误差造成的验证误报。

配对bootstrap按题重采样2000次，seed271，以下差值单位为百分点；区间只反映本题集重采样，不包含跨模型seed变化。

| 比较 | 准确率差值 | 95%区间 |
|---|---:|---:|
| think_minus_direct | -2.16 | [-7.25, 2.94] |
| extract_solve_minus_direct | 41.96 | [36.86, 47.06] |
| revise_flag_minus_direct | 20.00 | [16.47, 23.33] |
| revise_evidence_minus_direct | 46.86 | [42.35, 51.18] |

thinking与direct差值区间包含0。本次没有按结果调整参数或重跑模型。

## 真实对局分析

第6节已完成。meta.json完整内容如下：

```json
{
  "backend": "z3",
  "games_available": 12446,
  "games_sampled": 600,
  "seed": 271,
  "seconds": 1502.6
}
```

A1/A2、A3、A4输出均在results/colab_run/results/analysis/，供后续研究分析。分析使用审计后12446局，抽样600局；与原始解析数相差1局，对应审计发现的规则违例局。

## 归档与完整性

两个ZIP均保存于results/colab_run/并解压，CRC检查通过。avalon_results.zip为3461888字节，32个归档条目，SHA256：`9f9c4adce62ab81cfc127c87c601cd55618b32c79ed0303794cfb350f3346f33`，与远端输出一致。COMPLETED.json确认analysis_done=true，记录数direct510、extract510、reveal122、think510、revise_flag255、revise_evidence255。原始逐题输出、任务、评分、运行元数据均保留。Windows下载目录中的重复ZIP未删除。

## 异常、授权变更与清理

1. 原打包代码p.unlink()违反不删除文件要求。用户明确允许仅移除该语句；已重新生成notebook，解析JSONL和其ZIP都保留。
2. A100两次申请均分配L4，硬件断言中止，未加载模型。两个旧运行时均释放。用户随后授权其他GPU，仅将两处硬件断言改为CUDA及BF16支持，未改实验协议，重新生成notebook。详见CHANGES_BY_CODEX.md。
3. H100首次连接报TypeError: Failed to fetch，未执行实验；刷新重新选择后实际分配上述RTX PRO 6000。硬件名称按运行元数据记录。
4. 本地等待期间只读进程查询失败、浏览器连接失效、上传后短暂白屏；未因此重复本地验收或模型实验。Colab屏幕外输出延迟呈现，通过滚动确认完成。
5. 按用户要求，长计算阶段每30分钟检查。模型与CPU分析完成后打包。自动下载事件超时，结果ZIP未及时落盘；数据ZIP成功。追加仅用于传输的单元尝试files.download及data链接。浏览器工具拒绝data协议下载后停止该路径，由用户手动完成下载。没有重新执行实验。
6. 2026-11-13用户确认下载后，文件大小、SHA256、CRC与记录数检查通过。检查Colab时提示因空闲断开，删除运行时菜单禁用；管理会话明确显示没有正在进行的会话，因此无需新建连接进行释放。凭证：results/colab_run/runtime_released.png。
7. 未修改或删除_archive_tau2/，未删除项目文件。运行期间历史记录保留在RUN_REPORT_execution_history.md。本报告取代其中的中间状态。
