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

当前基于 V2.4，默认 `defense`。2026-09-12 离线审查修复建设筹资停工、无效/重复资金预留、同名任务旧状态污染、HTTP日志异常及斜线弹道拦截，并保持损炮后“两火箭、一电磁炮”组成。恢复开发先读 [docs/STATUS.md](docs/STATUS.md)，问题与验证边界见 [docs/OFFLINE_AUDIT.md](docs/OFFLINE_AUDIT.md)，规格映射见 [docs/COVERAGE.md](docs/COVERAGE.md)。本补丁尚无新实机结果，历史测试记录不代表当前胜率。

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
