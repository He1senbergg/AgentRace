# 需求覆盖审计（2026-09-10，本地交付审计）

真值：`AI Spec/未来战争_v1.0_比赛全貌_开发整合版.md`。本表从规格逐项核对代码与测试，不把测试通过当作官方兼容证明。实现均位于`src/main3.py`；测试位置均位于`tests/`。已完成独立只读审查；本地交付完成，正式比赛行为仍按表中残余风险交由用户验证。

“本地”指对应测试实际通过；“部分”表示尚有规则歧义、实战效果或本地缺口。评分/机器人移动等由平台结算，客户端不能自行产生这些状态。

| ID / 来源 | 要求 | 实现位置 | 验证位置 / 当前结论 |
|---|---|---|---|
| C01 §2–3 | 10天×130回合、70白天/60夜晚、双半场 | Phase、GameSession | test_world.test_phase_boundaries、test_integration.test_two_halves_full_observation_replay；本地，0/1起点需平台确认 |
| C02 §4 | 41×32、坐标边界 | valid_position、neighbors、World | test_world、test_protocol.test_command_shapes；本地 |
| C03 §4、7 | 建筑/角色/机器人/设施/矿阻挡移动 | World._roles、occupied、ActionValidator | test_world.test_multicell_dynamic_obstacles、test_move_conflicts；本地 |
| C04 §5 | 基地2×2、12武器格、20墙格 | station_cells、building_ring | test_world.test_station_and_rings；部分：左上锚点几何需平台碰撞确认 |
| C05 §6 | 切比雪夫、八方向、允许穿角 | distance、neighbors、World.path | test_world.test_shortest_path_and_corner_cut；本地 |
| C06 §7 | 不抢格、不交换、移动每人一次 | ActionValidator.targets/busy、MoveReservations | test_actions.test_move_conflicts_and_active_task_lock、test_world.test_move_conflicts；本地，隐藏敌人碰撞由平台反馈 |
| C07 §8 | 部分视野与当前/历史分离 | World.enemies、GameMemory.enemy_history | test_memory.test_history_is_not_current_obstacle_and_news_deduplicates；本地；不自行模拟平台视野 |
| C08 §9、49–50 | 动态角色ID、类型、生命值；缺字段容错 | World._roles、level_of、positive_health | test_world.test_malformed_and_duplicate_roles、test_actions.test_health_numeric_boundaries_do_not_raise；本地 |
| C09 §10、61、81 | 等级静态表与runtime属性优先 | ActionValidator攻击射程、DefensePlanner | test_actions.test_attack_cone_controller_cooldown_and_runtime_range；部分：attackPower尚未用于伤害估值（A01，保留语义风险） |
| C10 §11 | 角色死亡/重现，不伪造复活、背包状态 | World按当前health解析 | test_tasks.test_dead_displaced_or_ended_task_cannot_execute、test_integration长局；本地；复活时间由平台执行 |
| C11 §12 | 仅worker、白天、邻接建造、合法区域、25金币 | ActionValidator build、DefensePlanner.construct | test_actions.test_build_regions_counts_budget_and_unknown_rules、test_defense.test_build_requires_confirmed_name_and_never_overwrites；本地，build.name按用户确认默认采用roleType |
| C12 §12 | 全局武器≤3、墙≤20、覆盖不新增数量 | ActionValidator计数/modified | test_actions.test_build_regions_counts_budget_and_unknown_rules、test_wall_limit_and_replacement_count；本地 |
| C13 §10、12 | 墙消耗石头；拆墙不返还；仅工人邻接remove | Rules.wall_stone_cost、ActionValidator | test_actions.test_upgrade_and_remove_do_not_double_modify_building、test_build_regions_counts_budget_and_unknown_rules；部分：默认成本1已由官方完整内嵌图确认，test_official_wall_cost_one_stone_default验证 |
| C14 §13 | 控制者活着且邻接、仅控制一座、夜间攻击 | ActionValidator attack、DefensePlanner.fire | test_actions攻击案例、test_defense.test_two_weapons_use_distinct_controllers；本地，控制是否占个人动作按保守互斥 |
| C15 §14 | 切比雪夫射程，runtime优先 | ActionValidator、DefensePlanner.fire | test_actions.test_attack_cone_controller_cooldown_and_runtime_range；本地 |
| C16 §15 | 加特林目标数=等级、任意方向夹角≤90° | ActionValidator向量点积 | test_defense.test_gatling_opposite_targets_stay_in_cone、test_actions攻击90°边界；本地 |
| C17 §15、18 | 加特林弹道最近机器人拦截 | DefensePlanner.damage | test_defense.test_railgun_energy_and_gatling_interception；部分：准确共线估计；网格擦边及同回合预测死亡后是否仍拦截未验证 |
| C18 §16 | 电磁炮一个终点、能量依次扣减、到终点停止 | DefensePlanner.damage、ActionValidator | test_defense.test_railgun_energy_and_gatling_interception；部分：非共线弹道及同回合存活/能量结算未验证 |
| C19 §17 | 火箭目标数=等级、中心20/周边10、叠加、不阻挡 | DefensePlanner.damage/fire | test_defense.test_rocket_aoe_and_cooldown；本地静态模型 |
| C20 §17 | 火箭冷却、等级3全图 | runtime cooldown/range、静态后备表 | test_defense.test_rocket_aoe_and_cooldown、test_http密集请求；本地；真实冷却更新由平台提供 |
| C21 §19 | 攻击/道具先于移动，伤害回合末结算 | 仅生成动作，不修改观测health | test_defense火力估值；部分：死亡机器人当回合行为不明，不模拟 |
| C22 §20 | worker邻接collect，容量，矿刷新，可多人采同矿 | ActionValidator、EconomyPlanner.workers、World重建 | test_actions.test_collect_same_mine_night_and_wrong_actor、test_dynamic_mine_and_two_workers_no_move_collision；本地；10次后刷新由平台执行 |
| C23 §21 | vendor邻接批量卖矿，实时价格 | shop_prices、ActionValidator sell、EconomyPlanner | test_actions.test_default_callback_collect_then_sell_from_observation、test_capacity_multiset_and_no_sale_credit；本地 |
| C24 §22、25 | shop邻接买动态商品，金币/容量检查 | EconomyPlanner.purchase、ActionValidator buy | test_actions.test_dynamic_purchase_item_and_budget、test_purchase_full_inventory_does_not_travel；本地 |
| C25 §23 | 券等级匹配、建筑邻接、最高3级，升级回满血 | UPGRADES、ActionValidator use、DefensePlanner.maintain | test_actions.test_upgrade_and_remove_do_not_double_modify_building、test_defense.test_emergency_upgrade_precedes_controller_use；部分：满血由平台回传，不本地伪造 |
| C26 §24 | WallFixer各等级修墙，Medicine自身修复 | maintain/support、USABLE | test_defense各等级修墙、低等级采购→修复、药品炸弹；本地 |
| C27 §24 | Bomb/Dizzy全图使用、仅机器人、3×3 | ActionValidator use、DefensePlanner.support | test_actions.test_consumables_and_summon_daily_limit、test_defense.test_medicine_and_bomb_use_observed_inventory；部分：眩晕5回合由平台执行，眩晕目标预留专项已通过（A02） |
| C28 §24、73 | 召唤令每天≤10张，作用于对手下一夜 | GameMemory.summon_attempts、ActionValidator | test_actions.test_summon_duplicate_gap_and_day_reset；部分：默认规划器日间使用已有召唤令并验证额度（A03）；生成敌方浪潮由平台执行 |
| C29 §26 | 背包多重集、容量、已知道具大小写 | inventory、ActionValidator | test_actions容量/消耗品/宝藏测试；本地；动态商品不擅改拼写 |
| C30 §27、53 | 全图机器人、targetTeam可缺、每日重建 | World.robots、DefensePlanner.robots | test_defense.test_other_side_and_unknown_robot_target、test_http密集场景；部分：正式接口§1.5已确认roles包装 |
| C31 §28 | 官方新闻跨日事件、停采、价格方向、到期 | GameMemory.news、NewsPlanner、resource_events、EconomyPlanner | test_news.test_harvest_event_expires_and_runtime_price_controls_choice；部分：真实自然语言推理未联调 |
| C32 §29、72 | 跨日民间线索、位置/时间/物品证据、高置信度 | NewsPlanner两次解析、parse_news_decision | test_news证据/不一致拒绝、test_memory新闻历史；部分：完整原文已保留，120k跨日新闻回归通过（A04） |
| C33 §30 | pioneer邻接、item精确multiset、合法失败也耗物 | ActionValidator summonTreasure、TreasurePlanner | test_actions.test_treasure_inventory_and_drop、test_news采购/预算/窗口；本地，不臆造平台消耗 |
| C34 §30 | 结果0–4、有来源才回收、成功/已空不重试 | TreasurePlanner.pending/attempts/terminal | test_news.test_all_result_codes_and_gap_do_not_repeat_consumption；本地；未知结果保守停止 |
| C35 §31、51 | 仅己方任务、pioneer领取、任务点2多格、isValid/cooldown | task_options、ActionValidator acceptTask | test_actions.test_task_own_side_multicell_and_submission、test_tasks.test_only_eligible_own_tasks_and_route；本地 |
| C36 §31 | 接受动作无目标字段，重叠邻域不能识别所选任务 | TaskPlanner.accepted_task仅唯一邻接时记录 | test_tasks.test_overlapping_points_do_not_invent_task_timeout；部分：平台选择方式未给 |
| C37 §31–32 | 活跃任务不离开、死亡/离开/超时停止 | TaskPlanner、ActionValidator move、DefensePlanner.characters | test_tasks死亡/离开、timeout同描述新实例；本地，未知截止只依赖真实phaseTask |
| C38 §33–34 | prompt/llmResp跨回合、普通3次/日、任务免费 | TaskPlanner.pending、GameMemory额度、GameSession最终门禁 | test_tasks.test_quota_gate_duplicate_reset_gap_and_rollback、test_news.test_platform_quota_error_stops_ordinary_retries_until_day_reset；本地 |
| C39 §35 | 仅任务executeCmd、不同步等待、不本机执行 | TaskPlanner、GameSession最终门禁 | test_tasks完整异步序列；本地；真实沙盒15秒/无网络由平台保证 |
| C40 §35 | exitCode/TIMEOUT/JUDGER_ERROR/TRUNCATED | command_observation、bounded_text | test_tasks.test_command_failure_markers_preserved、test_strict_json_and_output_boundaries；本地 |
| C41 §36–38 | SOP/SKILL经验复用，成功不能臆测 | task_experience、TaskPlanner.prompt | test_tasks.test_history_and_half_reset_only_preserves_labelled_experience；部分：无明确成功/通过率字段，当前仅未验证经验，省略skill保留与命令结果配对回归通过（A05） |
| C42 §37–38 | 错误答案若仍活跃可继续，超时/部分分数由平台结算 | TaskPlanner反馈与submitAnswer | test_tasks.test_wrong_answer_while_active_uses_feedback、test_expired_old_task_error_does_not_expire_new_description；部分：正式重试/评分结果待联调 |
| C43 §39–41 | 生存优先、任务与击杀积分、1300结束 | plan_turn紧急维护、任务、开火；不自行结束平台 | test_defense紧急维护、test_integration长局；部分：未验证胜率或官方计分 |
| C44 §42–45 | 参数端口HTTP、Flask SDK default host、Python3.11.10+Flask | main、run.sh | test_http启停/合法CLI/非法端口；本地Windows/WSL及最小文件复制启动通过；正式打包由用户验证 |
| C45 §46–55 | 顶层字段容错、news/errors/结果源回收 | World、GameMemory.observe | test_integration.test_malformed_optional_fields_do_not_collapse_planning、test_memory；本地 |
| C46 §56–60 | 三字段Response、12动作、目标数组、不重复key | ensure_valid_response、validate_command_shape、ActionValidator | test_protocol、test_actions全12动作、test_integration长局；本地 |
| C47 §61–63、77 | 畸形JSON/None/异常返回合法空响应并可恢复 | process_request异常边界 | test_protocol.test_bad_requests_recover、test_internal_exception_and_invalid_response、test_http；本地 |
| C48 §62、78 | 已连接5秒响应、不等待远程工具 | 有界地图规划、异步pending | test_http.test_dense_http_concurrent_duplicates_and_valid_configuration（1302机器人）；本地；正式硬件与未规定最大输入仍未验证 |
| C49 §64–66 | 事务、去重、失败回滚、反馈关联 | GameSession锁/副本/缓存、GameMemory.feedback | test_memory九项及test_integration长局；本地；协议无半场/请求ID，任意乱序无法证明 |
| C50 §67–71、83 | 经济/维修/防守/任务/宝藏共享调度 | plan_turn、ActionValidator共享预留 | test_defense采购/站位、test_news采购窗口、test_integration长局；部分：策略质量不是最优性证明 |
| C51 §79–80、85 | 单文件功能分区、标准库依赖、日志不泄漏 | src/main3.py分区、LOG | py_compile、pip check、test_protocol日志SECRET不输出；本地 |
| C52 §84 | 提交自测清单全部项 | 对应C01–C51 | 局部通过，A项及平台未决项仍在；不可勾选整体完成 |

