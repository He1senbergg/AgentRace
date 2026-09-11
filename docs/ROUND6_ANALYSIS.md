# Round6 战后复盘与证据封存

## 1. 封存范围与证据口径

- 仓库 checkpoint：`b51712864c0471837bb8aa3278f528251d20c09e`。起始工作区干净；远端相对5345b28仅新增14份Round6日志，确认后fast-forward取得证据，未变更运行代码。
- 完整读取game18～game24双方14个文件；我方4245条shadow_turn逐回合连续、579条trace_turn；对手167个MATCH2完整事件包均通过分片、解压长度和SHA-256校验。对手包内去重后239个嵌套事件，只是日志保留的样本，不等于完整比赛事件流。
- 日志全部标记strategy_mode=defense、authority=defense_with_legacy_task。日志未嵌入提交哈希，不能证明实机源码与本地HEAD逐字相同；以下机制解释以当前代码为依据。
- 我方回合起点为1。R70为第一夜前，R131为第一夜结束后首个白天观测；R200/R261为第二夜对应边界。各局R130与R131资产数据一致；跨界快照不是完整回合内部时序。
- “首次清空”指station缺失且角色/武器/墙均消失的首次观测；其后直到日志末尾均为空。前一回合还有正HP，因此清空发生在相邻两次观测之间。不能将所有墙同时消失记为分别被机器人击毁。
- 得分取文件名标签，官方最终结算payload缺失，故精确官方结算为unknown；日志末回合不是我方存活回合。无新的策略实现、参数调整或实机试验。

## 2. 七局结果总表

| 对局/我方侧 | 文件名得分 我方/对方 | R70完整benchmark | 首次全部资产清空 | 夜晚 | 我方日志截止 | 对手最后checkpoint R/score/baseHP |
|---|---:|---|---:|---|---:|---|
| game18 BlueSide | 274/1020 | 是 | R357 | Night3 | R634 | 620/905/1270 |
| game19 BlueSide | 453/1035 | 否 | R359 | Night3 | R643 | 620/904/1660 |
| game20 RedSide | 376/797 | 否 | R369 | Night3 | R496 | 490/731/475 |
| game21 BlueSide | 84/900 | 否 | R215 | Night2 | R611 | 590/769/205 |
| game22 BlueSide | 172/910 | 否 | R228 | Night2 | R619 | 590/768/790 |
| game23 BlueSide | 208/949 | 否 | R220 | Night2 | R629 | 620/830/1340 |
| game24 BlueSide | 240/924 | 是 | R226 | Night2 | R613 | 590/779/440 |

七局均未达到1300回合生存目标：4局在第二夜、3局在第三夜首次资产清空。game20对手文件原名拼为`eneny_BlueSide_797.log`，本轮保留原名。对手最后checkpoint数值不是文件名最终得分，禁止混同。

## 3. 每局关键观测

角色HP按完整ID列出：尾号10/12为worker，11为pioneer；R70均为3个满血角色且无活跃任务。M为当前物理邻接最大匹配数，不等于本回合可开火炮数（仍受cooldown、目标及任务占用限制）。全部武器构成为3 rocket，等级列来自metrics；没有gatling/railgun对照。墙HP为current/max。R70角色位置来自trace_turn，角色列表截断不用于计算墙总量。

### game18

