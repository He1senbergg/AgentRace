# 启动与人工接管

当前本地程序可运行，尚未完成正式比赛联调。武器build.name按用户确认默认采用gatling/railgun/rocket；roundNo起点仍需确认。不要把测试里的test-rocket当作正式名称。

## 当前个人机器的本地检查

在仓库根目录运行：

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe src\main3.py 8080
```

上述默认启动适合检查服务；起点未知时仅观察到roundNo=0才能识别昼夜。按Ctrl+C停止。端口由启动参数决定。

WSL必须选用已安装依赖的Linux解释器：

```powershell
wsl --exec bash -c 'AGENTRACE_PYTHON="$PWD/.venv/linux-test/bin/python" bash run.sh 8080'
```

不要在WSL使用Windows的`.venv/Scripts/python.exe`，也不要使用创建失败的`.venv/linux`。`run.sh`默认优先`.venv/bin/python`，否则使用系统python3；当前WSL的有效环境位于linux-test，故需上面的显式选择。

## 已确认参数的传入方式

- `--round-origin 0`或`--round-origin 1`：只能使用已确认的值。
- `--weapon-build-name TYPE=NAME`：TYPE为gatling、railgun或rocket；NAME默认与TYPE相同。传此参数会用提供的映射集合替换全部默认映射，每类传一个参数。
- `--wall-stone-cost 1`：当前默认就是1，来自官方完整建筑图，无需额外设置。

所有参数放在端口之后。默认已启用三类武器建造；出现起点未配置提示说明昼夜仍需观察0或明确配置。

## 最小运行文件与验证

保留`run.sh`和`src/main3.py`的相对目录，另备requirements-dev.txt供环境复现。主程序只依赖标准库与Flask及其传递依赖，不依赖AI Spec、Official、docs或tests。

2026-09-10已将仅上述两个运行文件复制到临时目录，在Windows和WSL CPython3.11.10分别启动真实HTTP，提交工人邻接铁矿的观测，均得到预期collect响应，进程退出且临时目录清理。WSL执行了复制后的run.sh。这证明本地文件闭包，不证明官方打包格式或CentOS兼容。

## 用户负责的正式接管验证

1. 确认正式端口、回合起点、武器名称，检查启动日志与首回合响应。
2. 使用正式观测验证建造、控制者站位和首次夜间开火；核对动作合法性反馈。
3. 验证一次真实LLM→沙盒→答案，以及新闻/宝藏流程；保留失败原始文本用于定位。
4. 确认平台退出/半场重启行为与人工接管方式。程序状态在内存中，重启不会恢复当前任务和配额历史。

本地检查不能替代这些步骤；尚未在正式平台执行，不可标记比赛就绪。

本次已按官方 SDK 对齐：可直接执行 `.venv/bin/python src/main3.py 8080`，或 `bash run.sh 8080`。默认监听 127.0.0.1，与官方 `app.run(port=...)` 一致；判题器需从同一网络命名空间访问。
