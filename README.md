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

P0–P5已接入callback；Windows与WSL CPython3.11.10全套92项测试通过，含真实HTTP和WSL run.sh。本地开发交付与独立审查已完成，正式平台联调由用户负责，尚未宣称比赛就绪。围墙默认成本已从官方内嵌原图确认是1石头；武器建造名按用户确认默认采用roleType；回合起点仍需确认。恢复入口为docs/STATUS.md，覆盖审计见docs/COVERAGE.md。

Windows启动：`.venv\Scripts\python.exe src\main3.py 8080`；全测试：`.venv\Scripts\python.exe -m unittest discover -s tests -v`。Linux启动仍为 `bash run.sh 8080`，可用 `AGENTRACE_PYTHON` 指定解释器；已在WSL执行POSIX启动脚本。项目依赖见 `requirements-dev.txt`。

准确的Windows/WSL启动、参数和人工接管检查见[docs/RUNBOOK.md](docs/RUNBOOK.md)。当前WSL须显式选择`.venv/linux-test/bin/python`，不能假定系统python3已安装依赖。

## 5. 开发记录

- ~v2.3：OpenAI -> Codex(GPT6 Astra low)
- v2.4:
    + OpenAI -> Codex(GPT6 Astra high)
    + Claude -> Claude(Sonnet5 Medium)