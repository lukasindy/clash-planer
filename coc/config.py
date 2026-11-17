from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
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
    boost_schedule: list = field(default_factory=list)   # [(von_ts, bis_ts, {"builder":20,...})]

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

    # ---------- Goldpass-Boost ----------
    def boost_pct(self, q: str, ts: float) -> float:
        """Boost in % für Warteschlange q zum Zeitpunkt ts (Zeitplan schlägt Grundwert)."""
        key = {"builder": "builder_percent", "lab": "lab_percent", "pets": "pet_percent"}.get(q, "")
        pct = float(self.boosts.get(key, 0) or 0)
        # Monatsstaffel: z. B. ab Tag 1 → 10 %, ab Tag 4 → 15 %, ab Tag 8 → 20 %
        monthly = self.boosts.get("monthly") or {}
        if monthly.get("steps") and q in monthly.get("queues", ["builder", "lab", "pets"]):
            day = self._local(ts).day
            for start_day, p in sorted(monthly["steps"]):
                if day >= int(start_day):
                    pct = float(p)
        for start, end, vals in self.boost_schedule:
            if start <= ts < end and q in vals:
                pct = float(vals[q])
        return max(0.0, min(pct, 90.0))

    def boost_factor(self, q: str, ts: float) -> float:
        return 1 - self.boost_pct(q, ts) / 100

    def boost_info(self, ts: float) -> dict:
        """Aktueller und nächster Boost-Abschnitt (für Anzeige)."""
        cur = {q: self.boost_pct(q, ts) for q in ("builder", "lab", "pets")}
        until = next((e for s, e, _ in self.boost_schedule if s <= ts < e), None)
        upcoming = [(s, e, v) for s, e, v in self.boost_schedule if s > ts]
        nxt = min(upcoming, key=lambda x: x[0]) if upcoming else None
        if not nxt:
            # nächste Änderung der Monatsstaffel suchen (stundenweise, max. 40 Tage)
            t = ts
            for _ in range(40 * 24):
                t += 3600
                vals = {q: self.boost_pct(q, t) for q in ("builder", "lab", "pets")}
                if vals != cur:
                    until = until or t
                    nxt = (t, t, vals)
                    break
        return {"now": cur, "until": int(until) if until else None,
                "next": {"from": int(nxt[0]), "until": int(nxt[1]), **nxt[2]} if nxt else None}

    def fmt_time(self, ts: float) -> str:
        days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        d = self._local(ts)
        return f"{days[d.weekday()]} {d:%d.%m. %H:%M}"


def _hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _to_ts(value, tz: ZoneInfo) -> float:
    if isinstance(value, datetime):
        d = value if value.tzinfo else value.replace(tzinfo=tz)
    elif isinstance(value, date):
        d = datetime(value.year, value.month, value.day, tzinfo=tz)
    else:
        txt = str(value).strip().replace("T", " ")
        fmt = "%Y-%m-%d %H:%M" if " " in txt else "%Y-%m-%d"
        d = datetime.strptime(txt, fmt).replace(tzinfo=tz)
    return d.timestamp()


def _season_end(ts: float, tz: ZoneInfo) -> float:
    """Goldpass-Saison endet zum Monatswechsel."""
    d = datetime.fromtimestamp(ts, tz)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return datetime(y, m, 1, tzinfo=tz).timestamp()


def _schedule(raw: dict, tz: ZoneInfo) -> list:
    out = []
    for e in raw.get("boosts", {}).get("schedule", []) or []:
        if "from" not in e:
            continue
        start = _to_ts(e["from"], tz)
        end = _to_ts(e["until"], tz) if e.get("until") else _season_end(start, tz)
        vals = {q: e[k] for q, k in (("builder", "builder"), ("lab", "lab"), ("pets", "pets")) if k in e}
        out.append((start, end, vals))
    return sorted(out, key=lambda x: x[0])


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
        boost_schedule=_schedule(raw, ZoneInfo(raw.get("timezone", "Europe/Vienna"))),
    )
