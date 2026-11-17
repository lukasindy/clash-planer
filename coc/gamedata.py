"""Spieldaten (Kosten, Bauzeiten, Voraussetzungen) laden.

Quelle: die öffentliche Spieldaten-Datei von ClashKing (assets.clashk.ing),
wird lokal in .cache/ zwischengespeichert und wöchentlich erneuert.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

SOURCES = [
    "https://assets.clashk.ing/static_data.json",
    "https://assets.clashk.ing/static_data",
]
CACHE_FILE = Path(os.environ.get("COC_CACHE_DIR", ".cache")) / "static_data.json"
MAX_AGE = 7 * 24 * 3600

# Kategorien in der Spieldaten-Datei -> unsere Art
SECTIONS = {
    "buildings": "building",
    "traps": "trap",
    "troops": "unit",
    "spells": "spell",
    "heroes": "hero",
    "pets": "pet",
    "guardians": "guardian",
}


def _download() -> dict:
    last_err = None
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "coc-upgrade-planner"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Spieldaten konnten nicht geladen werden: {last_err}")


def load_raw(force: bool = False) -> dict:
    if CACHE_FILE.exists() and not force:
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age < MAX_AGE:
            return json.loads(CACHE_FILE.read_text("utf-8"))
    try:
        data = _download()
    except RuntimeError:
        if CACHE_FILE.exists():  # lieber alte Daten als gar keine
            return json.loads(CACHE_FILE.read_text("utf-8"))
        raise
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data), "utf-8")
    return data


class GameData:
    """Zugriff auf Spielobjekte über ihre Export-ID."""

    def __init__(self, raw: dict):
        self.by_id: dict[int, dict] = {}
        self.kind: dict[int, str] = {}
        for section, kind in SECTIONS.items():
            for obj in raw.get(section, []):
                self.by_id[obj["_id"]] = obj
                self.kind[obj["_id"]] = kind
        th = self.by_id.get(1000001)
        # Wie viele Gebäude/Fallen von jeder Sorte pro Rathaus-Level erlaubt sind
        self._unlocks: dict[int, dict[int, int]] = {}
        if th:
            running: dict[int, int] = {}
            for lvl in sorted(th["levels"], key=lambda l: l["level"]):
                for u in lvl.get("unlocks", []) or []:
                    running[u["_id"]] = running.get(u["_id"], 0) + int(u.get("quantity", 0))
                self._unlocks[lvl["level"]] = dict(running)

    @classmethod
    def load(cls, force: bool = False) -> "GameData":
        return cls(load_raw(force))

    def get(self, data_id: int) -> dict | None:
        return self.by_id.get(data_id)

    def name(self, data_id: int) -> str:
        obj = self.by_id.get(data_id)
        return obj["name"] if obj else f"#{data_id}"

    def level(self, data_id: int, level: int) -> dict | None:
        obj = self.by_id.get(data_id)
        if not obj:
            return None
        for l in obj.get("levels", []):
            if l.get("level") == level:
                return l
        return None

    def max_count(self, data_id: int, th_level: int) -> int:
        return self._unlocks.get(th_level, {}).get(data_id, 0)

    def allowed_ids(self, th_level: int) -> dict[int, int]:
        return self._unlocks.get(th_level, {})

    @staticmethod
    def upgrade_info(obj: dict, lvl: dict) -> tuple[int, int, str]:
        """(Dauer in s, Kosten, Rohstoff) für das Erreichen dieses Levels."""
        duration = int(lvl.get("build_time", lvl.get("upgrade_time", 0)) or 0)
        cost = lvl.get("build_cost", lvl.get("upgrade_cost", 0)) or 0
        if isinstance(cost, dict):  # z. B. Ausrüstung mit Erzen – nicht relevant
            cost = 0
        res = lvl.get("upgrade_resource") or obj.get("upgrade_resource") or "?"
        return duration, int(cost), res
