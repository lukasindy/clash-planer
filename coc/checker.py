"""Prüft, ob Bauarbeiter, Labor oder Begleiterhaus frei sind/werden, und benachrichtigt.

Jedes Ereignis wird nur einmal gemeldet (gemerkt in state/notify_state.json).
Weil der Export ein Schnappschuss ist, gilt: Ein Upgrade, dessen Timer abgelaufen ist,
bedeutet "dieser Slot ist jetzt frei" – bis du einen neuen Export einspielst.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import notify
from .config import Config
from .planner import QUEUE_LABEL, Plan
from .report import fmt_cost, fmt_dur, level_txt
from .village import Village, apply_assumptions, load_village

STATE_FILE = Path("state/notify_state.json")
REMINDER_LINE = "Falls du schon etwas gestartet hast: bitte neuen Export einspielen."
ICON = {"builder": "🔨", "lab": "🧪", "pets": "🐾"}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text("utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", "utf-8")


def follow_mode(cfg: Config) -> bool:
    return bool(cfg.notify.get("follow_plan", True))


def effective_village(cfg: Config) -> Village:
    """Export + (im Plan-folgen-Modus) alle seitdem angenommenen Upgrades."""
    v = load_village(cfg.village_file)
    st = load_state()
    if follow_mode(cfg) and st.get("export_ts") == v.timestamp:
        apply_assumptions(v, st.get("assumed", []))
    return v


def enabled_queues(cfg: Config) -> list[str]:
    n = cfg.notify
    return [q for q, key in (("builder", "builders"), ("lab", "lab"), ("pets", "pets"))
            if n.get(key, True)]


def collect_events(v: Village, cfg: Config, now: float) -> dict[str, list[tuple[str, float, str]]]:
    """Pro Warteschlange: Liste (Schlüssel, Zeitpunkt frei, Beschreibung) aller fälligen Ereignisse."""
    ahead = float(cfg.notify.get("ahead_minutes", 0)) * 60
    out: dict[str, list] = {}
    for q in enabled_queues(cfg):
        cap = v.capacity(q)
        if cap == 0:
            continue
        active = sorted(v.active(q), key=lambda i: i.end)
        evs = []
        for n in range(max(cap - len(active), 0)):
            evs.append((f"{q}:free:{n}", v.timestamp, "war schon beim Export frei"))
        for inst in active:
            if inst.end <= now + ahead:
                evs.append((f"{q}:end:{int(inst.end)}:{inst.uid}", inst.end, f"#{inst.data_id}:{inst.level}"))
        if evs:
            out[q] = evs
    return out


def soon_events(v: Village, cfg: Config, now: float) -> list[tuple[str, str, object]]:
    """Upgrades, die innerhalb der Vorwarnzeit (Standard 60 Min.) fertig werden."""
    soon = float(cfg.notify.get("soon_minutes", 60)) * 60
    if soon <= 0:
        return []
    out = []
    for q in enabled_queues(cfg):
        for inst in v.active(q):
            if now < inst.end <= now + soon:
                out.append((f"soon:{q}:{int(inst.end)}:{inst.uid}", q, inst))
    return sorted(out, key=lambda e: e[2].end)


def _soon_message(evs, plan: Plan, cfg: Config, now: float, names: dict[int, str]) -> list[str]:
    lines = []
    for key, q, inst in evs:
        nm = names.get(inst.data_id, f"#{inst.data_id}")
        lines.append(f"{ICON[q]} {QUEUE_LABEL[q]}: {nm} → {inst.level + 1} fertig um "
                     f"{cfg.fmt_time(inst.end)[-5:]} (in {fmt_dur(inst.end - now)})")
        nxt = next((r for r in plan.for_queue(q) if r.start >= inst.end - 300), None)
        if nxt:
            lines.append(f"   ⏭️ Danach: {nxt.name} {level_txt(nxt)} ({fmt_dur(nxt.duration)}, {fmt_cost(nxt)})")
    lines += ["", "Tipp: Rohstoffe jetzt noch sammeln, falls sie nicht reichen."]
    return lines


def run_check(v: Village, plan: Plan, cfg: Config, now: float, names: dict[int, str],
              dry_run: bool = False) -> str:
    state = load_state()
    if state.get("export_ts") != v.timestamp:
        state = {"export_ts": v.timestamp, "sent": {}, "recommended": [], "assumed": [],
                 "last_reminder": 0, "stale_warned": False, "books_used": state.get("books_used")}
    sent: dict = state.setdefault("sent", {})
    nconf = cfg.notify
    quiet = bool(nconf.get("quiet_at_night", True)) and cfg.asleep(now)

    # 1) Vorwarnung (z. B. 1 Stunde vorher)
    soon_new = [e for e in soon_events(v, cfg, now) if e[0] not in sent]
    soon_log = None
    if soon_new and not quiet:
        stitle = "Clash: In " + fmt_dur(min(e[2].end for e in soon_new) - now) + " frei – " + \
                 " & ".join(dict.fromkeys(QUEUE_LABEL[e[1]] for e in soon_new))
        smsg = "\n".join(_soon_message(soon_new, plan, cfg, now, names))
        soon_log = f"**Vorwarnung:** {stitle}\n\n```\n{smsg}\n```"
        if not dry_run:
            errs = notify.send(stitle, smsg, tags=["alarm_clock"], priority=3)
            if errs:
                soon_log += "\n\nFehler beim Senden: " + "; ".join(errs)
        for key, *_ in soon_new:
            sent[key] = now

    # 1b) Bücher-Tag am Monatsanfang
    book_steps = [r for r in plan.steps if r.book and r.start <= now + 120]
    today = cfg._local(now).strftime("%Y-%m-%d")
    if book_steps and state.get("books_used") != today and not quiet:
        blines = []
        for r in book_steps:
            book = "Buch des Bauens" if r.queue == "builder" else "Labor-Buch"
            blines.append(f"{ICON[r.queue]} {book}: {r.name} {r.from_lvl} → {r.to_lvl} ({fmt_cost(r)})")
        saved = sum(plan.book_savings[:len(book_steps)])
        blines += ["", f"Upgrade starten → sofort Buch einsetzen. Spart zusammen ca. {fmt_dur(saved)}."]
        btitle = "📖 Clash: Bücher-Tag!"
        bmsg = "\n".join(blines)
        soon_log = (soon_log + "\n\n" if soon_log else "") + f"**Bücher-Tag:**\n\n```\n{bmsg}\n```"
        if not dry_run:
            notify.send(btitle, bmsg, tags=["books"], priority=4)
        state["books_used"] = today
        if follow_mode(cfg):
            for r in book_steps:   # sofort fertig → gilt als erledigt
                state.setdefault("assumed", []).append({
                    "uid": r.uid, "data_id": r.data_id, "section": r.section, "queue": r.queue,
                    "from_lvl": r.from_lvl, "start": now, "end": now, "name": r.name})
                sent[f"{r.queue}:end:{int(now)}:{r.uid}"] = now

    # 2) Wirklich frei
    events = collect_events(v, cfg, now)
    new: dict[str, list] = {q: [e for e in evs if e[0] not in sent] for q, evs in events.items()}
    new = {q: evs for q, evs in new.items() if evs}

    lines: list[str] = []
    log: list[str] = []
    recommended = set(state.setdefault("recommended", []))
    new_recs: list = []
    for q, evs in new.items():
        parts = []
        n_free = sum(1 for e in evs if not e[2].startswith("#"))
        if n_free:
            parts.append("1 war schon beim Export frei" if n_free == 1
                         else f"{n_free} waren schon beim Export frei")
        for key, when, desc in evs:
            if desc.startswith("#"):
                data_id, lvl = desc[1:].split(":")
                nm = names.get(int(data_id), f"#{data_id}")
                parts.append(f"{nm} → {int(lvl) + 1} " + ("fertig" if when <= now else f"in {fmt_dur(when - now)} fertig"))
        lines.append(f"{ICON[q]} {QUEUE_LABEL[q]}: " + "; ".join(parts))
        # Empfehlungen: die nächsten Plan-Schritte, die noch nicht empfohlen wurden
        recs = [r for r in plan.for_queue(q)
                if f"{r.uid}:{r.to_lvl}" not in recommended and not r.book][:len(evs)]
        for r in recs:
            lines.append(f"   👉 Empfehlung: {r.name} {level_txt(r)} ({fmt_dur(r.duration)}, {fmt_cost(r)})")
            new_recs.append(r)

    title = None
    if lines and not quiet:
        title = "Clash: " + " & ".join(QUEUE_LABEL[q] for q in new) + " frei!"
        if follow_mode(cfg) and new_recs:
            lines.append("")
            lines.append("Anders gebaut oder Trank benutzt? Export kopieren & Kurzbefehl tippen.")
    elif not lines:
        # Erinnerung, falls etwas weiter untätig ist
        rh = float(nconf.get("reminder_hours", 0))
        idle_now = [q for q in enabled_queues(cfg)
                    if v.capacity(q) - sum(1 for i in v.active(q) if i.end > now) > 0]
        if rh > 0 and idle_now and now - state.get("last_reminder", 0) >= rh * 3600 and not cfg.asleep(now):
            title = "Clash: Erinnerung – " + " & ".join(QUEUE_LABEL[q] for q in idle_now) + " noch frei"
            lines = [REMINDER_LINE]
            state["last_reminder"] = now

    stale_days = float(nconf.get("stale_export_days", 7))
    stale_msg = None
    if stale_days and now - v.timestamp > stale_days * 86400 and not state.get("stale_warned") and not quiet:
        stale_msg = (f"Dein letzter Export ist {fmt_dur(now - v.timestamp)} alt. Zeit für einen "
                     "Abgleich: Export kopieren & Kurzbefehl tippen.")

    if soon_log:
        log.append(soon_log)
    if title:
        msg = "\n".join(lines)
        log.append(f"**Benachrichtigung:** {title}\n\n```\n{msg}\n```")
        if not dry_run:
            errs = notify.send(title, msg, tags=["crossed_swords"])
            if errs:
                log.append("Fehler beim Senden: " + "; ".join(errs))
            if not notify.channels():
                log.append("⚠️ Kein Benachrichtigungskanal eingerichtet (Secrets NTFY_TOPIC usw.).")
        for evs in new.values():
            for key, *_ in evs:
                sent[key] = now
        state["recommended"] = sorted(recommended | {f"{r.uid}:{r.to_lvl}" for r in new_recs})
        if follow_mode(cfg) and lines and lines[0] != REMINDER_LINE:
            # Plan-folgen-Modus: wir gehen davon aus, dass du die Empfehlungen startest
            for r in new_recs:
                st = r.start
                # Nachts benachrichtigt (Nachtruhe aus) → du startest wohl gleich, nicht erst morgens
                if not nconf.get("quiet_at_night", True) and cfg.asleep(now) and st > now:
                    st = now
                state.setdefault("assumed", []).append({
                    "uid": r.uid, "data_id": r.data_id, "section": r.section, "queue": r.queue,
                    "from_lvl": r.from_lvl, "start": st, "end": st + r.duration, "name": r.name})
    elif quiet and new:
        log.append("🌙 Schlafenszeit – Benachrichtigung wird beim Aufwachen geschickt.")
    elif not soon_log:
        log.append("Nichts Neues zu melden.")

    if stale_msg:
        log.append(f"**Hinweis:** {stale_msg}")
        if not dry_run:
            notify.send("Clash: Export veraltet", stale_msg, tags=["hourglass"], priority=3)
        state["stale_warned"] = True

    if not dry_run:
        save_state(state)
    return "\n\n".join(log) + "\n"
