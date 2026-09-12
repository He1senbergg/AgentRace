# 启动与人工接管

当前为 V2.4 + Task R1 本地复核版本，默认 `defense`；本补丁尚无新实机结果。比赛入口只接收端口。武器build.name按用户确认采用gatling/railgun/rocket；首观测0或1自动识别roundNo起点，按正常比赛流程从开局启动。最新验证与风险见 [STATUS.md](STATUS.md) 和 [TASK_R1_LOCAL_REVIEW.md](TASK_R1_LOCAL_REVIEW.md)。

## 当前个人机器的本地检查

在仓库根目录运行：

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe src\main3.py 8080
```

上述默认启动适合检查服务；首次观测roundNo=0或1可识别昼夜。按Ctrl+C停止。端口由启动参数决定。

WSL必须选用已安装依赖的Linux解释器：

```powershell
wsl --exec bash -c 'AGENTRACE_PYTHON="$PWD/.venv/linux-test/bin/python" bash run.sh 8080'
```

不要在WSL使用Windows的`.venv/Scripts/python.exe`，也不要使用创建失败的`.venv/linux`。`run.sh`默认优先`.venv/bin/python`，否则使用系统python3；当前WSL的有效环境位于linux-test，故需上面的显式选择。

## 比赛启动参数

只传一个位置参数 `port`，范围 1–65535，例如 `python src/main3.py 8080` 或 `bash run.sh 8080`。原策略模式、回合起点、墙成本及武器名称覆盖选项已删除，传入会报参数错误。

生产默认使用 defense、墙消耗1石头、三类武器同名建造映射和开局0/1自动识别。内部 GameSession / Rules 仍可在测试中显式构造；离线回放工具可单独选择历史策略。中途冷启动缺少起点历史的限制仍在，不通过比赛命令行猜测或覆盖。

## 最小运行文件与验证

人工确认比赛允许额外 Python 源文件，保持 main3.py 既有入口即可。保留 `run.sh`、`src/main3.py` 和完整 `src/agentrace/` 的相对目录，另备 requirements-dev.txt 供环境复现。无需 bundle/构建生成步骤。主程序只依赖标准库与 Flask 及其传递依赖，不依赖 AI Spec、Official、docs、tools 或 tests；tests/fixtures/v22_baseline.py 是测试基线，不上传。

历史：2026-09-10 曾验证旧版单文件闭包。当前模块版已在临时目录仅复制上述运行文件，Windows Python 3.11 直接启动及 Git Bash 执行未修改 run.sh，真实 HTTP 状态/正文与冻结 V2.2 一致。该验证不冒充当前版本的 WSL/CentOS 或正式判题实测。

## 用户负责的正式接管验证

1. 确认正式端口、回合起点、武器名称，检查启动日志与首回合响应。
2. 使用正式观测验证建造、控制者站位和首次夜间开火；核对动作合法性反馈。
3. 验证一次真实LLM→沙盒→答案，以及同描述任务结束后重新领取；默认 defense 尚未接入新闻/宝藏执行，不能据 legacy 的相关测试认定它已启用。
4. 确认平台退出/半场重启行为与人工接管方式。程序状态在内存中，重启不会恢复当前任务和配额历史。

本地检查不能替代这些步骤；尚未在正式平台执行，不可标记比赛就绪。

当前启动：`.venv/bin/python src/main3.py 6666`；监听 0.0.0.0。重提交后查看前3次 [trace_request]/[trace_response] 日志及判题器原始异常。手动探测会占用日志次数并可能改变对局内存，正式运行前应重启进程。

## 角色不动：采集回合诊断

替换部署中的src/main3.py及完整src/agentrace/并重启，沿用原启动方式，无需开启debug或新增参数。Linux手动启动并保留控制台日志：

```bash
mkdir -p log
.venv/bin/python -u src/main3.py 6666 > log/diagnostic-run.log 2>&1
```

平台自动启动时直接下载平台控制台日志。确认出现[trace_turn]；保存启动部分、首10条及后续失败记录。round是观测回合，roles中的pos是当前位置，actions是本次输出摘要，feedback是上一回合结果，error_codes是平台错误码（4为指令错误）；feedback_associated表示能否与前一观测关联。phase=null表示昼夜尚未知。actions_total=0表示未输出角色动作；存在move但后续false或坐标不变需结合连续观测排查。日志各类条目最多12个，不是完整请求/响应转储。请勿用手动请求探测正在比赛的进程。

## 最新版本：1基开局与地图

只传端口，首个有效观测roundNo=1时自动设origin=1（首观测0仍为0基）；按比赛开局启动。更新文件并重启后确认首条[trace_turn]的phase非空、actions含build，之后weapons增长；第71回合检查回防和attack。摘要现为前10次、每10次及昼夜边界；[trace_map]在首观测、每50次和昼夜边界打印。将比赛完整控制台日志保存到log/Versus对应新局目录，保留地图的多行坐标，不仅截取HTTP 200行。诊断日志中的任务error_codes=[1]表示任务超时，不能当成网络超时。

最新日志：每个已提交非缓存回合均输出[turn]动作和角色状态；control_weapon表示正在操作指定武器，active_task表示任务占用，no_command仅表示未给该角色动作。武器cooldown/level/range及adjacent帮助定位不开火原因。详细[trace_turn]和[trace_map]仍按原周期采样；HTTP 200本身不证明动作成功。
