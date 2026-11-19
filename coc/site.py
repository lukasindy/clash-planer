"""Daten für die Web-App (docs/data.json) erzeugen."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .names_de import de_name
from .gamedata import GameData
from .planner import QUEUES, Plan
from .village import Village

MAX_STEPS = 2000


def _step(s, extra=None) -> dict:
    d = {"q": s.queue, "slot": s.slot, "name": s.name, "id": s.data_id, "from": s.from_lvl, "to": s.to_lvl,
         "start": int(s.start), "end": int(s.end)}
    if s.cost:
        d["cost"], d["res"] = s.cost, s.resource
    if s.new:
        d["new"] = True
    if s.goblin:
        d["goblin"] = True
    if s.assumed:
        d["assumed"] = True
    if getattr(s, "book", False):
        d["book"] = True
    if getattr(s, "hammer", ""):
        d["hammer"] = s.hammer
    if getattr(s, "pick", ""):
        d["pick"] = True
    if getattr(s, "est", False):
        d["est"] = True
    if s.section == "heroes":
        d["hero"] = True
    if extra:
        d.update(extra)
    return d


def _choices(gd: GameData, v: Village) -> dict:
    """Namen, die als Wunsch/Hammer-Ziel in Frage kommen (noch nicht maximal auf diesem Rathaus)."""
    from .planner import NEVER_PLAN
    out = {"building": set(), "heroes": set(), "fighting": set(), "spells": set()}
    for i in v.instances:
        if i.queue not in ("builder", "lab") or i.data_id in NEVER_PLAN or i.level < 1:
            continue
        obj, nxt = gd.get(i.data_id), gd.level(i.data_id, i.level + 1)
        if not obj or not nxt or (nxt.get("required_townhall") or 0) > v.th:
            continue
        if not (nxt.get("build_time") or nxt.get("upgrade_time") or nxt.get("build_cost") or nxt.get("upgrade_cost")):
            continue   # Platzhalter-Level, gibt es im Spiel noch nicht
        if obj.get("super_troop") or obj.get("is_seasonal"):
            continue
        kind = ("heroes" if i.section == "heroes" else "building") if i.queue == "builder" else \
            ("spells" if i.section == "spells" else "fighting")
        out[kind].add(de_name(obj["name"]))
    return {k: sorted(x) for k, x in out.items()}


def _icons() -> dict:
    p = Path("docs/icons/index.json")
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def site_data(gd: GameData, v: Village, plan: Plan, cfg: Config, now: float) -> dict:
    running = []
    for s in plan.running:
        # Startzeit = Ende minus volle Dauer des Levels (für den Fortschrittsbalken)
        obj, lvl = gd.get(s.data_id), gd.level(s.data_id, s.to_lvl)
        dur = int(GameData.upgrade_info(obj, lvl)[0] * cfg.boost_factor(s.queue, now)) if obj and lvl else 0
        start = s.assumed and s.start or (s.end - dur if dur else v.timestamp)
        extra = {"start": int(start)}
        if obj and lvl:
            extra["res"] = GameData.upgrade_info(obj, lvl)[2]
        running.append(_step(s, extra))
    return {
        "generated": int(now),
        "export": int(v.timestamp),
        "tag": v.tag,
        "th": v.th, "lab": v.lab_level, "pets": v.pet_house_level, "heroHall": v.hero_hall_level,
        "capacity": {q: v.capacity(q) for q in QUEUES},
        "tz": str(cfg.tz), "sleep": [cfg.sleep_start.strftime("%H:%M"), cfg.sleep_end.strftime("%H:%M")]
        if cfg.sleep_aware else None,
        "boost": cfg.boost_info(now),
        "choices": _choices(gd, v),
        "bookOptions": plan.book_options,
        "bookUnmet": plan.book_unmet,
        "settings": {
            "builder_picks": cfg.planner.get("books", {}).get("builder_picks", []),
            "lab_picks": cfg.planner.get("books", {}).get("lab_picks", []),
            "heroes_picks": cfg.planner.get("books", {}).get("heroes_picks", []),
            "books": {"builder": cfg.planner.get("books", {}).get("builder", 1),
                      "lab": cfg.planner.get("books", {}).get("lab", 2),
                      "heroes": cfg.planner.get("books", {}).get("heroes", 0)},
            "hammers": cfg.raw.get("hammers", {}),
        },
        "repo": "lukasindy/clash-planer",
        "icons": _icons(),
        "running": running,
        "steps": [_step(s) for s in sorted(plan.steps, key=lambda s: s.start)[:MAX_STEPS]],
        "stepCount": {q: len(plan.for_queue(q)) for q in QUEUES},
        "finish": {q: int(plan.finish(q)) if plan.finish(q) else None for q in QUEUES},
        "costs": {q: plan.costs(q) for q in QUEUES},
    }


def write_site(path: str, data: dict) -> None:
    import re
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    html = Path(path).parent / "index.html"
    if html.exists():
        m = re.search(r'APP_VERSION = "([^"]+)"', html.read_text("utf-8"))
        if m:
            data["appVersion"] = m.group(1)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
