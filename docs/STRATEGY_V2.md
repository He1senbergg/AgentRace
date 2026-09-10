# AgentRace `STRATEGY_V2.md`
## 从“逐回合规则堆叠”转向“长期战略规划”的第二版核心策略

> 目标：替换当前 `plan_turn()` 顶层“依次调用 planner、谁先抢到资源谁执行”的决策方式。
>
> 本文只设计战略，不修改代码。后续 Codex / GPT 的职责是**按本文实现并验证**，而不是继续自行发明玩法。
>
> 依据：
>
> - `AI Spec/未来战争_v1.0_比赛全貌_开发整合版.md`
> - `docs/DESIGN.md`
> - `docs/STATUS.md`
> - `docs/VERSUS_ROUND2_ANALYSIS.md`
> - `src/main3.py`
> - `log/Versus/round2/game1/ally_RedSide_299.log`
> - `log/Versus/round2/game1/enemy_BlueSide_712.log`
> - `log/Versus/round2/game2/ally_RedSide_379.log`
>
> 本文中的数字分为三类：
>
> - **[RULE]**：比赛规则直接给出；
> - **[OBSERVED]**：真实 Versus 日志中观察到；
> - **[V2 TARGET]**：为了下一轮开发设定的策略目标，不代表官方规则，也不代表已证明最优。
>
> 第一原则：**先把生存链打穿，再做宝藏、骚扰、复杂新闻套利。**
>
> 第二原则：**Codex 不再决定“这个游戏应该怎么玩”；Codex 只负责实现已经确定的策略。**

---

# 1. 当前问题的准确诊断

当前代码已经有：

```text
World
Phase
GameMemory
ActionValidator
EconomyPlanner
DefensePlanner
TaskPlanner
NewsPlanner
TreasurePlanner
HTTP / protocol
路径规划
动作合法性
测试
```

这些不是当前最大的瓶颈。

最大的瓶颈是：

```text
没有真正的 StrategicPlanner
```

当前 `plan_turn()` 的逻辑本质仍然是：

```text
protect
→ resume_upgrade
→ emergency maintain
→ news
→ fire
→ support
→ liquidate
→ maintain
→ position_controllers
→ construct / fortify
→ treasure
→ provision
→ task
→ summon
→ workers
```

这是一条**固定优先级流水线**。

它解决的是：

```text
“当前这一回合还有什么动作能做？”
```

而比赛真正需要解决的是：

```text
“距离下一夜还有 40 回合，
为了下一夜结束基地仍然活着，
这 40 回合三个人各自必须完成什么？”
```

因此当前版本虽然功能很多，但依旧表现为：

```text
React / Behavior Tree

看到状态
→ 做当前看起来合理的动作
→ 下一回合再重新看
→ 再做一个动作
```

缺少：

```text
长期目标
资源预算
角色职责
硬截止时间
计划承诺
偏离检测
重新规划
```

---

# 2. V1 为什么会出现“代码越来越多，分数仍然很低”

## 2.1 局部 planner 之间没有统一目标

例如：

```text
EconomyPlanner：
想提高采矿收益

DefensePlanner：
想修建筑、升级、站位

TaskPlanner：
想让 pioneer 做任务

TreasurePlanner：
想买任务用品、跑宝藏

Provision：
想给人物带药
```

它们每一个单独看都合理。

但没有一个上层系统回答：

```text
今天只有 70 回合，
总金币只有 145，
三个人总共只有 210 个角色动作机会，

到底应该把这些资源投到哪里？
```

所以会出现：

```text
局部最优
+
局部最优
+
局部最优
=
全局很差
```

---

## 2.2 当前经济函数优化的是“这一趟采矿值不值”

当前矿选择大体使用：

```text
矿价 × 可采数量
──────────────
移动 + 采集 + 运送
```

这是合理的局部收益率。

但它没有回答：

```text
我真正缺的是金币还是 stone？
当前多赚 50 金币，是否比多造 5 面墙更重要？
距离夜晚只剩 18 回合，还应该继续赚钱吗？
```

V2 必须从：

```text
mine ROI
```

提升成：

```text
night readiness deficit
```

驱动经济。

---

## 2.3 当前建设没有真正的“目标阵容”

当前源码统计了已有武器种类，但武器选择仍会固定偏向某一类型。

更本质的问题不是具体选哪一炮，而是当前没有下面这个概念：

```text
Night 1 的目标资产是什么？
Night 2 的目标资产是什么？
Night 3 的目标资产是什么？
```

没有目标态，程序就只能：

```text
有钱 → 看当前哪个 upgrade/build 能做 → 做
```

---

## 2.4 夜战依然主要是“本回合攻击收益”

当前代码已经有：

```text
AoE
剩余血量扣减
加特林锥角
railgun 共线
controller 匹配
```

但目标函数主要仍在评估：

```text
当前这一炮打出去造成多少加权伤害
```

比赛真正应该评估：

```text
如果这只机器人未来 5～10 回合不死，
它会给基地 / 墙 / 炮手造成多少损失？
```

因此 V2 的战斗核心不是：

```text
damage now
```

而是：

```text
future damage prevented
```

---

## 2.5 controller 没有长期“岗位”

当前代码可以每回合重新做 controller 匹配。

这会导致：

```text
A 今天贴炮1
下一回合炮1 cooldown
A 被其他 planner 抢走
再下一回合炮1 ready
A 已经离开
```

或者：

```text
三个角色在炮位之间反复重新分配
```

强对手日志给出的重要信号是：

```text
每一夜开始前，
三个人已经稳定处在安全的炮位邻接位置。

整夜的核心不是“继续寻路”，
而是“持续保持炮手 uptime”。
```

V2 必须引入：

```text
persistent controller assignment
```

---

# 3. 真实日志给出的最重要基准

不要先猜最优策略。

先把真实的 712 分对手当成：

```text
第一个可复现 benchmark
```

它不一定能活 1300 回合，但目前明显比我们的 299 / 379 强。

---

# 4. 712 分对手的真实战略轨迹

以下均来自：

```text
log/Versus/round2/game1/enemy_BlueSide_712.log
docs/VERSUS_ROUND2_ANALYSIS.md
```

## 4.1 Day 1

**[OBSERVED]**

任务：

```text
R12 左右：
第一项任务完成
约获得 80 gold
累计 score ≈ 105

R29 左右：
第二项任务完成
累计 score ≈ 191
```

墙：

```text
R23
R24
R26
R27
R28
R37
R41
R45

累计造出 8 面墙
```

R71 第一夜开始时：

```text
gold = 60
score = 191

station:
L1
HP 1500

weapons:
rocket L2 HP1500
rocket L1 HP1000
rocket L1 HP1000

walls:
8 × L1
全部满血

characters:
worker 220
pioneer 200
worker 220

全部满血
```

这是我们目前最重要的“开局参考态”。

---

# 5. 强对手 Day1 布局

其 station：

```text
station.pos = (9,22)
```

武器：

```text
rocket: (9,20) L2
rocket: (8,22) L1
rocket: (8,23) L1
```

相对 station.pos：

```text
( 0,-2)
(-1, 0)
(-1,+1)
```

墙：

```text
(12,22)
(12,23)
(12,21)
(12,24)
(12,20)
(12,19)
(11,24)
(11,19)
```

