"""Kommandozeile:  python -m coc <befehl>

  status          laufende Upgrades + Restzeiten + nächste Empfehlung
  plan            PLAN.md neu schreiben
  check           prüfen & benachrichtigen (läuft per GitHub Actions)
  import DATEI    neuen Export übernehmen (DATEI oder '-' für stdin)
  import-issue    Export aus einem GitHub-Issue übernehmen (Umgebungsvariable ISSUE_BODY)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .checker import effective_village, run_check
from .config import load_config
from .gamedata import GameData
from .names_de import de_name
from .planner import make_plan
from .report import plan_markdown, status_markdown
from .village import load_village, parse_export


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def _save_export(text: str, cfg) -> None:
    v = parse_export(text)  # prüft das Format
    Path(cfg.village_file).parent.mkdir(parents=True, exist_ok=True)
    raw = v.raw
    Path(cfg.village_file).write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", "utf-8")


def _settings_issue(cfg) -> int:
    """Einstellungen aus der Web-App (Issue mit {"coc_settings": {...}}) in config.toml übernehmen."""
    import re
    from .config import update_config
    body = os.environ.get("ISSUE_BODY", "")
    m = re.search(r"\{.*\}", body, re.S)
    try:
        data = json.loads(m.group(0))["coc_settings"] if m else None
        if not isinstance(data, dict):
            raise ValueError("kein coc_settings-Block")
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        Path("issue_comment.md").write_text(f"❌ Einstellungen nicht lesbar: {e}\n", "utf-8")
        return 1
    upd, lines = {}, []
    clean = lambda xs: [str(x).strip() for x in xs if str(x).strip()][:10]
    if "builder_picks" in data:
        upd["planner.books.builder_picks"] = clean(data["builder_picks"])
        lines.append(f"- 📖 Buch des Bauens: {', '.join(upd['planner.books.builder_picks']) or 'automatisch'}")
    if "heroes_picks" in data:
        upd["planner.books.heroes_picks"] = clean(data["heroes_picks"])
        lines.append(f"- 📖 Buch der Helden: {', '.join(upd['planner.books.heroes_picks']) or 'automatisch'}")
    if "lab_picks" in data:
        upd["planner.books.lab_picks"] = clean(data["lab_picks"])
        lines.append(f"- 📖 Labor-Bücher: {', '.join(upd['planner.books.lab_picks']) or 'automatisch'}")
    names = {"building": "Hammer des Bauens", "heroes": "Hammer der Helden",
             "fighting": "Hammer des Kampfes", "spells": "Hammer der Zauber"}
    for k, label in names.items():
        h = data.get("hammers", {})
        if k in h:
            n = max(0, min(int(h.get(k) or 0), 20))
            pick = str(h.get(f"{k}_pick", "") or "").strip()
            upd[f"hammers.{k}"] = n
            upd[f"hammers.{k}_pick"] = pick if n else ""
            if n:
                lines.append(f"- 🔨 {label}: {n}× → {pick or 'automatisch'}")
    update_config(cfg.path, upd)
    Path("issue_comment.md").write_text("✅ Bücher-Tag-Einstellungen übernommen:\n\n" + "\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coc", description="Clash-of-Clans-Upgrade-Planer")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--now", type=float, help="Zeitpunkt simulieren (Unix-Sekunden, zum Testen)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("plan")
    p.add_argument("--out", default="PLAN.md")
    p.add_argument("--site", default="docs/data.json")
    c = sub.add_parser("check")
    c.add_argument("--dry-run", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("file")
    sub.add_parser("import-issue")
    sub.add_parser("test-notify")
    sub.add_parser("settings-issue")
    sub.add_parser("icons")
    ai = sub.add_parser("appicon")
    ai.add_argument("--check", action="store_true", help="Exit 0, wenn ein neues Symbol nötig ist")
    args = ap.parse_args(argv)

    if args.cmd == "appicon":
        cfg = load_config(args.config)
        th = load_village(cfg.village_file).th if Path(cfg.village_file).exists() else 0
        cur = Path("docs/icon-th.txt").read_text().strip() if Path("docs/icon-th.txt").exists() else ""
        if args.check:
            return 0 if th and str(th) != cur else 1
        from .icons import make_app_icon
        ok = make_app_icon(th)
        print("App-Symbol für Rathaus", th, "erstellt" if ok else "– kein Bild gefunden")
        return 0

    if args.cmd == "icons":
        from .gamedata import load_raw
        from .icons import download_icons
        print(download_icons(load_raw()))
        return 0

    if args.cmd == "settings-issue":
        return _settings_issue(load_config(args.config))

    if args.cmd == "test-notify":
        from . import notify
        ch = notify.channels()
        if not ch:
            msg = "❌ Kein Kanal eingerichtet – Secret NTFY_TOPIC (oder Telegram/Discord) fehlt."
            print(msg); _summary(msg)
            return 1
        errs = notify.send("Clash: Test ✅", "Benachrichtigungen funktionieren! "
                           "Jetzt nur noch den ersten Export schicken.", tags=["tada"])
        msg = ("❌ Fehler: " + "; ".join(errs)) if errs else f"✅ Testnachricht gesendet über: {', '.join(ch)}"
        print(msg); _summary(msg)
        return 1 if errs else 0

    cfg = load_config(args.config)
    now = args.now or time.time()

    if args.cmd == "import":
        text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text("utf-8")
        _save_export(text, cfg)
        args.cmd = "plan"
        args.out = "PLAN.md"
    elif args.cmd == "import-issue":
        body = os.environ.get("ISSUE_BODY", "")
        try:
            _save_export(body, cfg)
        except (ValueError, json.JSONDecodeError) as e:
            Path("issue_comment.md").write_text(
                f"❌ Konnte den Export nicht lesen: {e}\n\n"
                "Bitte im Spiel *Einstellungen → Weitere Einstellungen → Datenexport → Kopieren* "
                "und den kompletten Text als Issue-Text einfügen.\n", "utf-8")
            print(f"Fehler: {e}", file=sys.stderr)
            return 1
        args.cmd = "plan"
        args.out = "PLAN.md"
        issue_mode = True
    else:
        issue_mode = False

    if not Path(cfg.village_file).exists():
        msg = (f"Noch kein Export vorhanden ({cfg.village_file}). "
               "Lege ein Issue mit deinem Export an oder kopiere ihn in diese Datei.")
        print(msg)
        _summary(msg)
        return 0

    gd = GameData.load()
    v = effective_village(cfg)
    from .checker import load_state
    used = load_state().get("books_used")
    if used:   # Bücher heute schon eingesetzt → nicht nochmal einplanen
        cfg.raw.setdefault("planner", {}).setdefault("books", {})["skip_date"] = used
    plan = make_plan(gd, v, cfg, now)

    if args.cmd == "status":
        out = status_markdown(v, plan, cfg, now)
        print(out)
        _summary(out)
    elif args.cmd == "plan":
        md = plan_markdown(v, plan, cfg, now)
        Path(args.out).write_text(md, "utf-8")
        from .site import site_data, write_site
        write_site(getattr(args, "site", "docs/data.json"), site_data(gd, v, plan, cfg, now))
        status = status_markdown(v, plan, cfg, now)
        print(status)
        _summary(status)
        if issue_mode:
            repo = os.environ.get("GITHUB_REPOSITORY", "")
            server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            link = f"{server}/{repo}/blob/HEAD/PLAN.md" if repo else "PLAN.md"
            Path("issue_comment.md").write_text(
                f"✅ Export übernommen! Ganzer Plan: [PLAN.md]({link})\n\n" + status, "utf-8")
    elif args.cmd == "check":
        names = {i.data_id: de_name(gd.name(i.data_id)) for i in v.instances}
        log = run_check(v, plan, cfg, now, names, dry_run=args.dry_run)
        status = status_markdown(v, plan, cfg, now)
        print(log)
        print(status)
        _summary(log + "\n" + status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
