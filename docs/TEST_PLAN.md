# AgentRace 测试计划

当前整体状态：NOT READY。原仓库无测试。计划使用标准库 unittest，Flask test client 与真实 HTTP 子进程测试；不以本地模拟冒充官方判题。

## 环境

本机 python3 是 3.10.12，python3.11 是 3.11.0rc1，均未预装 Flask；正式要求 3.11.10。仓库 .venv 已安装 Flask 3.1.3（requirements-dev.txt 记录依赖）；精确平台兼容仍未验证。

## 分阶段验证

| 阶段 | 必测案例 | 状态 |
|---|---|---|
| P0 协议 | POST /、argv 端口、UTF-8、空/畸形 JSON、None、内部异常、安全三字段输出、启动停止、重复请求 | PASS：7项测试，见 tests/test_protocol.py、tests/test_http.py |
| P1 世界/状态 | 地图边界、基地4格、任务点2多格、观测刷新、八方向、穿角、不可达、抢格/交换、半场重置、事务/去重 | 部分 PASS：世界6项、状态9项；平台包装及半场语义待确认 |
| P2 动作/经济 | 全12动作字段/类型/角色约束、背包重复物品、共享金币不足、容量边界、买卖邻接、矿耗尽 | PASS：test_actions.py 19项；平台未决项仍未验证 |
| P3 建设夜战 | 日夜边界、区域/数量限制、升级等级、控制者唯一/邻接、冷却、弹数、90度边界、射程、火箭3×3 | 部分PASS：test_defense.py 13项；完整覆盖审计待续 |
| P4 任务 | 接取合法性、等待反馈、锁定开拓者、死亡/离开/超时、LLM额度、延迟结果、命令错误/超时/截断、答案重试、技能验证复用 | NOT RUN |
| P5 新闻宝藏 | 跨日历史、新闻期限、实时价格优先、物品multiset、缺乏证据不献祭、结果0–4、跨局清理 | NOT RUN |
| P6 集成 | 1300回合/双半场、异常/缺字段序列、并发重复请求、最大地图性能、资源清理、真实启动脚本 | NOT RUN |

## 预定命令

- 全测试：`.venv/bin/python -m unittest discover -s tests -v`
- 语法：`.venv/bin/python -m py_compile src/main.py`
- 启动：`bash run.sh PORT`
- 最终审查：需求→实现→测试映射；`git diff --check` 和完整 diff；独立正确性审查。

性能测试必须测完整 callback/HTTP 时间，不能用单次寻路证明5秒期限。畸形数据测试检查响应结构及进程仍可处理下一条请求。集成模拟的结算规则必须注明其来源及未覆盖的官方行为。

## 无法在当前材料中确认

官方连接/打包方式、Python 3.11.10、wall成本、build.name、roundNo起点、基地占格、精确弹道、任务反馈细节、沙盒持久性、半场生命周期。交接必须逐项保留，不能标 PASS。完整功能实现前不可宣布完成。

## 最新执行证据

P0 全测试7项成功，耗时0.474秒；py_compile、git diff --check成功。真实HTTP测试需要沙箱外本地socket权限；普通沙箱运行因PermissionError失败，未隐藏或跳过。后续策略加入后必须重新测试完整请求时延。

## P1 部分验证

`tests/test_world.py` 6项 PASS：双起点昼夜边界、地图角落、基地4格/12武器格/20墙格、多格任务点、观测消失重建、最短路/穿角/不可达、抢格/交换/重复动作拒绝、畸形和重复ID输入。全测试13项 PASS（0.371秒，受审查权限含真实HTTP）；py_compile、git diff --check PASS。此处为历史结果；跨回合状态与callback集成已在下述最新P1验证中完成，机器人包装仍待平台确认。

## P1 状态集成验证（最新）

