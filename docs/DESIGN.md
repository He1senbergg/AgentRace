# AgentRace 技术设计

## V2.3 当前设计（覆盖下方 V2.2 历史日间策略）

运行时仍为既有8个agentrace业务模块及main3入口。model.ProductionPolicy只服务V2.3，不修改legacy DefensePolicy/base_reserve。memory.CapitalGoal属于Day1Plan；NEW_DAY重建日计划，GameMemory.observe和候选事务不变。当前HEAD默认defense是此前已提交事实，本轮不变；显式shadow继续返回100% legacy Response。

日间调用：reconcile → observe_growth/NEW_DAY → 预算与原健康/基地fallback → schedule_production → 当前回程安全截止 → 每个job经ActionArbiter提交。plan_turn、TaskPlanner、EconomyPlanner、DefensePlanner、controller匹配/夜战执行块不变。活动任务先锋TASK_LOCK，未活动且任务可行TASK，否则LOGISTICS；恢复健康先于新任务，LOGISTICS不可collect/build。

购买目标按目标ID/目标等级持久保存。DEFICIT建立缺口；FUNDING只让worker筹资；观察金币充分为FUNDED，下一步PROCURE；缺口可用当前背包闭合则LIQUIDATE（原cash_in(force=True)），无新矿行程。BUY只扣本候选staged余额，不假定到包；观察到券才DELIVER/APPLY；USE接受后VERIFY，目标实际等级/HP达到才DONE。券消耗但目标未变保持VERIFICATION_PENDING，不重复买券；由其他目标完成同一武器等级数量目标时旧目标SUPERSEDED，不谎报该建筑升级成功。BLOCKED分别记录资金/预算/背包/角色/路径/截止等枚举。

每个hard purchase记录goal_id/type/target/cost、观察现金、该owner背包可卖价值、现金是否足额/缺口、owner/role、路线与截止可行性、当前执行性、state/block_reason；附block_reasons允许同时出现资金与deadline。施工goal另外输出数量目标和stone_cost；无owner字段为null。不把背包估值当现金，执行出售后仍等goldNum对账。日志state是本候选接受动作后的状态，路径/资金诊断来自提交前观测；accepted_action只代表发出的动作，不证明平台成功。

墙施工选择每个owner独立slot，跨回合保持；slot是建造目标，采石途中不把它覆盖为矿坐标。completion_trip只估算下一墙（k=1）：缺石采集 + 到slot建造 + 回防 + 5回合margin。不可行PAUSED，下一观察重算，benchmark与execution不会因full-batch估计下降。静态估计不含人物/机器人，包含其他已预留施工位置；当前一步仍看瞬时占位。8墙能否全部完成不是启动第一墙的条件。

容量实验：D1/2/3 floor=8000/12000/15000；D4+为max(15000,上一夜观测初始capacity+ceil(压力/500)*500)。压力=0.5*墙HP减少+1000*缺失墙ID数+2*基地HP减少+1000*缺失控制员ID数。连续观察才能累计HP减少；夜首、夜末或连续性缺失标complete=false，只代表已观察下界。ID缺失是风险代理，不证明战斗死亡；参数不是平台规则。墙count benchmark仍8/9/10，武器最低仍D1/2=2/1/1，D3+=2/2/1，不追L3。

限制：日志没有完整逐回合Request。game17资金冻结的证据与受控重放范围见ROUND5_ANALYSIS；未证明真实地图上所有deadlines可兑现、实验增长值最优或1300回合存活。无实机实验。以下模块拆分/旧策略段落保留为历史依据，不覆盖本节。


## Gate1 Shadow（当前；优先于下文历史策略记录）

实现范围只到可运行的 Shadow，实际响应仍由原 plan_turn 生成。不提供 V2 authority 选项。

平台固定启动方式下，DEFAULT_STRATEGY_MODE="shadow"同时作为GameSession及argparse默认；保留显式legacy，端口仍使用原位置参数。新增日志只暴露现有目标、job/deadline、控制员映射、预算、差异及回防/任务估算。估算在原计算点保存在本轮planner临时字典，不新增策略状态、不为日志重新寻路。wall_target_changed比较本轮前后值，reason来自已有降级原因；未知数据用null/空结构。

perf_counter分别测量legacy规划、Shadow复制和规划、handle入口至Shadow日志输出前的总处理时间。总计包含锁等待/原诊断，不含本条Shadow日志I/O或HTTP发送；这是诊断口径，不是判题端耗时。total>3000ms或shadow>1500ms仅输出[shadow_performance] WARNING。日志异常隔离；传给Shadow的是实际响应副本，不能写回roleCommandMap/prompt/executeCmd。

V2.1 controller coverage：`ControllerAssignment`只保存角色的物理safe_slot；每回合`adjacent_matching()`按当前邻接关系为ready武器求最大匹配，weapon↔controller不是持久所有权。物理coverage匹配（忽略cooldown）和ready weapon匹配分开记录；只有未被物理匹配的角色才移动去补未覆盖炮位。冷却不触发换岗，且当前角色已邻接任意炮时不会因slot名字变化移动。

