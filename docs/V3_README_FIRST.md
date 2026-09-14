# V3.1 使用说明：这是已修复的代码包

版本：v3.1-reviewed-fix。基线：本次上传的 AgentRace-main-DeepSeek修复版.zip。

## 推荐：覆盖补丁

1. 停止正在运行的旧进程，备份当前 AgentRace 文件夹。
2. 将覆盖补丁解压到现有仓库根目录。src/tests/tools/docs 要分别与原目录合并覆盖，不要解压到 src 里。上传后另有修改时，先保存那些改动再覆盖。
3. 沿用原来能运行的解释器、Flask 环境、启动命令和端口重新启动。

补丁不删除 .venv、.git 或比赛日志。没有新增依赖，不需要 Codex/OpenCode 重新实现。

启动日志应为：

```text
[main] strategy_mode=survival; survival policy=v3.1-reviewed-fix
```

必须确认 strategy_mode=survival。仅版本号正确但环境变量仍是 AGENTRACE_STRATEGY=defense 时，跑的是旧模式。

## 完整包

完整包可用于另存一份工程；不附带 .git、.venv、缓存或平台二进制。新目录里需使用你已有的 Python/Flask 解释器；不要假定新目录内自带虚拟环境。未修改 run.sh 或入口端口契约。

## 已执行验证

383 项完整测试及干净覆盖副本 383 项均通过，含真实 HTTP/入口；原八项审查与 32 项新增回归通过。连续建设、券交付、首夜炮手、两种起点经济及随机输入已有记录。说明见 docs/V3_1_FIX_REPORT.md，原始结果在 docs/validation_v31/。

需要本机复跑全部验证时，在仓库根目录、已有环境中执行：

```bash
python -B tools/validate_survival_v31.py --output-dir local_validation_v31
```

不必为了使用补丁手工研究 JSON 或运行每个复现脚本。经济模拟没有官方机器人伤害，不能称为已存活 1300 回合；真实比赛仍需本版新日志。