## 审计项结论

- A01未验证风险：官方字段仍仅写“攻击力数值”，未定义多发/溅射映射。采用任务书各等级公式；不臆造动态字段含义，用户正式验证。
- A02已解决：眩晕预留、三类武器所有等级目标数、满级券拒绝已补专项回归。
- A03已解决：默认规划器在日间闲置时使用已有召唤令；每日额度及夜间优先级已测，不主动采购。
- A04已解决本地截断：保留完整新闻、任务文本和答案，120k/80k回归通过；外部LLM上下文上限仍待联调。
- A05已解决：后续省略skill保留原经验，探索命令与结果配对；仍不假定成功。
- A06完成：独立只读审查无新增确定性协议错误；具体同回合弹道假设已列入C17/C18和REVIEW，完整92项回归通过。

## 最新验证证据与限制

Windows92项PASS（10.308秒），WSL92项PASS（17.223秒）。包含实际run.sh、1302机器人密集HTTP四并发重复与后续请求、双半场2600回合观测回放。最小运行文件复制到临时目录后，两环境HTTP采矿亦通过。

C17/C18新增异阵营前方机器人拦截/能量消耗和fire选点回归；C42新增提交合法性true/false/缺失反馈。历史TCP清理失败及修正见TEST_PLAN.md。

正式判题由用户承担，不再是Agent本地工作的接入前置条件；以上证据仍不能证明官方物理结算、模型解题、正式硬件时限或胜率。独立只读审查已完成，未发现新增确定性协议错误；同回合预测死亡的拦截反例见REVIEW。
