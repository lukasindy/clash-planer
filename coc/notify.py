"""Benachrichtigungen: ntfy (Push aufs Handy), Telegram, Discord.

Aktiviert wird, was als Umgebungsvariable (GitHub-Secret) gesetzt ist:
  NTFY_TOPIC (+ optional NTFY_SERVER, NTFY_TOKEN)
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  DISCORD_WEBHOOK_URL
"""
from __future__ import annotations

import json
import os
import urllib.request


def _post(url: str, payload: dict, headers: dict | None = None) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def channels() -> list[str]:
    ch = []
    if os.environ.get("NTFY_TOPIC"):
        ch.append("ntfy")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        ch.append("telegram")
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        ch.append("discord")
    return ch


def send(title: str, message: str, tags: list[str] | None = None, priority: int = 4) -> list[str]:
    """Schickt an alle konfigurierten Kanäle. Gibt Fehlermeldungen zurück (leer = ok)."""
    errors = []
    env = os.environ
    if env.get("NTFY_TOPIC"):
        try:
            server = (env.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
            headers = {"Authorization": f"Bearer {env['NTFY_TOKEN']}"} if env.get("NTFY_TOKEN") else {}
            _post(server, {"topic": env["NTFY_TOPIC"], "title": title, "message": message,
                           "tags": tags or [], "priority": priority}, headers)
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy: {e}")
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        try:
            _post(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                  {"chat_id": env["TELEGRAM_CHAT_ID"], "text": f"{title}\n\n{message}"})
        except Exception as e:  # noqa: BLE001
            errors.append(f"telegram: {e}")
    if env.get("DISCORD_WEBHOOK_URL"):
        try:
            _post(env["DISCORD_WEBHOOK_URL"], {"content": f"**{title}**\n{message}"})
        except Exception as e:  # noqa: BLE001
            errors.append(f"discord: {e}")
    return errors
