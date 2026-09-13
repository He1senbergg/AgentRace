# V3 关键代码阅读与逐行讲解

完整策略位于 `src/agentrace/survival.py`。下面解释实际交付代码中的关键函数，不要求你逐行手工粘贴；部署时直接使用完整 src。

## 1. 参数和状态如何流动

`GameSession.handle(data)` 先把请求转换为 World 和观察增量 delta，在副本 memory 上运行策略，再经最终动作校验、序列化与缓存后提交。SurvivalPlanner 中 `world` 是本回合事实，`memory` 是跨回合状态，`delta` 是前后观察比较，`rules` 是已有规则配置。`jobs` 是工作计划，不是裁判执行成功证明；背包和建筑等级必须从 world 重新确认。

## 2. `fits`：实际源码逐行

文件行号：192–204。

```python
    def fits(self, actor, visits, margin=4):
        """Trips include EVERY action, travel and an assigned return; no expected income."""
        if not self.phase or not self.phase.is_day:
            return False
        cursor = self.characters[actor]['cell']
        cost = 0
        for cells, actions in visits:
            route = self.path(cursor, cells, True, True)
            if not route:
                return False
            cursor, cost = (route[-1], cost + len(route) - 1 + actions)
        back = self.return_cost(actor, cursor)
        return back is not None and cost + back + margin <= 71 - self.phase.round_in_day
```

| 源码行号 | 功能、参数或效果 |
|---:|---|
| 192 | 定义方法。actor 是当前人物 ID；visits 是按执行顺序排列的“目标格集合、动作回合数”；margin 默认额外留 4 回合缓冲。 |
| 193 | 文档字符串：估算包括全部动作、各段移动以及返回分配炮位；不把预计收入当现款。 |
| 194 | 没有有效日夜信息，或当前已经是夜晚，不接新的白天往返任务。 |
| 195 | 返回 False，表示不能安全安排这趟工作。 |
| 196 | 从角色本回合观察到的位置出发，而不是从计划中的未来位置出发。 |
| 197 | 累计回合成本从 0 开始。 |
| 198 | 按行程顺序处理各目的地；cells 是目标格集合，actions 是抵达后需要的动作数。 |
| 199 | 调用静态几何寻路；第一个 True 表示到目标邻格即可，第二个 True 表示用静态障碍做行程预测。 |
| 200 | 某一段没有路径，整趟不能成立。 |
| 201 | 直接返回 False，而不是继续拿不存在的路径估算。 |
| 202 | 把下一段起点更新到路径末尾；路径点数减 1 是移动步数，再加采集/买入/使用等动作回合。 |
| 203 | 从最后一个工作点估算返回自己分配站位的成本。 |
| 204 | 只有回程可达，且工作＋回程＋缓冲不超过白天剩余动作回合才返回 True。回合 1–70 为白天，所以当前仍可执行的回合数为 71-round_in_day。 |

实例：R50 从人物位置去商店需要 4 步，买券 1 步，再去炮旁 5 步，使用 1 步，回自己的站位 2 步，额外缓冲 4 步，总成本 17；R50 仍有 21 个白天动作回合，因此可安排。R58 只剩 13 回合，同一行程应拒绝。这个判断不包含尚未发生的任务奖励。

## 3. `return_home`：实际源码逐行

文件行号：210–217。

```python
    def return_home(self, actor):
        slot = self.return_slots.get(actor)
        if slot is not None:
            self.move(actor, {slot}, 'return_to_battery', adjacent=False)
        elif self.base:
            self.move(actor, station_cells(self.base['cell']), 'return_to_base')
        else:
            self.note(actor, 'base_missing')
```

| 源码行号 | 功能、参数或效果 |
|---:|---|
| 210 | 定义人物返位方法；actor 是人物 ID，不是武器 ID。 |
| 211 | 查询该人物本轮被联合分配到的唯一目标站位。 |
| 212 | 存在专属站位时优先使用它。 |
| 213 | 移动到这个精确格，adjacent=False 表示不能只到它旁边就当完成。日志原因是 return_to_battery。 |
| 214 | 没有分配炮位、但基地仍存在时使用基地周围作保守退路。 |
| 215 | 把基地完整 2×2 足迹作为目标，默认移动到其邻格，而不是进入建筑格。 |
| 216 | 连基地都没有时，不编造返程目标。 |
| 217 | 记录 base_missing 原因，不发出非法移动。 |

实例：先锋位于 `(9,23)`，此格实际上分给一个返防工人；先锋自己的格为 `(7,21)`。当没有任务/采购/卖矿可做时，立即调用此方法离开，避免“别人等你让位，你等自己的截止时间”的假性堵路。

## 4. 批量建墙的关键状态

`build_walls(actor)` 的参数 actor 是工人 ID；本轮读到的 `bag` 是真实背包。`missing` 表示目标墙数减目前墙数，`stones` 是每面成本，`have=bag['stone']//stones` 是当前可建几面。

`stage='quarry'` 表示先备料，`stage='build'` 表示已进入连续建设。`quota=min(missing, job.get('quota', min(8, missing)))` 把本次配额限制在未完成墙数和已有固定批量之内；不会每次采一块就把“当前已有数量”重新解释成足额。`have >= quota` 才切到建造；已经处于 build 且还有石头时继续建，石头耗尽才回 quarry。

例如缺 8 面墙、石头单价成本为 1、背包初始 0：先连续采到 8 块，再逐个建。缺口后来只剩 3 面时，配额降到 3，避免过量采料。若时间不够采满，`fits()` 会筛出可以完成返程的小批量；并非强制不顾日落采满八块。

## 5. 其他函数定位

| 函数 | 作用 |
|---|---|
| `observe`，第 47 行 | 从实际观察清理死亡 owner、检测连续无进展移动，记录真实资产变化 |
| `assign_return_slots`，第 144 行 | 联合枚举人物、武器、独立站位，避免每座炮各自贪心抢同一个人 |
| `construction_safe`，第 219 行 | 在拟建建筑加入后检查友军通路和炮旁可达性 |
| `service_candidates`，第 346 行 | 由当前建筑等级生成真实升级/维护缺口；非紧急墙升级后置 |
| `held_delivery`，第 377 行 | 只使用真实背包道具，目标消失后重选匹配对象 |
| `procure`，第 409 行 | 检查跨角色持券和本回合买单，资金与全程预算成立才采购 |
| `medicine`，第 452 行 | 必要时自用药、顺路备药，但不吞掉已够升级的钱 |
| `income`，第 510 行 | 在工作窗口内采矿出售，缺钱不会只站着等 |
| `night`，第 554 行 | 控制人唯一匹配、攻击后更新预测剩余血量、再支援与归位 |
| `run`，第 599 行 | 安排白天/夜晚顺序；空闲先锋无事可做时立即返位 |
| `report`，第 667 行 | 输出可复核状态与每个人未行动/行动的原因 |

完整函数细节见源码；上述行为是否能提高正式对战成绩仍不能由单元测试单独保证。
