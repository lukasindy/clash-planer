"""Daten für die Web-App (docs/data.json) erzeugen."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .gamedata import GameData
from .planner import QUEUES, Plan
from .village import Village

MAX_STEPS = 400


def _step(s, extra=None) -> dict:
    d = {"q": s.queue, "slot": s.slot, "name": s.name, "from": s.from_lvl, "to": s.to_lvl,
         "start": int(s.start), "end": int(s.end)}
    if s.cost:
        d["cost"], d["res"] = s.cost, s.resource
    if s.new:
        d["new"] = True
    if s.goblin:
        d["goblin"] = True
    if s.assumed:
        d["assumed"] = True
    if extra:
        d.update(extra)
    return d


def site_data(gd: GameData, v: Village, plan: Plan, cfg: Config, now: float) -> dict:
    speed = {q: 1 - float(cfg.boosts.get(k, 0)) / 100
             for q, k in (("builder", "builder_percent"), ("lab", "lab_percent"), ("pets", "pet_percent"))}
    running = []
    for s in plan.running:
        # Startzeit = Ende minus volle Dauer des Levels (für den Fortschrittsbalken)
        obj, lvl = gd.get(s.data_id), gd.level(s.data_id, s.to_lvl)
        dur = int(GameData.upgrade_info(obj, lvl)[0] * speed.get(s.queue, 1)) if obj and lvl else 0
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
        "running": running,
        "steps": [_step(s) for s in sorted(plan.steps, key=lambda s: s.start)[:MAX_STEPS]],
        "stepCount": {q: len(plan.for_queue(q)) for q in QUEUES},
        "finish": {q: int(plan.finish(q)) if plan.finish(q) else None for q in QUEUES},
        "costs": {q: plan.costs(q) for q in QUEUES},
    }


def write_site(path: str, data: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
