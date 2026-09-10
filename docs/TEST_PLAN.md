# AgentRace 测试计划

当前状态：本地交付完成，完整92项通过且独立只读审查完成；正式平台验证由用户负责，未宣称比赛就绪。需求逐条映射见COVERAGE.md，审查发现见REVIEW.md。

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
