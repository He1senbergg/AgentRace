# AgentRace

## 1. 定义

这是一场部门内的游戏比赛。

根据赛事规则，实现了代码之后，会在本地拉起进程，人工将去处理参赛。

## 2. 仓内文件定义

- `Official`: 原始的文件，含有多模态信息，本地agent读取会被华为网关拦截。仅仅在特别需要时读取，但也谨防读取图片与上传图像。
- `AI Spec`: 经过AI读取`Official`之后，重新撰写的纯文本版赛事解读。

## 3. 任务

根据`AI Spec`里的markdown，设计思路，并实现代码。谨防出现bug，会导致被直接判负，所以你需要完成一系列的测试，确保不会出问题。在代码实现完成后，会由人工接管真正的实际比赛。

为防止被华为的网关拦截，你需要在这个`README.md`里更新关键步骤、进度，以便如果真的断了，我能直接让后续的回话读`README.md`就继续开发与自验证。

---

## 4. 当前开发检查点

当前为 **Survival V3.1（2026-09-14）**，启动标识 `v3.1-reviewed-fix`。基于上传的 DeepSeek 版本，修复满背包禁售、日落交付离岗、基地救急优先级及已开火建筑交付过滤，保留此前有效修复。没有重新设计炮位或改变任务链路。

Python 3.11.10 / Flask 3.1.3：**完整 383 项通过，干净覆盖副本 383 项再次通过**，含真实 HTTP/入口；32 项新增回归及原八项审查通过。四张初始地图 × 两种资金仍 8 墙/3 炮/3 炮手；加八生成地图后 24 个条件的首日关键指标与基线一致。两种起点各 1300 步经济、12 组夜战输入和 600+600 随机/重复请求通过。**这些不是官方夜战或存活满局成绩。**

最新说明：[docs/V3_1_FIX_REPORT.md](docs/V3_1_FIX_REPORT.md)；证据：[docs/V3_1_VALIDATION.json](docs/V3_1_VALIDATION.json) 与 docs/validation_v31/；检查点：[docs/STATUS.md](docs/STATUS.md)。validation_v3/ 为旧版历史。

入口仍只接收端口；真实入口默认 survival，`AGENTRACE_STRATEGY=defense` 可选择旧模式。必须保留完整 src；沿用原 Python/Flask 环境，不新增依赖。先看 [V3_README_FIRST.md](V3_README_FIRST.md) 应用覆盖补丁；本地完整复验命令是 `python -B tools/validate_survival_v31.py --output-dir local_validation_v31`。未 Git 提交或推送。

## 5. 开发记录

- V3.1：ChatGPT 本地修复 DeepSeek 版本审阅发现，交付代码/测试/原始证据。

- ~v2.3：OpenAI -> Codex(GPT6 Astra low)
- v2.4:
    + default
        - OpenAI -> Codex(GPT6 Astra high)
        - Claude -> Claude(Sonnet5 Medium)
    + v2.4.1:
        - OpenAI -> Codex(GPT6 Astra Ultra)
    + v2.4.2:
        - OpenAI -> ChatGPT Web(GPT6 Pro)
        - 本地 Codex：任务链路复核、边界修复与 Windows / WSL 完整验证。
    + v3:
        - OpenAI -> ChatGPT Web(GPT6 Pro)

## 历史检查点：Task R1（不代表 V3 验证）


当前为 **V2.4 + Task R1（2026-09-12，本地复核完成）**，默认 `defense`。本轮实现 LLM 任务链路修复：分阶段提示词、定向格式修复、有工具来源的候选保底、重复操作限制、上下文去重和可选私有原文审计。本地复核额外修复最终阶段候选丢失与 JSON 来源数字精度。按用户要求，比赛主入口已收敛为只接收端口，删除四项命令行覆盖选项；经济/防御策略默认值及第三方依赖未改。

先读 [docs/STATUS.md](docs/STATUS.md)，本地复核见 [docs/TASK_R1_LOCAL_REVIEW.md](docs/TASK_R1_LOCAL_REVIEW.md)，部署见 [docs/TASK_R1_CHANGELOG.md](docs/TASK_R1_CHANGELOG.md)。Python 3.11.10 / Flask 3.1.3：Windows 完整测试 303 通过、1 项平台跳过；WSL 304 项全部通过，包含真实 HTTP 和入口测试。真实模型与比赛收益仍需实机验收。此前 V2.4 审查见 [docs/OFFLINE_AUDIT.md](docs/OFFLINE_AUDIT.md)。

Windows启动：`.venv\Scripts\python.exe src\main3.py 8080`；全测试：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`。Linux启动仍为 `bash run.sh 8080`，可用 `AGENTRACE_PYTHON` 指定解释器。部署须同时复制完整 `src/agentrace/`，不能只换 `main3.py`。项目依赖见 `requirements-dev.txt`。

准确的Windows/WSL启动、参数和人工接管检查见[docs/RUNBOOK.md](docs/RUNBOOK.md)。当前WSL须显式选择`.venv/linux-test/bin/python`，不能假定系统python3已安装依赖。

