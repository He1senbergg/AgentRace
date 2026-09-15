# AgentRace

## 1. 定义

这是一场部门内的游戏比赛。

参赛代码上传到对战平台，由平台注入端口并执行；赛后只取回平台提供的标准输出日志。

## 2. 仓内文件定义

- `Official`: 原始的文件，含有多模态信息，本地agent读取会被华为网关拦截。仅仅在特别需要时读取，但也谨防读取图片与上传图像。
- `AI Spec`: 经过AI读取`Official`之后，重新撰写的纯文本版赛事解读。

## 3. 任务

根据`AI Spec`里的markdown，设计思路，并实现代码。谨防出现bug，会导致被直接判负，所以你需要完成一系列的测试，确保不会出问题。在代码实现完成后，会由人工接管真正的实际比赛。

为防止被华为的网关拦截，你需要在这个`README.md`里更新关键步骤、进度，以便如果真的断了，我能直接让后续的回话读`README.md`就继续开发与自验证。

---

## 4. 当前开发检查点：V3.6

规则优先级：本次原始 `Official/任务书.md` 高于旧AI解读和旧复盘。半场两基地先后被毁时，先毁者负；不能以最高分替代胜负。上下半场各胜一场才比较总分。

唯一生产源 `src/main3.py`，标准库普通单文件；提交 `CoreGeek.tar.gz`，其中只含 `CoreGeek/main3.py`。平台传端口、仅print诊断，不要求环境变量或下载运行目录文件。

启动：`build=v3.6-frontline-survival`，策略：`v3.6-firepower-with-frontline-floor`。

本轮保留14格C形、炮位/炮型/伤害/任务执行器及NIGHT_WORK。C12缩边和开局排他正面优先因经济退化未采用。新增正面二级墙条件目标、维护总额/日额双预算、完整武器升级链资金保护、原地维修不抢当前可开炮角色。低HP已有药品优先保角色。

回归105项、已有任务命令81项、真实HTTP22项通过；Round12 8936帧兼容重放，不是新对局；受控无伤害经济模型12/12保留任务及炮升级时点，9图有部分二级前墙。没有官方实机新成绩，不能宣称1300回合已通过。

详细依据：`docs/V3.6_审计报告.md`、`docs/V3.6_证据与验证.json`。

### 维护者离线命令（不是平台部署前置步骤）

```bash
python tools/run_v36_tests.py
python tools/verify_task_commands.py
python tools/build_single_file.py
python tools/verify_platform.py
python tools/compare_economy_v36.py
```

旧tests和旧报告保留作为历史，不要无条件重新启用已退役策略断言；当前测试入口只使用 `run_v36_tests.py`。补丁带齐当前测试夹具，包括Round12经济输入与冻结的V3.5比较源；这些仅用于本地验证，不会打入平台单文件。

## 5. 实机下一轮

保持对手和设置不变，先红蓝各一半场。以胜负、两侧基地最后可见/首次缺失、入夜前正面HP/等级、前炮死亡、炮升级落地回合为主要验收项。平台输出仍保留REPLAY3。内部任务与日志不得直接公开。

## 6. 拉取对战日志

`auto_log_downloader.py` 通过浏览器下载双方日志，需要 Python 3.8+、Playwright 和 Microsoft Edge；首次运行时在打开的浏览器中完成内网登录，登录状态保存在脚本旁的 `.browser-profile/`。

在仓库根目录运行：

```bash
python -m pip install playwright
python auto_log_downloader.py                  # 练习赛第 1 页，默认队伍 OpenAI
python auto_log_downloader.py --pages 2-3       # 指定页码，也支持 1,3-5 或 all
python auto_log_downloader.py --round 14        # 补下载已有 round14，校验并跳过完整文件
```

默认保存到**当前工作目录**的 `log/`，可用 `--output 路径` 修改。每次普通运行创建 `roundN`（已有最大轮次 +1，首次为 round1）；该轮从上一轮最大 `gameN` +1 开始编号，首次为 game1。补下载用 `--round N`，复用已有场次目录，新场次继续编号。目录示例：`log/round14/game101/`，包含双方 `.log` 和 `match.json`；本轮结果见 `round14/summary.json`。普通运行不会跨轮去重，同一页重复运行仍会新建一轮。

文件名包含己方/对方、红蓝方、分数和胜负，如 `ally_BlueSide_1214_lose.log`。`--team 队伍名`、`--phase 海选` 可切换队伍和阶段；`--dry-run` 仅预览，不创建日志目录。网站未提供的日志会记入汇总的 `unavailable`。

默认使用运行环境中的 Edge。若在 WSL 中没有 Linux 版 Edge，可从 Windows 进入此仓库目录后运行 Windows Python；或安装 Chromium（`python -m playwright install chromium`）并加 `--channel chromium`。`--profile 路径` 可复用已有的专用登录目录。日志与浏览器登录目录仅供内部使用，不要公开。
