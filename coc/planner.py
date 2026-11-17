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
NEVER_PLAN = {WALL, BOB_HUT, 1000093, 1000097, 1000105}  # Mauer, B.O.B, Helferhütte, Werkbank, Wächterschrein


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
    assumed: bool = False
    section: str = ""
    book: bool = False            # mit Buch sofort fertig (Bücher-Tag am Monatsanfang)
    hammer: str = ""              # mit Hammer sofort fertig: building/heroes/fighting/spells
    pick: str = ""                # dein Wunsch aus config.toml, der hier erfüllt wurde

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    start: float
    steps: list[Step] = field(default_factory=list)
    running: list[Step] = field(default_factory=list)   # Upgrades, die beim Start schon laufen
    idle_at_start: dict[str, int] = field(default_factory=dict)
    book_savings: list = field(default_factory=list)
    book_options: dict = field(default_factory=dict)   # was am nächsten Bücher-Tag möglich ist
    book_unmet: list = field(default_factory=list)     # Wünsche, die nicht gingen (+ Grund)

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
        # Arbeitskopie der Instanzen
        self.inst: dict[int, Instance] = {
            i.uid: Instance(i.uid, i.data_id, i.section, i.queue, i.level, i.end, i.goblin, i.assumed)
            for i in village.instances if i.queue in QUEUES
        }
        cwl = pc.get("cwl", {})
        self.cwl_on = bool(cwl.get("heroes_blocked", True))
        self.cwl_days = (int(cwl.get("start_day", 1)), int(cwl.get("end_day", 11)))
        self._retry_at: float | None = None
        bk = pc.get("books", {})
        self.books_on = bool(bk.get("enabled", True))
        self.books_day = int(bk.get("day", 1))
        self.books_n = {"builder": int(bk.get("builder", 1)), "lab": int(bk.get("lab", 2))}
        self.book_picks = {"builder": list(bk.get("builder_picks", []) or []),
                           "lab": list(bk.get("lab_picks", []) or [])}
        hm = cfg.raw.get("hammers", {})
        self.hammers = {k: int(hm.get(k, 0) or 0) for k in ("building", "heroes", "fighting", "spells")}
        self.hammer_picks = {k: str(hm.get(f"{k}_pick", "") or "") for k in self.hammers}
        self._first_book_day = True
        self.book_slot = max(village.capacity("builder") - 1, 0)   # dieser Bauarbeiter ist am 1. frei
        self.book_times = self._make_book_times() if self.books_on else []
        self._books_done: set[float] = set()
        self.busy: set[int] = set()
        self._in_book = False
        self._ends: dict[int, float] = {}
        self.reserved: dict[int, str] = self._reserve_picks()
        self._next_uid = min(list(self.inst) + [0]) - 1
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
            # Nur was DIESES Rathaus-Level neu freischaltet. Ältere Gebäude, die fehlen, wurden
            # meist zusammengelegt (z. B. Kanonen → Querschläger-Kanone, Scattershot ab RH19).
            new_at_th = allowed - self.gd.max_count(data_id, th - 1)
            for _ in range(min(allowed - have, max(new_at_th, 0))):
                section = "traps" if kind == "trap" else "buildings"
                self.inst[self._next_uid] = Instance(self._next_uid, data_id, section, "builder", 0)
                self._next_uid -= 1

    def _candidates(self, q: str, start: float, instant: bool = False) -> list[tuple[tuple, int, Instance, int, int, str]]:
        th = self._lvl(TOWN_HALL)
        lab = self._lvl(LABORATORY)
        ph = self._lvl(PET_HOUSE)
        hh = self._lvl(HERO_HALL)
        out = []
        for inst in self.inst.values():
            if inst.queue != q or inst.uid in self.busy or inst.data_id in NEVER_PLAN:
                continue
            if inst.uid in self.reserved and not self._in_book:
                continue   # für den Bücher-Tag reserviert
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
            if dur <= 0 and cost <= 0:
                continue  # Platzhalter-Level in den Spieldaten (noch nicht im Spiel)
            # Goldpass-Boost, der am STARTZEITPUNKT gilt, senkt Zeit UND Kosten
            f = self.cfg.boost_factor(q, start)
            dur, cost = int(dur * f), int(cost * f)
            if inst.section == "heroes" and self.cwl_on and not instant:
                clash = self._cwl_overlap(start, start + dur)
                if clash is not None:
                    # Held wäre während der CWL im Upgrade → später nochmal versuchen
                    self._retry_at = clash if self._retry_at is None else min(self._retry_at, clash)
                    continue
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

    # ---------- Bücher am Monatsanfang ----------
    def _make_book_times(self) -> list[float]:
        """Jeden Monat am Bücher-Tag zur Aufwachzeit (bzw. jetzt, wenn heute Bücher-Tag ist)."""
        from datetime import datetime
        tz, out = self.cfg.tz, []
        h, m = self.cfg.sleep_end.hour, self.cfg.sleep_end.minute
        d = datetime.fromtimestamp(self.start, tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while d.timestamp() <= self.horizon:
            bt = d.replace(day=self.books_day, hour=h, minute=m).timestamp()
            today = datetime.fromtimestamp(bt, tz).strftime("%Y-%m-%d")
            if bt <= self.start < bt + 86400 - 3600 * h:
                if self.cfg.planner.get("books", {}).get("skip_date") != today:
                    out.append(self.start)        # heute ist Bücher-Tag (und noch nicht erledigt)
            elif bt > self.start:
                out.append(bt)
            d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
        return out

    def _book_deadline(self, q: str, slot: int, start: float) -> float | None:
        """Bis wann dieser Platz fertig sein muss, damit am Bücher-Tag das Buch genutzt werden kann."""
        if not self.book_times or self.books_n.get(q, 0) <= 0:
            return None
        if q == "builder" and slot != self.book_slot:
            return None
        return next((bt for bt in self.book_times if bt >= start and bt not in self._books_done), None)

    def _reserve_picks(self) -> dict[int, str]:
        """Wünsche/Hammer-Ziele für den Bücher-Tag reservieren: je Wunsch EIN passendes Exemplar
        (das niedrigste, das gerade nicht im Upgrade ist). Bis zum Bücher-Tag wird es nicht vorgeschlagen."""
        if not self.books_on:
            return {}
        picks = self.book_picks["builder"] + self.book_picks["lab"] + \
            [p for k, p in self.hammer_picks.items() if p and self.hammers.get(k)]
        out: dict[int, str] = {}
        for p in picks:
            free = sorted((i for i in self.inst.values()
                           if i.uid not in out and not i.busy and self._match(p, i)), key=lambda i: i.level)
            if free:
                out[free[0].uid] = p
        return out

    def _match(self, pick: str, inst: Instance) -> bool:
        p = pick.strip().lower()
        name = self.gd.name(inst.data_id)
        return bool(p) and p in (name.lower(), de_name(name).lower())

    def _pick_target(self, cands, picks: list[str]):
        """Erst deine Wünsche (in Reihenfolge), sonst das längste Upgrade."""
        for p in picks:
            hit = next((c for c in cands if self.reserved.get(c[2].uid) == p), None) or \
                next((c for c in cands if self._match(p, c[2])), None)
            if hit:
                picks.remove(p)
                return hit, p
        return (max(cands, key=lambda c: c[3]), "") if cands else (None, "")

    def _instant(self, plan, q, slot, t, c, pick="", book=False, hammer=""):
        key, group, inst, dur, cost, res = c
        obj = self.gd.get(inst.data_id)
        plan.steps.append(Step(q, slot, t, t, inst.uid, inst.data_id, de_name(obj["name"]),
                               inst.level, inst.level + 1, 0 if hammer else cost, res,
                               new=inst.level == 0, section=inst.section, book=book,
                               hammer=hammer, pick=pick))
        plan.book_savings.append(dur)
        inst.level += 1
        self._add_new_buildings()

    def _why_not(self, pick: str) -> str:
        """Warum ein Wunsch am Bücher-Tag nicht geht."""
        insts = [i for i in self.inst.values() if self._match(pick, i)]
        if not insts:
            return "nicht in deinem Dorf gefunden"
        lab, th, hh, ph = (self._lvl(LABORATORY), self._lvl(TOWN_HALL), self._lvl(HERO_HALL), self._lvl(PET_HOUSE))
        reasons = []
        for i in insts:
            nxt = self.gd.level(i.data_id, i.level + 1)
            if not nxt or not (nxt.get("build_time") or nxt.get("upgrade_time") or nxt.get("build_cost") or nxt.get("upgrade_cost")):
                reasons.append("schon maximal (höheres Level gibt es im Spiel noch nicht)")
            elif i.uid in self.busy:
                reasons.append("läuft da gerade noch")
            elif (nxt.get("required_townhall") or 0) > th:
                reasons.append(f"braucht Rathaus {nxt['required_townhall']}")
            elif (nxt.get("required_lab_level") or 0) > lab and i.queue == "lab":
                lab_end = next((self._ends.get(x.uid) for x in self.inst.values()
                                if x.data_id == LABORATORY and x.uid in self.busy), None)
                when = f", Labor-Upgrade fertig {self.cfg.fmt_time(lab_end)}" if lab_end else ""
                reasons.append(f"braucht Labor {nxt['required_lab_level']} (du hast {lab}{when})")
            elif (nxt.get("required_hero_tavern_level") or 0) > hh:
                reasons.append(f"braucht Heldenhalle {nxt['required_hero_tavern_level']}")
            else:
                reasons.append("passt nicht zu diesem Buch/Hammer")
        return reasons[0]

    def _options(self, t) -> dict:
        """Alles, was am Bücher-Tag grundsätzlich geht – auch wenn der Planer es sonst gerade
        anderweitig verplant hätte (dein Wunsch wird dafür bis zum Bücher-Tag reserviert)."""
        th, lab, hh = self._lvl(TOWN_HALL), self._lvl(LABORATORY), self._lvl(HERO_HALL)
        out = {k: set() for k in ("building", "heroes", "fighting", "spells")}
        locked = {k: {} for k in out}
        for i in self.inst.values():
            if i.queue not in ("builder", "lab") or i.data_id in NEVER_PLAN or i.level < 1:
                continue
            if i.data_id == TOWN_HALL and not self.include_th:
                continue
            obj = self.gd.get(i.data_id)
            if not obj or obj.get("village", "home") != "home" or obj.get("super_troop") or obj.get("is_seasonal"):
                continue
            nxt = self.gd.level(i.data_id, i.level + 1)
            if not nxt or not (nxt.get("build_time") or nxt.get("upgrade_time") or nxt.get("build_cost") or nxt.get("upgrade_cost")):
                continue
            kind = ("heroes" if i.section == "heroes" else "building") if i.queue == "builder" else \
                ("spells" if i.section == "spells" else "fighting")
            name = de_name(obj["name"])
            if (nxt.get("required_townhall") or 0) > th:
                continue   # gehört zum nächsten Rathaus – nicht anzeigen
            why = None
            if i.queue == "lab" and (nxt.get("required_lab_level") or 0) > lab:
                why = f"braucht Labor {nxt['required_lab_level']}"
            elif i.section == "heroes" and (nxt.get("required_hero_tavern_level") or 0) > hh:
                why = f"braucht Heldenhalle {nxt['required_hero_tavern_level']}"
            if why:
                locked[kind].setdefault(name, why)
            else:
                out[kind].add(name)
        o = {k: sorted(v) for k, v in out.items()}
        o["locked"] = {k: sorted([[n, w] for n, w in v.items() if n not in out[k]]) for k, v in locked.items()}
        o["builder"] = o["building"]
        o["lab"] = sorted(out["fighting"] | out["spells"])
        return o

    def _use_books(self, plan, idle, t):
        self._books_done.add(t)
        self._in_book = True
        if self._first_book_day:
            plan.book_options = {"time": int(t), **self._options(t)}
            wanted = [("📖", p) for p in self.book_picks["builder"] + self.book_picks["lab"]] + \
                     [("🔨", p) for k, p in self.hammer_picks.items() if p and self.hammers.get(k)]
        used: list[str] = []
        for q in ("builder", "lab"):
            slot = self.book_slot if q == "builder" else 0
            if self.books_n.get(q, 0) <= 0 or slot not in idle[q]:
                continue
            for _ in range(self.books_n[q]):
                cands = [c for c in self._candidates(q, t, instant=True) if c[2].section != "heroes"]
                c, pick = self._pick_target(cands, self.book_picks[q] if self._first_book_day else [])
                if not c:
                    break
                self._instant(plan, q, slot, t, c, pick=pick, book=True)
                if pick:
                    used.append(pick)
        # Hämmer (nur am ersten Bücher-Tag – danach sind sie verbraucht)
        if self._first_book_day:
            for kind, n in self.hammers.items():
                q = "builder" if kind in ("building", "heroes") else "lab"
                for _ in range(n):
                    cands = self._candidates(q, t, instant=True)
                    if kind == "building":
                        cands = [c for c in cands if c[2].section != "heroes"]
                    elif kind == "heroes":
                        cands = [c for c in cands if c[2].section == "heroes"]
                    elif kind == "fighting":
                        cands = [c for c in cands if c[2].section != "spells"]
                    else:
                        cands = [c for c in cands if c[2].section == "spells"]
                    # Hammer ist gratis → lohnt sich am meisten beim teuersten/längsten
                    picks = [self.hammer_picks[kind]] if self.hammer_picks[kind] else []
                    c, pick = self._pick_target(cands, picks)
                    if not c:
                        break
                    self.hammer_picks[kind] = ""
                    self._instant(plan, q, -1, t, c, pick=pick, hammer=kind)
                    if pick:
                        used.append(pick)
        if self._first_book_day:
            for icon, p in wanted:
                if p not in used:
                    plan.book_unmet.append({"pick": p, "why": self._why_not(p)})
        self._first_book_day = False
        self._in_book = False
        self.reserved.clear()   # nach dem Bücher-Tag wieder normal planbar

    def _cwl_windows(self, a: float, b: float):
        """CWL-Zeiträume (Start, Ende) im Bereich a..b, in deiner Zeitzone."""
        from datetime import datetime
        tz = self.cfg.tz
        d = datetime.fromtimestamp(a, tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        sd, ed = self.cwl_days
        while d.timestamp() <= b:
            ws = d.replace(day=sd).timestamp()
            we = d.replace(day=ed).timestamp() + 86400
            yield ws, we
            d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)

    def _cwl_overlap(self, a: float, b: float) -> float | None:
        """Ende des CWL-Fensters, das mit [a, b) überlappt (= frühester neuer Versuch), sonst None."""
        for ws, we in self._cwl_windows(a, b):
            if a < we and b > ws:
                return we
        return None

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
                                     inst.level, inst.level + 1, 0, "", goblin=inst.goblin,
                                     assumed=inst.assumed, section=inst.section))
            heapq.heappush(events, (inst.end, next(seq), "done", inst.queue, slot, inst.uid))
            self._ends[inst.uid] = inst.end
            inst.end = None
        for q in QUEUES:
            free = max(cap[q] - used[q], 0)
            plan.idle_at_start[q] = free
            for s in range(used[q], used[q] + free):
                idle[q].append(s)

        self._add_new_buildings()
        for bt in self.book_times:
            heapq.heappush(events, (bt, next(seq), "book", None, None, None))
        t = self.start
        if self.book_times and self.book_times[0] == self.start:
            self._use_books(plan, idle, t)
        self._assign_all(plan, idle, events, seq, t)
        while events:
            t, _, kind, q, slot, uid = heapq.heappop(events)
            if t > self.horizon:
                break
            if kind == "retry":
                self._retry_pending = False
            if kind == "book" and t > self.start:
                self._use_books(plan, idle, t)
            if kind == "done":
                self.inst[uid].level += 1
                self.busy.discard(uid)
                if slot is not None:
                    idle[q].append(slot)
                self._add_new_buildings()
            self._assign_all(plan, idle, events, seq, t)
        return plan

    def _assign_all(self, plan, idle, events, seq, t):
        self._retry_at = None
        self._assign_queues(plan, idle, events, seq, t)
        # Freie Bauarbeiter, aber Helden durch CWL blockiert → nach der CWL erneut planen
        if self._retry_at and idle["builder"] and not getattr(self, "_retry_pending", False):
            self._retry_pending = True
            heapq.heappush(events, (self._retry_at, next(seq), "retry", "builder", None, None))

    def _assign_queues(self, plan, idle, events, seq, t):
        for q in QUEUES:
            for slot in sorted(idle[q]):
                start = self.cfg.earliest_start(t)
                cands = self._candidates(q, start)
                if not cands:
                    break
                deadline = self._book_deadline(q, slot, start)
                if deadline is not None:
                    # Muss vor dem Bücher-Tag fertig sein (sonst bleibt der Platz bis dahin frei)
                    cands = [c for c in cands if start + c[3] <= deadline]
                    if not cands:
                        continue
                key, group, inst, dur, cost, res = self._choose(cands, start)
                idle[q].remove(slot)
                self.busy.add(inst.uid)
                end = start + dur
                obj = self.gd.get(inst.data_id)
                plan.steps.append(Step(q, slot, start, end, inst.uid, inst.data_id,
                                       de_name(obj["name"]), inst.level, inst.level + 1,
                                       cost, res, new=inst.level == 0, section=inst.section))
                heapq.heappush(events, (end, next(seq), "done", q, slot, inst.uid))
                self._ends[inst.uid] = end


def make_plan(gd: GameData, village: Village, cfg: Config, now: float) -> Plan:
    return Planner(gd, village, cfg, now).run()
