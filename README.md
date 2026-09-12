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

当前为 **V2.4 + Task R1（2026-09-12，本地复核完成）**，默认 `defense`。本轮实现 LLM 任务链路修复：分阶段提示词、定向格式修复、有工具来源的候选保底、重复操作限制、上下文去重和可选私有原文审计。本地复核额外修复最终阶段候选丢失与 JSON 来源数字精度。按用户要求，比赛主入口已收敛为只接收端口，删除四项命令行覆盖选项；经济/防御策略默认值及第三方依赖未改。

先读 [docs/STATUS.md](docs/STATUS.md)，本地复核见 [docs/TASK_R1_LOCAL_REVIEW.md](docs/TASK_R1_LOCAL_REVIEW.md)，部署见 [docs/TASK_R1_CHANGELOG.md](docs/TASK_R1_CHANGELOG.md)。Python 3.11.10 / Flask 3.1.3：Windows 完整测试 303 通过、1 项平台跳过；WSL 304 项全部通过，包含真实 HTTP 和入口测试。真实模型与比赛收益仍需实机验收。此前 V2.4 审查见 [docs/OFFLINE_AUDIT.md](docs/OFFLINE_AUDIT.md)。

Windows启动：`.venv\Scripts\python.exe src\main3.py 8080`；全测试：`.venv\Scripts\python.exe -B -m unittest discover -s tests -q`。Linux启动仍为 `bash run.sh 8080`，可用 `AGENTRACE_PYTHON` 指定解释器。部署须同时复制完整 `src/agentrace/`，不能只换 `main3.py`。项目依赖见 `requirements-dev.txt`。

准确的Windows/WSL启动、参数和人工接管检查见[docs/RUNBOOK.md](docs/RUNBOOK.md)。当前WSL须显式选择`.venv/linux-test/bin/python`，不能假定系统python3已安装依赖。

## 5. 开发记录

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
