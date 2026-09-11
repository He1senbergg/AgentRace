# Round3 实机证据与 V2.1 Shadow 修订

三局实际响应均来自legacy；Shadow意图没有执行，不能把比赛失守归因于V2动作。

MATCH2按run/event拼接全部分片，校验原文长度和SHA-256，再解压JSON。所有事件都解码；日志自己的log_omitted不是解码失败，缺失事件仍是unknown。
defense_daily数组仅使用前五列x/y/id/level/HP，并与同回合defense_checkpoint交叉核对；其余未命名列不用于推导。墙HP总和不是战斗EHP或因果证明。
下表严格取指定回合，不用R330冒充R331、R71冒充R70。score是日志累计总分，任务独立得分unknown；任务/升级事件另列。

## game8

敌方源文件：`log/Versus/round3/game8/enemy_BlueSide_678.log`；完整校验解码 194 个事件。
事件计数：`{'startup': 1, 'world': 1, 'shop': 2, 'state_change': 20, 'game_start': 1, 'defense_checkpoint': 5, 'news': 7, 'defense_daily': 11, 'action': 15, 'status': 3, 'wall_plan': 2, 'task_accept_attempt': 2, 'task_text': 6, 'task_open': 6, 'sandbox_command': 18, 'sandbox_result': 17, 'task_document': 10, 'task_fast_path': 2, 'answer_submit': 3, 'task_end': 5, 'model_call': 14, 'model_reply': 13, 'wall_probe': 8, 'upgrade_attempt': 9, 'upgrade_result': 9, 'log_omitted': 3, 'errors': 1}`。

| 阵营/回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| enemy R70 | [1500] | unknown | unknown | 8 / 8000 | {1: 8} | 100 | 193 |
| ally R70 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [1, 1, 1] | 8 / 8000 | unknown（摘要无墙level） | 61 | unknown |
| enemy R131 | [1455] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 8 / 7035 | {1: 8} | 100 | 233 |
| ally R131 | [1360] | 3 / {'20010': 65, '20011': 200, '20012': 220} | [1, 1, 1] | 8 / 5705 | unknown（摘要无墙level） | 61 | unknown |
| enemy R261 | [1455] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 2, 1] | 12 / 12100 | {2: 3, 1: 9} | 20 | 385 |
| ally R261 | [1265] | 3 / {'20010': 210, '20011': 200, '20012': 130} | [2, 1, 1] | 8 / 4905 | unknown（摘要无墙level） | 27 | unknown |
| enemy R331 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| ally R331 | [1265] | 3 / {'20010': 210, '20011': 200, '20012': 130} | [2, 1, 1] | 8 / 6745 | unknown（摘要无墙level） | 57 | unknown |
| enemy R390 | [1090] | unknown | unknown | 10 / 7440 | {'unknown': 10} | 70 | 549 |
| ally R390 | [] | 0 / unknown | [] | 0 / 0 | unknown（摘要无墙level） | 57 | unknown |

敌方邻近检查点（与精确指定回合分开）：

| 回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| R71 | [1500] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 8 / 8000 | {1: 8} | 100 | 193 |
| R200 | [1455] | unknown | unknown | 12 / 13265 | {1: 9, 2: 3} | 20 | 330 |
| R201 | [1455] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 2, 1] | 12 / 13265 | {2: 3, 1: 9} | 20 | 330 |
| R330 | [1455] | unknown | unknown | 12 / 14580 | {1: 7, 2: 4, 3: 1} | 70 | 482 |
| R391 | [1070] | unknown | unknown | 10 / 7395 | {1: 6, 2: 4} | 70 | 549 |

任务结束记录：下列score/gold是事件报告余额，不假定全由任务单独贡献。

- R12：started=9，score=105，gold=80，errors=[]。
- R25：started=16，score=193，gold=160，errors=[]。
- R151：started=141，score=233，gold=40，errors=[{'errorCode': 1, 'description': 'timeout'}]。
- R158：started=155，score=330，gold=120，errors=[]。
- R279：started=269，score=385，gold=30，errors=[{'errorCode': 1, 'description': 'timeout'}]。

升级结果记录（buy成功不等于已使用；未记录的后续事件为unknown）：

