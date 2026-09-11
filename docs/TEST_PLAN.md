# AgentRace 测试计划

## Round6 checkpoint复验

Round6七局均未达生存目标，V2.3实战验收失败；本轮不新增或修改测试。现有全量命令：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，210项PASS（24.021秒），无跳过；git diff --check通过。通过仅表示既有工程回归正常，不能证明benchmark、墙HP代理、资金预留或deadline策略正确。下一阶段V2.4 Strategy Re-baseline需重新建立实战假设与对照；本轮不实现。


## V2.3 历史验证及测试规格变更

当前默认mode以进入本轮前HEAD的defense为准。本轮不改默认、不以默认切换掩盖回归。先完成只读诊断且387固定请求Response/状态一致，再改日间策略。新增test_round5.py覆盖真实game17时间线、下一墙/不坍缩、双工slot持久性、RETURN重分配、80+4铜变现/观察100再买/到包再用/观测等级DONE、资金与deadline拆分、先锋任务/权限、增长floor/压力、夜末断档、低血先锋、满包绕行、强制出售ROI、未验证use、死亡换owner、其他炮升级满足目标后旧goal停止采购、夜末最终损伤与完整性。独立审查补充的VERIFY/DONE动作关联一致性有断言覆盖。

全量首次208项：22fail/10error（50.372秒），不是PASS。为了鉴别预存问题，在临时目录用git show恢复HEAD运行105个相关旧测试，复现22fail/8error（9.905秒）。因此没有批量改assert：legacy测试明确strategy_mode=legacy，日志隔离测试明确shadow；本轮defense行为变化由独立V2.3断言保护。最终全量210项PASS（24.719秒），无跳过；V2.3专项16项PASS（1.706秒）；入口/replay4项PASS（7.761秒）；legacy/shadow冻结对照262请求PASS。git diff --check通过。

规格发生变化的断言逐项：

| 测试 | 所属/原保护 | 新规格及理由 |
|---|---|---|
| test_shadow.wall_job_persists_and_stone_cost_scales | defense：采满全局8墙石头、job持久 | 有下一墙材料即可move/build；仍检查同owner/job创建回合，cost差另测单墙 |
| test_shadow.impossible_full_wall_job_downgrades_before_early_return | defense：full batch降低目标 | 下一墙不可行PAUSED，8目标不降；不凭errand失败提前RETURN |
| test_round3.benchmark_never_follows_execution_downgrade | defense：benchmark8/execution4/unmet4 | 本轮禁止递减execution；8/8/0，DEADLINE诊断仍存在 |
| test_round3.day2_wall_service_precedes_upgrade_and_day3_targets | defense：D2 8000/D3 10000 | 用户明确改floor12000/15000；墙优先、禁止L3断言保留 |
| test_round4.partial_wall_target_keeps_largest_feasible_and_rule_cost | defense：5/3/2/1全批降级、三墙石耗差3 | 改下一墙PAUSED与不坍缩，单墙cost1→2差1；新增两工与game17独立回归 |
| test_round4.default_shadow_equal_legacy_and_defense_explicit | 启动默认与shadow隔离 | 默认defense已在HEAD；显式shadow仍必须与legacy相等 |
| test_shadow_instrumentation.default_and_explicit_cli_mode_preserve_positional_port | 启动默认/端口 | 默认defense、显式legacy；端口断言不动，其余4项显式shadow而非改变隔离断言 |
| test_http真实默认进程日志 | 启动模式 | expected mode=defense；密集机器人、响应、5秒门槛和清理不变 |
| test_entrypoints直接HTTP/run.sh/package | 部署入口对照冻结shadow | 不传mode测试实际默认defense，与当前显式defense独立进程结果相等；legacy冻结等价另测 |
| test_entrypoints.replay | 两个不同默认mode比较 | 工具新增仅本地--strategy-mode透传，双方显式legacy；原结果等价断言不变 |
| test_equivalence定义与请求序列 | 重构期间所有策略都冻结 | 仅StrategicPlanner/新增战略字段允许改变；原字段默认、GameMemory、ActionValidator、EconomyPlanner、DefensePlanner、TaskPlanner、plan_turn、session全部AST冻结；controller匹配及夜战块单独AST冻结。legacy/shadow Response/HTTP/cache/fingerprint与所有非strategic记忆仍逐项比较，defense不再要求等于V2.2 |