相对 station.pos：

```text
(+3, 0)
(+3,+1)
(+3,-1)
(+3,+2)
(+3,-2)
(+3,-3)
(+2,+2)
(+2,-3)
```

纯文本：

```text
大致方向：

                后方

        R
        R   S S
            S S

              W W
              W
              W
              W
              W
              W W

             前方 / 地图中心方向
```

注意上图只是拓扑表达，不代表字符比例。

最重要的结构是：

```text
墙在朝地图中心的一侧形成屏障
武器和炮手在基地后侧/侧后
经济通道没有被完整封死
```

这与我们 round2 旧版把炮放到前沿有明显区别。

---

# 6. 强对手 Night1 结束

R131：

**[OBSERVED]**

```text
station HP = 1475

rocket:
L2 HP1500
L1 HP1000
L1 HP995

walls:
8 面仍存在
虽然部分已经受到伤害

characters:
220
200
220

全部存活并接近满血

gold = 60
score = 231
```

第一夜只让基地损失：

```text
25 HP
```

而且：

```text
三个角色全部活着
三门炮全部活着
八面墙全部还在
```

这是当前我们的第一阶段必须追上的指标。

---

# 7. 强对手 Night2 前后

R201，第二夜开始：

**[OBSERVED]**

```text
station HP = 1475
gold = 80
score = 328

weapons:
rocket L2
rocket L1
rocket L1

walls:
10 面

其中已有多面墙升到 L2

characters:
220
200
220
全部存活
```

R261，第二夜结束 / 第三天开始：

```text
station HP = 1410

三角色：
220
200
220

三炮：
仍然 L2/L1/L1

墙：
10 面均仍有大量剩余 HP
```

第二夜只再掉：

```text
65 station HP
```

也就是说：

```text
R1 → R261
基地仍然 1410 / 1500
角色 3/3 全活
```

这足以说明：

> 在前两夜，“活下来”的关键并不是疯狂冲高级武器。

---

# 8. 强对手 Night3 前后

R331，第三夜开始：

**[OBSERVED]**

```text
station HP = 1410
gold = 4
score = 544

weapons:
rocket L2
rocket L1
rocket L1

walls:
12 面

部分墙：
L2
一面甚至 L3

worker 背包中已有：
WeaponUpgradeVoucher2 × 1

三个角色：
全部满血
```

但 R391，第三夜结束：

```text
station HP = 420

三个角色：
200
200
220
仍然全部存活

多数墙仍然存在，
但前线墙已经严重损坏。
```

这说明：

```text
712 分策略前两夜非常强，
第三夜开始明显进入火力/墙体强度不足阶段。
```

因此我们不能只复制它。

我们的目标应是：

```text
先复制它的 Day1～Night2
再专门改进 Night3
```

---

# 9. 我方两个失败样本

## 9.1 game1：299 分

R71：

```text
gold = 145

station = 1500

weapons:
rocket L1
rocket L1
rocket L1

wall = 0

三角色满血
```

R131：

```text
station = 560

已经死了一个 worker

剩：
worker 95
pioneer 155
```

R201：

```text
station 已升级到 L2 = 3000

三门炮依旧 L1
```

R240：

```text
角色 = 0
武器只剩 2
station = 930
```

最终第二夜失守。

结论：

```text
升级 station 不能替代：
墙
炮手存活
持续开火
```

---

## 9.2 game2：379 分

R71：

```text
gold = 35

weapons:
rocket L2
rocket L1
rocket L1

三角色存活
```

但只有：

```text
极少量墙体
```

R131：

```text
station = 1245

worker = 175
pioneer = 200
worker = 175
```

R201：

```text
station = 1245
gold = 158

一面墙已经被升到 L3
```

R230：

```text
station = 170

两个 worker 已死亡
只剩 pioneer

三门武器全 ready，
但 adjacent controller = 0
```

R240：

```text
己方单位全部消失
```

核心失效链非常明确：

```text
墙体布局差
→ 机器人过早进入核心区域
→ 炮手受到攻击
→ worker 死亡
→ ready 武器没人控制
→ 火力 uptime 暴跌
→ 基地快速被打穿
```

---

# 10. V2 的第一战略目标不是 1300 回合

直接把：

```text
“活到1300”
```

作为当前优化目标太远。

调试时无法知道：

```text
一次修改到底好还是坏
```

V2 使用分阶段 Gate。

---

# 11. Survival Gates

## Gate 1：第一夜

**[V2 TARGET]**

R131：

```text
station HP >= 1400
characters_alive = 3
weapons_alive = 3
walls_alive >= 8
```

参考对象：

```text
712 对手：
station 1475
characters 3/3
weapons 3/3
walls 8/8
```

没有通过 Gate1：

```text
禁止优化 Day2 以后策略。
```

---

## Gate 2：第二夜

R261：

```text
station HP >= 1300
characters_alive = 3
weapons_alive = 3
walls_alive >= 9
```

参考：

```text
712 对手：
station 1410
characters 3/3
weapons 3/3
walls 10
```

没有通过 Gate2：

```text
只分析 Day2 / Night2。
```

---

## Gate 3：第三夜

R391：

```text
station HP >= 1000
characters_alive = 3
weapons_alive = 3
```

这里故意比 712 对手更高。

因为：

```text
712 对手 R391 只剩 420 HP
```

V2 必须在这里超越它。

---

## Gate 4：第四夜

R521：

```text
station HP >= 1000
characters_alive >= 2
weapons_alive = 3
```

如果能稳定做到：

```text
R521
```

再开始向：

```text
R651
R781
R911
R1041
R1171
R1300
```

逐夜扩展。

---

# 12. V2 顶层目标函数

不再使用：

```text
当前能做什么就做什么
```

也不直接使用简单加权：

```text
score = A*金币 + B*血量 + C*任务分
```

因为这种加权非常容易：

```text
拿几十金币
换掉一个炮手的命
```

V2 用**字典序目标**。

从高到低：

```text
1. 不发生协议异常
2. 基地不死
3. 三个 controller 尽量存活
4. 保持武器 firing uptime
5. 维持防御屏障
6. 完成高价值任务
7. 扩张经济
8. 击杀积分
9. 宝藏
10. PvP 召唤骚扰
```

即：

```text
survival
≫
combat continuity
≫
economy
≫
optional score
```

---

# 13. 新架构：必须增加 `StrategicPlanner`

目标结构：

```text
HTTP
 ↓
World / Memory
 ↓
StrategicPlanner
 │
 ├── DailyPlan
 ├── DefenseReadiness
 ├── BudgetPlan
 ├── RoleAssignments
 └── Deadlines
 ↓
Tactical Planners
 │
 ├── Task
 ├── Economy
 ├── Construction
 ├── Maintenance
 ├── Position
 └── Combat
 ↓
Action Arbiter
 ↓
ActionValidator
 ↓
Response
```

关键变化：

```text
旧版：
各 planner 自己争角色/金币

V2：
StrategicPlanner 先把
角色、金币、时间、目标
分配好

各 planner 只能执行被分配的工作
```

---

# 14. `DailyPlan`

建议内部结构：

