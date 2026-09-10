# AgentRace 测试计划

## Gate1 Shadow 验证（当前）

- `tests/test_shadow.py`：双资源攻击与后续移动/另一炮冲突；接受扣staged、拒绝不扣、下观测gold对账；初始75建炮预留；gap不关联意图；镜像布局/临时占位/静态资源阻挡；cost=2墙工批量采集且不被铜矿抢占；动态路程触发回防；冷却保持映射；Shadow重复请求/异常隔离/实际响应一致；禁止v2启动模式；TASK频道不被ECONOMY覆盖；失效炮位释放job；八墙不足先降级；格子索引伤害与旧公式等价；跨昼夜与R131/R261观测边界响应对照。
- `tests/test_http.py` 的密集真实进程测试使用 `--strategy-mode shadow`，仍保留原5秒限制、1302机器人、并发重复、可配置武器名/石耗、进程退出/端口释放；检查只有3条已提交Shadow报告且无Shadow异常。另一HTTP测试仍覆盖默认legacy。
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