下列测试仅明确执行模式，**原断言完全不变**。原因统一是原用例验证legacy或注入的planner，HEAD默认defense不执行该planner；显式选择使原保护真实执行，既不要求legacy接受新防御政策，也不放宽协议/事务断言：

| 文件 | 测试方法 | 模式 |
|---|---|---|
| tests\test_actions.py | test_default_callback_collect_then_sell_from_observation | legacy |
| tests\test_actions.py | test_dynamic_mine_and_two_workers_no_move_collision | legacy |
| tests\test_actions.py | test_final_gate_rolls_back_illegal_planner_output | legacy |
| tests\test_actions.py | test_summon_duplicate_gap_and_day_reset | legacy |
| tests\test_defense.py | test_default_summon_uses_inventory_with_daily_quota_and_night_priority | legacy |
| tests\test_defense.py | test_low_level_wall_purchase_then_observed_repair | legacy |
| tests\test_defense.py | test_emergency_procurement_does_not_duplicate_worker_errands | legacy |
| tests\test_defense.py | test_full_callback_dense_robot_budget_and_repeat | legacy |
| tests\test_defense.py | test_build_requires_confirmed_name_and_never_overwrites | legacy |
| tests\test_diagnostics.py | test_actions_positions_feedback_and_unknown_phase | legacy |
| tests\test_diagnostics.py | test_invalid_input_sampling_and_duplicate_suppression | legacy |
| tests\test_diagnostics.py | test_diagnostic_failure_does_not_replace_response | legacy |
| tests\test_diagnostics.py | test_every_turn_reports_actions_and_weapon_state_without_duplicate_logs | shadow |
| tests\test_integration.py | test_two_halves_full_observation_replay | legacy |
| tests\test_integration.py | test_malformed_optional_fields_do_not_collapse_planning | legacy |
| tests\test_memory.py | test_callback_integration_and_duplicate_isolation | legacy |
| tests\test_memory.py | test_parallel_duplicates_run_planner_once | legacy |
| tests\test_memory.py | test_transaction_rolls_back_planner_and_validation_failures | legacy |
| tests\test_memory.py | test_conflicting_same_round_does_not_commit_and_http_recovers | legacy |
| tests\test_memory.py | test_history_is_not_current_obstacle_and_news_deduplicates | legacy |
| tests\test_memory.py | test_feedback_does_not_infer_success_or_associate_across_gap | legacy |
| tests\test_memory.py | test_identity_change_and_round_regression_reset_history | legacy |
| tests\test_memory.py | test_missing_invalid_input_and_origin | legacy |
| tests\test_memory.py | test_unserializable_response_does_not_commit | legacy |
| tests\test_news.py | test_long_multiday_news_preserved_in_prompt | legacy |
| tests\test_news.py | test_platform_quota_error_stops_ordinary_retries_until_day_reset | legacy |
| tests\test_news.py | test_two_independent_readings_then_exact_sacrifice | legacy |
| tests\test_news.py | test_bad_evidence_unknown_items_bounds_and_disagreement | legacy |
| tests\test_news.py | test_all_result_codes_and_gap_do_not_repeat_consumption | legacy |
| tests\test_news.py | test_snapshot_change_gap_task_quota_and_half_reset | legacy |
| tests\test_round2.py | test_first_day_batch_stone_builds_eight_walls_and_releases_worker | legacy |
| tests\test_round2.py | test_late_day_cash_really_becomes_upgrade_before_night | legacy |
| tests\test_self5.py | test_wounded_pioneer_buys_before_accepting_task | legacy |
| tests\test_self5.py | test_heal_reserves_controller_before_ready_gun | legacy |
| tests\test_self5.py | test_last_exploration_round_has_result_answer_and_feedback_room | legacy |
| tests\test_strategy_regressions.py | test_fifth_command_allowed_and_duplicate_is_idempotent | legacy |
| tests\test_strategy_regressions.py | test_short_deadline_stops_commands_but_accepts_last_round_answer | legacy |
| tests\test_strategy_regressions.py | test_task_budget_includes_return_and_rejects_unknown_timeout | legacy |
| tests\test_strategy_regressions.py | test_idle_pioneer_prepares_defense | legacy |
| tests\test_strategy_regressions.py | test_small_bag_is_sold_before_defense_and_income_not_prespent | legacy |
| tests\test_strategy_regressions.py | test_full_bag_with_few_minerals_still_goes_to_vendor | legacy |
| tests\test_strategy_regressions.py | test_disappearing_mine_does_not_interrupt_cash_delivery | legacy |
| tests\test_strategy_regressions.py | test_survivor_moves_to_rocket_then_fires | legacy |
| tests\test_strategy_regressions.py | test_command_status_logged_without_payload | legacy |
| tests\test_tasks.py | test_submission_legality_feedback_uses_json_string_actor_key | legacy |
| tests\test_tasks.py | test_full_task_text_and_large_answer_are_not_silently_limited | legacy |
| tests\test_tasks.py | test_skill_is_preserved_when_later_decision_omits_it | legacy |
| tests\test_tasks.py | test_overlapping_points_do_not_invent_task_timeout | legacy |
| tests\test_tasks.py | test_expired_old_task_error_does_not_expire_new_description | legacy |
| tests\test_tasks.py | test_timeout_and_same_description_new_instance | legacy |
| tests\test_tasks.py | test_history_and_half_reset_only_preserves_labelled_experience | legacy |
| tests\test_tasks.py | test_accept_then_prompt_command_result_answer_and_unverified_end | legacy |
| tests\test_tasks.py | test_wrong_answer_while_active_uses_feedback | legacy |
| tests\test_tasks.py | test_missing_malformed_late_or_cross_task_results_not_executed | legacy |
| tests\test_tasks.py | test_dead_displaced_or_ended_task_cannot_execute | legacy |
| tests\test_tasks.py | test_command_failure_markers_preserved | legacy |
| tests\test_tasks.py | test_only_eligible_own_tasks_and_route | legacy |
| tests\test_tasks.py | test_quota_gate_duplicate_reset_gap_and_rollback | legacy |

