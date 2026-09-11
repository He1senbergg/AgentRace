# AgentRace 当前检查点

## 当前阶段
2026-09-10：当前上传版本默认 Shadow（DEFAULT_STRATEGY_MODE），无需平台添加参数；显式 --strategy-mode legacy 可本地回退。Shadow只记录V2意图，roleCommandMap/prompt/executeCmd全部仍由legacy返回。已补最小instrumentation，不改变策略或端口参数；本patch完成后停止，不切换V2实际决策权。以下round2实机成果为历史背景，1300回合目标尚未证明。

## 默认 Shadow instrumentation patch
- 日志增加strategy_mode、defense_target、详细jobs/deadline、controllers/assignment_status、budget、timing_ms、结构化divergence（保留weapon actor/controllerId）、wall_target_changed、pre_night估算和task估算；没有值时为null/空结构。
- perf_counter计时：legacy规划、Shadow复制/规划、handle入口至日志输出前的总处理时间（包括锁等待和原诊断）。总计不包含本条Shadow日志自身I/O及HTTP发送；重复缓存不重复输出。total>3000ms或shadow>1500ms只告警，不改变实际动作。
- Shadow只拿实际响应的副本；Shadow/report/日志异常不能替换实际响应。未改攻击评分、TaskPlanner或后续天政策。
- 2026-09-11 round3 V2.1：拉取并分析 game8/game9/game10。修正 controller 为“持久角色站位/区域 + 每回合当前邻接最大匹配”；不因 exact safe_slot 或 cooldown 改换 weapon ownership。修正 benchmark_wall_target=8（Day1恒定）与 execution_wall_target/unmet_wall_target 分离；长期deadline使用static blockers。新白天重建DailyPlan并清除CONTROL/RETURN/PRE_NIGHT残留。Shadow扩展到Day3：Day2墙数9/EHP约8000，Day3墙数10/EHP约10000、武器2/2/1均为实验参数，不是规则。
- round3 evidence：game10 R331旧Shadow ready=0而实际邻接至少3人，legacy两炮开火；game9旧映射漏掉实际炮手。game8/game10 Shadow早期墙目标降至7/4但legacy R70实际均8墙。敌方MATCH2三局共571事件全部完成分片、长度、SHA-256校验；R330敌墙总HP分别14580/9775/13755，精确R331缺失写unknown，详见 [ROUND3_ANALYSIS.md](ROUND3_ANALYSIS.md)。墙缺失指标改为wall_ids_missing_since_night_start，不归因摧毁。
- 验证：新增5项instrumentation与原14项Shadow专项合计19项PASS；最终Windows全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，160项PASS（19.999秒），包含默认Shadow真实HTTP和显式legacy回退。首次全量仅旧日志数量断言失败，改为两类日志各一条后重验通过；未放宽性能门槛。diff --check通过。已停止于本patch，不进入V2 authority。
- V2.1验证：round3专项（匹配、R331 fixtures、静态deadline、墙目标分层、NEW_DAY、Day2/Day3 wall service、墙缺失归因、MATCH2完整性）28项PASS；最终Windows全量169项PASS（28.788秒）。实际响应仍legacy，未启用V2 authority。

## 本轮 Shadow 检查点
- src/main3.py 新增 ObservationDelta、RoleJob、ControllerAssignment、BudgetReserve、JobAuthorization/ActionProposal/ActionArbiter、CanonicalLayout、Day1Plan、StrategicState、StrategicPlanner。仍单文件部署，无新增依赖。
- GameMemory.observe 是唯一原始反馈关联边界；Shadow 在观察后、legacy规划前的独立 memory 上计算。真实 previous_actions/配额/任务状态不接收 intended actions，缓存请求不重复运行 Shadow；失败保留旧战略检查点并记录异常类型。
- attack 原子占用 weapon+controller；验证接受后才扣本回合 staged_gold，拒绝不扣。每次新观测以 goldNum 重新建立预算，不预支任务或售矿收益。初始75优先锁三炮，余款才进入首个升级预留。
- 四种 mode：DAY_NORMAL/RECOVERY/PRE_NIGHT/NIGHT。首日建炮、批量取石筑墙、升级、任务和经济由持久 job 表达；回防基于当前路径、job完成动作、返程及5回合策略余量。墙计划不可完成先降低执行目标，benchmark仍为8墙。
- 静态障碍与临时角色/机器人占位分离；布局以实际基地 footprint 中心镜像，逐候选检查静态炮位出口；石耗均来自 rules.wall_stone_cost。
- 日志仅基础观测/命令指标，不计算击杀、漏射或因果伤害。R71 benchmark 与 R131/R261 生存审查分离；后者核对基地HP、存活角色/武器和控制员可用性，墙数/HP仅诊断。
- 14项新增专项已通过；独立只读审查反馈的任务频道覆盖、过早回防、失效驻守已修正。最终复核无阻塞Shadow交付问题。
- 本轮未修改用户的 docs/STRATEGY_V2.md；未自动创建Git commit。

