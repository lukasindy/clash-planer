"""Upgrade-Planer: simuliert Bauarbeiter, Labor und Begleiterhaus in die Zukunft.

Ablauf (ereignisgesteuert):
  * Start = jetzt (bzw. Export-Zeitpunkt). Laufende Upgrades blockieren ihren Slot bis zum Ende.
  * Sobald ein Slot frei wird, wird das nächste Upgrade gewählt:
      - Bauarbeiter: Prioritätsstufe (config) → neue Gebäude zuerst → längstes Upgrade zuerst
      - Labor/Begleiterhaus: Wunschreihenfolge aus config, danach kürzeste zuerst
  * Schlafenszeit: Nachts startest du nichts (Start verschiebt sich auf das Aufwachen), und
    innerhalb derselben Prioritätsstufe wird das Upgrade gewählt, das am wenigsten Zeit
    nachts fertig herumsteht.
  * Abhängigkeiten werden mitsimuliert: z. B. schaltet ein fertiges Labor-Upgrade neue
    Forschungen frei, eine höhere Heldenhalle neue Heldenlevel, usw.
Rohstoff-Einkommen kennt der Planer nicht – die Kosten werden aufgelistet.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field

from .config import Config
from .gamedata import GameData
from .names_de import de_name
from .village import (BOB_HUT, BUILDERS_HUT, HERO_HALL, LABORATORY, PET_HOUSE, TOWN_HALL,
                      WALL, Instance, Village)

QUEUES = ("builder", "lab", "pets")
QUEUE_LABEL = {"builder": "Bauarbeiter", "lab": "Labor", "pets": "Begleiterhaus"}
NEVER_PLAN = {WALL, BOB_HUT}


@dataclass
class Step:
    queue: str
    slot: int
    start: float
    end: float
    uid: int
    data_id: int
    name: str
    from_lvl: int
    to_lvl: int
    cost: int
    resource: str
    new: bool = False
    goblin: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    start: float
    steps: list[Step] = field(default_factory=list)
    running: list[Step] = field(default_factory=list)   # Upgrades, die beim Start schon laufen
    idle_at_start: dict[str, int] = field(default_factory=dict)

    def for_queue(self, q: str) -> list[Step]:
        return [s for s in self.steps if s.queue == q]

    def finish(self, q: str) -> float | None:
        ends = [s.end for s in self.steps + self.running if s.queue == q]
        return max(ends) if ends else None

    def costs(self, q: str | None = None) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            if q and s.queue != q:
                continue
            out[s.resource] = out.get(s.resource, 0) + s.cost
        return out


class Planner:
    def __init__(self, gd: GameData, village: Village, cfg: Config, now: float):
        self.gd, self.v, self.cfg = gd, village, cfg
        self.start = max(now, village.timestamp)
        pc = cfg.planner
        self.tiers: dict[str, int] = pc.get("tiers", {})
        self.default_tier = int(pc.get("default_tier", 4))
        self.include_th = bool(pc.get("include_townhall", False))
        self.include_new = bool(pc.get("include_new_buildings", True))
        self.horizon = self.start + float(pc.get("horizon_days", 730)) * 86400
        self.lab_prio = {n: i for i, n in enumerate(pc.get("lab_priority", []))}
        self.pet_prio = {n: i for i, n in enumerate(pc.get("pet_priority", []))}
        b = cfg.boosts
        self.speed = {
            "builder": 1 - float(b.get("builder_percent", 0)) / 100,
            "lab": 1 - float(b.get("lab_percent", 0)) / 100,
            "pets": 1 - float(b.get("pet_percent", 0)) / 100,
        }
        # Arbeitskopie der Instanzen
        self.inst: dict[int, Instance] = {
            i.uid: Instance(i.uid, i.data_id, i.section, i.queue, i.level, i.end, i.goblin)
            for i in village.instances if i.queue in QUEUES
        }
        self.busy: set[int] = set()
        self._next_uid = -1
        self._known_th = 0

    # ---------- Zustand ----------
    def _lvl(self, data_id: int) -> int:
        return max((i.level for i in self.inst.values() if i.data_id == data_id), default=0)

    def _add_new_buildings(self) -> None:
        """Virtuelle Instanzen (Level 0) für noch nicht gebaute Gebäude/Fallen anlegen."""
        th = self._lvl(TOWN_HALL)
        if th == self._known_th:
            return
        self._known_th = th
        if not self.include_new:
            return
        for data_id, allowed in self.gd.allowed_ids(th).items():
            if data_id in NEVER_PLAN or data_id == BUILDERS_HUT:
                continue
            kind = self.gd.kind.get(data_id)
            if kind not in ("building", "trap"):
                continue
            obj = self.gd.get(data_id)
            if obj.get("village", "home") != "home":
                continue
            lv1 = self.gd.level(data_id, 1)
            if not lv1 or (len(obj["levels"]) == 1 and not lv1.get("build_time")):
                continue  # Deko-ähnliche Dinge ohne Bauzeit
            have = sum(1 for i in self.inst.values() if i.data_id == data_id)
            for _ in range(allowed - have):
                section = "traps" if kind == "trap" else "buildings"
                self.inst[self._next_uid] = Instance(self._next_uid, data_id, section, "builder", 0)
                self._next_uid -= 1

    def _candidates(self, q: str) -> list[tuple[tuple, int, Instance, int, int, str]]:
        th = self._lvl(TOWN_HALL)
        lab = self._lvl(LABORATORY)
        ph = self._lvl(PET_HOUSE)
        hh = self._lvl(HERO_HALL)
        out = []
        for inst in self.inst.values():
            if inst.queue != q or inst.uid in self.busy or inst.data_id in NEVER_PLAN:
                continue
            obj = self.gd.get(inst.data_id)
            if not obj:
                continue
            if inst.data_id == TOWN_HALL and not self.include_th:
                continue
            if obj.get("village", "home") != "home":
                continue
            if obj.get("super_troop") or obj.get("is_seasonal"):
                continue
            nxt = self.gd.level(inst.data_id, inst.level + 1)
            if not nxt:
                continue
            if (nxt.get("required_townhall") or 0) > th:
                continue
            if q == "builder" and (nxt.get("required_hero_tavern_level") or 0) > hh:
                continue
            if q == "lab":
                if inst.level < 1 or (nxt.get("required_lab_level") or 0) > lab:
                    continue
            if q == "pets":
                if inst.level < 1 or (nxt.get("required_pet_house_level") or 0) > ph:
                    continue
            dur, cost, res = GameData.upgrade_info(obj, nxt)
            if q in ("lab", "pets") and dur <= 0 and cost <= 0:
                continue
            dur = int(dur * self.speed[q])
            name = obj["name"]
            if q == "builder":
                tier = int(self.tiers.get(name, self.default_tier))
                key = (tier, 0 if inst.level == 0 else 1, -dur, name)
                group = (tier,)
            else:
                prio = (self.lab_prio if q == "lab" else self.pet_prio).get(name)
                key = (0, prio, dur, name) if prio is not None else (1, 0, dur, name)
                # Wunschliste strikt einhalten; nur beim Rest darf die Nachtplanung umsortieren
                group = (0, prio) if prio is not None else (1,)
            out.append((key, group, inst, dur, cost, res))
        out.sort(key=lambda c: c[0])
        return out

    def _choose(self, cands, start: float):
        best_group = cands[0][1]
        group = [c for c in cands if c[1] == best_group]
        if not self.cfg.sleep_aware or len(group) == 1:
            return group[0]
        # Am wenigsten "nachts fertig und wartet" – bei Gleichstand die Prioritätsreihenfolge
        return min(group, key=lambda c: (round(self.cfg.sleep_waste(start + c[3]) / 600), group.index(c)))

    # ---------- Simulation ----------
    def run(self) -> Plan:
        plan = Plan(start=self.start)
        seq = itertools.count()
        events: list = []
        idle: dict[str, list[int]] = {q: [] for q in QUEUES}
        cap = {q: self.v.capacity(q) for q in QUEUES}

        # Laufende Upgrades
        used = {q: 0 for q in QUEUES}
        for inst in list(self.inst.values()):
            if not inst.busy:
                continue
            if inst.end <= self.start:   # schon fertig, aber noch kein neuer Export
                inst.level += 1
                inst.end = None
                continue
            slot = None
            if not inst.goblin:
                slot = used[inst.queue]
                used[inst.queue] += 1
            self.busy.add(inst.uid)
            obj = self.gd.get(inst.data_id) or {"name": f"#{inst.data_id}"}
            plan.running.append(Step(inst.queue, slot if slot is not None else -1, self.v.timestamp,
                                     inst.end, inst.uid, inst.data_id, de_name(obj["name"]),
                                     inst.level, inst.level + 1, 0, "", goblin=inst.goblin))
            heapq.heappush(events, (inst.end, next(seq), "done", inst.queue, slot, inst.uid))
            inst.end = None
        for q in QUEUES:
            free = max(cap[q] - used[q], 0)
            plan.idle_at_start[q] = free
            for s in range(used[q], used[q] + free):
                idle[q].append(s)

        self._add_new_buildings()
        t = self.start
        self._assign_all(plan, idle, events, seq, t)
        while events:
            t, _, kind, q, slot, uid = heapq.heappop(events)
            if t > self.horizon:
                break
            if kind == "done":
                self.inst[uid].level += 1
                self.busy.discard(uid)
                if slot is not None:
                    idle[q].append(slot)
                self._add_new_buildings()
            self._assign_all(plan, idle, events, seq, t)
        return plan

    def _assign_all(self, plan, idle, events, seq, t):
        for q in QUEUES:
            while idle[q]:
                cands = self._candidates(q)
                if not cands:
                    break
                start = self.cfg.earliest_start(t)
                key, group, inst, dur, cost, res = self._choose(cands, start)
                slot = min(idle[q])
                idle[q].remove(slot)
                self.busy.add(inst.uid)
                end = start + dur
                obj = self.gd.get(inst.data_id)
                plan.steps.append(Step(q, slot, start, end, inst.uid, inst.data_id,
                                       de_name(obj["name"]), inst.level, inst.level + 1,
                                       cost, res, new=inst.level == 0))
                heapq.heappush(events, (end, next(seq), "done", q, slot, inst.uid))


def make_plan(gd: GameData, village: Village, cfg: Config, now: float) -> Plan:
    return Planner(gd, village, cfg, now).run()