运行命令：`.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_round5.py -q`；最终全量使用 `discover -s tests -q`。不重复长序列全三模式V2.2等价（defense策略已获准改变）。以下为历史测试记录。


当前是保持 V2.2 行为的模块拆分。历史 V2.2 全量186项PASS（27.028秒）；本轮新增等价与入口验证，结果见下节。默认仍 Shadow，实机收益未验证。

最终模块版全量：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，194项PASS（47.111秒），无跳过。仅执行一次最终全量；长序列单独运行，不在普通全量中重复。

## 模块化等价验证（当前）

- 不可变基线：tests/fixtures/v22_baseline.py，加 SHA-256 校验；.gitattributes 禁止对该基线做换行转换，Windows/Linux均按相同字节校验。基线只用于测试，不随比赛代码部署。
- tests/test_equivalence.py：依赖层级/无环检查、58个函数类AST及常量表达式一致性、基线摘要、独立进程固定请求等价。比较完整 roleCommandMap/prompt/executeCmd、HTTP状态与正文、规范化记忆、cached_response、fingerprint；不比较类模块路径/repr/对象身份。
- 短序列：11组387次请求，每次拆分后执行；legacy/shadow/defense、0/1起点、两侧、昼夜/Day4边界、任务LLM/命令/答案/错误、重复/冲突/断档/重置、HTTP畸形输入、planner/validation失败后恢复。
- 长序列：同一生成器扩到11组15675次请求，固定两边PYTHONHASHSEED=0，不让两个实现各自生成后续输入。命令：PowerShell `$env:AGENTRACE_FULL_EQ='1'; .venv\Scripts\python.exe -B -m unittest discover -s tests -p test_equivalence.py -q`。之后清除该环境变量，避免普通全量重复长序列。
- 长序列结果：4项PASS（357.106秒）。首轮大量展开快照导致测试父进程约1GB，新版子进程触发240秒工具超时；改为对完整规范化状态生成SHA-256，Response/HTTP正文/cached_response仍直接比较后通过，未调整240秒门槛或比赛代码。短序列保留完整字段；长序列状态不符可按定位回合重跑非摘要前缀。
- tests/test_entrypoints.py：4项PASS（14.015秒）。仅复制src与run.sh的隔离部署目录，从其他工作目录直接启动/使用原run.sh；真实HTTP状态/正文与冻结基线一致。另测正常package导入和仓库外相对路径replay，baseline/modular均完成相同70回合离线模型。
- 本轮run.sh验证使用Windows Git Bash及Windows Python3.11，不冒充当前模块版的WSL/CentOS验证。原run.sh未修改。未执行正式比赛或改默认模式。
- 每步专项记录：model/world6；memory9；actions23+protocol7；economy/strategy_regressions12+round4 17；defense18+versus8+round系列32；task15+news9；strategy/shadow19+round系列32；session/memory9+shadow19+diagnostics4。各步短equivalence均通过。

