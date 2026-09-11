# AgentRace 当前检查点

## 当前阶段
2026-09-11：V2.3 Parallel Production + Capital Deployment已完成本地实现、验证与独立审查，现暂停等待用户审阅。已完整解析game17的623条Shadow记录/82条trace。R18现金80，R28升级工提前RETURN，R37现金144时无升级owner，R70现金194仍三炮L1；不是全程缺钱。详见ROUND5_ANALYSIS.md。

- 日间购买状态、强制变现、双worker独立施工slot、下一墙可行性、先锋LOGISTICS和实验增长floor已实现。legacy/base_reserve、夜战、TaskPlanner、共享validator/observe/session/入口未改。默认HEAD原本已defense，本轮保留，旧文档shadow属历史状态；人工确认多Python文件部署仍有效。
- 16项V2.3专项通过；冻结legacy/shared/night AST及legacy/shadow实际Response对照通过。仅诊断阶段还验证了完整387请求状态/响应与V2.2一致。
- 首轮全量208项有22失败/10错误；未称通过。临时目录还原未修改HEAD复现22失败/8错误，主要是旧测试隐式默认模式与HEAD defense不符。修正测试显式模式、保留legacy断言；V2.3政策断言变更逐项列TEST_PLAN。独立审查3项边界问题已修复并补测试。
- 最终全量210项PASS（24.719秒），无跳过；入口/replay4项PASS（7.761秒），V2.3专项16项PASS（1.706秒）；冻结legacy/shadow对照262请求PASS，git diff --check通过。独立审查的执行边界及诊断关联问题均已修复并回归。
- 下一步：用户审阅，已停止；不自动实机、不自动提交。1300回合存活、增长参数效果未证明。未增加依赖/运行模块/提交bundle。

## 模块拆分检查点（历史 V2.2）
- 基线是本轮开始时完整 V2.2，冻结于 tests/fixtures/v22_baseline.py，SHA-256：105a44200a24a0e5db8c2062e6206f129e3055568b0a6e5f4a10e101b5a76934。该文件只供测试，不部署。
- src/main3.py 为186行薄入口，保留 app/SESSION/callback/CLI/HTTP hooks 与原项目名称显式导出；业务位于 src/agentrace/{model,memory,actions,economy,defense,task_news,strategy,session}.py。package __init__.py 无副作用。GameSession 仅整体迁入 session。
- 58个原有函数/类 AST 完全一致，原有常量表达式受回归锁定；所有业务方法体、plan_turn调用次序、任务pending、候选事务和动作扣账未变。普通测试 patch 定义模块，不建立代理。
- 每次只迁一模块，逐步专项及短序列equivalence全部通过。独立只读审查确认无循环依赖和比赛入口阻塞；replay仓库外相对路径问题已修复并专项验证。
- 真实入口专项4项PASS（14.015秒）：package导入、隔离多文件目录直接HTTP、未改run.sh的Git Bash真实HTTP、仓库外相对路径replay。HTTP状态/正文及replay最终结果与冻结V2.2一致。
- 长序列equivalence通过：11组15675次固定请求，4项门禁PASS（357.106秒），涵盖三模式、两起点、两侧及完整回合范围；Response/HTTP/缓存/fingerprint一致，所有规范化状态字段摘要一致。首轮工具保留两份完整对象树导致父进程约1GB且新版子进程240秒超时，未报告Response差异；只将长序列状态输出改为完整字段SHA-256摘要后通过，Response仍原样比较，240秒子进程门槛未变，独立审查确认未过滤字段。
- 最终全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`：194项PASS（47.111秒），无跳过；git diff --check通过，run.sh无修改。已停止，未自动提交、未进入实机策略实验。运行部署必须同时带上完整 src/agentrace/，不能继续只复制 main3.py。
- 运行文件行数：main3 186；model359、memory167、actions365、economy141、defense523、task_news469、strategy811、session289；package标记__init__ 1行。当前可作为人工提交检查点。

## V2.2 历史检查点
- 修改前完整读取 round4 game11/game12、ROUND3_ANALYSIS 和 main3.py。两局相反开局均在 Night3 崩溃：game11 投资单门 L3，game12 买 5 次 WallFixer、墙容量停留 8000，R330 有 75/220 HP worker。详见 [ROUND4_ANALYSIS.md](ROUND4_ANALYSIS.md)。
- 墙服务优先可交付的 L1/L2 升级，以同时恢复当前 HP 和增长最大 HP；L3/资金或时间不足时尝试 fixer。预算按当回合接受动作扣款，不预支任务收益；无法采购的服务允许同 owner 筹资，保留原工作目标。
- 武器 breadth-first，Night3 2/2/1；legacy maintain 的 L2 特殊排序也已删除，因此默认 Shadow 的真实 legacy 行为包含这项修复和墙券采购修复。不是旧版本逐字不变；同版本 shadow/legacy 响应一致。
- 控制员按实验 80% 阈值购买一个或使用已有 Medicine；不抢占活跃任务先锋。L1 基地低于实验 70% 可 emergency 升级；Night3 防线缺口且可行墙/武器增长均不可完成时才 fallback。
- Day1 benchmark=8 不下降，execution 部分墙与 unmet/reason 保留，石耗 rules.wall_stone_cost。Night2 容量目标 9000，Night3 当前 HP 10000 preferred/最大 HP 10000/stretch12000、武器2/2/1；Day4+沿用 Day3 目标，无新长期战略。
- defense 只接管防御/工人经济/回防/站位/夜间开火；TaskPlanner 类未修改，通过同一 validator、真实 candidate memory 执行一次并独占 active pioneer。Task prompt/executeCmd 仍属于 TaskPlanner；最终动作继续经协议与 ActionValidator 复验，失败不提交候选记忆。
- 日志新增 current/max HP、墙等级计数、controller health/readiness、日初/日落恢复与容量对照、任务观测边界/错误/金币；断档及缺失的起点保留 null。独立审查发现的 Day4 停工和 authority 标记歧义已修复；最新只读复核未发现阻塞项。
- 新增 round4 检查点、健康/升级/部分墙/筹资/交付/authority 隔离专项。原日志数值自动核对；测试几何人工构造并明确标注，不冒充完整战斗 replay。默认仍只 Shadow，不把本地逻辑通过写成第三夜实机成功。
- 验证：round4 专项17项PASS；Shadow专项19项PASS。最终全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`：186项PASS（27.028秒）。首轮全量仅旧“优先L3”策略断言不符新需求；更新后185项通过，再补满背包可购性边界和测试，最终186项通过。TaskPlanner、DefensePlanner.attack_plan/damage AST与HEAD一致；git diff --check通过（仅工作区换行格式提示）。
- 下一步：用户审阅；已停止，不自动改默认模式，不自动提交 Git。当前可作为人工提交检查点。

