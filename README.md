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

## 4. 当前开发检查点：V3.7

当前入口：`src/main3.py`；平台产物：`CoreGeek/main3.py`、`CoreGeek.tar.gz`。

### 平台提交

保留旧V3.6作为回滚，沿用已验证的上传流程直接替换 `CoreGeek.tar.gz`。包内只有 `CoreGeek/main3.py`；不用安装依赖、设置环境变量或人工指定端口。平台按原方式注入位置参数端口。所有诊断仍由print输出，无需取回平台文件系统中的文件。

启动应出现：

```text
build=v3.7-sustainment-recovery
survival policy=v3.7-repair-retreat-rebuild
```

仍出现 `_v34` 的任务技能名正常：本次任务执行器没有改写。保留原始REPLAY3打印行。

### 修复范围

满血不耗药、按个人持有量补给、真正离炮撤退、解除跨天维护断供、短程移动维修、优先及时卖矿重建、基地券可持有等待受伤再用。保留14格C形、炮位、任务和攻击计算。候选版未得到新的官方成绩，不保证1300回合。

### 文件与覆盖

本补丁只覆盖同名源码、入口、工具及现行测试，不删除旧日志、环境和其他文件。不要把整个新目录再次套进仓库内部。`docs/V3.7_修复与验证报告.md` 与 `docs/V3.7_验证结果.json` 给出实际测试结果、废止的旧策略断言和限制。

维护后使用 `python -B tools/build_single_file.py` 重新生成入口包；不要再使用其他旧模块打包方式。当前交付已生成，参赛前不需重新构建。

### 可选本地测试

```bash
python -B tools/run_v37_tests.py
python -B tools/verify_task_commands.py
python -B tools/verify_platform.py
python -B tools/check_v37_invariants.py
```

这些是维护者的本地验证，不是平台启动命令，不要求用户从平台取回runs目录。测试目录有历史冻结源码/实际输入夹具，仅供比较，均不会被平台入口导入。

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

### 下载后自动解密

下载器会保留按分数/胜负命名的原始 `.log`，识别到 ASL1 加密日志后自动调用仓库内 `SecureLog/log_tool.py`，使用 `AgentRace_LogKeys/private.pem` 和固定的 `--backend rsa`。这两个路径相对于下载脚本所在目录，不受 `--output` 或运行目录影响；解密使用运行下载器的同一个 Python，请在该环境安装 `python -m pip install rsa==4.9`。

每份加密日志在同一个 game 目录下产生三份文件，例如：

```text
ally_RedSide_1234_win.log                            # 下载原文件（密文）
ally_RedSide_1234_win_decrypted.log                  # 解密后的日志
ally_RedSide_1234_win_decrypted.log.report.json      # 解密报告
```

旧明文日志不执行解密。`--round N` 补下载也会补做解密，并校验已有解密日志与报告；完整产物跳过，缺失或损坏的产物重新生成。解密退出码 2 时保留部分恢复结果和报告，并计入本轮错误；致命失败保留原始下载，不会将其当作解密成功。解密状态与文件校验值记入 `match.json` 的 `downloads.*.decryption`，本轮错误见 `summary.json`。`--dry-run` 不执行解密。