## Gate1 Shadow 验证（历史）

默认模式与instrumentation patch最终全量：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，160项PASS（19.999秒）。首次全量159项通过、1项旧日志数量断言失败；仅将断言更新为[turn]/[shadow_turn]分别一次，重复请求不重复输出，再全量通过。没有新增策略功能或放宽超时限制。

V2.1 round3专项：`test_round3.py` 覆盖 game9/game10 R331 最大邻接匹配、cooldown与物理覆盖分离、静态deadline、benchmark/execution墙目标、NEW_DAY清理、Day2/Day3 wall service、墙缺失不归因摧毁、三局MATCH2完整性；28项（含既有Shadow instrumentation）PASS。最终全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`：169项PASS（28.788秒）。

- `tests/test_shadow.py`：双资源攻击与后续移动/另一炮冲突；接受扣staged、拒绝不扣、下观测gold对账；初始75建炮预留；gap不关联意图；镜像布局/临时占位/静态资源阻挡；cost=2墙工批量采集且不被铜矿抢占；动态路程触发回防；冷却保持映射；Shadow重复请求/异常隔离/实际响应一致；禁止v2启动模式；TASK频道不被ECONOMY覆盖；失效炮位释放job；八墙不足先降级；格子索引伤害与旧公式等价；跨昼夜与R131/R261观测边界响应对照。
- `tests/test_http.py` 的密集真实进程测试不传strategy-mode，验证默认Shadow；仍保留原5秒限制、1302机器人、并发重复、可配置武器名/石耗、进程退出/端口释放，检查3条已提交Shadow报告且无异常。另一HTTP测试显式传legacy验证回退。
- `tests/test_shadow_instrumentation.py` 新增5项：CLI默认与显式legacy/端口不变；完整日志字段及非负perf_counter耗时；Shadow改写副本后异常与日志异常不影响实际响应；性能告警及告警日志失败不改变响应；weapon actor与controllerId差异及回防/任务字段。与14项已有Shadow专项合计19项PASS（0.108秒）。既有响应对照测试改用显式legacy，避免误把两个默认Shadow互相对照。
- 专项：`$env:PYTHONPATH='tests'; .venv\Scripts\python.exe -B -m unittest test_shadow test_http -q`，18项PASS（12.461秒）。
- 首次本轮全量154项中密集HTTP超时失败；没有放宽门槛。定位为Shadow重复攻击估算全机器人扫描，改仅Shadow的格子索引后补等价测试并重验。最终全量结果见STATUS本轮验证。
- 独立只读审查发现的频道覆盖、过早RETURN和失效驻守均有针对性回归；未以反复全量代替审查。
- 以上证明程序逻辑、HTTP及Shadow隔离；观测回放未模拟战斗。历史round2只有摘要，不能声称完整日志重放或V2已达到benchmark。
- 实机Gate：R71记录3rocket、L2/L1/L1、>=8wall、3角色及控制员就绪；R131/R261核对基地HP、角色存活、武器存活和控制员可用性，不以固定墙数判断通过。墙HP/数量为诊断；未执行新实机比赛，所有生存收益仍未验证。
- 本批结束后停止，用户确认前不切换实际V2决策；不实现额外Day2/Day10、MPC、GoldClaim或完整MatchAnalyzer。

round2最新：一次Windows `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，141项PASS（15.956秒），不重复WSL。新增test_round2六项覆盖多回合升级交付、满血墙资金门禁、并行墙工、全局操炮匹配、首日八石八墙闭环、堵墙释放。原前向炮位断言因已确认布局缺陷改为后向；名称/合法性/首夜攻击保留。专项及独立复查完成，差异空白检查通过。历史结果如下；真实1300回合生存仍未知。