```python
DailyPlan(
    day=1,
    mode="BUILD_DEFENSE",

    hard_goals={
        "weapon_count": 3,
        "wall_count": 8,
        "min_weapon_levels": [2, 1, 1],
        "controllers_ready": 3,
    },

    budgets={
        "weapon_build": 75,
        "weapon_upgrade": 100,
        "wall": 8,
        "medicine": 0,
        "reserve_gold": 0,
    },

    role_jobs={
        worker1: ...,
        worker2: ...,
        pioneer: ...,
    },

    deadlines={
        "task_stop": ...,
        "economy_stop": ...,
        "all_home": ...,
    }
)
```

它不是当前回合动作。

它表示：

```text
这一天要达成什么。
```

---

# 15. 计划不能每回合重建

正常情况下：

```text
DayPlan 在白天开始时生成一次
```

然后：

```text
Round t
执行一步

Round t+1
观察结果

如果没有重大偏离：
继续原计划
```

只有遇到 Replan Trigger 才重规划。

---

# 16. Replan Trigger

仅以下情况允许大幅改变计划：

```text
1. 新的一天开始
2. 夜晚开始
3. 角色死亡
4. 角色复活
5. 武器被毁
6. 关键墙被毁
7. station 进入危险血量
8. active task 开始/结束
9. 分配矿消失
10. 路径连续失败
11. 金币跨过关键购买门槛
12. 夜间防线被突破
13. 当前计划已经不可能在 deadline 前完成
```

不能因为：

```text
旁边突然出现一个价格稍好的矿
```

就把一个已经走了 8 回合的 worker 整个调头。

---

# 17. Role Commitment

每个人要有长期 job。

例如：

```text
worker1:
FORTIFY

worker2:
BUILD_AND_UPGRADE

pioneer:
TASK
```

一个 job 包含：

```text
type
target
phase
start_round
deadline
expected_finish
abort_conditions
```

除非 abort condition 发生：

```text
不允许别的低优 planner 抢这个角色。
```

---

# 18. Day 1：V2 开局模板

这是最重要的一天。

目标不是赚钱最多。

目标是：

```text
在第一夜开始之前，
构建一个可复现的防御状态。
```

---

# 19. Day1 目标态

R71 前：

**[V2 TARGET]**

```text
3 × rocket

等级至少：
L2 / L1 / L1

墙：
至少 8 面

角色：
3/3 活着
3/3 已回基地
3/3 已分配炮位

pioneer：
尽可能完成前两个任务

medicine：
非强制囤货
避免默认每个 worker 带 2 个药

禁止：
继续在远端采矿
继续跑 vendor
继续跑 shop
继续做来不及回来的新任务
```

为什么把：

```text
8 wall + L2/L1/L1
```

当第一目标？

不是因为理论证明最优。

而是因为真实 712 分样本已经证明：

```text
这套状态可以把第一夜基地损失压到 25。
```

这是当前最强的经验 benchmark。

---

# 20. Day1 角色职责

## pioneer

第一优先：

```text
自进化任务
```

理由：

```text
712 对手在 R12 / R29 已完成两个任务，
任务既给 score，又给 gold，
而 gold 直接转化为第一夜防御。
```

因此 pioneer 开局不是：

```text
挖矿
买药
闲逛
```

而是：

```text
TASK_1
→ TASK_2
→ 回防
```

一旦任务耗时过长，则受 deadline 限制。

---

## worker A：武器工

职责：

```text
造 3 座 rocket
→ 必要的第一座 weapon L2 运券/升级
→ 回炮位
```

起始 75 gold：

```text
刚好可以支付 3 × 25 的武器建造成本
```

如果地图/站位导致另一个 worker 建炮更快，可以动态交换 worker 身份，但 job 不变。

---

## worker B：墙工

职责：

```text
找最近可行 stone
→ 一次性准备 8 stone
→ 连续建设 8 面前墙
→ 回防
```

不要：

```text
采1块
建1墙
再跑矿
再采1块
```

保持 batch construction。

---

# 21. Day1 金币预算

默认：

```text
starting gold = 75
```

先锁死：

```text
75 → 3 weapons
```

然后任务/经济新增 gold 优先：

```text
100 → WeaponUpgradeVoucher1
```

因此 Day1 前 175 gold 的战略含义非常清楚：

```text
75:
三炮

100:
第一炮升 L2
```

在这两个目标未完成前：

```text
不允许购买：
WallUpgradeVoucher
StationUpgradeVoucher
Bomb
DizzyWeapon
RobotSummonOrder
非必要 Medicine
宝藏用品
```

除非明确的 emergency。

---

# 22. Day1 不再默认“每炮手两瓶 Medicine”

目前真实 game2：

```text
两个 worker 在 R71 各带 2 瓶 Medicine
```

这至少占用了：

```text
40 gold
```

而强对手 R71：

```text
三个角色背包都是空
```

不能仅凭这一点证明药一定不值。

但能证明：

```text
“Day1 默认给每个人囤两瓶药”
不是复制强基准所需要的动作。
```

V2 默认：

```text
Day1 不主动囤药
```

只有：

```text
角色已经受伤
且确实需要治疗
```

才进入 emergency purchase。

---

# 23. Day1 布局：先复现强对手

第一阶段不要让 build planner 自由搜索所谓“最优位置”。

先把可复现 benchmark 做出来。

## Challenger canonical template

station.pos = `(sx, sy)`。

武器候选优先：

```text
(sx,   sy-2)
(sx-1, sy)
(sx-1, sy+1)
```

第一座 L2 建议放：

```text
(sx, sy-2)
```

墙优先：

```text
(sx+3, sy)
(sx+3, sy+1)
(sx+3, sy-1)
(sx+3, sy+2)
(sx+3, sy-2)
(sx+3, sy-3)
(sx+2, sy+2)
(sx+2, sy-3)
```

这正是 712 分真实日志中的 Day1 布局。

---

# 24. Defender 的模板

地图上下半场对称。

建议先使用：

```text
180° mirror
```

转换 challenger canonical template。

地图：

```text
x: 0..40
y: 0..31
```

单格镜像：

```text
mirror(x,y) = (40-x, 31-y)
```

如果直接按 relative offset 表达，则 defender 可使用 canonical 的 180° 旋转偏移。

注意：

```text
这是 [OBSERVED STRATEGY] 的镜像推导，
不是官方规则。
```

实现必须先经过：

```text
合法建造区检查
occupied 检查
path 检查
```

若模板格不可用：

```text
才回退到动态候选选择。
```

---

# 25. Day1 Deadline

不能等到 R70 才想起回家。

定义：

```text
home_ready_round
```

根据实际最远角色回基地炮位的最短路径计算：

```text
return_deadline
=
70
-
path_to_controller_slot
-
safety_margin
```

建议 safety margin 初版：

```text
4～6 回合
```

进入：

```text
PRE_NIGHT
```

后：

```text
禁止所有非回防型远程任务。
```

理想目标：

```text
R65 左右：
三名 controller 已基本就位
```

实际使用动态路径计算，不硬编码 R65。

---

# 26. Night1：核心不是“杀最多”，是“不让防线崩”

夜间战略：

```text
角色岗位固定
↓
每门炮保持 controller
↓
根据 cooldown 开火
↓
只在必要时治疗
↓
不追怪
↓
不离开炮位
```