- R40：buy WeaponUpgradeVoucher1，result=True，gold=60。
- R55：use WeaponUpgradeVoucher1，result=True，gold=100。
- R150：buy WallUpgradeVoucher1，result=True，gold=40。
- R162：use WallUpgradeVoucher1，result=True，gold=120。
- R163：use WallUpgradeVoucher1，result=True，gold=120。
- R164：use WallUpgradeVoucher1，result=True，gold=120。
- R176：buy WeaponUpgradeVoucher1，result=True，gold=20。
- R193：use WeaponUpgradeVoucher1，result=True，gold=20。
- R279：buy WallUpgradeVoucher2，result=True，gold=30。

## game9

敌方源文件：`log/Versus/round3/game9/enemy_BlueSide_639.log`；完整校验解码 189 个事件。
事件计数：`{'startup': 1, 'world': 1, 'shop': 2, 'state_change': 24, 'game_start': 1, 'defense_checkpoint': 5, 'news': 6, 'defense_daily': 11, 'action': 9, 'status': 6, 'wall_plan': 3, 'task_accept_attempt': 4, 'task_text': 5, 'task_open': 5, 'sandbox_command': 17, 'sandbox_result': 17, 'task_document': 10, 'task_fast_path': 2, 'answer_submit': 3, 'task_end': 5, 'model_call': 13, 'model_reply': 12, 'upgrade_attempt': 10, 'upgrade_result': 9, 'wall_probe': 2, 'errors': 1, 'log_omitted': 3, 'defense_alert': 2}`。

| 阵营/回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| enemy R70 | [1500] | unknown | unknown | 2 / 2000 | {1: 2} | 60 | 196 |
| ally R70 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [2, 1, 1] | 8 / 8000 | unknown（摘要无墙level） | 25 | unknown |
| enemy R131 | [1275] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 2 / 1370 | {1: 2} | 60 | 236 |
| ally R131 | [1470] | 3 / {'20010': 220, '20011': 200, '20012': 205} | [2, 1, 1] | 8 / 7030 | unknown（摘要无墙level） | 25 | unknown |
| enemy R261 | [1115] | 2 / {'10010': 220, '10012': 220} | [2, 1, 1] | 6 / 5535 | {2: 3, 1: 3} | 80 | 388 |
| ally R261 | [1375] | 3 / {'20010': 120, '20011': 200, '20012': 205} | [2, 1, 1] | 8 / 5540 | unknown（摘要无墙level） | 71 | unknown |
| enemy R331 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| ally R331 | [1375] | 3 / {'20010': 120, '20011': 200, '20012': 205} | [2, 2, 1] | 8 / 6425 | unknown（摘要无墙level） | 47 | unknown |
| enemy R390 | [320] | unknown | unknown | 6 / 2970 | {'unknown': 6} | 100 | 550 |
| ally R390 | [] | 0 / unknown | [] | 0 / 0 | unknown（摘要无墙level） | 47 | unknown |

敌方邻近检查点（与精确指定回合分开）：

| 回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| R71 | [1500] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 2 / 2000 | {1: 2} | 60 | 196 |
| R200 | [1275] | unknown | unknown | 6 / 7500 | {1: 3, 2: 3} | 80 | 333 |
| R201 | [1275] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 6 / 7500 | {2: 3, 1: 3} | 80 | 333 |
| R330 | [1115] | unknown | unknown | 8 / 9775 | {1: 5, 3: 2, 2: 1} | 100 | 485 |
| R391 | [300] | unknown | unknown | 6 / 2920 | {1: 4, 3: 1, 2: 1} | 100 | 550 |

任务结束记录：下列score/gold是事件报告余额，不假定全由任务单独贡献。

- R12：started=9，score=105，gold=80，errors=[]。
- R23：started=16，score=196，gold=160，errors=[]。
- R149：started=139，score=236，gold=20，errors=[{'errorCode': 1, 'description': 'timeout'}]。
- R155：started=152，score=333，gold=100，errors=[]。
- R297：started=287，score=388，gold=20，errors=[{'errorCode': 1, 'description': 'timeout'}]。

升级结果记录（buy成功不等于已使用；未记录的后续事件为unknown）：

- R28：buy WeaponUpgradeVoucher1，result=True，gold=60。
- R44：use WeaponUpgradeVoucher1，result=True，gold=60。
- R148：buy WallUpgradeVoucher1，result=True，gold=20。
- R161：use WallUpgradeVoucher1，result=True，gold=100。
- R163：use WallUpgradeVoucher1，result=True，gold=100。
- R175：buy WallUpgradeVoucher1，result=True，gold=80。
- R190：use WallUpgradeVoucher1，result=True，gold=80。
- R278：buy WallUpgradeVoucher2，result=True，gold=20。
- R294：use WallUpgradeVoucher2，result=True，gold=20。