V2.1 wall/day：`benchmark_wall_target`与`execution_wall_target`分离，`unmet_wall_target`只作差值；Day1 benchmark恒为8，deadline不足只能降低execution并记录`DEADLINE_INFEASIBLE`。长期可行性使用`World.static_occupied`，一步动作仍可使用完整临时占位。phase.day变化立即重建DayPlan并清掉CONTROL/RETURN/PRE_NIGHT残留；Day2/3只Shadow执行墙修复/升级优先，实验EHP/数量目标不会变成比赛规则。缺墙只输出`wall_ids_missing_since_night_start`，不声称击杀原因。

最小数据结构及所有权：

| 类型/字段 | 生命周期、写入者、读取者与重置 |
| --- | --- |
| ObservationDelta: round_no:int, phase:Phase或None, continuous:bool, gold:int, task_active:bool, feedback:dict | 每观测产生一次；仅GameMemory.observe写，StrategicPlanner读；不再解析一套raw feedback。feedback关联的actions只能是legacy实际响应。 |
| StrategicState: plan:Day1Plan, last_round:int或None, metrics:dict | 半场内由Shadow候选reconcile写；下一观测复制读取；换身份/回合回退随GameMemory重置。失败不提交。 |
| Day1Plan: mode:str, jobs:dict[str,RoleJob], controllers:dict[str,ControllerAssignment], budget:BudgetReserve, wall_target:int, reasons:list[str] | mode仅DAY_NORMAL/RECOVERY/PRE_NIGHT/NIGHT；jobs与controllers跨回合；budget/reasons每观测重建；只支持首日白天政策。 |
| RoleJob: owner:str, job_type:str, target:object, phase:str, priority:int, created_round:int, deadline:int, progress:int, completion_condition:str, abort_condition:str | StrategicPlanner写，执行器读；观测完成、死亡、deadline、失效关联时释放。progress保留扩展位，不按发出意图增加。紧急治疗暂停job；经济helper无权抢建造job。 |
| ControllerAssignment: weapon:str, controller:str, safe_slot:tuple[int,int] | reconcile写，夜战和回防读；死亡/建筑位置改变/slot成为静态障碍允许重配，冷却和临时占位不释放。safe仅是命名，不声称无伤。 |
| BudgetReserve: observed_gold:int, staged_gold:int, reserved_gold:dict[str,int], committed_gold:int, committed_items:Counter[(actor,item)] | 每候选回合重置为真实goldNum；仅仲裁接受后扣staged并记commit；拒绝不扣。commit是候选回合意图，不是平台成功证明。 |
| JobAuthorization: resources:frozenset[str], actions:frozenset[str], bucket:str；ActionProposal: actor:str, command:dict, resources:frozenset[str] | 每proposal构造、ActionArbiter读；attack资源必须精确包含weapon和controller。试算ActionValidator小账本，预算与资源全部满足才原子发布。 |
| CanonicalLayout: footprint:frozenset, front:tuple, weapon_slots/wall_slots:tuple, static_blockers/transient_occupancy:frozenset | 每观测由World规范化几何生成；规划读取；临时单位占位不会永久删除canonical slot。 |

调用顺序：GameSession.handle缓存检查 → candidate.observe返回delta → 保存独立Shadow memory → legacy plan_turn及双重协议/动作校验 → StrategicPlanner.reconcile → 续接/失效jobs、资金预留、炮手映射 → 动态deadline及墙目标降级 → job生成proposal → arbiter → divergence → 原有candidate实际响应提交 → 隔离输出shadow日志。Shadow既不调用observe第二次，也不将intended任务命令当作下一轮已执行命令。

预算优先锁缺炮数×25（受观测余额限制），余款再锁首个WeaponUpgradeVoucher1的实际商店价；任务收益只有出现于后续goldNum才进入预留。Medicine/WallUpgrade/TreasureItem不能动用正常升级预留；本slice不生成这些可选采购。持有Medicine的急救use允许暂停job且占用角色，不能同回合操炮。未建立GoldClaim或预计收益账本。

布局以基地2×2 footprint的倍坐标中心变换canonical slots，按实际基地朝地图中心决定镜像；fallback按canonical距离排序。构建前检查静态炮位出口和当前动作合法性。World.occupied保留旧语义；新增static/transient集合来自同一次World解析。所有墙采集/建造成本读取rules.wall_stone_cost。

PRE_NIGHT：当日最后白天回合D=current+70-round_in_day；估算剩余job动作C和从完成点至slot最短路L，满足current+C <= D-5-L+1才继续。全墙目标不满足时先逐步降低执行wall_target；无法继续墙子目标时释放给可打断经济，不因benchmark失败直接提前离岗。未知路径保守处理；估算中的自身旧位置必须清除，不能把它当未来障碍。活动任务先锋继续交由TaskPlanner消费反馈，并标记controller不可用。

