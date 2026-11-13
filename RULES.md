# 阿瓦隆规则条款覆盖表

材料：*The Resistance: Avalon* 官方规则书（Indie Boards & Cards，Don Eskridge 设计）。表中规则为本项目的转述，不是原文摘录。
核对来源：rulespal.com 的规则书整理页、avalon-game.com 规则 wiki（出队人数表）。两处来源的差异记在“解释选择”一节。

实现：`avalon/smt.py`（Z3，按条款编号跟踪每个约束实例）与 `avalon/oracle.py`（独立穷举，表格重新录入，任务规则用另一种写法）。测试编号见 `avalon/cases.py`。

## 1. 已形式化的条款

| 编号 | 规则书章节 | 规则（转述） | 形式化 | 测试 |
|---|---|---|---|---|
| S-SIZE | Set Up | 5–10 人 | n ∈ {5,…,10} | 随机实例 |
| S-COUNT | Set Up | 好人/坏人人数表：5→3/2，6→4/2，7→4/3，8→5/3，9→6/3，10→6/4 | 配置中坏人角色数 = E(n) | T01–T03 |
| S-TOTAL | Set Up | 每人发一张角色牌 | 配置总数 = n | 篡改实例 |
| S-UNIQUE | Optional Characters | 梅林、派西维尔、莫甘娜、莫德雷德、奥伯伦各至多一张 | 特殊角色计数 ≤ 1 | — |
| S-DEAL[r] | Set Up | 角色按配置随机发放 | Σᵢ[roleᵢ=r] = count(r)，对每个角色 r | T01 |
| V-SELF | Set Up | 每人知道自己的角色 | role_p = 自身角色（视角事实） | T33, T35 |
| K-EVIL | Evil reveals itself | 坏人（奥伯伦除外）开局互相认识 | 对 j≠p：(evil_j ∧ role_j≠奥伯伦) ⇔ j∈seen | T31, T32 |
| K-MERLIN | Merlin looks into the future | 梅林看到坏人，莫德雷德除外 | 对 j≠p：(evil_j ∧ role_j≠莫德雷德 [∧ role_j≠奥伯伦]) ⇔ j∈seen | T26–T28, T43–T44 |
| K-PERCIVAL | Percival | 派西维尔看到梅林和莫甘娜，但分不清 | 对 j≠p：role_j∈{梅林,莫甘娜} ⇔ j∈seen | T29, T30, T34 |
| K-NONE | Set Up | 忠臣与奥伯伦开局不获得信息 | seen = ∅ | 随机实例 |
| K-SELF | — | 看到的人不含自己 | p∉seen | 随机实例 |
| T-LEADER | Team Building | 每次提案后队长顺时针传给下一人 | leader_{k+1} = leader_k + 1 (mod n) | T16 |
| T-SIZE | Team Building | 各轮出队人数见表 | \|team\| = SIZE[n][q] | T04–T05 |
| T-DISTINCT | Team Building | 每人至多一枚队伍标记 | 队员互不相同 | 随机实例 |
| T-VOTE | Team Building | 过半赞成才通过，平票视为否决 | approved ⇔ 2·#赞成 > n | T12–T14 |
| T-HAMMER | Team Building | 同一轮连续 5 次否决，坏人立即获胜 | 每轮 ≤5 次提案；第 5 次否决后游戏结束且坏人胜 | T15 |
| T-LAST | Team Building | 通过的提案即出队队伍，通过后不再提案 | 最后一次提案通过且其队伍 = 任务队伍 | 篡改实例 |
| Q-SIZE | Quest Phase | 执行任务的人数与表一致 | \|team_q\| = SIZE[n][q] | T06 |
| Q-GOOD | Quest Phase | 好人必须出成功；坏人可出成功或失败 | 对队员 i：¬evil_i → ¬fail_card_{q,i} | T17–T25, T35 |
| Q-COUNT | Quest Phase | 洗混后翻开任务牌，可见失败票张数 | Σᵢ fail_card_{q,i} = 记录的失败票数 | T17–T25 |
| Q-RESULT / Q-TWOFAIL | Quest Phase | 出现失败票即失败；7 人及以上的第 4 个任务需 2 张 | failed_q ⇔ fails_q ≥ need(n,q)，need = 2 当 q=4 且 n≥7，否则 1 | T07–T11 |
| R-ORDER | Quest Phase | 任务按 1→5 顺序进行（未启用 Targeting） | 第 k 条任务记录的编号 = k | 篡改实例 |
| G-END | Game End | 三胜或三负时游戏立即结束 | 达到 3 次成功或失败后不再有任务 | T39 |
| G-OUTCOME | Game End | 三个任务失败则坏人胜 | 3 次失败 ⇒ 结果为坏人胜 | 随机实例 |
| G-ASSASSIN | Assassinate Merlin | 三个任务成功后才进入刺杀 | 有刺杀 ⇒ 成功数 ≥ 3 | T38 |
| G-MERLIN-HIT | Assassinate Merlin | 刺中梅林则坏人胜，否则好人胜 | (role_a = 梅林) ⇔ 坏人胜 | T36, T37 |
| L-WHEN | Lady of the Lake | 第 2、3、4 个任务结束后各使用一次 | 使用轮次 ∈ {2,3,4}、递增、对应任务已结算 | — |
| L-FIRST | Lady of the Lake | 开局时湖中仙女在首位队长右手边的玩家手中 | 首位持有者 = 首位队长 − 1 (mod n) | T41 |
| L-CHAIN | Lady of the Lake | 被查验者获得湖中仙女 | 第 k 位持有者 = 第 k−1 次的被查验者 | T41 |
| L-PREV | Lady of the Lake | 用过湖中仙女的人不能被查验 | 被查验者 ∉ 历任持有者 | T41 |
| K-LADY | Lady of the Lake | 持有者得知被查验者的阵营（仅自己知道） | 持有者视角：evil_t = 查验结果 | T40 |

