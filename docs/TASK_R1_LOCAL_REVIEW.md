# Task R1 本地复核（2026-09-12）

> 本报告记录 Task R1 复核时的结果。随后按用户要求将 main3.py 收敛为仅接收端口，并重新通过两平台完整测试；最新入口与测试状态见 STATUS.md、RUNBOOK.md 和 TEST_PLAN.md 的“仅端口比赛入口”章节。

## 结论与范围

网页端的主要诊断有依据，分阶段 prompt、带原文和错误类型的格式修复、上下文去重、候选来源校验、有限重试及未验证方法检索值得保留。它解决的是任务控制链路中的机械损耗，尚未证明真实模型推理、字段得分或胜率改善。

本次读取当前未提交改动、已提交的 `LLMInvokAnalyse/`、调用方/被调用方、测试和相关 AI Spec。当前本地 HEAD：`e39e71e15cb16a00501fcc9e5c874c960cfd62d0`。未访问 Official，未连接外部模型，未执行比赛沙盒命令，未提交或推送 Git。

原网页端缺 Flask 的结论只适用于其环境。本机既有 Windows 和 WSL 虚拟环境均有 Python 3.11.10 / Flask 3.1.3，无需修改或安装依赖。

## 已复现并修复的问题

1. **最终阶段连同合法来源候选一起丢弃（P1）。** R2 执行命令、R3 得到完整成功输出 `42` 并进入最终阶段，R4 返回 command 加 `candidate_answer=42 / candidate_source_round=3` 时，原实现只记 `final_answer_required`，没有保存候选、也没有提交。现在仅在回复通过全部结构校验、唯一错误是阶段禁止 command 时，独立验证候选来源后进入既有保底路径；命令仍不执行。未知字段、错误类型、错误来源和伪造候选继续拒绝。
2. **JSON 来源比较损失数字精度（P1）。** 原实现把 `9007199254740993.0` 与 `9007199254740992.0`、`1e-400` 与 `0.0` 等误判为相同，可能授权提交与输出不同的候选。现在严格 JSON 校验后，以标准库 Decimal 保留数值精度，并用独立数字类型标记区分布尔和字符串；不同数字拒绝，等值指数写法可接受，无法表示的指数安全拒绝。

测试先在未修实现上失败，再应用修复。新增 `tests/test_task_review.py` 共 6 项，含真实任务流程、三个策略模式及错误分支。另在 `tests/test_http.py` 增加 1 项真实服务测试，覆盖格式错误→修复→命令→自动提交、4 个并发重复请求、错误/部分正确反馈、重复答案阻断、改进答案、结束、普通日志无原文及 5 秒响应约束。

## 验证结果

| 实际命令 / 检查 | 结果 |
|---|---|
| Windows `.venv/Scripts/python.exe -B -m unittest discover -s tests -q` | 304 项：303 通过、1 项 POSIX symlink 平台跳过；39.746 秒 |
| WSL `.venv/linux-test/bin/python -B -m unittest discover -s tests -q` | 304 项全部通过，无跳过；49.752 秒 |
| Windows `-m unittest discover -s tests -p test_task_review.py -q` | 新增 6 项通过 |
| Windows `-m unittest discover -s tests -p test_http.py -q` | 5 项真实 HTTP 测试通过；6.624 秒 |
| WSL 系统 `python3 -B tools/test_core_offline.py --report /tmp/agentrace-task-r1-review-core.json` | 282 项通过；22 项明确排除（包括本次新增 HTTP）；仅是补充核心检查 |
| 对当前 HEAD 的独立进程差分 | 11 组、387 条无任务请求全部一致 |
| 冻结 AST、fixture 哈希、依赖方向、完整 diff 和规格复核 | 已完成；未发现其余需在本轮阻断交付的问题 |

两次完整测试均包含原有 HTTP、实际入口 / run.sh、故障与事务恢复、缓存并发、密集输入和观测回放。Windows 跳过的 symlink 测试在 WSL 已实际执行通过。测试异常注入是预期故障路径；没有把失败结果作为 PASS。Git 仅提示已有 LF/CRLF 转换，`git diff --check` 无空白错误。

额外差分使用 `tests.test_equivalence.cases(False)` 全部三个模式、两个起点，包括 HTTP 与故障注入；显式清空活动任务及任务领取选项。将 HEAD 的 `src/` 导出到独立临时目录，两边运行相同的 `tests/equivalence_runner.py modular`，逐项比较完整 Response、缓存 Response、fingerprint、规范化 GameMemory。无字段删除或宽松数值比较。该对照补充了原冻结 V2.2 测试未覆盖的当前 defense 基线；不等于实际战斗模拟。