基础metrics只记录观测gold/HP/资产数/等级、当前持久映射的邻接人数、actual fire命令数和连续关联的失败结果数。R71 benchmark字段固定检查3rocket、L2/L1/L1、8墙、3角色、3映射邻接；执行目标降级不修改benchmark。R131/R261仅审查stationHP、角色/武器存活和controller可用性，墙数/HP是诊断，不能据此判定gate通过。没有robot减少=击杀、ready未fire=漏射的推导。

Shadow日志列出jobs、intended/actual白名单动作字段、差异actor列表以及prompt/executeCmd存在性/是否不同；不记录任务正文/答案/命令原文。临时失败记录异常类型。1302机器人HTTP测试发现重复火箭全扫描超时，ShadowDefensePlanner使用格子索引实现同一伤害估值，legacy DefensePlanner不变；专项验证重叠机器人、地图边缘和剩余HP等价。

尚未证明：V2闭环benchmark、真实夜战生存、动态堵路脱困、最优炮手补位、后续天恢复策略。获得用户确认前停在Shadow；确认后仍应先解决实机切换相关缺口，不能直接声称比赛就绪。

## 目标与依据

以 `AI Spec/未来战争_v1.0_比赛全貌_开发整合版.md` 为工作真值，已阅读规则、协议和工程建议。不读取 Official/。目标是完整的经济、建设、防守、任务与宝藏 Agent，而非空响应或仅采矿基线。

现状：`src/main3.py` 已有协议校验、世界模型与几何，已有基础经济策略；已有测试与启动脚本。无需编译；正式环境 Python 3.11.10 + Flask，其他依赖限标准库。先在单文件中按功能组织，避免额外 Python 文件未被平台打包的风险。

## 需求与实现边界

| 规格章节 | 需求 | 计划责任 |
|---|---|---|
| 3–9、47–54 | 130 回合每日昼夜、41×32、八邻域、穿角、动态地图、局部视野 | Phase / World / geometry |
| 10–26、58–59 | 背包多重集、经济、建筑区域/上限、升级、物品 | Economy / Construction / Validator |
| 13–19、27 | 控制者、夜战、射程、弹数、锥角、冷却、机器人 | Combat / Validator |
| 28–30、72 | 跨天新闻、价格预测、宝藏坐标时间物品推理与结果 | News / Treasure |
| 31–38 | 接任务、保持邻接、异步 LLM/沙盒、答案、技能复用 | TaskAgent |
| 39–41 | 生存优先、任务和击杀积分 | Scheduler |
| 42–63、77–78 | POST /、端口参数、UTF-8、三字段响应、5秒期限 | HTTP / protocol |
| 64–66 | 回收执行结果、跨回合记忆、半场隔离 | GameMemory |

## 数据流

HTTP 解码 → 串行状态事务 → 解析与索引 → 新半场检测 → 回收上一轮结果 → 保存新闻/敌情 → 任务状态机 → 各规划器候选 → 共享金币/物品/控制者/目的格预留 → 统一动作验证 → 严格 JSON 响应。

外层异常回退为空响应并记录函数名和异常类型；不得输出完整请求、沙盒内容或潜在凭据。内部失败不能被标记为策略成功。LLM 与沙盒由平台异步执行，本地不等待、不执行 LLM 生成的命令。

## 状态与安全

每回合重建可见障碍；历史敌情不可当作当前障碍。基地占格集中封装。寻路使用有界八邻域 BFS，允许穿角；对己方当前占格和目标格保守预留，禁止交换。

重复请求不得重复增加 LLM 计数或消费历史；回合回退、阵营/队伍变化触发对局状态重置。任务技能与对局记忆分离，只有可验证的反馈才提升为成功技能。状态锁避免 Flask 并发污染。

统一校验所有 12 类动作，先检查字段类型与目标数组，再检查角色、阶段、距离、容量、预算、建筑区域、目标数量、控制者互斥。缺失/错误输入不得生成猜测性动作。

## 尚未确认的规则与处理

- 回合从 0/1 起：集中配置；收到首回合 0 可识别，否则实际平台确认，禁止隐蔽散落假设。
- station 左上角：按文字几何 `(x,y),(x+1,y),(x,y-1),(x+1,y-1)` 封装，平台碰撞确认仍必需。
- wall默认消耗1石头，依据AI Spec/官方材料核对补充.md中的完整内嵌表格；保留显式成本配置。
- 武器 build.name 未正式举例：映射独立配置，平台验证 gatling/railgun/rocket 后才可称已确认。
- 控制武器占用人物动作：采用保守互斥，避免非法双动作。
- 弹道栅格边界、敌方单位可否被武器伤害、死亡机器人同回合行为：不假装精确模拟；优先明确机器人目标，记录预测不确定性。
- 错误答案后是否继续、沙盒文件持久性：每回合看真实 phaseTask/反馈，不假定成功，不依赖未验证文件保留。
- 夜间仅 attack/build 有明确限制，不能额外禁止其他动作。
- 半场重启/重置、Python 精确版本、提交文件打包均需实际平台验证。