---

# 27. Persistent Controller Assignment

进入夜晚前生成：

```text
controller_weapon_map
```

例如：

```text
worker1  → rocket A
pioneer  → rocket B
worker2  → rocket C
```

整夜保持。

只有以下情况重新分配：

```text
武器被毁
controller 死亡
controller 与武器永久失联
某武器无法继续工作
```

不能因为：

```text
另一座炮当前 cooldown=0
```

就让人物跨区换炮。

---

# 28. Controller Slot

不是只分配：

```text
character → weapon
```

还应分配：

```text
character → exact safe adjacent cell
```

该格应尽量满足：

```text
1. 与自己的 weapon Chebyshev <= 1
2. 不占 station
3. 不占 wall
4. 不占另一 controller
5. 尽量位于 wall 后方
6. threat exposure 最低
7. 最好还能邻接另一门炮，作为灾难情况下 backup
```

进入夜晚后：

```text
除 emergency 外，
controller 不主动离开 slot。
```

---

# 29. 夜间治疗策略

当前 `protect()` 在 fire 之前执行。

V2 应改成：

```text
先判断 weapon 是否 ready
再决定角色这一回合的价值
```

建议：

```text
weapon cooldown > 0：
controller 可以治疗

weapon cooldown == 0：
默认优先开火

只有角色处于高概率一回合死亡风险：
才牺牲一次 fire 去治疗
```

也就是说：

```text
Medicine 尽量吃在 cooldown 空窗
```

而不是任意回合抢走 controller。

---

# 30. Night Combat V2 的目标函数

旧逻辑：

```text
当前 damage × 当前距离权重
```

V2：

```text
优先最大化：
未来 H 回合避免的防御损失
```

初版：

```text
H = 5～8
```

无需一开始做精确机器人模拟。

---

# 31. Robot Threat Score

建议每只机器人构造：

```text
Threat(robot)
```

输入：

```text
attackPower
health
到 station 的距离
到关键墙的距离
到 controller 的距离
是否已经突破墙线
是否已经进入攻击距离3
是否 stunned
```

一个初始可调模型：

```text
eta = 机器人到核心防御区域的距离代理

future_attacks
≈ max(0, H - eta)

threat
=
attackPower × future_attacks
+ station_immediate_bonus
+ controller_immediate_bonus
+ breach_bonus
```

注意：

```text
这只是排序模型。
不声称精确模拟官方机器人 AI。
```

---

# 32. Kill Value

不能只看：

```text
打多少 HP
```

还要看：

```text
这一轮是否能直接减少一个未来攻击源。
```

例如：

```text
10 HP smallRobot
```

和：

```text
对 500 HP largeRobot 打 10
```

同样是 10 damage，

但杀掉前者会立刻：

```text
减少一个攻击单位
```

因此加入：

```text
kill_bonus
```

---

# 33. Rocket 目标选择

Rocket 的真正优势：

```text
3×3 AoE
```

候选 target 不应该只用机器人当前格。

候选集合：

```text
每个机器人格
+
它周围 8 格
```

这部分当前代码已经在做，可以保留。

V2 改的是 score：

```text
score(target)
=
Σ 对覆盖机器人造成的 damage × threat(robot)
+
kill_bonus
-
overkill_penalty
```

---

# 34. 一回合三炮要联合规划

不能：

```text
炮1先选
炮2看剩余
炮3看剩余
```

纯贪心虽然简单，但可能错过：

```text
炮1 AOE 打左群
炮2 AOE 打右群
炮3补刀
```

更好的组合。

因为只有最多三门炮，可以使用小规模 Beam Search：

```text
每门炮先生成 Top-K volley
K ≈ 6～10

然后搜索：
炮1候选 × 炮2候选 × 炮3候选
```

最多：

```text
10³ = 1000
```

规模非常小。

最终选：

```text
全局 threat reduction 最大
```

---

# 35. 不需要现在上强化学习

当前首先需要：

```text
稳定 planner
+
真实 evaluator
+
真实日志
```

而不是 RL。

因为当前真正不确定的是：

```text
状态转移规律
墙的实际作用
机器人真实路径/攻击
火力策略
```

连环境模型都没搞清楚时，RL 只会扩大调试空间。

---

# 36. Day2：第一夜后的“恢复日”

Day2 一开始先做：

```text
damage assessment
```

不是马上采矿。

检查：

```text
station health
wall health
weapon health
characters health
destroyed walls
destroyed weapons
gold
任务可用性
```

---

# 37. Day2 优先级

建议：

```text
1. 恢复已经受损的核心防御
2. 保证三炮仍存在
3. 保证三人可以继续当炮手
4. 扩墙到 10 左右
5. 继续任务/赚钱
6. 再考虑额外武器升级
```

这里尤其注意：

```text
墙不是装饰物。

机器人会攻击阻挡移动的单位，
墙 HP 实际上是在购买“火箭多打几轮的时间”。
```

---

# 38. Wall Repair vs Upgrade

对 L1 / L2 受损墙：

如果本来就计划升级，

通常：

```text
直接升级
```

比：

```text
先 WallFixer
再升级
```

更省动作和金币。

因为升级：

```text
会直接回满血
+
提高最大 HP
```

因此：

```text
damaged L1:
优先考虑 UpgradeVoucher1

damaged L2:
优先考虑 UpgradeVoucher2

L3 damaged:
WallFixer
```

但如果：

```text
金币不足
```

WallFixer 10 gold 仍是很高性价比的临时修复。

---

# 39. Station Upgrade 不再作为默认救命答案

game1 已经证明：

```text
station L2 = 3000
```

但：

```text
没有墙
炮手死完
```

依旧会崩。

StationUpgrade 的正确定位：

```text
防线已经基本成立以后，
用来恢复 station + 增加事故容错。
```

不是：

```text
替代墙和火力。
```

---

# 40. Day2 V2 目标态

R201：

```text
station >= 1300～1400，或已经 L2
3 characters alive
3 weapons alive
rocket levels >= L2/L1/L1

walls >= 10
至少把最受攻击的前墙升级/修复

所有角色在 night 前重新固定炮位
```

第一阶段应尽量追平：

```text
712 opponent R201
```

---

# 41. Night2

Night2 与 Night1 最大不同：

```text
机器人更多
```

真实日志：

```text
Day1 night:
我方样本观察到约 70 robots

Day2 night:
约 90 robots
```

这属于实测现象，不是官方增长公式。

因此 V2 不能只判断：

```text
“Night1 活过了，所以原配置继续不动。”
```

Day2 必须增加：

```text
屏障 EHP
或
火力
```

至少一个维度。

---

# 42. Night2 成功标准

R261：

```text
station >= 1300
3/3 characters alive
3/3 weapons alive
```

如果没做到：

```text
分析重点必须是：

墙什么时候破？
哪个 controller 先进入机器人攻击范围？
哪门 ready weapon 从哪回合开始没人？
```

不要先分析：

```text
任务做少了
宝藏没拿
新闻没吃到
```

---

# 43. Day3：真正需要超越 712 的地方

712 对手：

```text
R261 station = 1410
R331 station = 1410
```

说明 Day3 白天没有继续损血。

但 Night3：

```text
1410 → 420
```

损失：

