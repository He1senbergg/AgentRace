# 先读这里：V3 是候选版，不是正式胜率认证

完整包建议解压到新目录，保留你的原工程。覆盖补丁则解压到原仓库根目录，覆盖 src、tests、tools、docs 和 README；两种方式二选一。

源码已经修改完成，不需要再让 Codex 根据说明重新实现。必须带完整 src/agentrace，不能只替换 main3.py。

真实入口默认 survival，启动仍只接收端口；使用原本正常工作的 Python/Flask 环境：Linux/WSL `bash run.sh 6666`；Windows `.venv\Scripts\python.exe src\main3.py 6666`。端口和解释器路径沿用你现有配置。

需要回滚时设环境变量 AGENTRACE_STRATEGY=defense；清除该变量或设为 survival 恢复新版。

请读 docs/V3_AUDIT_AND_FIX_REPORT.md。322 项核心测试通过，另 22 项 HTTP/入口相关测试因当前容器缺真实 Flask 未获通过。白天模型对照与 1300 步经济连续性不是官方生存或胜率证明。真实模型任务和平台夜战仍待验收。

新函数逐行说明：docs/V3_CODE_GUIDE.md；原始测试证据：docs/validation_v3；覆盖范围：docs/V3_VALIDATION.json；源码差异：V3_patch.diff。