## 实施顺序

P0 HTTP 与结构校验 → P1 世界模型/寻路/状态 → P2 全动作校验与经济 → P3 建设升级/夜战 → P4 任务状态机/技能 → P5 新闻宝藏 → P6 集成仿真、覆盖审计、独立审查与交接。每阶段均先设计、实现、定向测试、集成、审查、更新检查点。阶段完成不代表整体完成。

## P0 实施结果

`src/main3.py` 保留官方 Flask 接口，新增空响应工厂、动作结构校验、响应三字段校验、异常回退及端口检查。移除 import 时重开 stdout/stderr 文件描述符的行为；只在 CLI 启动时设置 UTF-8，避免导入测试关闭共享流。`run.sh` 支持从任意工作目录启动，优先显式 AGENTRACE_PYTHON，再用本地 .venv，最后 python3；exec 保证停止信号到达服务器进程。

结构校验只证明字段格式，尚不证明动作在世界状态中合法。callback 已接入P2经济与动作状态校验；P0本身只负责结构边界。HTTP 异常日志只包含异常类型，不包含潜在敏感载荷。真实 HTTP 测试覆盖启动、畸形请求后的恢复、重复请求和终止清理；尚无复杂策略时延证据。

## P1 几何与世界模型实施

跨回合事务设计：GameSession 用进程内锁串行处理；复制已提交记忆，在副本上回收反馈、更新历史、调用规划器并验证/序列化响应，全部成功才提交。最近一个请求按完整 JSON 内容去重，返回独立响应副本；同身份同回合但内容不同拒绝提交。无有效 roundNo/teamId/type 的请求返回空响应且不改变记忆。新闻以回合保存原文与变化事件，在起点不明时不伪造日期；敌情记录 last_seen_round，当前障碍仅来自 World。反馈只在连续下一回合关联上一轮动作，漏回合时不错误归因。

半场检测按 AI Spec §65 建议：roundNo 回退或 teamId/type 改变时重置对局记忆。仅观察到回合0可自动确定0起点；1起点需显式配置。协议没有半场ID、请求ID或乱序保证，因而同身份旧请求延迟到达与半场回退无法区分；该重置启发式需平台确认，不能声称已解决任意乱序。同回合不同内容的重试语义也未知，当前保守拒绝。通用技能已作为独立的未验证经验保存。事务只保证本地记忆，不声称跨HTTP送达/平台执行的恰好一次语义。

已增加 Phase、World、station_cells/building_ring、八邻域 BFS 和 MoveReservations。Phase 必须显式提供0/1起点，无静默默认；回合限定单半场1300回合。World 每次从当前请求重建障碍，包括所有任务点坐标和基地4格；重复ID不参与规划，但其观测占格仍保留。路径返回完整最短路线，None 表示不可达，单元素表示已到目标。

移动预留保守禁止进入任何当前单位占格，因而也禁止交换；代价是暂不利用己方同步移动腾出的格子。机器人外层按官方接口§1.5使用roles包装，兼容旧数组输入；字段核对见AI Spec/官方材料核对补充.md。World 和 GameSession 已接入 callback；跨回合事务、历史与最近请求去重已实现。默认规划器已接入P2–P5的经济、防守、任务和宝藏策略。可通过 `bash run.sh PORT --round-origin 0|1` 指定已确认起点。

## P2 设计与实现

依据§11–26、30–35、46–59、75–76：ActionValidator以当前World和Phase校验12种动作，以候选顺序确定优先级。校验成功后才提交角色/控制者、金币、目标格、建筑数量和升级目标预留；拒绝候选不改变预留。卖矿收入、采矿所得、拆墙腾出的空间和购买所得均不作为同回合后续动作的可用资源。背包采用Counter；商店名以实时列表为准，重复商品定义拒绝使用，已知消耗品仅在无歧义时兼容背包大小写。

武器建造名称按用户确认采用roleType枚举作为默认值，Rules仍支持覆盖；围墙默认成本1已确认，仍允许配置覆盖。攻击按runtime射程优先、缺失才采用静态表，cooldown缺失按§49为0；目标数、控制者互斥及加特林点积>=0检查硬合法性，不模拟未确认弹道。机器人召唤令按每天已发送数量保守预扣，失败也不返还额度，未知起点/中途首次接入当日不使用召唤令。

经济规划按实时价格与可达路程选择矿，满包/达到批量阈值后卖矿；矿消失每回合重规划。两个工人可以同时采同一矿（§20.4），只对移动目标做互斥。采购作为显式需求接口供P3/P5调用，避免无需求购买。任务活跃时经济规划不占用pioneer；全局调度、任务推理和新闻预测在后续阶段接入。

## P3 设计与当前实现

Construction负责配置允许的武器建造、升级券与修复物品使用/采购；优先保基地，普通白天只分配一个工人施工以保留经济来源。墙建造必须有确认成本，并保留通行口。CLI支持覆盖建造名称和墙成本，默认值分别来自用户确认的Role解释和官方完整图。

