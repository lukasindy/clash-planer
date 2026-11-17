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
from .village import parse_export


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coc", description="Clash-of-Clans-Upgrade-Planer")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--now", type=float, help="Zeitpunkt simulieren (Unix-Sekunden, zum Testen)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("plan")
    p.add_argument("--out", default="PLAN.md")
    c = sub.add_parser("check")
    c.add_argument("--dry-run", action="store_true")
    i = sub.add_parser("import")
    i.add_argument("file")
    sub.add_parser("import-issue")
    sub.add_parser("test-notify")
    args = ap.parse_args(argv)

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
    plan = make_plan(gd, v, cfg, now)

    if args.cmd == "status":
        out = status_markdown(v, plan, cfg, now)
        print(out)
        _summary(out)
    elif args.cmd == "plan":
        md = plan_markdown(v, plan, cfg, now)
        Path(args.out).write_text(md, "utf-8")
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
