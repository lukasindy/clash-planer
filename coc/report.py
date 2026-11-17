"""Ausgabe als Markdown (PLAN.md, GitHub-Zusammenfassung, Issue-Kommentar)."""
from __future__ import annotations

from .config import Config
from .planner import QUEUE_LABEL, QUEUES, Plan, Step
from .village import Village

RES_SHORT = {"Gold": "Gold", "Elixir": "Elixier", "Dark Elixir": "Dunkles Elixier", "Gems": "Juwelen"}


def fmt_dur(sec: float) -> str:
    sec = max(int(sec), 0)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}T {h}h" if h else f"{d}T"
    if h:
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{m}m"


def fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} Mio".replace(".", ",").replace(",0 ", " ")
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def fmt_cost(s: Step) -> str:
    if not s.cost:
        return "–"
    return f"{fmt_num(s.cost)} {RES_SHORT.get(s.resource, s.resource)}"


def level_txt(s: Step) -> str:
    txt = "neu bauen" if s.new else f"{s.from_lvl} → {s.to_lvl}"
    return txt + (" 📖 mit Buch" if getattr(s, "book", False) else "")


def running_table(plan: Plan, cfg: Config, now: float) -> list[str]:
    out = ["| Warteschlange | Was | Level | fertig am | Restzeit |", "|---|---|---|---|---|"]
    for s in sorted(plan.running, key=lambda s: s.end):
        label = QUEUE_LABEL.get(s.queue, s.queue) + (" (Goblin)" if s.goblin else "")
        if s.assumed:
            label += " *(angenommen)*"
        rest = "✅ fertig" if s.end <= now else fmt_dur(s.end - now)
        out.append(f"| {label} | {s.name} | {s.from_lvl} → {s.to_lvl} | {cfg.fmt_time(s.end)} | {rest} |")
    if len(out) == 2:
        out.append("| – | nichts läuft | | | |")
    if any(s.assumed for s in plan.running):
        out += ["", "*angenommen* = so wie empfohlen gestartet (Plan-folgen-Modus). "
                "Anders gebaut? Einfach einen neuen Export schicken."]
    return out


def overview(v: Village, cfg: Config, now: float) -> list[str]:
    age = now - v.timestamp
    return [
        f"- **Spieler:** `{v.tag}`",
        f"- **Rathaus:** {v.th} · **Bauarbeiter:** {v.builders} · **Labor:** {v.lab_level} · "
        f"**Begleiterhaus:** {v.pet_house_level} · **Heldenhalle:** {v.hero_hall_level}",
        f"- **Export vom:** {cfg.fmt_time(v.timestamp)} (vor {fmt_dur(age)})",
    ]


def idle_lines(plan: Plan) -> list[str]:
    out = []
    for q in QUEUES:
        n = plan.idle_at_start.get(q, 0)
        if n:
            out.append(f"> ⚠️ **{QUEUE_LABEL[q]}: {n} frei!** Jetzt etwas starten.")
    return out


def steps_table(steps: list[Step], cfg: Config, limit: int, show_slot: bool) -> list[str]:
    head = "| # | Start | Was | Level | Dauer | Kosten | fertig |"
    out = [head, "|---|---|---|---|---|---|---|"]
    for n, s in enumerate(steps[:limit], 1):
        slot = f" *(B{s.slot + 1})*" if show_slot else ""
        out.append(f"| {n} | {cfg.fmt_time(s.start)} | {s.name}{slot} | {level_txt(s)} | "
                   f"{fmt_dur(s.duration)} | {fmt_cost(s)} | {cfg.fmt_time(s.end)} |")
    if len(steps) > limit:
        out.append(f"| … | | *noch {len(steps) - limit} weitere Schritte* | | | | |")
    if not steps:
        out.append("| – | | nichts mehr zu tun auf diesem Rathaus-Level 🎉 | | | | |")
    return out


def plan_markdown(v: Village, plan: Plan, cfg: Config, now: float) -> str:
    limit = int(cfg.planner.get("steps_shown", 25))
    L = [f"# 🏰 Upgrade-Plan", ""]
    L += overview(v, cfg, now)
    L += [f"- **Plan erstellt:** {cfg.fmt_time(now)}", ""]
    L += idle_lines(plan)
    L += ["", "## ⏳ Läuft gerade", ""] + running_table(plan, cfg, now)
    for q in QUEUES:
        steps = plan.for_queue(q)
        if not steps and not plan.finish(q):
            continue
        L += ["", f"## {'🔨' if q == 'builder' else '🧪' if q == 'lab' else '🐾'} {QUEUE_LABEL[q]} – nächste Schritte", ""]
        L += steps_table(steps, cfg, limit, show_slot=(q == "builder"))
    L += ["", f"## 📊 Bis alles für Rathaus {v.th} fertig ist", "",
          "| Warteschlange | Schritte | fertig ungefähr | Kosten |", "|---|---|---|---|"]
    for q in QUEUES:
        fin = plan.finish(q)
        costs = ", ".join(f"{fmt_num(c)} {RES_SHORT.get(r, r)}" for r, c in plan.costs(q).items() if c)
        L.append(f"| {QUEUE_LABEL[q]} | {len(plan.for_queue(q))} | "
                 f"{cfg.fmt_time(fin) if fin else '–'} | {costs or '–'} |")
    L += ["", "---",
          "*Zeiten ohne Bauarbeiter-/Forschungstränke, Helfer und Juwelen. Der Plan geht davon aus, "
          "dass genug Rohstoffe da sind. Nach jedem neuen Export wird er neu berechnet.*", ""]
    return "\n".join(L)


def status_markdown(v: Village, plan: Plan, cfg: Config, now: float) -> str:
    L = ["## 🏰 Clash-Status", ""] + overview(v, cfg, now) + [""] + idle_lines(plan)
    L += [""] + running_table(plan, cfg, now)
    nxt = [plan.for_queue(q)[0] for q in QUEUES if plan.for_queue(q)]
    if nxt:
        L += ["", "**Als Nächstes empfohlen:**"]
        for s in nxt:
            L.append(f"- {QUEUE_LABEL[s.queue]}: **{s.name}** {level_txt(s)} "
                     f"({fmt_dur(s.duration)}, {fmt_cost(s)}) – ab {cfg.fmt_time(s.start)}")
    return "\n".join(L) + "\n"