Combat负责夜间开火、冷却检查、控制者分配与入夜前站位。任务中的pioneer不参与防守移动。火箭采用3×3预计伤害与已分配伤害扣减；加特林方向硬校验，电磁炮使用明确共线目标估算穿透收益。精确非共线弹道边界没有依据，不宣称复现官方结算。优先威胁己方基地的存活机器人；运行时射程优先。输出仍经过同一个ActionValidator。

恢复复查发现维护规划只在三级墙使用WallFixer，遗漏§24允许的低等级受损墙。维护时优先使用角色已持有的修墙道具，再考虑升级券；满血墙不消耗修复品。此选择不改变动作验证规则，也不假定采购当回合即可使用。

DefensePlanner已接入plan_turn：基地紧急维护→开火→消耗品→站位→普通维护/建设→工人经济。控制者待机仅做本地预留，不发送虚构wait动作；伤害扣减仅服务选点，不写入平台观测。已有13项防守测试，尚无正式平台弹道/全局调度最优性证据。

## P4实施设计（2026-09-10）

依据§31–38、51、55、63–65。TaskPlanner独占活跃任务的pioneer；按可达距离选择己方可领取任务点，使用地图展开双格任务点。acceptTask后只在真实phaseTask出现时使用任务LLM/沙盒权限。死亡、离开、描述变化和回合缺口使旧结果失去归属，不消费无来源llmResp/lastCmdResult。

每个外部操作记录发送回合和任务实例。LLM回复使用程序规定的严格JSON对象（answer或command二选一，可带skill说明），不把自然语言任意提取为答案或命令。只消费紧邻发送回合的回复；缺失或畸形结果进入诊断提示，不同步等待，不在本机执行命令。命令结果保留exitCode/TIMEOUT/JUDGER_ERROR/TRUNCATED原义供LLM修正，当前任务原文完整保留，过去探索历史按条数和字符数限制并标记截断。任务仍存在时才允许修正答案；结束不等于成功，动作true也不等于答案正确。技能先保存为未经验证的经验；只有明确的任务成功证据才可提升，现有协议缺少独立成功字段，不能伪造已验证技能。通用经验可作为后续提示参考，不自动重放旧答案或假定沙盒文件仍在。

普通阶段LLM额度在观察到日初时重置；中途接入/缺口保守停用直至下个已知日初，任务期间不扣普通额度。最终响应门禁也检查executeCmd任务权限及普通LLM额度，事务失败不提交配额或任务状态。P5共用该额度与单一异步请求归属，不能与任务争抢响应。

Windows真实HTTP测试直接使用项目解释器和绝对入口路径，从系统临时目录启动；POSIX仍实际执行run.sh。两者均测畸形请求恢复、重复请求、5秒响应约束及进程清理，后续WSL完整测试已验证POSIX脚本，正式CentOS仍未验证。

## P5设计（§28–30、34、72）

NewsPlanner共享普通阶段每日3次LLM配额，任务期间不发送全局推理请求。每次请求绑定发送回合及新闻快照摘要，只消费下一回合结果；新闻改变、漏回合使旧快照失效。提取资源有效日区间、可采状态、价格方向及宝藏坐标/开放回合区间/物品多重集。每项推理必须引用当前历史中的原文片段；输出需通过严格JSON、地图/半场边界、日区间、动态商品名及证据校验。宝藏还要求两次独立提取的语义结果完全一致，才进入执行阶段；这提高谨慎程度但不能证明自然语言推理必然正确，正式线索质量属于平台未验证风险。

当前价格仍只用vendorShopList，新闻不替代实际价格。明确停采事件使规划器暂避该资源，价格上涨预期只在有现金缓冲和背包余量时短暂延后出售。旧事件到期失效，新线索触发重新推理。

TreasurePlanner在没有活跃任务时控制pioneer：确认全套物品有容量/预算/可达时间后采购，逐回合观察真实背包，再移动到候选位置邻接格，只有开放窗口内按精确多重集献祭。各类调度共享动作/金币预留。每个语义候选至多献祭一次；结果1/4停止后续尝试，2/3否定该候选，0也不盲目重发；漏回合导致结果未知时停止继续冒险。成功/失败结果必须关联本机前一回合的献祭动作。半场重置清除新闻、候选、尝试和配额；仅同一teamId的未验证任务经验可跨半场作为提示参考。

## 本轮复查修正

任务命令结果结构化记录退出码、超时、判题器错误及截断；长文本保留头尾并标记本地截断。最近8次探索观察参与后续提示；已知领取回合和timeoutRounds给出保守截止，超过截止或明确errorCode=1时停止远程操作，等待真实新任务。缺领取历史时不伪造截止。

低等级受损墙无现成修理品时也可采购WallFixer，已有升级券仍可优先使用。紧急维护已分配角色后跳过该回合普通维护/建设，避免同一升级目标重复采购并耗尽两名工人的经济行动。

## P6验证设计