证据文件：[ally_BlueSide_274.log](../log/Versus/round6/game18/ally_BlueSide_274.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 359 | 47 | 1500 | 8/8000/8000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R131 Night1后 | 702 | 47 | 1340 | 8/7300/8000 | 2/1/1 | 10010:195, 10011:200, 10012:220 | 3 |
| R200 Night2前 | 994 | 62 | 1340 | 9/9935/10000 | 2/1/1 | 10010:195, 10011:200, 10012:220 | 3 |
| R261 Night2后 | 1337 | 62 | 840 | 9/8500/10000 | 2/1/1 | 10010:195, 10011:75, 10012:150 | 3 |
| R330 Night3前 | 1628 | 12 | 840 | 10/10985/11500 | 2/1/1 | 10010:195, 10011:200, 10012:220 | 3 |
| R356 清空前末次 | 1785 | 12 | 30 | 10/8360/11500 | 2/1/1 | 10011:200, 10012:220 | 2 |
| R357 首次清空 | 1788 | 12 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行320）：10010 worker@(9, 23)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10011 pioneer@(7, 22)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(8, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/HOLD；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R83（行438），station=1485，仍有8墙/currentHP=7745。
- 发送的fire命令数（不等于命中/击杀）：Night1=16，Night2=22。
- 【事实】完整Day1 benchmark达标，第一夜后基地1340；第二夜后840。Day3墙容量升至11500但武器仍2/1/1，清空前10墙尚存。不能据此把损失归因为“没建够八墙”。
- 任务错误原始代码（不推算损失金币）：R41:[2, 1]；R153:[1]；R167:[1]；R295:[2, 1]；R310:[1]。

### game19

证据文件：[ally_BlueSide_453.log](../log/Versus/round6/game19/ally_BlueSide_453.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 359 | 84 | 1500 | 4/4000/4000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 2 |
| R131 Night1后 | 702 | 84 | 990 | 4/3765/4000 | 2/1/1 | 10010:210, 10011:200, 10012:220 | 3 |
| R200 Night2前 | 995 | 8 | 3000 | 6/6500/6500 | 2/1/1 | 10010:210, 10011:200, 10012:220 | 3 |
| R261 Night2后 | 1338 | 8 | 2320 | 6/5340/6500 | 2/1/1 | 10010:165, 10012:35 | 2 |
| R330 Night3前 | 1630 | 48 | 2320 | 6/7450/7500 | 2/1/1 | 10010:220, 10011:200, 10012:35 | 3 |
| R358 清空前末次 | 1793 | 48 | 130 | 6/6110/7500 | 2/1/1 | 10010:40 | 1 |
| R359 首次清空 | 1796 | 48 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行320）：10010 worker@(6, 20)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10011 pioneer@(7, 22)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(8, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/TRAVEL；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行435），station=1460，仍有4墙/currentHP=3965。
- 发送的fire命令数（不等于命中/击杀）：Night1=17，Night2=25。
- 【事实】首夜只有4墙、R70物理匹配2。Day2基地升至3000；第二夜后先锋缺失，worker10012为35HP。R330先锋又出现，不能把曾缺失角色认定为永久死亡；最后仅1角色但仍3炮/6墙。
- 任务错误原始代码（不推算损失金币）：R37:[2, 1]；R151:[2]；R152:[1]；R166:[1]；R308:[2]；R309:[1]。

### game20

证据文件：[ally_RedSide_376.log](../log/Versus/round6/game20/ally_RedSide_376.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 359 | 80 | 1500 | 5/5000/5000 | 2/1/1 | 20010:220, 20011:200, 20012:220 | 3 |
| R131 Night1后 | 702 | 80 | 965 | 5/4855/5000 | 2/1/1 | 20010:220, 20011:95, 20012:220 | 3 |
| R200 Night2前 | 993 | 26 | 3000 | 7/8000/8000 | 2/1/1 | 20010:220, 20011:200, 20012:220 | 3 |
| R261 Night2后 | 1336 | 26 | 2520 | 7/6465/8000 | 2/1/1 | 20010:220, 20012:205 | 2 |
| R330 Night3前 | 1629 | 52 | 2520 | 7/8895/9000 | 2/1/1 | 20010:220, 20011:200, 20012:205 | 3 |
| R368 清空前末次 | 1823 | 52 | 55 | 7/5890/9000 | 2/1/1 | 20010:220 | 1 |
| R369 首次清空 | 1826 | 52 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行320）：20010 worker@(31, 8)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；20011 pioneer@(30, 11)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；20012 worker@(31, 12)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：20011=RETURN/HOLD；20010=RETURN/HOLD；20012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行435），station=1470，仍有5墙/currentHP=5000。
- 发送的fire命令数（不等于命中/击杀）：Night1=17，Night2=24。
- 【事实】本组唯一我方RedSide。Day2基地升至3000，第二夜后先锋缺失，R330又出现；R368仅1角色但仍3炮。样本只有一局红方，不能估计选边效应。
- 任务错误原始代码（不推算损失金币）：R25:[1]；R165:[2, 1]；R296:[2]；R297:[1]；R311:[1]。

### game21

证据文件：[ally_BlueSide_84.log](../log/Versus/round6/game21/ally_BlueSide_84.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 361 | 96 | 1500 | 8/8000/8000 | 1/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R131 Night1后 | 704 | 96 | 200 | 8/7180/8000 | 1/1/1 | 10010:220, 10011:90, 10012:220 | 3 |
| R200 Night2前 | 997 | 68 | 200 | 9/9945/10000 | 1/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R261 Night2后 | 1340 | 68 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |
| R214 清空前末次 | 1079 | 68 | 45 | 9/9670/10000 | 1/1/1 | 10010:220, 10011:200, 10012:180 | 3 |
| R215 首次清空 | 1082 | 68 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行322）：10010 worker@(7, 21)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10011 pioneer@(9, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(8, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/HOLD；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行437），station=1460，仍有8墙/currentHP=7910。
- 发送的fire命令数（不等于命中/击杀）：Night1=26，Night2=9。
- 【事实】8墙满血进入首夜，但炮全L1。R131基地仅200，Day2仍未恢复基地，墙却增至9945/10000；R214基地45时仍9墙9670HP且3角色。R215清空。
- 任务错误原始代码（不推算损失金币）：R24:[1]；R42:[2]；R43:[1]；R165:[2, 1]；R179:[2, 1]。

### game22

证据文件：[ally_BlueSide_172.log](../log/Versus/round6/game22/ally_BlueSide_172.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 360 | 32 | 1500 | 6/6000/6000 | 1/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R131 Night1后 | 703 | 32 | 585 | 6/5070/6000 | 1/1/1 | 10010:220, 10011:200 | 2 |
| R200 Night2前 | 995 | 56 | 585 | 8/9000/9000 | 1/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R261 Night2后 | 1338 | 56 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |
| R227 清空前末次 | 1117 | 56 | 70 | 7/7310/8000 | 1/1/1 | 10011:200, 10012:220 | 2 |
| R228 首次清空 | 1120 | 56 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行321）：10010 worker@(7, 22)，背包矿物{'copper': 0, 'iron': 4, 'stone': 1}；10011 pioneer@(8, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(9, 23)，背包矿物{'copper': 10, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/HOLD；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行436），station=1460，仍有6墙/currentHP=5875。
- 发送的fire命令数（不等于命中/击杀）：Night1=25，Night2=18。
- 【事实】6墙/3L1进入首夜，R131仅2角色；R200恢复为3角色（再出现机制未在此推定）。第二夜7墙7310HP尚存时基地仅70，随后清空。
- 任务错误原始代码（不推算损失金币）：R24:[1]；R43:[2, 1]；R146:[2]；R147:[1]；R160:[2, 1]。

### game23

证据文件：[ally_BlueSide_208.log](../log/Versus/round6/game23/ally_BlueSide_208.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 360 | 62 | 1500 | 2/2000/2000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R131 Night1后 | 703 | 62 | 835 | 2/2000/2000 | 2/1/1 | 10010:220, 10011:150, 10012:220 | 3 |
| R200 Night2前 | 995 | 48 | 835 | 5/5500/5500 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 2 |
| R261 Night2后 | 1338 | 48 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |
| R219 清空前末次 | 1092 | 48 | 40 | 5/5485/5500 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R220 首次清空 | 1096 | 48 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行321）：10010 worker@(7, 21)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10011 pioneer@(9, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(7, 22)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/HOLD；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行436），station=1450，仍有2墙/currentHP=2000。
- 发送的fire命令数（不等于命中/击杀）：Night1=17，Night2=13。
- 【事实】首夜仅2墙但均保持满血至R131，基地835。Day2增至5墙5500HP，R219仍3满血角色、3炮、5485墙HP而基地40。随后清空。
- 任务错误原始代码（不推算损失金币）：R36:[2]；R37:[1]；R165:[2, 1]；R181:[2, 1]。

### game24

证据文件：[ally_BlueSide_240.log](../log/Versus/round6/game24/ally_BlueSide_240.log)。下表行号为该原始文件的shadow_turn行。

| 回合/含义 | 行号 | gold | stationHP | 墙数/current/max HP | rocket等级 | 角色ID:HP | M |
|---|---:|---:|---|---|---|---|---:|
| R70 Night1前 | 359 | 32 | 1500 | 8/8000/8000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R131 Night1后 | 702 | 32 | 890 | 8/7635/8000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R200 Night2前 | 996 | 29 | 890 | 9/10000/10000 | 2/1/1 | 10010:220, 10011:200, 10012:220 | 3 |
| R261 Night2后 | 1339 | 29 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |
| R225 清空前末次 | 1112 | 29 | 45 | 9/9145/10000 | 2/1/1 | 10010:220, 10011:200 | 2 |
| R226 首次清空 | 1115 | 29 | ∅（非观测到HP=0） | 0/0/0 | ∅ | ∅ | 0 |

- R70角色位置（trace行320）：10010 worker@(7, 21)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10011 pioneer@(9, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}；10012 worker@(8, 19)，背包矿物{'copper': 0, 'iron': 0, 'stone': 0}。
- R70 jobs：10011=RETURN/HOLD；10010=RETURN/HOLD；10012=RETURN/HOLD；task active=False。
- 首次基地掉血：R82（行435），station=1460，仍有8墙/currentHP=7915。
- 发送的fire命令数（不等于命中/击杀）：Night1=16，Night2=17。
- 【事实】完整Day1 benchmark达标，首夜后基地890、8墙7635HP。Day2增至9墙10000HP，R225基地45时尚有9145墙HP、2满血角色及3炮，R226清空。
- 任务错误原始代码（不推算损失金币）：R37:[2, 1]；R146:[2, 1]；R158:[2]；R159:[1]；R189:[2]；R190:[1]。

## 4. 四个重点核查

### 4.1 Day1 benchmark 与生存

- 【事实】七局全部3 rocket，只有game18、game24同时满足8墙及2/1/1；七局全部度过第一夜。因此“活过第一夜”这个二值指标在本样本没有差异，无法检验benchmark正相关。
- 【事实】达标组Night2后存活1/2，未达标组2/5；首次清空分别为357/226与359/369/215/228/220。未达标的game19、20比两个达标样本中至少一局生存更久。
- 【事实】达标组第一夜后基地HP为1340/890；未达标组990/965/200/585/835。8墙全L1的game21基地200，2墙2/1/1的game23基地835，是“只看墙数”不可靠的直接对照。
- 【推断】完整benchmark不是存活的充分条件，也不是本组活过第一夜的必要条件。
- 【假设】benchmark是否带来平均生存收益仍未验证；仅7局、地图/位置/经济/敌情不同，不能声称正相关成立，也不能声称负相关成立。三炮构成在本组恒定，完全无法比较不同武器组合。

### 4.2 无立即执行能力的资金预留

- 【事实】game20 R1～R2（行55/61）：75G全部build预留、free=0；三人实际均move，无build。说明为未来建炮提前锁资确实存在；这可以是有意的开局保护，单凭这两回合不能判定有害。BUILD_WEAPON日志executable_now=True也不等于已发build。
- 【事实】game21 R46（行210）：96G全部upgrade预留，free=0；券cost100/gap4，owner=null，NO_ACTOR+FUNDING_GAP；两个worker都BUILD_WALL。R50～R70仍96G，R70三人RETURN，无任何动作。不能把这解释为“有100金币但不买”，实际现金还差4。
- 【事实】game18 R190（行925）：62G，wall预留20/free42；新墙升级goal40006价格20、funded_cash=True但owner=null/NO_ACTOR；一人ECONOMY，两人RETURN。足额现金与无法派遣并存。
- 【代码事实】strategy.py:710～766先按缺失武器/墙服务/升级需要建立BudgetReserve，然后208～272分配owner。升级预留不以最终route/deadline/owner可用为前提；actions.BudgetReserve.available扣除其他bucket预留。因此“reserved=有可执行行程”的假设不成立。
- 【推断】预算和执行分配之间存在可观察的不一致；它会限制其他bucket可用资金。
- 【假设】释放预留后能否完成更有价值动作、是否因此能避免战败均未证明。NO_ACTOR不区分死亡、任务占用、所有候选路线/期限落选；不能据该标签自行确定唯一根因。

### 4.3 未完成建设与暂停/回防

| 对局 | Day1首次DEADLINE_INFEASIBLE（当时墙数） | Day1最后发wall build | R70墙数 |
|---|---|---|---:|
| game18 | 无 | R46 | 8 |
| game19 | R48 / 3墙 / 行214 | R62 | 4 |
| game20 | R57 / 4墙 / 行280 | R57 | 5 |
| game21 | R59 / 7墙 / 行288 | R60 | 8 |
| game22 | R52 / 6墙 / 行266 | R51 | 6 |
| game23 | R48 / 2墙 / 行215 | R47 | 2 |
| game24 | R53 / 6墙 / 行268 | R58 | 8 |

- 【事实】game23 R50（行260）：DAY_NORMAL、gold/free均62、2墙；两worker均BUILD_WALL/PAUSED，无实际命令；路线True、deadline False。离日落尚20轮，但程序判下一墙完整行程不可完成，确实在未完成防御时停工。
- 【代码事实】completion_trip:512按下一墙的采集、到位、建造及回程估算；reconcile:800～806将不可行job标PAUSED，并把记录的remaining改为0。execute_job:923再次按deadline拒绝。此处日志estimated_finish=49只是暂停后的零工作估计，不是原建墙行程真的能在R49结束。
- 【代码事实】direct_due:817按角色当前位置到controller slot的直接路径与5轮margin决定RETURN；本轮代码白天重新分配RETURN，没有复现Round5那种永久残留即可解释全部停工的证据。
- 【事实】6局出现Day1期限暂停，但game21/24之后另一工人仍继续并最终完成8墙。因此不能把任一DEADLINE_INFEASIBLE当作全队或全天停工。所有局R70均PRE_NIGHT/RETURN；game19仍只有2个物理邻接匹配，提前回防也未保证三人就位。
- 【假设】margin过大、路线过保守、slot选择不当或是否仍存在安全替代动作，均需反事实路线复核；本轮不把“还有20回合”直接当作“必能再建墙”。

### 4.4 墙总量能否代理基地安全

- 【事实】game23第一夜基地损失665HP，两墙损失0；game20第一夜基地损失535HP，5墙仅损失145HP；game24第一夜基地损失610HP，8墙仅损失365HP。
- 【事实】清空前game21有9670/10000墙HP、基地45；game23有5485/5500墙HP、基地40；game24有9145/10000墙HP、基地45。七局清空前都仍有全部3炮及多面墙，先前表格保留确切数量。
- 【推断】wall_count/wall_total_hp作为“基地保护已足够”的单独代理不可靠，无法代表有效覆盖或威胁消除；它们作为资产统计仍然有效。不能再把修复/增加总HP等同于改善存活。
- 【假设】是否为绕墙、墙位没有覆盖威胁方向、攻击距离、炮位/火力节奏、目标评分或敌方策略造成直接基地伤害尚未区分。defense.attack_plan:337按估计伤害及角色/基地附近权重评分，没有从本组日志得到逐次命中/伤害归因；本轮不修改scorer。

## 5. intended / actual / 平台执行的三层边界

- 【事实】4245条报告的divergent_actor_ids全为空，prompt/executeCmd差异标记均false；全部是defense authority。
- 【代码事实】strategy.run:1037在authority模式把actual=intended，因此零divergence在此模式不是独立执行成功证明，也不是与legacy策略的有效比较。session.handle仍执行协议、ActionValidator复验后提交；没有把这些报告当作服务器战斗结果。
- 【事实】日志未出现Traceback、process_request异常或shadow_performance告警。关联反馈失败仅game21 R152一次：trace行807的10012 success=False，对应R151 move到(21,17)；报告associated_failures=1。没有错误代码说明具体失败原因。其余报告未记录关联失败，不等于所有动作都已得到完整成功反馈。
- 【事实】每局只有前三次trace_request/trace_response包；trace_turn也只是抽样且角色列表可能截断。不能独立逐回合证明所有发送动作与平台结果相等，不能把ready炮没fire直接记为漏射，不能把机器人数量减少记为击杀。
- 【推断】现有证据更支持策略层效果不佳，而不是一个已证明的大规模Response替换故障；但不能排除稀疏日志未覆盖的执行差异。

## 6. 对手材料交叉核对

| game | 对手R70 score/base/actors | R130 | R200 | R260 |
|---|---|---|---|---|
| game18 | 210/1500/3 | 250/1500/3 | 508/1500/3 | 563/1500/3 |
| game19 | 210/1500/3 | 250/1500/3 | 508/1500/3 | 563/1500/3 |
| game20 | 307/1500/3 | 347/1500/3 | 444/1500/3 | 499/1500/3 |
| game21 | 210/1500/3 | 250/1500/3 | 444/1500/3 | 499/1500/3 |
| game22 | 210/1500/3 | 250/1500/3 | 444/1500/3 | 499/1500/3 |
| game23 | 210/1500/3 | 250/1500/3 | 444/1500/3 | 499/1500/3 |
| game24 | 210/1500/3 | 250/1500/3 | 444/1500/3 | 499/1500/3 |

这些是对手日志自报checkpoint，七局R260均base1500/3角色，与我方损伤形成观察对照；不同地图侧与策略并非受控实验。MATCH2 tail只保留少量事件，不能从缺少upgrade事件推出从未升级，也不反推未知字段含义。文件名得分与最后日志score不同，最终官方结算仍unknown。

## 7. 封存结论和下一阶段

**V2.3已经过Round6实战验证失败：七局均未完成1300回合生存目标。** 这是目标验收结论，不是对每个独立机制的因果判决。

V2.3以下核心策略全部降级为hypothesis：固定三rocket/八墙/2-1-1开局；总墙HP容量目标及日增长公式；现有canonical布局保护能力；下一墙与5轮margin估算的收益；预算预留与资本分配优先级；并行工人/先锋物流对经济效率的改善；80%控制员健康与70%基地emergency阈值的充分性；既有火力评分/驻守组合能支撑长期防守。程序中已有实现或单测通过不提升这些假设的实机可信度。

下一阶段命名为 **V2.4 Strategy Re-baseline**。需要先重建可检验假设与对照口径；本checkpoint不指定新武器组合、参数、调度优先级或修复方案。协议契约、动作原子性等工程约束不因策略失败而降级。

## 8. 证据清单（SHA-256）

| 文件 | SHA-256 |
|---|---|
| log/Versus/round6/game18/ally_BlueSide_274.log | `d5e1f16d1e1cee50bcb0f06e359e89badbf29c36fbfd5ed1354a8cbbcee205c7` |
| log/Versus/round6/game18/enemy_RedSide_1020.log | `8abc3d8d1872a463d77769d95576f936da8fe438635de829a6fbb2d0fa12403d` |
| log/Versus/round6/game19/ally_BlueSide_453.log | `e640245043079f7d42b12024eb623d479230eadc20ef07ddf8605baf1092d78d` |
| log/Versus/round6/game19/enemy_RedSide_1035.log | `a3db05abddb0e95e8277750f802c5bc6424de690b22e982a782d2848aa8883dd` |
| log/Versus/round6/game20/ally_RedSide_376.log | `01c0dc9a407effcb18ae0a23c095d263dce603ea3607962ed0417858fce262c8` |
| log/Versus/round6/game20/eneny_BlueSide_797.log | `312d0c33b04d78506d211aba4b02dab676fdab087c060ea60bcfcedb10d9e4ff` |
| log/Versus/round6/game21/ally_BlueSide_84.log | `5a14f0917b8233ea35a29c56791268d85a860547087beaeb4c15e036b685260a` |
| log/Versus/round6/game21/enemy_RedSide_900.log | `da54af5398a8d598c9828b69bdc90f820c8862d05cb204bbf674f28cc512c10b` |
| log/Versus/round6/game22/ally_BlueSide_172.log | `a4f9f86164fb75ea19bea4be330cd1e912afd8af3fedeaff4ce0c2e1a09780e9` |
| log/Versus/round6/game22/enemy_RedSide_910.log | `1d0e09f24acb0dfe8742ff16d63ac10733bfb98f32700f3f5df8f7545575306f` |
| log/Versus/round6/game23/ally_BlueSide_208.log | `119a21bcefe87c3ee2ac5a07427665bd2afcde5062ff420f7d7eb05f725f6762` |
| log/Versus/round6/game23/enemy_RedSide_949.log | `e5375e223588166e3bdcbde1e7843f8877ce769c0cddfdf7b59b8a5bd1346544` |
| log/Versus/round6/game24/ally_BlueSide_240.log | `6c14941f95afd97abee6eda8df13582650fd1a2a5ad92e5091eb985bcd3ae03a` |
| log/Versus/round6/game24/enemy_RedSide_924.log | `722c7ecdd86998dbd314adff2677a0b2dfb231e5cde70bb49e2257b38a6d767d` |

运行源码冻结指纹：

| 文件 | SHA-256 |
|---|---|
| src/agentrace/strategy.py（HEAD blob字节） | `3a110d6c691ecb530493b9b3e81c20eaac6c2dd2df61386305269fbdad29ca4e` |
| src/agentrace/defense.py（HEAD blob字节） | `986074cb2983f1b9f1d5155966a35cde5288011a8c81a7dab1d8035dcb94e6cf` |
| src/agentrace/actions.py（HEAD blob字节） | `adebf03aee8cffdb0e34461009968a25e3507b25f46ae949691b08222c3eb9ff` |
| src/agentrace/model.py（HEAD blob字节） | `254579f668a25382066fc835c072ef555d7b7bb6849f01b5925a0c07424aa7df` |
| src/agentrace/session.py（HEAD blob字节） | `e00c1ca34afef16e6efca0326d5ffcef49e5724a4c8900ac1ed0a745071c728d` |

## 9. 测试与范围

本轮仅文档封存。现有全量测试210项PASS（24.021秒），无跳过，命令为`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`；git diff --check通过。独立只读复核未发现表格/行号或证据归因错误。测试通过只能说明仓库既有逻辑/接口回归正常，不能撤销Round6策略验收失败。