## 对原分析的核对

从 Round6 的 7 个 `ally*.log` 独立解析 `[turn]`，按文件内回合去重并检查重复一致性，仅在连续下一回合关联模型/命令结果；任务段按 active 变化划分。重算结果与 `AgentRace_Round6_LLM_Stats.json` 核心计数一致：

- 4,245 条 turn、35 次领取 / 35 段任务、198 次模型调用。
- 174 次回复通过旧解析、24 次不通过；117 次转命令、27 次转提交、30 次两者皆无。后 30 次均对应之前的 answer_only 请求。
- 152 次命令，exitCode 0/126/1/2 分别 132/10/9/1 次。
- 28 段含超时、8 段无提交、20 次错误码 2。
- prompt 字符最短 6,824、中位数 16,209.5、最长 43,504。

旧探针 JSON 是旧版本缺陷的记录，不能把旧断言直接当新实现的目标。新实现已由当前测试验证对应分支。旧日志没有模型回答原文，无法复算具体格式错误类型，也不能把 20 次错误码 2 解释成 20 次零分。

## 规格覆盖复核

以下章节均指 `AI Spec/未来战争_v1.0_比赛全貌_开发整合版.md`；动作合法性与评分还核对了 `AI Spec/官方材料核对补充.md`。

| 要求 | 实现 | 验证 |
|---|---|---|
| §31–32：任务所有者、邻接、死亡/结束/超时 | TaskPlanner.run、GameMemory.observe、ActionValidator | test_tasks、test_task_protocol_r1 |
| §33、35：LLM/工具结果跨回合，工具状态与截断 | pending 关联、command_observation、observe_task_command | 迟到、漏回合、跨题、失败/截断专项 |
| §34：任务期间豁免普通调用额度，对外仅原协议 | GameSession 门禁、原 Response 校验 | test_tasks、test_protocol、test_http |
| §37：已提交部分答案的保底价值，仅任务继续时改进 | candidate、fallback、submit、submission feedback | R1 截止/去重专项、新增最终候选及 HTTP 流程 |
| §36：SOP 复用，不能把结束当已验证成功 | skill 与 candidate 分离、select_task_experience | 相关性、旧结果不注入、unverified、跨半场测试 |
| §59.8：taskAnswer 字符串与动作合法性 | submit / ActionValidator / ensure_valid_response | 原任务与协议测试、HTTP 编码和直接大答案 |
| §callback 5 秒预算、失败恢复 | 未修改入口与事务；默认关闭原文 IO | 两平台真实 HTTP、密集输入、故障/并发、审计 IO 故障测试 |

来源匹配、完整围栏接受、字符预算及有限重试是内部工程策略，不是新增官方协议。原冻结测试只放开明确变更的方法，任务时序由独立期望覆盖，不强求新 prompt 与旧文本相等。

## 剩余边界与下一步

- 尚未调用真实赛事模型；不能确认它会使用 stdout 标记或候选字段，也不能给出 prompt 改后正确率、字段通过率、奖励或胜率。
- 自动提交假定模型已让工具仅输出符合题意的答案；退出码 0 和来源相同不能证明字段、单位或数值正确。通用任务 schema/语义校验和经评分认证的技能库仍未实现。
- 来源采用完整输出，不能自动合并多轮结果中的零散字段。无候选时仍可能超时无提交。未知截止时间、无观测空窗的同描述换题、真实沙盒持久性仍有边界。
- §37 明确最高已提交通过率的价值，但错误答案后是否一定继续、细粒度反馈仍需实测；运行时只在观测任务仍活动时继续。
- 36,000 是辅助上下文字符预算，长输出仍按头尾裁切，并非语义压缩或实际模型 token 上限。默认 defense 的新闻/寻宝能力未在本轮接入。
- 私有审计默认关闭，未擅自开启持久采集。开启后的磁盘阻塞、Windows 目录权限及原文保存要求仍由实际部署环境约束。

`TASK_R1_VALIDATION.json`、`TASK_R1_MANIFEST.json` 保留网页端历史证据，已显式标注不代表当前工作区哈希。恢复以 STATUS 和本报告为准。当前可作为人工 Git 提交检查点；下一步为人类接管正式环境，观察协议遵守率、无提交超时率、完成回合及字段得分。