Versus最新：8项新增test_versus通过，覆盖镜像前向建设、固定运券与出售互斥、死亡解除、治疗暂停、基地抢修取消武器采购、资金预留、L3优先、取石时限。一次完整135项中133通过，2项旧首回合建设场景失败；调整工人站位及开局8回合三炮检查后，test_http/test_live_regressions共8项PASS（12.219秒）。源代码未再变化，未重复全量/WSL，原完整命令不标PASS。其余历史结果如下。朝向/墙/升级收益和1300回合生存仍待实机。

Self5 实现后最新验证：Windows `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，127项PASS（15.819秒），仅运行一次最终单环境全量。包含真实HTTP/密集/并发和两个半场各1300回合观测回放。Self5七项覆盖：治疗优先于开火、安全冷却移动、不能绕炮离岗、药品预算与返程、低血先锋采购优先、跨日旧矿收益重选、D-3命令至答案及重复请求。实际伤害/任务部分答案正确性/完整1300回合生存仍待平台验证。以下120项为历史。局部测试使用简洁输出，文档变更不跑套件，无平台相关理由不重复双环境。

当前状态：Self4 修复后 Windows/WSL 完整 120 项通过，独立只读复核完成；正式平台验证由用户负责，未宣称比赛就绪。下文旧测试数量属于历史记录，以本节最新结果为准。

## Self4 最新验证

- Windows：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`，120 项 PASS（15.344 秒）。
- WSL：`wsl --exec .venv/linux-test/bin/python -B -m unittest discover -s tests -q`，120 项 PASS（22.154 秒）。包含实际 HTTP、并发、密集输入及 2600 回合回放。
- py_compile 和 git diff --check 通过。
- 新增 test_self4.py 七项：嵌套任务文档发现/保留/去重、发现超时后恢复、远商人四矿继续采集、完整三火箭建设、健康基地不抢升级、集群合成伤害、605 目录及控制字符输出字节边界。
- 策略回归改为允许第五条命令且重复请求幂等；保留截止门禁。出售回归按距离批量调整输入，仍验证实际移动和出售。
- 70 回合经济对照：旧版收入 67/移动 110，新版收入 115/移动 94，并完成一次火箭升级。运行 `tools/replay_day.py log/Self/4.log`，可用 `--source` 指定旧版本。无刷新/任务/战斗，不证明实战收益。见 SELF4_ANALYSIS.md。
- 实机待核对：任务发现及答题成功、首夜升级、回防及时性、三火箭实际防守。武器名称已有用户确认且 Self4 建造反馈合法，首观测 roundNo=1 已有日志证据；不再视为完全未知。

## 环境与命令