- 定向 `test_memory.py` 最初8项通过；新增序列化回滚后共9项。
- 全测试 `.venv/bin/python -m unittest discover -s tests -v`：22项 PASS，0.385秒，受审查权限包含真实HTTP。普通沙箱执行曾因禁止socket而失败，未跳过测试。
- 状态案例：callback集成、32个并发相同请求只规划一次、缓存响应独立副本、规划/格式/UTF-8序列化失败回滚、同回合内容冲突HTTP回退后恢复、新闻去重跨日保留、敌情历史不污染障碍、连续反馈/漏回合隔离、身份变化/回合回退重置、非法输入、0/1起点与1300边界。
- 世界输入补测畸形roleType和5000位字符串ID；真实HTTP现使用带身份和中文新闻的有效请求并实际重复相同请求。
- 尚无任意乱序、跨HTTP送达恰好一次、正式Robot包装、正式半场生命周期或完整策略5秒时延证据。

| P1 要求来源 | 实现 | 验证 |
|---|---|---|
| §3 昼夜与起点 | Phase / GameSession.origin | test_world.test_phase_boundaries / test_memory.test_missing_invalid_input_and_origin |
| §4–9、47–54 世界与历史隔离 | World / GameMemory.observe | test_world / test_memory.test_history_is_not_current_obstacle_and_news_deduplicates |
| §64 上回合反馈不假定成功 | GameMemory.feedback | test_memory.test_feedback_does_not_infer_success_or_associate_across_gap |
| §65 半场重置建议 | GameSession.handle | test_memory.test_identity_change_and_round_regression_reset_history；平台真实语义未验证 |
| §66、77 状态事务/稳定响应 | GameSession / callback / process_request | test_memory的并发、回滚、冲突恢复测试 / test_http |

这仅是P1局部覆盖映射，不能替代最终全部规格覆盖审计。已完成本阶段本地代码复查；最终独立审查仍待完成。

## P2 恢复后验证

全套41项PASS，包含受审查权限真实HTTP；普通沙箱socket失败保留记录。test_actions.py共19项：12动作、共享金币、背包重复/容量、同矿采集、控制者/建造/升级互斥、锥角边界、夜间限制、召唤额度与重复/漏回合、默认callback采矿卖矿、动态矿与采购、非法规划回滚、非有限/大整数生命值、无目标道具多余坐标拒绝。此次未验证正式平台。

| 来源 | 实现 | 验证 |
|---|---|---|
| §11–26、58–59、76 | ActionValidator / inventory / Rules | ActionTests |
| §20–22、25–26 | EconomyPlanner / plan_turn | EconomyTests |
| §24、64–66 | GameMemory召唤额度 / GameSession最终校验 | test_summon_duplicate_gap_and_day_reset / test_final_gate_rolls_back_illegal_planner_output |

P3需验证：建造配置缺失/合法配置、预留与三武器上限、保留墙通道、升级/维修/容量、基地濒危、控制者分配、入夜返程、冷却、锥角、火箭重叠与共线穿透、无机器人/畸形数据、完整callback时延。

## P3恢复后验证

本次全套54项PASS（0.890秒，受审查权限含真实HTTP），防守定向13项PASS（0.061秒）；py_compile、git diff --check成功。普通沙箱先前53项运行有1项socket PermissionError，不计为全套通过。

| 来源 | 实现 | 验证 |
|---|---|---|
| §12 建造配置/区域/不误覆盖 | DefensePlanner.construct / ActionValidator | test_build_requires_confirmed_name_and_never_overwrites / test_wall_plan_preserves_cardinal_gaps / test_actions |
| §13–18 控制、目标与伤害估算 | DefensePlanner.fire / damage | 双控制者、锥角、火箭范围/冷却、电磁穿透与加特林拦截测试 |
| §23–24 升级修复/消耗品 | maintain / support | 紧急升级、药品炸弹、各等级墙修复及满血不消耗 |
| §67、78 站位/时限 | position_controllers / GameSession | 入夜返程/冷却驻留、200机器人callback与重复请求 |

此映射为局部证据。待补：采购与维修调度多回合、CLI建造配置、密集场景真实HTTP时限、全局策略及正式弹道验证。已有性能用例不证明所有输入均满足5秒。
