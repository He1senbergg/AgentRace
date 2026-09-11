"""AgentRace economy; mechanically extracted from frozen V2.2."""
from .model import (
    MINERALS,
    WEAPONS,
    inventory,
    nonnegative_int,
    positive_health
)


class EconomyPlanner:
    def __init__(self, validator):
        self.v = validator
        self.world = validator.world

    def travel(self, actor, cells):
        role = self.world.characters[actor]
        route = self.world.path(role["cell"], self.world.adjacent_goals(cells, role["cell"]), self.v.targets)
        return bool(route and len(route) > 1 and self.v.add(actor, {
            "action": "move", "targetPos": [{"x": route[1][0], "y": route[1][1]}]}))

    def purchase(self, actor, name, count=1):
        role = self.world.characters.get(actor)
        bag = inventory(role) if role else None
        price = self.v.prices.get(name)
        if bag is None or price is None or type(count) is not int or count <= 0:
            return False
        missing = count - bag[name]
        capacity = role.get("backPackCapability", 100 if role["roleType"] == "worker" else 40)
        if (missing <= 0 or price * missing > self.v.gold or not nonnegative_int(capacity)
                or sum(bag.values()) + missing > capacity):
            return False
        if self.v.add(actor, {"action": "buy", "name": name, "num": missing}):
            return True
        return self.travel(actor, self.world.zones["weaponShop"])

    def return_steps(self, start):
        weapons = {r["cell"] for r in self.world.roles.values()
                   if isinstance(r.get("roleType"), str) and r["roleType"] in WEAPONS and positive_health(r.get("health"))}
        if not weapons:
            return 0
        route = self.world.path(start, self.world.adjacent_goals(weapons, start), self.v.targets)
        return len(route) - 1 if route else None

    def cash_in(self, role, force=False):
        actor = role["id"]
        if actor in self.v.busy:
            return False
        bag = inventory(role)
        if bag is None:
            return False
        minerals = sorted((m for m in MINERALS if bag[m] and self.v.vendor.get(m, 0) > 0),
                          key=lambda m: (-bag[m] * self.v.vendor[m], m))
        if not minerals:
            return False
        route = self.world.path(role["cell"], self.world.adjacent_goals(
            self.world.zones["vendor"], role["cell"]), self.v.targets)
        if not route:
            return False
        phase = self.v.memory.phase
        back = self.return_steps(route[-1])
        duration = len(route) - 1 + len(minerals) + (back if back is not None else 0) + 3
        if phase and (not phase.is_day or back is None or duration > 71 - phase.round_in_day):
            return False
        count = sum(bag[m] for m in minerals)
        due = phase and duration + 8 >= 71 - phase.round_in_day
        capacity = role.get("backPackCapability", 100)
        full = nonnegative_int(capacity) and sum(bag.values()) >= capacity
        batch = min(20, max(4, 2 * (len(route) - 1)))
        if len(route) > 1 and count < batch and not due and not full and not force:
            return False
        name = minerals[0]
        if self.v.add(actor, {"action": "sell", "name": name, "num": bag[name]}):
            return True
        return self.travel(actor, self.world.zones["vendor"])

    def liquidate(self):
        phase = self.v.memory.phase
        if phase and phase.is_day:
            for role in sorted(self.world.characters.values(), key=lambda r: r["id"]):
                if self.v.memory.wall_builder and role['id'] == self.v.memory.wall_builder['actor']:
                    continue
                if role["roleType"] == "worker":
                    self.cash_in(role)

    def workers(self):
        for actor, role in sorted(self.world.characters.items()):
            if self.v.memory.wall_builder and actor == self.v.memory.wall_builder['actor']:
                continue
            if actor in self.v.busy or role["roleType"] != "worker":
                continue
            bag = inventory(role)
            capacity = role.get("backPackCapability", 100)
            if bag is None or not nonnegative_int(capacity):
                continue
            minerals = [m for m in MINERALS if bag[m] and m in self.v.vendor]
            phase = self.v.memory.phase
            if self.cash_in(role):
                continue
            if sum(bag.values()) >= capacity:
                continue
            options = []
            for mineral in sorted(MINERALS):
                if phase and any(event["resource"] == mineral and event["harvestable"] is False
                                 and event["start_day"] <= phase.day <= event["end_day"]
                                 for event in self.v.memory.resource_events):
                    continue
                price = self.v.vendor.get(mineral)
                if price is None or price <= 0:
                    continue
                for cell in sorted(self.world.zones[mineral]):
                    route = self.world.path(role["cell"], self.world.adjacent_goals({cell}, role["cell"]), self.v.targets)
                    if not route:
                        continue
                    delivery = self.world.path(route[-1], self.world.adjacent_goals(
                        self.world.zones["vendor"], route[-1]), self.v.targets)
                    if self.world.zones["vendor"] and not delivery:
                        continue
                    transport = len(delivery) - 1 if delivery else 0
                    back = self.return_steps(delivery[-1]) if delivery else 0
                    batch = min(10, capacity - sum(bag.values()))
                    if phase and phase.is_day and delivery:
                        budget = 71 - phase.round_in_day - (len(route) - 1 + transport + len(minerals) + 1 + (back or 0) + 3)
                        if back is None or budget < 1:
                            continue
                        batch = min(batch, budget)
                    score = price * batch / (len(route) - 1 + batch + transport + 1)
                    options.append((score, mineral, cell, route))
            if not options:
                self.v.memory.worker_mines.pop(actor, None)
                self.cash_in(role, force=True)
                continue
            previous = self.v.memory.worker_mines.get(actor)
            retained = [o for o in options if (o[1], o[2]) == previous]
            best_score = max(o[0] for o in options)
            retained = [o for o in retained if o[0] >= best_score * 0.8]
            _, mineral, cell, route = max(retained or options, key=lambda choice: (choice[0], choice[1], choice[2]))
            self.v.memory.worker_mines[actor] = (mineral, cell)
            target = cell if len(route) == 1 else route[1]
            self.v.add(actor, {"action": "collect" if len(route) == 1 else "move",
                               "targetPos": [{"x": target[0], "y": target[1]}]})