## game10

敌方源文件：`log/Versus/round3/game10/enemy_RedSide_748.log`；完整校验解码 188 个事件。
事件计数：`{'startup': 1, 'world': 1, 'shop': 2, 'state_change': 19, 'game_start': 1, 'defense_checkpoint': 5, 'news': 6, 'defense_daily': 11, 'status': 3, 'action': 15, 'wall_plan': 3, 'task_accept_attempt': 3, 'task_text': 6, 'task_open': 5, 'sandbox_command': 16, 'sandbox_result': 16, 'task_document': 10, 'task_fast_path': 3, 'answer_submit': 5, 'task_end': 5, 'model_call': 11, 'model_reply': 10, 'wall_probe': 8, 'errors': 2, 'upgrade_attempt': 9, 'upgrade_result': 9, 'log_omitted': 3}`。

| 阵营/回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| enemy R70 | [1500] | unknown | unknown | 8 / 8000 | {1: 8} | 140 | 290 |
| ally R70 | [1500] | 3 / {'10010': 220, '10011': 200, '10012': 220} | [2, 1, 1] | 8 / 8000 | unknown（摘要无墙level） | 10 | unknown |
| enemy R131 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [2, 1, 1] | 8 / 6810 | {1: 8} | 140 | 330 |
| ally R131 | [1500] | 3 / {'10010': 210, '10011': 200, '10012': 220} | [2, 1, 1] | 8 / 6870 | unknown（摘要无墙level） | 10 | unknown |
| enemy R261 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [2, 2, 1] | 10 / 9975 | {2: 3, 1: 7} | 60 | 482 |
| ally R261 | [1455] | 3 / {'10010': 175, '10011': 200, '10012': 220} | [2, 2, 1] | 9 / 7315 | unknown（摘要无墙level） | 20 | unknown |
| enemy R331 | unknown | unknown | unknown | unknown | unknown | unknown | unknown |
| ally R331 | [1455] | 3 / {'10010': 175, '10011': 200, '10012': 220} | [2, 2, 1] | 9 / 8085 | unknown（摘要无墙level） | 79 | unknown |
| enemy R390 | [195] | unknown | unknown | 11 / 7325 | {'unknown': 11} | 115 | 650 |
| ally R390 | [5] | 2 / {'10011': 200, '10012': 220} | [2, 2, 1] | 5 / 3625 | unknown（摘要无墙level） | 79 | unknown |

敌方邻近检查点（与精确指定回合分开）：

| 回合 | station HP | actor count / HP | weapon levels | wall count / total HP | wall levels计数 | gold | total score |
|---|---|---|---|---|---|---|---|
| R71 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [2, 1, 1] | 8 / 8000 | {1: 8} | 140 | 290 |
| R200 | [1500] | unknown | unknown | 10 / 11195 | {2: 3, 1: 7} | 60 | 427 |
| R201 | [1500] | 3 / {'20010': 220, '20011': 200, '20012': 220} | [2, 2, 1] | 10 / 11195 | {2: 3, 1: 7} | 60 | 427 |
| R330 | [1500] | unknown | unknown | 12 / 13755 | {2: 3, 3: 1, 1: 8} | 115 | 568 |
| R391 | [195] | unknown | unknown | 11 / 7325 | {2: 3, 1: 8} | 115 | 650 |

任务结束记录：下列score/gold是事件报告余额，不假定全由任务单独贡献。

- R13：started=10，score=105，gold=80，errors=[]。
- R25：started=16，score=193，gold=160，errors=[]。
- R53：started=50，score=290，gold=140，errors=[]。
- R139：started=136，score=427，gold=220，errors=[]。
- R153：started=143，score=427，gold=60，errors=[{'errorCode': 1, 'description': 'timeout'}]。

升级结果记录（buy成功不等于已使用；未记录的后续事件为unknown）：

- R34：buy WeaponUpgradeVoucher1，result=True，gold=60。
- R43：use WeaponUpgradeVoucher1，result=True，gold=60。
- R140：buy WallUpgradeVoucher1，result=True，gold=160。
- R141：buy WeaponUpgradeVoucher1，result=True，gold=60。
- R151：use WallUpgradeVoucher1，result=True，gold=60。
- R152：use WallUpgradeVoucher1，result=True，gold=60。
- R155：use WallUpgradeVoucher1，result=True，gold=60。
- R161：use WeaponUpgradeVoucher1，result=True，gold=60。
- R269：buy WallUpgradeVoucher2，result=True，gold=30。

