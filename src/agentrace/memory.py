"""AgentRace memory; mechanically extracted from frozen V2.2."""
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from .model import (
    Phase,
    nonnegative_int,
    object_list
)


@dataclass(frozen=True)
class ObservationDelta:
    """One observation boundary, produced only by GameMemory.observe."""
    round_no: int
    phase: object
    continuous: bool
    gold: int
    task_active: bool
    feedback: dict


@dataclass
class RoleJob:
    owner: str
    job_type: str
    target: object
    phase: str
    priority: int
    created_round: int
    deadline: int
    progress: int = 0
    completion_condition: str = "observed_target"
    abort_condition: str = "dead_or_unreachable_or_deadline"


@dataclass(frozen=True)
class ControllerAssignment:
    controller: str
    safe_slot: tuple


@dataclass
class Day1Plan:
    day: int = 1
    mode: str = "DAY_NORMAL"
    jobs: dict = field(default_factory=dict)
    controllers: dict = field(default_factory=dict)
    budget: object = None
    benchmark_wall_target: int = 8
    execution_wall_target: int = 8
    wall_hp_target: int = 8000
    weapon_level_target: tuple = (2, 1, 1)
    reasons: list = field(default_factory=list)

    @property
    def unmet_wall_target(self):
        return max(0, self.benchmark_wall_target - self.execution_wall_target)


@dataclass
class StrategicState:
    plan: Day1Plan = field(default_factory=Day1Plan)
    last_round: object = None
    metrics: dict = field(default_factory=dict)
    night_key: object = None
    night_start_walls: object = None
    last_wall_hp: dict = field(default_factory=dict)
    wall_damage: dict = field(default_factory=dict)
    previous_night_walls: dict = field(default_factory=dict)
    day_start: dict = field(default_factory=dict)


@dataclass
class GameMemory:
    identity: tuple
    origin: object = None
    last_round: object = None
    phase: object = None
    news: list = field(default_factory=list)
    enemy_history: dict = field(default_factory=dict)
    previous_actions: dict = field(default_factory=dict)
    feedback: dict = field(default_factory=dict)

    summon_attempts: int = 0
    summon_day_known: bool = False
    llm_calls_today: int = 0
    llm_day_known: bool = False
    task: object = None
    accepted_task: object = None
    worker_mines: dict = field(default_factory=dict)
    upgrade_trip: object = None
    wall_builder: object = None
    task_experience: list = field(default_factory=list)
    resource_events: list = field(default_factory=list)
    news_pending: object = None
    news_analyzed: object = None
    treasure: object = None
    treasure_digest: object = None
    treasure_pending: object = None
    treasure_attempts: set = field(default_factory=set)
    treasure_terminal: str = ""
    treasure_result: object = None
    strategic: StrategicState = field(default_factory=StrategicState)
    task_diagnostics: dict = field(default_factory=dict)
    observed_task_active: object = None
    observed_gold: object = None

    def observe(self, world, round_no):
        if round_no == 0:
            self.origin = 0
        elif self.origin is None and self.last_round is None and round_no == 1:
            # Self/1.log confirms the platform's initial observation is round 1.
            self.origin = 1
        self.phase = Phase.from_round(round_no, self.origin) if self.origin is not None else None
        if self.phase is not None and self.phase.round_in_day == 1:
            self.summon_attempts = 0
            self.summon_day_known = True
            self.llm_calls_today = 0
            self.llm_day_known = True
        elif self.last_round is not None and round_no != self.last_round + 1:
            self.summon_day_known = False
            self.llm_day_known = False
        if (not (self.phase is not None and self.phase.round_in_day == 1)
                and any(type(error.get("errorCode")) is int and error["errorCode"] == 5
                        for error in object_list(world.data.get("errors")))):
            self.llm_calls_today = 3
        # These fields describe the previous platform round, not necessarily
        # the last request seen by this process. Never associate across a gap.
        continuous = self.last_round is not None and round_no == self.last_round + 1
        active = isinstance(world.data.get('phaseTask'), str) and bool(world.data['phaseTask'])
        self.task_diagnostics = {
            'task_started': round_no if active and self.observed_task_active is False and continuous else None,
            'task_end': round_no if not active and self.observed_task_active is True and continuous else None,
            'task_error_codes': [e['errorCode'] for e in object_list(world.data.get('errors'))
                                 if type(e.get('errorCode')) is int and e['errorCode'] in (1, 2)],
            'gold_before': self.observed_gold if continuous else None,
            'gold_after': world.our.get('goldNum'),
        }
        self.observed_task_active, self.observed_gold = active, world.our.get('goldNum')
        raw_results = world.data.get("lastRoundRoleActionResults")
        results = raw_results if isinstance(raw_results, dict) else {}
        self.feedback = {
            "source_round": round_no - 1,
            "associated": continuous,
            "actions": deepcopy(self.previous_actions) if continuous else {},
            "results": {actor: value for actor, value in results.items()
                        if isinstance(actor, str) and type(value) is bool},
            **{key: deepcopy(world.data.get(key)) for key in
               ("errors", "lastSummonTreasureResult", "llmResp", "lastCmdResult")},
        }
        raw_news = world.data.get("worldNews")
        if isinstance(raw_news, dict):
            news = {key: value for key in ("officialNews", "folkLegends")
                    if isinstance(value := raw_news.get(key), str) and value}
            if news and (not self.news or self.news[-1]["text"] != news
                         or self.news[-1]["day"] != (self.phase.day if self.phase else None)):
                self.news.append({"round": round_no, "day": self.phase.day if self.phase else None,
                                  "text": news})
        for actor, role in world.enemies.items():
            self.enemy_history[actor] = {"round": round_no, "cell": role["cell"],
                                         "roleType": role.get("roleType"), "health": role.get("health")}
        self.last_round = round_no
        gold = world.our.get("goldNum")
        return ObservationDelta(round_no, self.phase, continuous, gold if nonnegative_int(gold) else 0,
                                isinstance(world.data.get("phaseTask"), str) and bool(world.data["phaseTask"]),
                                deepcopy(self.feedback))