```text
990 HP
```

说明前两夜的配置到 Night3 已经不够。

所以 V2 在 Day3 必须进行第一次明显火力升级。

---

# 44. Day3 目标态

**[V2 TARGET]**

建议 Night3 开始前至少实现：

```text
方案 A：
rocket L3
rocket L2
rocket L1

或

方案 B：
rocket L3
rocket L1
rocket L1
+
station L2
+
更高墙体 EHP
```

优先由真实日志 A/B 测试决定。

第一轮建议先测试：

```text
L3/L2/L1
```

因为强对手 R331 已经：

```text
手持 WeaponUpgradeVoucher2
```

但没有在入夜前完成使用。

这很可能是一个值得修正的 timing 问题：

```text
升级券买到了
≠
防御能力已经形成
```

V2 必须保证：

```text
deadline 前完成购买 + 运送 + 使用
```

不能只把券买进背包。

---

# 45. Day3 墙目标

712 对手 R331：

```text
12 walls
```

V2 初始目标：

```text
12～14 walls
```

但不要平均升级。

使用：

```text
damage heatmap
```

对过去两夜受击最多的墙优先：

```text
升级
修复
补洞
```

不是：

```text
按墙 ID 顺序升级
```

---

# 46. Damage Heatmap

跨夜保存每座墙：

```text
health_at_night_start
health_at_night_end
destroyed_round
```

计算：

```text
absorbed_damage
```

得到：

```text
hot wall lanes
```

例如：

```text
front-center：
连续两夜吃掉 2000+ damage

rear wall：
0 damage
```

下一天资源应优先：

```text
hot lane
```

而不是 rear wall。

---

# 47. Day4～Day10：不再硬编码每天完全相同

进入 Day4 后改为：

```text
Readiness-driven strategy
```

每日白天根据上一夜结果判定模式。

---

# 48. 四种战略模式

## RECOVERY

触发：

```text
station < 60% maxHP
或
characters_alive < 3
或
weapon_count < 3
或
关键墙大面积被毁
```

目标：

```text
停止非必要扩张
先恢复防御闭环
```

---

## DEFENSE_GROWTH

触发：

```text
能活，但上一夜 damage 明显偏高
```

目标：

```text
升级主炮
补墙
升级热点墙
station 升级
```

---

## ECONOMY

触发：

```text
上一夜损伤很小
防御明显有余量
```

目标：

```text
更多采矿
任务
积累下一阶段升级资金
```

---

## PRE_NIGHT

触发：

```text
距离夜晚已经不足完成当前远途任务并安全返回
```

目标只有：

```text
所有人回岗位
完成已经买好的关键升级
停止新远途
```

---

# 49. 防御“目标资产”应动态升级

不要写：

```text
永远8墙
```

而是：

```text
上一夜 wall loss == 0 且 station damage 很低：
可以暂缓扩墙

上一夜前墙大量掉血：
增加 wall EHP

上一夜墙还很多但 station 大量掉血：
可能存在墙布局漏洞 / breach，需要改布局

上一夜 controller 死：
先修 controller safety，而不是继续堆墙数量
```

---

# 50. 长期武器目标

基于目前真实数据，V2 第一阶段继续采用：

```text
3 rocket
```

理由：

```text
1. 712 分样本就是 3 rocket
2. rocket 路径无遮挡
3. 对大量机器人有 3×3 AoE
4. L2/L3 多枚导弹
5. 长射程适合让 controller 躲在墙后
```

这不代表：

```text
railgun / gatling 永远不好
```

但在尚未复制强基准之前，不应该同时修改：

```text
布局
墙
武器种类
攻击算法
经济
```

变量太多会失去因果分析能力。

---

# 51. 长期升级建议

初始待测轨迹：

```text
Night1:
L2 / L1 / L1

Night2:
L2 / L1 / L1
或 L2 / L2 / L1

Night3:
至少 L3 / L2 / L1

Night4:
向 L3 / L2 / L2 推进

Night5+:
目标 L3 / L3 / L3
```

实际是否需要更快，由 Gate 数据决定。

---

# 52. 经济不再追求“金币最大化”

定义：

```text
Gold has no terminal value by itself.
```

比赛结束时手里：

```text
500 gold
```

但基地死了，没有意义。

每一天的钱应分成：

```text
mandatory defense budget
reserve
optional budget
```

---

# 53. BudgetPlan

示例：

```text
Day3：

gold = 280

mandatory:
WeaponUpgrade2 = 150
WeaponUpgrade1 = 100

reserve:
WallFixer = 20

optional:
10
```

一旦建立：

```text
EconomyPlanner
ConstructionPlanner
ProvisionPlanner
TreasurePlanner
```

都不能突破 mandatory reserve。

---

# 54. 不允许“低价值支出抢高价值资金”

例如当前常见风险：

```text
还差 100 gold 买主炮升级

但 planner 先：
买墙升级券
买 Medicine
买任务用品
```

V2 必须由 budget allocator 阻止。

判断不是：

```text
我现在买得起吗？
```

而是：

```text
我买完它以后，
还能完成本日 hard goal 吗？
```

---

# 55. Task Strategy

任务仍然非常重要。

因为它同时给：

```text
score
+
gold
```

而且 712 对手开局明显依靠了快速任务。

但任务不能破坏：

```text
night readiness
```

---

# 56. Task Deadline

每次准备接任务前先计算：

```text
travel_to_task
+
estimated_task_time
+
return_to_controller_slot
+
safety_margin
```

如果：

```text
剩余白天回合
<
上述预算
```

则：

```text
不接新任务
```

active task 除外，它有自己的超时机制。

---

# 57. 任务速度的战略意义

任务积分：

```text
完整完成
=
基础奖励
+
速度奖励
```

因此 pioneer 不应该：

```text
走两步任务
→ 被别的 planner 拉去买东西
→ 再回来继续任务
```

任务一旦开始：

```text
pioneer job = TASK_LOCK
```

直到：

```text
完成
失败
超时
或必须为了夜晚生存主动放弃
```

---

# 58. Treasure / News 的 V2 定位

当前阶段：

```text
News parsing：
保留

Treasure：
默认低优先

PvP summon：
默认低优先
```

因为当前核心失败发生在：

```text
第二夜
```

不是：

```text
没拿到宝藏
```

只有 Gate1 + Gate2 稳定通过后，再重新提高 treasure 优先级。

---

# 59. Night Evaluator

每一夜都必须输出一份结构化总结。

例如：

```text
[NightEvaluator]

night=2

station:
start=1475
end=1410
damage=65

characters:
start_alive=3
end_alive=3
first_loss_round=None

weapons:
start_alive=3
end_alive=3

walls:
start=10
end=10
destroyed=0
damage=...

combat:
ready_weapon_rounds=...
fired_rounds=...
ready_but_no_controller=...
ready_with_target_but_no_fire=...

controller:
10010 uptime=...
10011 uptime=...
10012 uptime=...

robots:
start_count=90
end_count=0/remaining
kills=...
```

---

# 60. 最关键的新指标：Weapon Uptime

定义：

```text
opportunity =
weapon cooldown == 0
AND
存在值得攻击的目标
```

如果同时：

```text
有 adjacent controller
并成功发 attack
```

记：