长局测试回放两个1300回合的确定性观测序列，覆盖昼夜、角色死亡/重现、任务异步结果、新闻跨日、重复请求及半场隔离；它是协议/状态压力回放，不是官方战斗模拟，不推导胜率。断言响应字段、控制者与角色互斥、预算、地图/回合范围及历史有界；输入故障序列与压力回放分开，便于定位。

密集HTTP测试启动真实子进程并使用合法CLI配置，发送除己方占格外1312格地图全铺机器人的观测，检查完整请求往返低于5秒、并发相同请求一致、畸形请求后恢复以及终止清理。日志保存在测试临时文件中用于失败诊断；不屏蔽意外异常来取得通过。

## 审计修正与官方核对

弹道按§15.3、§16纳入全部存活机器人，targetTeam只用于防守目标优先级，不能用于忽略路径阻挡。全体机器人共享剩余伤害估值；火箭溅射也记录旁侧机器人伤害，选点收益只计算己方威胁。回合末死亡与同回合后续弹道的精确结算次序仍需平台验证。

围墙默认成本1来自PDF内嵌完整原图；武器名默认采用用户确认的roleType枚举。已有召唤令仅在日间其他高优先级动作之后使用，不主动采购。眩晕目标按本回合预留，避免重复消费。完整新闻历史、当前任务原文及答案不再按任意字符数截断；过去命令观察仍有限条数并显式保留截断标记。省略skill保留已有说明，命令与结果成对记录。HTTP使用严格JSON入口，事务成功前不改变状态。WSL已通过实际run.sh测试，不能代替正式CentOS验证。

默认武器映射为gatling/railgun/rocket各自同名。CLI不传--weapon-build-name使用全部三种；传入时以提供的映射集合替换默认集合，便于限定类型或使用其他名称，重复类型/名称仍拒绝。

## 判题入口与诊断（2026-09-10）

保留官方首个位置参数端口约定，以及现有 CLI 参数校验、UTF-8 行缓冲。按 AI Spec §43.2 恢复监听所有 IPv4 接口 0.0.0.0，避免判题器通过非回环网卡访问失败；这尚不能证明线上故障根因。关闭 debug/reloader。before_request/after_request 对前3次 HTTP 交换记录固定格式元数据，覆盖404/405；锁保护全局计数，Flask g隔离并发请求编号，不持锁处理请求，不记录载荷。响应日志只证明服务生成响应，不代表判题器收到或接受。

## 回合诊断

GameSession在锁内、响应完成校验并提交后输出[trace_turn]元数据；诊断异常隔离，不能替换已提交动作。按会话实例记录前10次非缓存观测、每50次采样，异常额外日志预算20次；角色、动作和反馈各最多12条。仅记录坐标、数值、白名单类型、动作和错误码，不输出任务原文、答案、动态商品名、prompt或executeCmd。重复请求直接使用缓存，不重复诊断。字段依据AI Spec §55、§64；默认回合起点及策略保持原样。

## 本轮实测驱动修正设计

Self/1.log的原始roundNo从1开始且初始75金币/4单位，与demo开局一致；依据AI Spec §3.2以实际首回合确认1基。仅在未配置且第一次观测为1时识别1基，0基与显式配置保留；中途接入不猜测。防御开火/控制者回防先于新任务和宝藏出行，已在任务中的先锋仍遵守不可移动约束。地图诊断绘制当前观测41×32字符图，y向上、基地完整占地、矿/商店/任务点及双方单位/机器人；每50次观测和昼夜边界输出，首观测必输出。回合摘要增加矿物库存、任务状态及防御数量，不记录任务原文。策略收益需平台复测，旧日志不能重建未记录的全局地图。

本轮复核与边界：新的0/1识别仅作用于GameMemory首次观测，显式0在round1仍为日内2，未配置且中途接入保持未知。新增地图只读World，不影响占用集/寻路；日志仍在响应提交后隔离。摘要更新为每10次并强制昼夜边界，地图为每50次及边界。已完成对照规格的单独代码复核及100项完整验证；任务超时根因和真实胜率未验证。

## Self/2.log诊断设计

每个已提交的非缓存回合输出[turn]短摘要，列出角色动作/控制的武器/任务占用/未下令状态，以及武器等级、冷却、攻击范围和邻接角色。未下令不自动归因为驻守或无目标，避免把推断写成事实。保留详细[trace_turn]与地图的原采样周期；非法输入仍限量，重复请求不重复输出，诊断异常仍隔离。仅白名单字段，不记录任务/命令原文。此次以完整运行证据定位策略瓶颈，不根据采样日志伪造未观测回合的动作。

## Self/3.log策略修正设计（历史；批量及四命令策略已由下节替代）

任务领取仅在已知日间且路程+timeoutRounds+回防路径+3回合余量可容纳时执行；重叠可领取任务使用最坏时限判断，仍不猜实际选中任务身份。无任务可做的先锋向防线准备。任务已有4次命令探索或截止剩余<=3时进入只答题阶段，不再发探索命令；截止当回合只能消费已有答案，不再请求来不及返回的LLM。该上限是策略选择，不是比赛限制，不能保证LLM服从或答案正确。