## 上一批 Shadow 验证（历史）
- Windows `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`：155项PASS（16.311秒），含Shadow真实HTTP密集输入/并发、默认legacy HTTP、2600观测集成及14项Shadow专项；无跳过。
- 首次全量发现Shadow重复火箭全扫描导致密集HTTP超时，改Shadow专用格子索引并增加等价回归；未放宽5秒限制。修复后18项Shadow+HTTP专项及最终全量通过。没有重复WSL测试。
- `git -c core.whitespace=cr-at-eol diff --check`通过。该批可作为人工Git提交检查点，尚未自动提交。

## Shadow 限制与停止点
- Day2及以后白天仅观测指标，不提供通用恢复/经济战略；后续夜间只复用持久控制员框架。未实现Day10/MPC/GoldClaim/新宝藏或PvP/完整MatchAnalyzer。
- 路径估算不证明未来占位、任务成功或战斗安全；当前炮手补位是确定性贪心，缺员/动态堵路下的最优匹配和脱困尚未验证。safe_slot 是策略名，不是无伤保证。
- Shadow逐轮跟随真实legacy观测，不是V2闭环实机；round2摘要日志不能补造完整观测进行比赛重放。不得以本地PASS证明R71 benchmark或R131/R261生存通过。
- 下一步：向用户报告Shadow验证结果后停止。用户确认之前禁止添加/启用V2实际决策模式。

## 当前实现
- 入口src/main3.py；保留严格协议校验、共享预算、重复缓存、事务回滚和诊断。
- 撤回上轮前向炮位：改侧后火箭与前侧墙线，后半圈保留通道；利用火箭路径无遮挡。布局收益仍需实机。
- 炮手全局匹配替代逐炮抢人，优先就绪炮和完整覆盖；最多343种组合，已邻接安全移动仍限一步。
- 升级在备药/提前回防前调度，固定运券依观测继续；健康角色为首个L2留资金；满血墙不再自动升级。
- 首日wall_builder批量取石筑最多八墙的主动目标，避免逐墙往返/矿物销售抢占，可与升级工并行。26回合采集往返预算加日落门禁；死亡/不可达/堵墙/任务不再可行即释放。
- 保留此前任务D-3最后探索、任务发现、Medicine治疗优先和跨日矿点收益重选。

## 验证
- 最终一次Windows：.venv\Scripts\python.exe -B -m unittest discover -s tests -q，141项PASS（15.956秒）。含实际HTTP/并发/密集输入及两个半场各1300观测回放；没有重复WSL全量。
- 新增六项round2回归，含实际应用动作的八石八墙（R46前完成）、145金币迟到升级交付和全局炮手匹配。模型不含战斗，不声称整场重放。
- 独立复核发现带石工人堵墙后不释放，已修复并覆盖；最终无新增阻塞问题。git diff --check通过。

## 风险与下一步
- 下一次实机先核对首夜墙数/炮等级、就绪炮缺员时间、第二日修理和收入，继续以1300回合持续防守为目标。
- 对手712分局首夜L2/L1/L1但有八墙，R131基地1475且炮手满血；对手亦非已验证的1300回合模板。
- 动态堵路、墙持续维修、真实解题率、多发/同回合死亡弹道等仍缺充分验证。两局分数与日志统计不能作为策略因果证明。
- 测试遵循成本偏好：局部简洁专项，交付时单次单环境全量，文档变化不跑套件；无平台理由不重复双环境。