```text
fired_opportunity
```

核心指标：

```text
weapon_uptime
=
fired_opportunity
/
attack_opportunity
```

另一个关键指标：

```text
ready_without_controller_rounds
```

它直接对应 round2 的真实死亡链。

---

# 61. Controller Survival Metric

记录：

```text
first_damage_round
first_critical_round
death_round
distance_to_wall_front
distance_to_station
weapon_assignment
```

如果人物死：

不能只说：

```text
worker 死了
```

必须知道：

```text
为什么机器人能够摸到这个炮手？
```

---

# 62. Defense Damage Attribution

每夜后把 damage 分成：

```text
wall_damage
weapon_damage
controller_damage
station_damage
```

理想防线应该满足：

```text
大量伤害被墙吸收
↓
机器人在墙前被 rocket 慢慢消灭
↓
controller 几乎不受伤
↓
station 几乎不受伤
```

这就是 712 样本前两夜呈现出的结构。

---

# 63. Match Analyzer 必须成为第一等工具

下一阶段优先级：

```text
不是先改策略代码
而是先把 Analyzer 做好
```

输入：

```text
ally log
enemy log
```

输出：

```text
timeline.md
summary.json
```

---

# 64. Timeline checkpoint

默认采：

```text
R1
R10
R20
R30
R40
R50
R60
R70
R71

之后每10回合

R130
R131
...
```

重大事件额外插入：

```text
任务完成
weapon build
weapon upgrade
wall build
wall upgrade
角色死亡
墙死亡
武器死亡
station 大幅掉血
```

---

# 65. 对手模仿不应该是“抄动作”

我们无法保证：

```text
矿位置
任务内容
机器人路径
```

每局一样。

因此模仿的是：

```text
strategic state trajectory
```

例如：

```text
R71：
3 rocket
1个L2
8 wall
3角色就位
```

而不是：

```text
R23 必须在 (12,22) build
```

位置模板可以优先使用，但状态目标比具体回合动作更重要。

---

# 66. V2 第一阶段开发验收标准

第一阶段实现完成，不要求：

```text
宝藏最优
新闻套利最优
PvP最优
1300回合
```

只要求：

```text
A. DayPlan 持久存在
B. 角色有长期 job
C. 有 hard deadline
D. 有预算锁
E. controller 夜间固定
F. Day1 能主动追目标态
G. Night evaluator 能输出完整指标
H. 不破坏现有协议安全
```

---

# 67. V2 第二阶段验收

实机：

```text
连续多局 Gate1 PASS
```

才进入 Gate2 调优。

目标：

```text
R131:
station >= 1400
3 characters
3 weapons
>=8 walls
```

如果失败：

只分析：

```text
Day1 + Night1
```

---

# 68. V2 第三阶段

Gate1 稳定后：

```text
Day2 repair/growth
+
Night2
```

目标：

```text
R261:
station >= 1300
3 characters
3 weapons
>=9 walls
```

---

# 69. V2 第四阶段

Gate2 稳定后才开始：

```text
Night3 增强
```

主要实验：

```text
A:
L3/L2/L1

B:
L3/L1/L1 + Station L2

C:
L2/L2/L1 + 更高墙体EHP

D:
更早 L3 + 少两面墙
```

使用真实 Versus A/B 比较：

```text
station_damage
controller_survival
weapon_uptime
wall_damage
```

而不是：

```text
“感觉这个方案更聪明”
```

---

# 70. 不要一次改变多个战略变量

错误做法：

```text
换武器布局
+
改炮种
+
改升级
+
改墙数量
+
改攻击评分
+
改任务优先级

打一局
```

即使分数提高：

```text
也不知道为什么。
```

正确实验：

```text
Baseline B0

B1:
只改 controller persistence

B2:
B1 + 8墙 benchmark

B3:
B2 + attack threat score

B4:
B3 + Day2 repair plan
```

逐层验证。

---

# 71. 版本必须带战略假设

以后每次 meaningful change 必须记录：

```text
Hypothesis:
Night2 失败主要源于 controller 暴露和 ready weapon 无人。

Change:
controller 固定 slot，除死亡/武器毁坏不换岗。

Expected metric:
ready_without_controller_rounds ↓
controller_death_round 延后
station_damage ↓

Result:
...
```

没有 hypothesis 的“继续优化代码”：

```text
禁止。
```

---

# 72. 建议新增文档

```text
docs/STRATEGY_V2.md
docs/MATCH_METRICS.md
docs/EXPERIMENTS.md
```

其中：

```text
STRATEGY_V2.md：
战略本身

MATCH_METRICS.md：
统一指标定义

EXPERIMENTS.md：
每次实机 A/B 的假设和结果
```

不要把这些继续堆进：

```text
STATUS.md
```

STATUS 只保留当前结论。

---

# 73. 推荐新增代码概念

如果仍维持单 `main3.py`，也按下面逻辑分区：

```text
StrategicState
DailyPlan
StrategicPlanner
RoleJob
BudgetPlan
DefenseReadiness
ControllerAssignment
NightCombatOptimizer
NightEvaluator
```

它们应位于原有 tactical planner 的上面。

---

# 74. 新 `plan_turn()` 应该长什么样

概念上：

```python
def plan_turn(world, memory, rules=None):
    validator = ActionValidator(world, memory, rules)

    strategy = StrategicPlanner(world, memory, rules)

    strategy.observe_previous_result()
    strategy.update_or_replan()

    if strategy.phase == "NIGHT":
        actions = strategy.execute_night_turn(validator)
    else:
        actions = strategy.execute_day_turn(validator)

    actions = strategy.resolve_conflicts(actions)
    actions = validator.validate(actions)

    strategy.record_decisions(actions)

    return build_response(actions)
```

重点不是具体 API。

重点是：

```text
顶层只允许 StrategicPlanner 决定优先级。
```

不再：

```text
十几个 planner 按源代码顺序抢资源。
```

---

# 75. Tactical Planner 的新职责

`EconomyPlanner`：

```text
不再决定“要不要采矿”
只决定：
给定“需要赚 X gold / 拿 Y stone”后，
怎么完成最省回合。
```

`ConstructionPlanner`：

```text
不再决定今天想造什么
只决定：
给定 desired layout 后，
哪个 worker 怎么去建。
```

`TaskPlanner`：

```text
不再自己决定什么时候优先于防御
只执行 StrategicPlanner 分配给 pioneer 的 TASK job。
```

`DefensePlanner`：

```text
白天负责执行 repair/build/upgrade 任务
夜间只负责实际 combat tactical optimization
```

---

# 76. Strategy 与 Tactic 的边界

例子：

StrategicPlanner：

```text
Day2：
必须新增2墙
修复3面热点墙
不要升级station
需要赚100 gold
R194以前全部回防
```

Tactical：

```text
哪个工人去哪个矿
走哪条路径
先修哪一面可达墙
具体哪回合买券
```

这才是正确分层。

---

# 77. 为什么这比继续用 GPT“走一步看一步”强

因为 GPT/Codex 的短期代码生成倾向会自然产生：

```text
发现局部问题
→ 加 if
→ 加优先级
→ 加例外
```

但 `DailyPlan` 强制代码始终回答：

```text
我现在这一步服务于哪一个长期目标？
```