经济提前变现安排在日间回防站位前，但必须验证商人路径、不同矿种出售回合和返回防线时间；正常8矿批次、现金不足25时4矿批次、接近日间截止时不足批次也卖。选矿评分计入运输成本，并拒绝无法日间采集后销售回防的路线。此处只预算未来动作，不预支出售所得。

夜战用现有弹道/伤害估值生成只读候选，按收益及炮手数量选武器。缺炮手时允许比较移动补位与当前开火，以收益/(移动或冷却等待+1)选择；保留控制者互斥、观察冷却和共享预计伤害，不将估计写回观测。无目标时仍用原有回防驻守。所有候选逐回合重算，不假定移动或伤害成功。

## Self/4.log改进设计

后续 Self5 分析见 SELF5_ANALYSIS.md；已落实的后续设计见本文末节。

规格§10/12允许三武器任意搭配，§17火箭范围伤害与长射程适合日志中的机器人群：默认优先三火箭，而不是强制每种一座；不覆盖已有建筑。正常升级优先火箭，基地濒危仍先救基地。采购须考虑商店往返及入夜截止。

经济改为逐个矿点评估采集批量与送货总成本，而不是先挑最近矿再比较资源类型。远商人采用距离相关批量，避免4矿跨图跑一趟；接近回防截止仍提前变现。矿物目标保持直到消失/不可达/不满足截止，避免每回合重新挑选导致往返。

任务不再限制总共4条命令：规格仅规定单命令15秒、任务回合截止。仅临近截止强制答案；安全提取题目中的.md文件名并在沙盒用有界搜索读取任务和同目录API文档，节约发现文件的LLM往返。保留发现材料及当前skill，不硬编码答案或服务端口。日志只证明提交失败和命令状态，不证明具体失败原因。

## round2：炮位、墙线与可执行的日间计划（取代上轮前向炮位）

炮台置于基地侧后方，前半圈筑墙、后半圈留出通道，利用火箭不受路径建筑阻挡。上轮前向炮位中间炮后侧空间被基地和另一炮堵住，已撤回。position_controllers全局枚举分配，最多3炮每炮6候选，优先就绪炮和覆盖/路程，避免冷却炮先占人；近邻安全移动约束保持。

日间先调度可完成的升级，再备药/提前回防；为首个L2保留健康角色药品预算，满血墙不自动升级。wall_builder从首日开始批量取石，保存actor/goal/building，避免每墙往返或矿物销售抢占；26回合采集往返预算与入夜预算同时满足，携石但墙位不可达也释放。墙工可和另一升级工并行。所有进度依赖下一观测，不将预测当成功。

## Versus：相对布局与持续升级（历史，前向炮位已替代）

两侧武器位置优先朝地图中心，炮手在可选安全位置中准备于武器后侧；是对称策略，不假定所有敌人来自中心。新增upgrade_trip保存actor/name/建筑格，基于观测背包继续采购或使用，避免任务被卖矿/补药/换工人打断。死亡、目标失效或购前时限不足取消；治疗优先并暂停配送。基地危急预留动态升级价，未购的非基地行程可被抢修取消。L2火箭且可负担时优先L3，其真实收益待验证。

第二天起三武器/非危急基地才主动就近取墙石，往返采集余量<=18回合且赶得上入夜；主动取石目标min(8,day*2)，不是硬墙上限。仍保留原墙位通道和合法性校验。具体日志证据及验证见VERSUS_ROUND1_ANALYSIS.md。

## Self5：面向1300回合的持续防守

治疗在开火占用炮手前执行：半血或附近机器人潜在两轮伤害超过当前血量时使用已有 Medicine。威胁按己方/未知目标阵营、非眩晕、三格内机器人基础攻击力相加，是保守风险评分，不是实际目标预测。火力选点增加炮手附近威胁权重；冷却期间从可用邻接格中优先选低威胁位置，同风险保持近路。不得把推测伤害写回观测。

白天为非任务占用角色采购两份 Medicine，预留未建武器金币、购买/返回防线时间，持有足量不再采购。早期仅路过商店备药，三武器建成后允许专程采购；不在夜间离岗购物。原有抢救基地优先级保留。诊断增加固定白名单商品名与药品数量，便于确认实际购用，无任务正文或动态商品泄漏。

补药调度在领取/移动任务前，低血先锋可先备药；健康先锋仅顺路采购，避免专程绕行消耗任务窗口。活跃任务先锋仍不参与。已邻接炮手仅比较一步可达且仍邻接的安全格，不能绕到武器对侧而离岗。旧矿目标只在收益达到当前最佳的80%时保留，避免跨日/复活/升级运输后锁定远矿；20%滞后是策略选择，非比赛规则。