## 默认 Shadow instrumentation patch
- 日志增加strategy_mode、defense_target、详细jobs/deadline、controllers/assignment_status、budget、timing_ms、结构化divergence（保留weapon actor/controllerId）、wall_target_changed、pre_night估算和task估算；没有值时为null/空结构。
- perf_counter计时：legacy规划、Shadow复制/规划、handle入口至日志输出前的总处理时间（包括锁等待和原诊断）。总计不包含本条Shadow日志自身I/O及HTTP发送；重复缓存不重复输出。total>3000ms或shadow>1500ms只告警，不改变实际动作。
- Shadow只拿实际响应的副本；Shadow/report/日志异常不能替换实际响应。未改攻击评分、TaskPlanner或后续天政策。
- 2026-09-11 round3 V2.1：拉取并分析 game8/game9/game10。修正 controller 为“持久角色站位/区域 + 每回合当前邻接最大匹配”；不因 exact safe_slot 或 cooldown 改换 weapon ownership。修正 benchmark_wall_target=8（Day1恒定）与 execution_wall_target/unmet_wall_target 分离；长期deadline使用static blockers。新白天重建DailyPlan并清除CONTROL/RETURN/PRE_NIGHT残留。Shadow扩展到Day3：Day2墙数9/EHP约8000，Day3墙数10/EHP约10000、武器2/2/1均为实验参数，不是规则。
- round3 evidence：game10 R331旧Shadow ready=0而实际邻接至少3人，legacy两炮开火；game9旧映射漏掉实际炮手。game8/game10 Shadow早期墙目标降至7/4但legacy R70实际均8墙。敌方MATCH2三局共571事件全部完成分片、长度、SHA-256校验；R330敌墙总HP分别14580/9775/13755，精确R331缺失写unknown，详见 [ROUND3_ANALYSIS.md](ROUND3_ANALYSIS.md)。墙缺失指标改为wall_ids_missing_since_night_start，不归因摧毁。
- 验证：新增5项instrumentation与原14项Shadow专项合计19项PASS；最终Windows全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，160项PASS（19.999秒），包含默认Shadow真实HTTP和显式legacy回退。首次全量仅旧日志数量断言失败，改为两类日志各一条后重验通过；未放宽性能门槛。diff --check通过。已停止于本patch，不进入V2 authority。
- V2.1验证：round3专项（匹配、R331 fixtures、静态deadline、墙目标分层、NEW_DAY、Day2/Day3 wall service、墙缺失归因、MATCH2完整性）28项PASS；最终Windows全量169项PASS（28.788秒）。实际响应仍legacy，未启用V2 authority。

## 本轮 Shadow 检查点
- 历史实现将 ObservationDelta、RoleJob、ControllerAssignment、BudgetReserve、JobAuthorization/ActionProposal/ActionArbiter、CanonicalLayout、Day1Plan、StrategicState、StrategicPlanner 放在 main3.py；当前已按上述模块拆分。人工确认支持多文件，无新增依赖。
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
- V2.2 有前三天防御增长目标，之后仅沿用 Day3 目标；未实现 Day10/MPC/GoldClaim/新宝藏或PvP/完整MatchAnalyzer。
- 路径估算不证明未来占位、任务成功或战斗安全；当前炮手补位是确定性贪心，缺员/动态堵路下的最优匹配和脱困尚未验证。safe_slot 是策略名，不是无伤保证。
- Shadow逐轮跟随真实legacy观测，不是V2闭环实机；round2摘要日志不能补造完整观测进行比赛重放。不得以本地PASS证明R71 benchmark或R131/R261生存通过。
- 下一步：向用户报告 V2.2 验证结果后停止。用户已允许显式 defense 模式，但默认仍 shadow，不能自行切换。

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
