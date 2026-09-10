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



## 人类备忘

### 人类理解流程

真正核心的流程其实就是：

```
AGENTS.md
    ↓
AI Spec
    ↓
/goal
    ↓
/plan
    ↓
实现
    ↓
测试
    ↓
STATUS.md
    ↓
git commit
    ↓
继续下一阶段
    ↓
/review
```

#### 1

当前 /goal 会绑定在当前 chat 上；官方建议详细长期内容放文件中，让 goal 保持相对精炼，这正好和我们的结构一致。

```
/goal 完成 AgentRace 比赛程序。严格遵守仓库根目录 AGENTS.md。以 AI Spec/ 为比赛需求工作真值，在不主动读取 Official/ 多模态内容的前提下，完成需求分析、技术设计、实现、测试、需求覆盖审计和最终代码审查。全过程持续维护 docs/STATUS.md、docs/DESIGN.md 和 docs/TEST_PLAN.md。正确性优先于开发速度；任何无法验证的比赛关键行为必须明确记录，不能假定正确。
```

#### 2

/plan 当前就是 Codex 的正式 plan mode，适合这种多步骤实现前分析。

```
/plan

首先完整理解当前项目，但不要读取 Official/ 中的多模态内容。

请读取：
- AGENTS.md
- docs/STATUS.md
- docs/DESIGN.md
- docs/TEST_PLAN.md
- AI Spec/ 下所有与本次比赛实现有关的纯文本材料
- 当前源代码、构建文件和测试代码

同时检查：
- git status
- git diff
- 仓库目录结构
- 程序入口
- 构建方式
- 运行方式
- 当前测试方式

然后形成完整开发计划。

重点回答：
1. 比赛程序到底需要完成什么。
2. 所有比赛关键输入、输出、协议和约束是什么。
3. 当前代码已经实现了什么。
4. 缺少什么。
5. 建议采用什么架构。
6. 最大的判负风险是什么。
7. 应该如何分阶段实现。
8. 每个阶段如何验证。

此阶段优先分析，不要为了推进速度而猜测赛事规则。
```

#### 3

看一遍它给你的 plan。 这里你不用逐行审查代码，只重点看三个问题：它有没有搞错比赛目标；有没有漏掉明显赛事规则；有没有准备擅自读取 Official/ 图片。如果都正常，就让它进入正式执行：

```
按照已经形成的计划继续执行。

先把已经确认的需求、架构和测试策略落实到
docs/DESIGN.md、
docs/TEST_PLAN.md、
docs/STATUS.md。

然后按照计划分阶段实现代码。

每完成一个阶段：
- 运行对应测试；
- 检查相关实现；
- 更新 STATUS.md；
- 再进入下一阶段。

不要因为当前测试通过就提前认为整体完成。
持续工作，直到当前计划中能够在本地完成的开发和验证工作全部完成。
```

#### 4

第一版全部做完后运行：

```
/review
```

#### 5

最后一个步骤不要在原 chat 里做。 保存好 Git checkpoint，然后 /new 开一个全新 chat，让它没有前面“这是我自己写的代码”的路径依赖。新 chat 自动重新加载 AGENTS.md。然后给它：

```
你现在执行 AgentRace 最终独立审计。

不要修改代码。

先读取：
AGENTS.md
docs/STATUS.md
docs/DESIGN.md
docs/TEST_PLAN.md
AI Spec/
当前源代码和测试

不要读取 Official/ 中的多模态内容。

请从赛事规格出发，而不是从现有实现出发。

逐条建立：

比赛要求
→ 实现位置
→ 测试/验证位置

然后重点寻找：
- 完全遗漏的要求
- 部分实现的要求
- 对规则的错误理解
- 没有测试覆盖的关键规则
- 边界条件
- 崩溃风险
- 超时风险
- 状态污染
- 并发问题
- 协议不兼容
- 启停问题
- 只在理想输入下才成立的代码
- 测试本身存在错误而造成的假阳性

不要因为测试通过就默认代码正确。

最终按严重度输出问题：
CRITICAL
HIGH
MEDIUM
LOW

如果某项无法确认，请明确标记为无法确认，而不是推断正确。
```

### Session 接续
如果你担心：

> 华为网关一拦，Codex session 没了，我重新开 Codex 怎么办？

真正救你的不是 /goal，而是：

```
AGENTS.md
+
AI Spec/
+
docs/STATUS.md
+
git commit
```

新 session 一进来，你只需要告诉它：

```
这是一次由于网络网关中断后的 AgentRace 开发恢复。

现在只恢复上下文，不修改任何代码或文档，不安装依赖，不执行长时间任务。

请读取：
- AGENTS.md
- docs/STATUS.md
- docs/DESIGN.md
- docs/TEST_PLAN.md

并检查：
- git status
- git diff --stat
- 当前已有测试文件
- STATUS.md 中记录的当前阶段和下一步

不要读取 Official/ 中的多模态内容。

完成后只向我汇报：
1. 上一次已经完成了什么；
2. 哪些测试已经明确通过；
3. 当前有哪些未提交修改；
4. 下一步原计划是什么；
5. 是否发现恢复状态与仓库实际状态不一致。

完成恢复检查后停止，不要继续实现。
```

就能恢复。

再执行

```
/goal 完成 AgentRace 比赛程序。严格遵守仓库根目录 AGENTS.md。以 AI Spec/ 为比赛需求工作真值，在不主动读取 Official/ 多模态内容的前提下，完成需求分析、技术设计、实现、测试、需求覆盖审计和最终代码审查。全过程持续维护 docs/STATUS.md、docs/DESIGN.md 和 docs/TEST_PLAN.md。正确性优先于开发速度；任何无法验证的比赛关键行为必须明确记录，不能假定正确。
```

### 自我代码审计

```
不要修改代码。

你现在作为独立赛事代码审计员。

逐条读取 AI Spec，
建立：
需求 -> 实现位置 -> 测试位置

三列映射。

寻找：
1. 未实现需求
2. 部分实现需求
3. 实现与规则不一致
4. 未测试需求
5. 可能导致崩溃/超时/协议错误/判负的问题

不要因为现有代码看起来合理而默认它正确。
```
## 当前开发检查点

P0–P5已接入callback；Windows与WSL CPython3.11.10全套92项测试通过，含真实HTTP和WSL run.sh。本地开发交付与独立审查已完成，正式平台联调由用户负责，尚未宣称比赛就绪。围墙默认成本已从官方内嵌原图确认是1石头；武器建造名按用户确认默认采用roleType；回合起点仍需确认。恢复入口为docs/STATUS.md，覆盖审计见docs/COVERAGE.md。

Windows启动：`.venv\Scripts\python.exe src\main.py 8080`；全测试：`.venv\Scripts\python.exe -m unittest discover -s tests -v`。Linux启动仍为 `bash run.sh 8080`，可用 `AGENTRACE_PYTHON` 指定解释器；已在WSL执行POSIX启动脚本。项目依赖见 `requirements-dev.txt`。

准确的Windows/WSL启动、参数和人工接管检查见[docs/RUNBOOK.md](docs/RUNBOOK.md)。当前WSL须显式选择`.venv/linux-test/bin/python`，不能假定系统python3已安装依赖。