规则实例以 `编号@位置` 的形式参与求解，例如 `Q-GOOD@q3:5` 表示“第 3 个任务中 6 号座位（0 起计为 5）若是好人则出成功”。不可满足时，`smt.py` 用基于删除的方法把冲突约束集最小化，输出的解释由条款实例和记录事实组成。

## 2. 解释选择（编码变体）

| 编号 | 问题 | 默认 | 另一种读法 | 影响（测试） |
|---|---|---|---|---|
| V-FAILCOUNT | 失败票张数是否公开 | 公开：规则书写的是洗混后翻开任务牌；avalonlogs 记录了 `numFails` | 只公开成败：有一份规则 wiki 写的是只公布任务结果 | 只公开成败时，“2 张失败 ⇒ 两人都是坏人”变为无法确定（T17 对比 T42） |
| V-OBERON | 梅林能否看到奥伯伦 | 能：规则书中坏人举拇指的步骤并未把奥伯伦排除 | 不能：部分规则整理认为奥伯伦对所有人隐藏 | 梅林看到 3 人在默认读法下一致，在另一读法下矛盾（T43 对比 T44） |
| L-FIRST | “队长右手边”指哪一位 | 队长按顺时针传递，右手边取上一座位 | 下一座位 | 只影响湖中仙女的合法性检查 |
| T-LEADER | 跨轮次时队长是否继续轮转 | 继续顺时针，与轮次无关 | — | 在真实日志上统计验证 |

## 3. 未形式化的内容及原因

| 内容 | 原因 |
|---|---|
| 讨论、声明、说谎 | 规则不约束玩家说什么，声明不是事实 |
| 投票与身份的关系 | 规则不限制任何人怎么投票，所以投票不携带逻辑信息（`selfcheck.py` 第 5 项验证：去掉所有投票后身份判定不变） |
| 坏人出成功票的策略 | 规则允许坏人出成功，因此成功的任务在逻辑上不排除坏人 |
| 刺客身份与刺杀前的讨论 | 不影响任何可验证结论；刺杀结果作为 G-MERLIN-HIT 建模 |
| Targeting 可选规则 | 真实日志所在平台未使用；R-ORDER 假设任务按顺序进行 |
| The Resistance 的 Plot 牌与忠诚牌 | 属于另一款游戏的扩展 |
| “不得出示角色牌” | 行为规范，不影响记录的一致性 |
| 5 人局加入派西维尔时应同时加入莫德雷德或莫甘娜 | 规则书写的是建议，作为配置提示，不作为约束 |