如果某动作：

```text
不推进 hard goal
也不是 emergency
```

就不应该执行。

---

# 78. 第一版战略评分不需要复杂

白天 job 候选可以按：

```text
hard_goal_deficit_reduction
/
expected_round_cost
```

排序。

例如：

```text
差 1 门炮：
build weapon
deficit reduction 很高

差 8 stone：
collect stone
deficit reduction 很高

已经有 8 wall：
第 9 块 stone 优先级下降

Night1 已满足目标：
继续赚 gold 才提高
```

---

# 79. Readiness Score 只用于诊断，不替代硬约束

可以打印：

```text
DefenseReadiness:
weapon_count
weapon_levels
wall_count
wall_total_hp
station_hp
controller_ready_count
medicine_count
return_slack
```

不要简单合成成一个分数后：

```text
score > 60 就算安全
```

硬条件应该独立存在。

---

# 80. PRE_NIGHT 是必须存在的显式状态

当前代码只是很多地方分别计算：

```text
还能不能赶回来
```

V2 要统一成：

```text
PRE_NIGHT
```

一旦进入：

```text
允许：
return
finish upgrade already in bag
finish nearby wall
heal

禁止：
new mine trip
new vendor trip
new optional shopping
new treasure trip
new long task
```

---

# 81. 夜晚不允许普通经济 planner 决策

虽然规则未必禁止：

```text
sell
buy
use
remove
```

夜晚使用。

但 V2 战略层默认：

```text
所有健康 controller 都属于 combat。
```

只有：

```text
武器 cooldown 回合的原地 use
```

或真正 emergency 才允许占用人物动作。

不在夜间：

```text
跑商店
跑小贩
采矿
```

除非未来实验证明确有价值。

---

# 82. 角色死亡是“生产能力永久损失”，不能只当掉 HP

角色死亡后要等待下一日复活窗口。

因此一个 worker 死亡的损失包括：

```text
当前夜晚：
少一门炮 controller

下一白天：
少采矿
少建墙
少修墙
少升级运输
```

所以 controller 生存价值应显著高于普通几百点即时伤害。

---

# 83. 墙的战略意义

墙有三个作用：

```text
1. 吸收机器人攻击
2. 强制机器人停下来打墙
3. 给 rocket 创造额外 cooldown 周期
```

例如一面 L1 wall：

```text
1000 HP
```

面对大量机器人时，它不是单纯：

```text
+1000 总防御血量
```

而是：

```text
可能额外争取若干轮全体 rocket 开火时间
```

这解释了为什么：

```text
8面合理位置的墙
```

可能远比：

```text
把 station 从1500升到3000
```

更有效。

---

# 84. 墙不应平均铺

优先：

```text
机器人主进攻方向
+
已经被历史证明是 hot lane 的位置
```

后侧保持：

```text
经济出口
炮手安全区
```

只有未来日志证明机器人经常绕后时才扩后墙。

---

# 85. 不要过早追求20墙全封闭

全环：

```text
可能阻断己方角色出入
```

而：

```text
任务
vendor
shop
矿
```

都需要外出。

V2 中期建议：

```text
front screen
→ extended front screen
→ side reinforcement
```

而不是：

```text
直接20墙封圈
```

---

# 86. 新的日志必须记录“为什么做这个动作”

为了后续模型能分析战略，每个动作附带内部 reason：

```text
[StrategicPlanner] role=20010 job=FORTIFY target_wall_count=8
[StrategicPlanner] role=20012 job=BUILD_WEAPON missing=1
[StrategicPlanner] role=20011 job=TASK deadline_round=61
[NightCombat] weapon=20040 target=(...) reason=highest_future_threat
```

不要只记录：

```text
action=move
```

---

# 87. 不要把所有日志都刷出来

只保留：

```text
计划生成
计划切换
重大偏离
deadline
build/upgrade完成
夜晚开始
夜晚结束
人物死亡
建筑死亡
关键 fire opportunity 丢失
```

热路径普通 move 可以降低日志级别。

日志格式继续遵守：

```text
[函数名] 日志信息
```

---

# 88. 本地测试体系也必须改变

当前 141 tests 主要证明：

```text
代码正确性
协议
状态
路径
长期不崩
```

V2 还需要：

```text
战略测试
```

---

# 89. 战略单元测试

例如：

```text
输入：
Day1 R40
已有3炮
墙只有3
worker空闲
有stone矿
gold很多

期望：
战略层仍优先完成8墙
而不是继续挖copper
```

再例如：

```text
Day1 R64
worker离炮位5步
附近有高价值copper

期望：
回防
不采矿
```

---

# 90. Controller 测试

```text
Night
3 weapons
3 controllers
weapon A cooldown=2

期望：
A controller 不因为 A cooldown
被移动去另一个weapon，
除非 assignment 已失效。
```

---

# 91. Budget 测试

```text
gold=110
本日 hard goal:
WeaponUpgradeVoucher1 = 100

Medicine price=10

人物满血

期望：
不买 Medicine
保留 100
```

---

# 92. Gate Replay 测试

本地不能模拟真实战斗。

但可以测试：

```text
给定一系列 observation，
StrategicPlanner 是否持续追正确目标。
```

例如：

```text
Day1 70 rounds observation replay
```

验证：

```text
不会忘记8墙目标
不会把wall_builder抢走
不会日落前继续跑矿
不会买掉升级预算
```

不能声称：

```text
因此一定活过第一夜
```

真正 Gate 只能用实机验证。

---

# 93. 建立最小的经验机器人模型

在有真实日志以后，可以学习：

```text
robot_pos(t)
→
robot_pos(t+1)
```

不需要机器学习。

统计：

```text
每类机器人
每种相对位置
下一步方向
遇墙后的行为
目标切换
```

先建立：

```text
EmpiricalRobotModel
```

---

# 94. 战斗模拟器的第一版只做“近似”

不追求复制判题器。

第一版可以只模拟：

```text
robot 每回合向目标核心区域移动1格
遇墙停止并攻击
进入攻击距离后造成 attackPower
rocket 根据 cooldown 开火
```

然后用真实日志不断修正。

目的不是：

```text
100% 复现比赛
```

而是让策略可以回答：

```text
方案A 和 方案B 哪个大概率更好？
```

---

# 95. Simulator 的用途

用于离线比较：

```text
8墙 vs 10墙
L3/L1/L1 vs L2/L2/L1
station L2 vs weapon L3
不同 rocket position
不同 controller slot
不同 target scoring
```

没有 simulator 时，每个参数都只能：

```text
打一局真实比赛
```

开发效率极低。

---

# 96. 参数搜索顺序

先手工定义小搜索空间：

```text
wall target:
8 / 10 / 12 / 14

first weapon upgrade:
L2

Night3:
L3/L1/L1
L2/L2/L1
L3/L2/L1

base upgrade threshold:
不同HP比例

pre-night safety margin:
4 / 6 / 8
```

先 grid search。

不需要神经网络。

---

# 97. 当前应暂时降级的功能

直到 Gate2 稳定：

```text
Treasure execution
主动购买 PvP summon
复杂新闻套利
非必要炸弹采购
过量 Medicine 囤积
探索性武器组合
```

不是删代码。

只是：

