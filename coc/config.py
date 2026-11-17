from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class Config:
    raw: dict
    tz: ZoneInfo
    village_file: str
    sleep_aware: bool
    sleep_start: dtime
    sleep_end: dtime
    boosts: dict = field(default_factory=dict)

    @property
    def notify(self) -> dict:
        return self.raw.get("notify", {})

    @property
    def planner(self) -> dict:
        return self.raw.get("planner", {})

    # ---------- Schlafenszeit ----------
    def _local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts, self.tz)

    def asleep(self, ts: float) -> bool:
        if not self.sleep_aware:
            return False
        t = self._local(ts).time()
        s, e = self.sleep_start, self.sleep_end
        return (s <= t < e) if s < e else (t >= s or t < e)

    def next_wake(self, ts: float) -> float:
        """Nächster Aufwachzeitpunkt nach ts (nur sinnvoll, wenn asleep(ts))."""
        d = self._local(ts)
        cand = d.replace(hour=self.sleep_end.hour, minute=self.sleep_end.minute,
                         second=0, microsecond=0)
        if cand <= d:
            cand += timedelta(days=1)
        return cand.timestamp()

    def earliest_start(self, ts: float) -> float:
        return self.next_wake(ts) if self.asleep(ts) else ts

    def sleep_waste(self, end_ts: float) -> float:
        """Sekunden, die etwas nachts fertig herumsteht, bevor du aufwachst."""
        return self.next_wake(end_ts) - end_ts if self.asleep(end_ts) else 0.0

    def fmt_time(self, ts: float) -> str:
        days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        d = self._local(ts)
        return f"{days[d.weekday()]} {d:%d.%m. %H:%M}"


def _hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def load_config(path: str = "config.toml") -> Config:
    raw = tomllib.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}
    sch = raw.get("schedule", {})
    return Config(
        raw=raw,
        tz=ZoneInfo(raw.get("timezone", "Europe/Vienna")),
        village_file=raw.get("village_file", "data/village.json"),
        sleep_aware=bool(sch.get("sleep_aware", True)),
        sleep_start=_hm(sch.get("sleep_start", "23:00")),
        sleep_end=_hm(sch.get("sleep_end", "07:00")),
        boosts=raw.get("boosts", {}),
    )
