"""In-Game-Export (Einstellungen → Weitere Einstellungen → Datenexport) einlesen.

Format (Auszug):
    {"tag": "#…", "timestamp": 1788969427,
     "buildings": [{"data": 1000008, "lvl": 9, "cnt": 4},
                   {"data": 1000021, "lvl": 12, "timer": 86400}],
     "units": [...], "spells": [...], "heroes": [...], "pets": [...],
     "buildings2": [...]   # Endung "2" = Bauarbeiterbasis
    }
`timer` = Sekunden Restzeit zum Zeitpunkt `timestamp`, `lvl` = aktuelles Level.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .gamedata import GameData

TOWN_HALL = 1000001
LABORATORY = 1000007
BUILDERS_HUT = 1000015
BOB_HUT = 1000064
PET_HOUSE = 1000068
BLACKSMITH = 1000070
HERO_HALL = 1000071
WALL = 1000010
STAR_LAB = 1000046
BUILDER_HALL = 1000034

# Export-Abschnitt -> Warteschlange ("builder", "lab", "pets"); "2" = Bauarbeiterbasis
def queue_for_section(section: str) -> str | None:
    base = section.rstrip("2")
    bb = section.endswith("2")
    if base in ("buildings", "traps", "heroes", "guardians"):
        return "bb_builder" if bb else "builder"
    if base in ("units", "troops", "spells", "siege_machines", "siege"):
        return "star_lab" if bb else "lab"
    if base == "pets":
        return "pets"
    return None


@dataclass
class Instance:
    uid: int
    data_id: int
    section: str
    queue: str
    level: int
    end: float | None = None      # Unix-Zeit, wann das laufende Upgrade fertig ist
    goblin: bool = False          # Goblin-Bauarbeiter/-Forscher (zusätzlicher Slot)
    assumed: bool = False         # vom Plan-folgen-Modus angenommen (nicht aus dem Export)
    helper: bool = False          # ein Helfer (Lehrling/Assistent) arbeitet automatisch daran
    base_end: float | None = None # Ende laut Export OHNE künftige Helfer-Einsätze

    @property
    def busy(self) -> bool:
        return self.end is not None


@dataclass
class Village:
    tag: str
    timestamp: float
    instances: list[Instance] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    helpers: list[dict] = field(default_factory=list)   # [{"id", "level", "ready": ts|None}]

    # ---------- Hilfen ----------
    def levels_of(self, data_id: int) -> list[int]:
        return [i.level for i in self.instances if i.data_id == data_id]

    def level_of(self, data_id: int) -> int:
        lv = self.levels_of(data_id)
        return max(lv) if lv else 0

    @property
    def th(self) -> int:
        return self.level_of(TOWN_HALL)

    @property
    def lab_level(self) -> int:
        return self.level_of(LABORATORY)

    @property
    def pet_house_level(self) -> int:
        return self.level_of(PET_HOUSE)

    @property
    def hero_hall_level(self) -> int:
        return self.level_of(HERO_HALL)

    @property
    def builders(self) -> int:
        huts = sum(1 for i in self.instances if i.data_id == BUILDERS_HUT and i.queue == "builder")
        bob = 1 if any(i.data_id == BOB_HUT for i in self.instances) else 0
        return max(huts + bob, 1)

    def capacity(self, queue: str) -> int:
        if queue == "builder":
            return self.builders
        if queue == "lab":
            return 1 if self.lab_level > 0 else 0
        if queue == "pets":
            return 1 if self.pet_house_level > 0 else 0
        if queue == "bb_builder":
            return 2 if self.level_of(BUILDER_HALL) >= 6 else (1 if self.level_of(BUILDER_HALL) else 0)
        if queue == "star_lab":
            return 1 if self.level_of(STAR_LAB) else 0
        return 0

    def active(self, queue: str, include_goblin: bool = False) -> list[Instance]:
        return [i for i in self.instances
                if i.queue == queue and i.busy and (include_goblin or not i.goblin)]


def _strip(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # Falls rund um das JSON noch Text steht (z. B. im Issue), nur das Objekt nehmen
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Kein JSON-Objekt gefunden.")
    return t[start:end + 1]


def parse_export(text_or_obj) -> Village:
    raw = text_or_obj if isinstance(text_or_obj, dict) else json.loads(_strip(text_or_obj))
    if "timestamp" not in raw or not any(k.startswith("buildings") for k in raw):
        raise ValueError("Das sieht nicht wie ein Clash-of-Clans-Dorfexport aus "
                         "(Felder 'timestamp'/'buildings' fehlen).")
    ts = float(raw["timestamp"])
    if ts > 1e12:  # Millisekunden
        ts /= 1000
    v = Village(tag=raw.get("tag", "?"), timestamp=ts, raw=raw)
    for h in raw.get("helpers", []) or []:
        if isinstance(h, dict) and "data" in h:
            cd = h.get("helper_cooldown")
            v.helpers.append({"id": int(h["data"]), "level": int(h.get("lvl", 1)),
                              "ready": ts + float(cd) if cd else None})
    uid = 0
    for section, rows in raw.items():
        if not isinstance(rows, list):
            continue
        queue = queue_for_section(section)
        if queue is None:
            continue
        for row in rows:
            if not isinstance(row, dict) or "data" not in row:
                continue
            lvl = int(row.get("lvl", 0 if "timer" in row else 1))
            goblin = bool(row.get("extra")) or any("goblin" in k for k in row)
            if "timer" in row:
                cnt = 1
                end = ts + float(row["timer"])
            else:
                cnt = int(row.get("cnt", 1))
                end = None
            for _ in range(cnt):
                v.instances.append(Instance(uid, int(row["data"]), section, queue, lvl, end, goblin,
                                            helper=bool(row.get("helper_recurrent"))))
                uid += 1
    apply_helpers(v)
    return v


def apply_assumptions(v: Village, assumed: list[dict]) -> None:
    """Plan-folgen-Modus: angenommene (empfohlene) Upgrades in den Export einrechnen."""
    by_uid = {i.uid: i for i in v.instances}
    for a in sorted(assumed, key=lambda a: a["start"]):
        inst = by_uid.get(a["uid"])
        if inst is None:
            if a["uid"] >= 0:
                continue
            inst = Instance(a["uid"], a["data_id"], a["section"], a["queue"], 0)
            v.instances.append(inst)
            by_uid[inst.uid] = inst
        if inst.data_id != a["data_id"]:
            continue  # passt nicht (anderer Export) – ignorieren
        inst.level = a["from_lvl"]
        inst.end = a["end"]
        inst.assumed = True


HELPER_QUEUE = {93000000: "builder", 93000001: "lab"}   # Bauarbeiter-Lehrling, Labor-Assistent
HELPER_PERIOD = 24 * 3600                                 # 1 Std. Arbeit + ca. 23 Std. Pause


def apply_helpers(v: Village, levels: dict[int, int] | None = None) -> None:
    """Künftige Helfer-Einsätze einrechnen: Ab "bereit" arbeitet der Helfer 1 Stunde und schafft
    dabei (1 + Level) Stunden Fortschritt (= Level Stunden gespart), danach alle 24 Std. wieder –
    so lange das Upgrade läuft."""
    for h in v.helpers:
        q = HELPER_QUEUE.get(h["id"])
        if not q:
            continue
        target = next((i for i in v.instances if i.helper and i.queue == q and i.end), None)
        if not target:
            continue
        mult = int(h.get("level", 1))
        t = h.get("ready") or v.timestamp           # nächster Einsatz
        end = target.end
        target.base_end = end
        while t < end:
            remaining = end - t
            if remaining <= (mult + 1) * 3600:       # wird während dieser Stunde fertig
                end = t + remaining / (mult + 1)
                break
            end -= mult * 3600
            t += HELPER_PERIOD
        target.end = end


def load_village(path: str) -> Village:
    with open(path, encoding="utf-8") as f:
        return parse_export(f.read())


def describe(gd: GameData, inst: Instance) -> str:
    from .names_de import de_name
    return de_name(gd.name(inst.data_id))