任务剩余三回合时允许消费上一轮请求的命令决策：D-3执行、D-2结果及LLM请求、D-1答案、D反馈。剩余三回合发起新LLM请求仍要求答案，避免下一轮再探索。短截止和重复请求语义保持。提示要求按已验证字段维护部分答案，不由本地代码编造答案；原始命令正文缺失时不假定exit126的具体原因。
# V2.2 防御增长增量（2026-09-11）

`DefensePolicy` 保存实验参数：控制员健康比例 0.8、基地 L1 emergency 比例 0.7、Night3 容量 10000 / stretch12000；不是平台规则。`max_health()` 使用 AI Spec 的角色/建筑等级 HP。`Day1Plan` 继续承载前三天目标，后续重复 Day3 目标，不增加通用战略框架。

`StrategicPlanner.reconcile()` 先从唯一 `ObservationDelta` 更新 HP/日夜状态，建立 observed/staged 预算，分别预留建炮、健康、基地 emergency/fallback、墙服务、武器升级。`wall_item()` 先尝试可交付的升级，再尝试 fixer；`service_trip()` 在静态障碍上计算取券、使用与回位的动作成本，加 5 回合实验余量，当前一步移动仍用动态障碍。持有道具省略购买成本。`execute_service()` 每次只发一个动作，下一观测确认持有/建筑等级与 HP，不把发出命令当成成功。墙收益由观测 current/max HP 分开体现。

墙热点按上一夜实际观察到的净 HP 下降、当前缺损排序；该差值不等于总伤害，治疗和观测断档可能遮蔽伤害。日落输出 start/end current/max HP 和武器等级；首次观测若已在日中，start=null。未达成 readiness 与资金/deadline 原因保留，benchmark 不覆盖。

HEAL 是一次恢复工作，不囤药。活跃任务先锋从防御 job 和夜间 controller 匹配中排除。无法采购的 WALL_SERVICE/UPGRADE 可在保留目标的同时调用受同 owner 限制的经济动作；scratch 清除 legacy 工人预留，避免两套 job 锁导致无法筹资。基金不提前计入售矿/任务奖励。

`GameSession(strategy_mode='defense')` 让 StrategicPlanner 使用真实 candidate memory；它先且只一次调用原 TaskPlanner，写入任务状态/频道并占用 active pioneer，再通过共享 validator/arbiter 执行其他 RoleJob。结束仍进行最终协议与动作验证、事务提交与重复缓存。没有执行旧防御后再覆盖动作的双 authority 合并。`shadow` 使用观测后的独立副本，真实输出仍由 legacy 产生；DEFAULT_STRATEGY_MODE 保持 shadow。defense 日志明确 authority，actual 为最终选择动作，divergence 不代表另跑一次 legacy 的对照；defense 计时独立列出。

TaskPlanner 实现及 attack target scorer 不变。`GameMemory.observe()` 额外形成任务开始/结束的连续观测边界、错误码与金币前后值；StrategicPlanner 不重复解析 raw 反馈，也不据此推断任务收益。
# 保持 V2.2 行为的模块拆分（2026-09-11，当前结构）

人工确认平台支持多个 Python 文件。运行代码直接使用 src/main3.py 与 src/agentrace/，不生成 bundle。run.sh 原样保留；主入口继续创建 app/SESSION，持有 callback、HTTP hooks 和 CLI。原有项目类/函数显式重新导出，主入口采用 __package__ 分支支持直接脚本和 package import，不修改 sys.path，不引入业务源码加载器。

模块依赖是 DAG：model 为底层；memory/actions → model；economy → model；defense → economy/model；task_news → actions/economy/model；strategy → 前述模块；session → strategy/memory/actions/model/task_news；main3 → 各模块。memory 保存 StrategicState/Day1Plan/RoleJob 等数据，不导入 strategy。业务模块均不导入 main3。

- model：World、Phase、几何/布局、Rules/DefensePolicy、常量与基础数据函数。
- memory：GameMemory/observe、ObservationDelta、战略状态数据类。
- actions：协议校验、strict_json、ActionValidator、BudgetReserve、ActionArbiter。
- economy / defense / task_news：原 planner 及相应辅助函数。
- strategy：plan_turn 和 StrategicPlanner，调用顺序与所有方法体原样保留。
- session：仅 GameSession，不接管入口的 app/SESSION/HTTP 全局状态。入口把原 LOG 对象显式绑定给 session，保持脚本与 package 导入时的日志名称；没有代理或函数重绑定。

冻结基线为 tests/fixtures/v22_baseline.py（测试专用，不部署），SHA-256 见同目录 v22_baseline.sha256。所有原有顶层函数/类 AST 与常量表达式受测试锁定。行为等价通过独立进程输入同一固定请求序列，比较 Response、HTTP 原始正文/状态和字段规范化状态，不比较类模块名或对象身份。测试注入指向定义模块。

replay 工具默认通过正常 src.main3 package import 运行；脚本启动以标准 -m 子进程切换到仓库根，转发前绝对化原调用者路径。自定义 --source 保留原有离线测试加载行为，未将该机制引入比赛运行模块；模拟规则不变。
