# Round5 / game17：V2.3 资金兑现与并行施工

## 证据边界

完整解析 `log/Versus/round5/game17/ally_BlueSide_192.log`：623 条 shadow_turn、82 条 trace_turn。日志模式是 defense；并非仅意图未执行的 Shadow 实验。以下行号指原始文件，不把受控地图测试称为完整比赛 replay。R18 没有完整背包/路径快照，无法补猜当时是否已有价值20的铜，也不能证明当时商店不可达或某条购买命令被官方拒绝。

| 回合 | 日志行 | gold | execution墙目标 | 关键状态 |
|---|---:|---:|---:|---|
| R1 | 55 | 75 | 8 | worker建炮、另一worker施工 |
| R2 | 61 | 50 | 6 | 单工全批估算首次压低目标 |
| R5 | 76 | 0 | 1 | 三炮L1；UPGRADE owner开始筹资 |
| R7 | 84 | 0 | 0 | 墙工变ECONOMY |
| R18 | 120 | 80 | 0 | UPGRADE仍有owner；按100G券缺20现金，库存可变现值unknown |
| R28 | 151 | 80 | 0 | 10010 UPGRADE→RETURN；预计完成R65、return_deadline64，直接回程仅6步 |
| R29 | 154 | 80 | 0 | 全局DAY_NORMAL，但10010的RETURN仍保留 |
| R37 | 181 | 144 | 0 | 现金已足；没有UPGRADE owner，原工人仍RETURN |
| R51 | 263 | 194 | 0 | 没有恢复升级调度 |
| R70 | 360 | 194 | 0 | 三人RETURN，三炮L1，upgrade预留100，无实际命令 |

根因不是“始终缺钱”：R18是现金缺口（库存能否闭合unknown）；R37之后是 `WRONG_JOB_STATE` 导致 `NO_ACTOR`。旧reconcile只给没有job的角色分配，RETURN的deadline延续到夜末；全局恢复DAY_NORMAL不释放它，金币增加也不会触发补位。R70临近日落，不能反推此刻买券仍来得及；应在R37到款时重新分配。R37同时出现任务结束/错误1，不能把80→144的64G全部归因成功任务奖励。

墙目标8→6→1→0是全局数量被单个工人的完整剩余批次估算覆盖，并非地图证明零墙可行。每次执行又基于已经降低的目标继续下调，形成不可恢复的停工。

## 修订

- CapitalGoal跨观测保存目标建筑、券、目标等级/HP、owner、状态及最后接受动作。资金、路径、deadline、角色占用、背包、预算分别诊断，不再使用FUNDS_OR_DEADLINE。
- 已有现金加该owner背包可卖矿物足够时，调用原 `cash_in(force=True)`；普通批次ROI不变，销售收入只有下一次goldNum观察到才可花。满包也必须计入vendor→shop→target→return完整路线。
- worker施工按下一墙（k=1）估算、预留独立slot；材料消耗用rules.wall_stone_cost。下一墙不可行仅PAUSED，不修改benchmark或永久递减execution目标。当前基准与执行目标均保留数量目标，实际缺口另看墙数/readiness，`unmet_wall_target`仍表示benchmark与execution之差。
- 白天重新评估RETURN和购买owner；当前直接回程的安全截止控制PRE_NIGHT，不用一次失败的完整errand把角色永久锁回家。资本服务、下一墙在发动作前各自验证完整截止。
- 活跃任务TASK_LOCK，新任务须可行；其余先锋可LOGISTICS，但低血先锋的既有HEAL优先于新任务。LOGISTICS不能collect/build。TaskPlanner、prompt/executeCmd、原异步记忆不变。
- 实验容量floor为8000/12000/15000。D4+取max(15000,上一夜观测初始容量+压力增长)。压力=0.5×连续观测墙HP减少 +1000×缺失墙ID数 +2×基地HP减少 +1000×缺失控制员ID数，向上取500的整倍数。缺失ID是风险代理，不声称死亡原因已确认；断档/缺夜首尾标complete=false，仅使用已观察下界。该公式需要实机校准，不是比赛规则。
- legacy base_reserve、普通经济模块、共享动作验证、GameMemory.observe、TaskPlanner及夜战评分/匹配/cooldown均未改。

## 验证与限制

`tests/test_round5.py` 用真实R1/R2/R5/R7/R18/R37/R70日志事实做对照，并用明确构造的可达地图验证分工和购买序列。它不能证明game17真实地图在R18一定完成采购，也不能证明1300回合存活。最终全量210项PASS（24.719秒，无跳过），专项16项PASS；旧测试模式及政策变更逐项说明见TEST_PLAN。legacy断言没有放宽。无新实机比赛。

进入本轮前HEAD已经默认 `defense`，STATUS和旧启动测试却仍写shadow。本轮保留该已提交默认值，不把此次测试修正写成V2.3切换authority。