```text
StrategicPlanner 默认不给预算和角色。
```

---

# 98. 当前应该保留的 V1 基础设施

不要推倒重写：

```text
HTTP server
safe fallback
strict response
World
Phase
GameMemory
BFS/path
MoveReservations
ActionValidator
Task LLM async plumbing
executeCmd async plumbing
新闻记忆
treasure memory
```

这些仍然有价值。

真正需要重构：

```text
plan_turn 顶层
建设决策
预算分配
角色任务分配
夜间 controller policy
combat objective
```

---

# 99. 第一轮实现建议

严格按顺序：

```text
Step 1
新增 StrategicPlanner / DailyPlan / RoleJob
不改 combat 算法

Step 2
Day1 benchmark：
3 rocket
8 walls
L2/L1/L1
deadline回防

Step 3
persistent controller assignment

Step 4
NightEvaluator / MatchAnalyzer

Step 5
实际比赛验证 Gate1

Step 6
只有 Gate1 稳定后
实现 Day2 recovery + Gate2

Step 7
再改 combat threat score

Step 8
再做 Night3 火力升级实验
```

---

# 100. 为什么不应该第一步就重写 combat

因为现在无法区分：

```text
是 attack target 选差了
```

还是：

```text
炮手根本没活着
武器根本没开火
墙根本没挡住
```

先解决：

```text
结构性生存
```

再优化：

```text
每一炮怎么打
```

---

# 101. 最重要的实验：先复制 712 的前两夜

V2 的第一个里程碑应明确写成：

```text
MILESTONE:
复现 opponent_712 的核心防御状态轨迹
而不是复现它的代码。
```

检查点：

```text
R71
R131
R201
R261
```

我方与 712 对手并列表格。

---

# 102. 推荐实验表

```text
Checkpoint | metric              | ours | benchmark
----------------------------------------------------
R71        | weapons             |      | L2/L1/L1
R71        | walls               |      | 8
R71        | alive actors        |      | 3
R131       | station HP          |      | 1475
R131       | alive actors        |      | 3
R201       | walls               |      | 10
R201       | alive actors        |      | 3
R261       | station HP          |      | 1410
R261       | alive actors        |      | 3
```

只要前面一列明显落后：

```text
先修前面的阶段。
```

---

# 103. 成功后的下一步

如果 V2 可以稳定：

```text
R261 station > 1300
3角色全活
```

说明已经完成从：

```text
React Agent
```

到：

```text
Plan-based Agent
```

的第一步。

再往后才值得投入：

```text
短视野 MPC
仿真搜索
新闻经济预测
宝藏推理
PvP 博弈
```

---

# 104. 给 Codex / GPT 的实施指令

下面这段可以直接复制给新的 Codex session：

```text
当前暂停继续做零散策略 patch。

请先完整读取：
- AGENTS.md
- AI Spec/未来战争_v1.0_比赛全貌_开发整合版.md
- docs/STATUS.md
- docs/DESIGN.md
- docs/VERSUS_ROUND2_ANALYSIS.md
- docs/STRATEGY_V2.md
- src/main3.py
- 相关 tests
- log/Versus/round2/

目标发生变化：

当前不以“功能覆盖更多”为目标，
也不允许继续通过固定优先级 + 局部 if 逐回合补策略。

本阶段目标是把现有 Agent 从 reactive planner 重构为：
StrategicPlanner
→ persistent DailyPlan
→ RoleJob
→ BudgetPlan
→ hard deadline
→ tactical execution
→ ActionValidator

优先级：

1. 保留现有 HTTP、协议、安全校验、World、Phase、GameMemory、
   路径、ActionValidator、任务异步接口等已经验证的基础设施。

2. 不要首先重写全部代码。
   重构重点是 plan_turn 顶层决策层。

3. 第一战略 benchmark 不是1300回合，
   而是复制 enemy_BlueSide_712 前两夜的状态轨迹：

   R71：
   - 3 rocket
   - L2/L1/L1
   - >=8 wall
   - 3 actors alive and home

   R131：
   - station >=1400
   - 3 actors alive
   - 3 weapons alive

   R201：
   - >=10 wall
   - 3 actors alive

   R261：
   - station >=1300
   - 3 actors alive
   - 3 weapons alive

4. Day1 必须形成持久计划：
   pioneer 优先任务；
   一个 worker 负责三炮/关键升级；
   一个 worker 批量取石完成8墙；
   日落前进入 PRE_NIGHT，停止远程经济活动并固定三名炮手。

5. controller assignment 必须跨回合持久。
   夜晚不能每回合因为 cooldown 重新把人物分给其他炮。
   controller 应有固定 safe slot。

6. 资源必须先由 StrategicPlanner 做预算。
   任何低优支出不得消耗本日 hard defense goal 的资金。
   Day1 默认取消“每个炮手主动囤两瓶Medicine”的策略，
   除非真实伤势触发 emergency。

7. 建造第一阶段优先复现712分对手的实测布局。
   Challenger canonical 坐标见 STRATEGY_V2.md；
   Defender 使用180°镜像，并始终通过合法性、建造区、
   occupied 和路径检查。

8. 先实现 NightEvaluator / MatchAnalyzer，
   至少统计：
   station damage
   actor death round
   weapon death
   wall damage
   ready weapon rounds
   ready_without_controller_rounds
   attack opportunities
   fired opportunities
   controller uptime
   gold at night start
   defense assets at R71/R131/R201/R261

9. 当前不要主动增强 Treasure、PvP summon、复杂新闻套利。
   保留代码，但 Gate2 稳定之前不给高优预算。

10. 当前不要上强化学习。
    不要声称本地 observation replay 证明生存。
    真正 Gate 需要实机日志验证。

11. 每次策略修改必须在 docs/EXPERIMENTS.md 写：
    Hypothesis
    Change
    Expected Metric
    Actual Result

12. 日志继续使用：
    [函数名] 日志信息

先只输出：
- 对当前代码的重构计划
- 新数据结构设计
- 哪些旧逻辑保留
- 哪些旧逻辑需要替换
- 新测试计划

此时不要直接大规模修改代码。

等计划确认后再进入实现。
```

---

# 105. 最终判断

当前项目不是：

```text
“6low 代码写得不够多”
```

而是：

```text
“程序还没有一个真正对1300回合负责的上层决策者”
```

V1 的结构是：

```text
很多聪明的小模块
+
没有统一战略
```

V2 要变成：

```text
一个明确的长期战略
↓
把今天拆成资源和角色任务
↓
各 tactical planner 只负责执行
↓
每夜用指标验证
↓
只有真实失败才能触发下一轮战略实验
```

当前最值得追求的不是立即做到：

```text
1300
```

而是按顺序做到：

```text
先稳定 R131
→ 再稳定 R261
→ 再超过对手的 R391
→ 再推 R521
→ 最终延伸到 R1300
```

从这一刻开始：

```text
“比赛分数”
```

不应再是唯一调试反馈。

真正的开发反馈应是：

```text
哪一个 Survival Gate 失败？
为什么失败？
哪个核心指标先恶化？
哪一个战略假设被实机证伪？
```

做到这一点，开发才会从：

```text
模型不断猜、不断补 if
```

变成：

```text
可测量、可复现、可迭代的策略工程。
```
