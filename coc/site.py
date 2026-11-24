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
    if getattr(s, "helper", False):
        d["helper"] = True
        if getattr(s, "base_end", None):
            d["baseEnd"] = int(s.base_end)
            d["helperUses"], d["helperEach"] = s.helper_uses, s.helper_each
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


def _raw_static() -> dict:
    from .gamedata import load_raw
    try:
        return load_raw()
    except Exception:  # noqa: BLE001
        return {}


def _icons() -> dict:
    p = Path("docs/icons/index.json")
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _advice(gd: GameData, v: Village, cfg: Config, now: float, top: int = 8) -> dict:
    """Wofür lohnt sich welches Buch / welcher Hammer JETZT am meisten?
    Bücher: gesparte Zeit (laufende Upgrades zählen mit ihrer Restzeit, Kosten zahlst du trotzdem).
    Hämmer: gesparte Zeit + gesparte Rohstoffe (nur Dinge, die gerade nicht im Upgrade sind)."""
    from .planner import NEVER_PLAN
    from .village import HERO_HALL, LABORATORY, TOWN_HALL
    th, lab, hh = v.th, v.level_of(LABORATORY), v.level_of(HERO_HALL)
    rows = []
    for i in v.instances:
        if i.queue not in ("builder", "lab") or i.data_id in NEVER_PLAN or i.goblin:
            continue
        if i.data_id == TOWN_HALL or i.level < 1:
            continue
        obj = gd.get(i.data_id)
        if not obj or obj.get("village", "home") != "home" or obj.get("super_troop") or obj.get("is_seasonal"):
            continue
        kind = ("heroes" if i.section == "heroes" else "building") if i.queue == "builder" else \
            ("spells" if i.section == "spells" else "fighting")
        base = {"id": i.data_id, "name": de_name(obj["name"]), "kind": kind}
        if i.end and i.end > now:     # läuft gerade → Buch macht den Rest sofort fertig
            rows.append({**base, "from": i.level, "to": i.level + 1, "save": int(i.end - now),
                         "running": True, "cost": 0, "res": ""})
            continue
        nxt = gd.level(i.data_id, i.level + 1)
        if not nxt:
            continue
        if (nxt.get("required_townhall") or 0) > th:
            continue
        if i.queue == "lab" and (nxt.get("required_lab_level") or 0) > lab:
            continue
        if i.section == "heroes" and (nxt.get("required_hero_tavern_level") or 0) > hh:
            continue
        dur, cost, res = GameData.upgrade_info(obj, nxt)
        q = "builder" if i.queue == "builder" else "lab"
        f = cfg.boost_factor(q, now)
        if dur <= 0 and cost <= 0:
            continue
        rows.append({**base, "from": i.level, "to": i.level + 1, "save": int(dur * f),
                     "running": False, "cost": int(cost * f), "res": res, "est": bool(nxt.get("estimated"))})
    # gleiche Sorte/Level nur einmal (z. B. 4 X-Bögen auf gleichem Level)
    seen, uniq = set(), []
    for r in rows:
        key = (r["id"], r["from"], r["running"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    by_time = lambda xs: sorted(xs, key=lambda r: -r["save"])[:top * 3]
    out = {}
    for k in ("building", "heroes", "fighting", "spells"):
        sub = [r for r in uniq if r["kind"] == k]
        out["book_" + k] = by_time(sub)[:top]
        out["hammer_" + k] = by_time([r for r in sub if not r["running"]])
    out["book_everything"] = by_time(uniq)[:top]
    return out


def _walls(gd: GameData, v: Village) -> dict:
    """Mauer-Zähler: wie viele sind maximal, was kostet der Rest (sofort, ohne Bauarbeiter)."""
    from .village import WALL
    obj = gd.get(WALL)
    if not obj:
        return {}
    levels = {l["level"]: l for l in obj["levels"]}
    max_lvl = max((l for l, d in levels.items() if (d.get("required_townhall") or 0) <= v.th), default=0)
    by = {}
    for i in v.instances:
        if i.data_id == WALL:
            by[i.level] = by.get(i.level, 0) + 1
    total = sum(by.values())
    upgrades, cost = 0, 0
    groups = []
    for lvl, n in sorted(by.items()):
        if lvl >= max_lvl:
            continue
        nxt = int(levels.get(lvl + 1, {}).get("build_cost", 0) or 0)
        to_max = sum(int(levels.get(x, {}).get("build_cost", 0) or 0) for x in range(lvl + 1, max_lvl + 1))
        groups.append({"level": lvl, "count": n, "next": nxt, "toMax": to_max, "steps": max_lvl - lvl})
        upgrades += n * (max_lvl - lvl)
        cost += n * to_max
    alt_from = min((l for l, d in levels.items() if d.get("alt_upgrade_resource")), default=None)
    return {"total": total, "allowed": gd.max_count(WALL, v.th), "max": max_lvl, "atMax": by.get(max_lvl, 0),
            "byLevel": sorted([[l, n] for l, n in by.items()], reverse=True), "groups": groups,
            "upgrades": upgrades, "cost": cost, "altFrom": alt_from}


HELPER_DE = {"Builder's Apprentice": "Bauarbeiter-Lehrling", "Lab Assistant": "Labor-Assistent",
             "Alchemist": "Alchemist", "Prospector": "Prospector"}


def _helpers(raw_static: dict, v: Village, now: float) -> list:
    """Wo arbeiten die Helfer gerade (automatisch) und wann sind sie wieder bereit?"""
    defs = {h["_id"]: h for h in raw_static.get("helpers", [])}
    out = []
    for h in v.helpers:
        d = defs.get(h["id"], {})
        name = d.get("name", f"#{h['id']}")
        lvl = next((l for l in d.get("levels", []) if l.get("level") == h["level"]), {})
        # Lehrling/Assistent: pro Einsatz (1 Std.) so viele Stunden Fortschritt wie das Level
        saves = int(lvl.get("boost_time_seconds", 0) or 0) * int(lvl.get("boost_multiplier", 0) or 0)
        q = {"Builder's Apprentice": "builder", "Lab Assistant": "lab"}.get(name)
        target = None
        if q:
            t = next((i for i in v.instances if i.helper and i.queue == q), None)
            if t:
                target = {"id": t.data_id, "name": de_name(gd_name(raw_static, t.data_id)),
                          "to": t.level + 1, "end": int(t.end) if t.end else None,
                          "baseEnd": int(t.base_end) if t.base_end else None,
                          "uses": t.helper_uses, "each": t.helper_each}
        out.append({"id": h["id"], "name": HELPER_DE.get(name, name), "level": h["level"], "queue": q,
                    "ready": int(h["ready"]) if h.get("ready") and h["ready"] > now else None,
                    "saves": saves if q else 0, "target": target})
    return out


def gd_name(raw_static: dict, data_id: int) -> str:
    for sec in ("buildings", "traps", "troops", "spells", "heroes", "pets", "guardians"):
        for o in raw_static.get(sec, []):
            if o["_id"] == data_id:
                return o["name"]
    return f"#{data_id}"


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
        "advice": _advice(gd, v, cfg, now),
        "walls": _walls(gd, v),
        "helpers": _helpers(_raw_static(), v, now),
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