Windows项目.venv和WSL .venv/linux-test均为CPython3.11.10，已安装requirements-dev.txt锁定依赖，pip check通过。WSL使用离线wheel安装，失败的.venv/linux不是有效环境。

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests -v
wsl --exec .venv/linux-test/bin/python -B -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
wsl --exec .venv/linux-test/bin/python -m pip check
.venv\Scripts\python.exe -m py_compile src/main3.py
git diff --check
```

最新实际全套使用上述unittest命令的`-q`输出模式：Windows92项PASS（10.308秒），WSL92项PASS（17.223秒）。没有跳过HTTP测试。

## 已执行类别

| 文件 | 数量 | 已覆盖重点 |
|---|---:|---|
| test_protocol.py | 6 | 三字段/12动作格式、UTF-8、空和畸形JSON、重复键/非有限数/无效Unicode、异常回退与恢复、日志不泄漏 |
| test_world.py | 6 | 双起点昼夜、地图边界、基地/建造环、多格任务点、八方向最短路/穿角/不可达、动态障碍与重复ID |
| test_memory.py | 9 | 事务回滚、序列化失败、并发重复、响应副本、冲突请求、漏回合反馈、身份/半场重置、新闻与敌情历史 |
| test_actions.py | 23 | 全12动作、共享金币/容量/背包多重集、目标和控制者预留、等级/射程/锥角、3武器/20墙、1石头默认成本、动态采矿与采购 |
| test_defense.py | 18 | 建造/维护/修墙采购、满血/满级边界、返程/驻留、控制者唯一、三武器选点、异阵营拦截、药品/炸弹/眩晕、已有召唤令和配额 |
| test_tasks.py | 15 | 领取/双格/重叠点、LLM→命令→结果→答案、任务切换/死亡/离开/超时、错误/缺失反馈、普通调用配额、命令故障标记、80k原文与答案、技能保留及三态合法性 |
| test_news.py | 9 | 跨日120k原文、证据与动态商品、两次一致解析、快照/任务隔离、宝藏预算/容量/路程/开放窗口、结果0–4与漏回合、事件到期和实时价格 |
| test_http.py | 4 | 实际子进程启停、任意工作目录、合法/非法CLI、1302机器人、四并发重复请求、畸形后恢复、请求5秒约束和监听清理 |
| test_integration.py | 2 | 双半场2600回合观测回放、畸形可选字段35组与正常策略共存 |

## 证据边界

- 2600回合测试是确定性观测回放，不是官方战斗模拟；不证明胜率、计分或机器人动作结算。
- 密集HTTP在当前Windows/WSL硬件通过，不证明任意输入或正式CentOS的5秒响应。完整新闻原文没有任意截断，但外部LLM上下文容量未知。
- LLM回复、沙盒结果和新闻线索由测试构造；真实解题能力、沙盒持久性、15秒平台超时、失败重试语义未联调。
- Robot.roles和围墙1石头已由官方材料核对；武器build.name、roundNo起点、动态attackPower及擦边/同回合弹道语义仍未验证。
- 协议无请求/半场ID；任意乱序与端到端恰好一次执行不能由本地去重证明。

## 历史失败及处理

- 旧机器普通沙箱socket PermissionError没有被隐藏或跳过；当前Windows与WSL实际HTTP均通过。
- 密集HTTP曾在子进程退出后立即检测到TCP仍可连接；未发现残留进程，改为2秒有界监听关闭检查后通过，未放宽响应5秒限制。
- 异阵营机器人弹道测试修复前失败：错误跳过前方机器人；修复后通过，并覆盖完整fire选点。
- 提交反馈ID类型疑点由三态测试排除：World已规范成字符串，原实现无需修改。

## 比赛就绪检查

- [x] 完整本地套件、真实HTTP、WSL run.sh、密集输入、重复运行与资源清理。
- [x] 需求覆盖表与明确的未验证项。
- [x] 独立只读子Agent审查，结论和未验证物理反例见REVIEW。
- [ ] 正式武器建造名称和回合起点确认，按确认值启动并验证首昼夜。
- [ ] 正式平台最小建造/开火/任务/宝藏/沙盒联调及日志检查。
- [ ] 交付环境构建与启动、人工接管演练。

只在代码有新变更、失败或明确未解疑点时重跑对应测试；不以反复运行同一套绿灯代替平台证据。

历史交付核验：仅复制run.sh与src/main.py到临时目录，Windows与WSL CPython3.11.10真实HTTP均返回预期采矿动作，进程退出和临时目录清理成功。未改应用代码，92项全套结果仍适用；启动/人工接管说明见RUNBOOK.md。正式平台配置与联调仍缺。

职责更新：正式判题/联调由用户负责，Agent不再以获取平台入口作为本地工作前置条件。上述正式验证项目保持未执行状态。

## 本次入口验证（2026-09-10）

直接执行 `src/main3.py <port>`：真实 HTTP、中文输入、重复请求、畸形请求恢复和进程清理；通过 run.sh 启动：可选配置、密集观测、并发重复请求和退出后端口释放。无效端口与配置必须非零退出。测试统一导入 src.main3。当前 Linux CPython 3.10.12：`.venv/bin/python -B -m unittest discover -s tests -q`，92 项 PASS（10.751 秒），含两项真实 HTTP 测试。首次沙箱运行因禁止 socket 导致两项失败，获准本地网络测试后全套通过；CRLF 感知的 git diff --check 通过；此前 Windows/WSL 数据为历史结果。

本次验证：Linux CPython 3.10.12，`AGENTRACE_TEST_HOST=172.23.57.83 .venv/bin/python -B -m unittest discover -s tests -q`，93项 PASS（8.354秒）；实际通过非回环网卡执行密集HTTP、并发重复请求，直接入口仍覆盖回环访问。新增404/405/200诊断、3次日志上限及载荷不泄漏验证。正式判题未重测；当前修改可作为人工提交检查点。

## 回合诊断验证（2026-09-10）

tests/test_diagnostics.py新增3项：动作/坐标/未知昼夜及失败反馈对应，非法观测与限量采样、缓存去重，诊断异常不影响动作或缓存；同时检查敏感原文不出现在日志。完整命令`.venv/bin/python -B -m unittest discover -s tests -q`：96项PASS，8.086秒，包含真实HTTP、并发、密集观测和2600回合回放。首次受限运行两项HTTP因socket权限失败；允许本地网络后全套通过。正式平台新增日志尚待用户重跑采集。

## Self实测回归（最新）

新增test_live_regressions.py四项，覆盖1基开局建造至首夜攻击、0基兼容/中途不推断、新任务不能抢占夜间炮手且活动任务隔离、41×32地图坐标/基地占地/外部文本不泄漏。诊断采样与未知起点测试同步更新。`.venv/bin/python -B -m unittest discover -s tests -q`：100项PASS，9.032秒；真实HTTP两项执行成功，无跳过。最终git -c core.whitespace=cr-at-eol diff --check通过。平台复测仍待执行，合成开局只结算move/build，不假装模拟完整战斗。

续接复核：同一完整命令100项PASS（9.266秒），包含实际HTTP与并发测试；首次沙箱socket受限的两项错误由允许本地网络重跑排除。当前检查点已合并旧结论，未改变策略代码。

## Self/2.log逐回合诊断验证

新增专项覆盖非详细采样回合仍输出动作，炮手与武器ID关联，冷却时未下令状态，重复请求不重复日志。4项诊断测试PASS；完整101项PASS（9.729秒），命令`.venv/bin/python -B -m unittest discover -s tests -q`，允许本地网络，密集HTTP响应约束未放宽。策略收益未验证；下一步测试任务截止加返程跨夜、动态矿刷新与出售路线、日间升级采购可完成性。


## Self/3.log 分析后的待补验证

本次仅执行日志JSON统计/连续性/动作与反馈核对，未重跑测试套件。新增待验证场景：矿点刷新后仍能在回防前出售不足20矿；短任务期限中多次LLM命令探索后及时提交；任务冷却空档的先锋准备动作；领取时限加回防路程门槛；炮手死亡后比较机枪/电磁炮/火箭的重新分配。沙盒执行结果缺摘要，19条executeCmd不能视为成功执行。详见SELF_LOG_ANALYSIS.md的Self/3.log章节。
# V2.2 专项与实机门槛（2026-09-11）

- `tests/test_round4.py`：17 项，game11 R131 与 game12 R131/R260/R330 数值自动核对原日志；受控几何检查墙升级/缺钱 fixer/L3 fixer、单瓶医疗、75/220 不健康、武器 breadth-first、基地 emergency/fallback 不抢可行增长、8→5/3/2/1 部分墙、非默认石耗、筹资不丢 job、满背包采购门禁及持券使用、墙券买入→观测持有→交付→观测容量增长、deadline、日落增长、任务断档诊断、TaskPlanner authority/频道/记忆隔离、默认 Shadow 等价、Day4 延续。
- 更新原 round3 壁修测试为增长优先券；更新 Versus 旧“先升 L3”断言为“即使能买 L3 也先补 L2”；instrumentation task 字段断言增加新诊断字段。不是放宽动作合法性或性能门槛。
- 专项命令：`.venv\Scripts\python.exe -m unittest discover -s tests -p test_round4.py -q`；Shadow 隔离专项 `-p "test_shadow*.py"`；最终全量 `.venv\Scripts\python.exe -B -m unittest discover -s tests -q`。
- 全量包含 HTTP、重复/并发、异常事务、密集状态性能及已有集成回放。新增 controlled checkpoint 测试仅证明程序分支/预算/状态关联，不能证明完整地图中的寻路交付成功、战斗收益、Night3 或 1300 回合存活。
- 实机下一门槛：用户审阅后显式 defense 新比赛；核对实际 strategy_mode/authority、墙 current/max 的日初日末增量、2/2/1 就绪、控制员健康与邻接匹配、局内服务失败/时长，以及 R390/R1300 存活。当前默认仍 shadow，尚无 V2.2 authority 实机通过证据。
