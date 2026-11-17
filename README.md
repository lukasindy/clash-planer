# 🏰 Clash of Clans – Upgrade-Planer & Timer-Wächter

Läuft komplett gratis auf GitHub Actions:

- **Plan:** berechnet die beste Reihenfolge für Bauarbeiter, Labor und Begleiterhaus
  (➜ [`PLAN.md`](PLAN.md)), inklusive Startzeiten, Kosten und wann alles für dein Rathaus fertig ist.
- **Timer:** zeigt, wie lange jedes laufende Upgrade noch braucht.
- **Benachrichtigung:** Push aufs Handy, sobald ein **Bauarbeiter**, das **Labor** oder das
  **Begleiterhaus** frei wird, zusammen mit einer Empfehlung, was du als Nächstes starten solltest.

## Wie es funktioniert

Die offizielle Clash-of-Clans-API liefert **keine** Gebäudelevel und Upgrade-Timer. Das Spiel hat
aber einen eingebauten **Dorf-Export**, der alles enthält (Level + Restzeiten). Den kopierst du und
legst ihn als Issue an. Den Rest erledigt das Repo:

```
Spiel → Datenexport kopieren → neues GitHub-Issue einfügen
      → Plan wird berechnet, Issue bekommt eine Zusammenfassung
      → alle 30 Min. prüft GitHub die Timer → Push, wenn etwas frei wird
```

Kosten, Bauzeiten und Voraussetzungen kommen aus den öffentlichen Spieldaten von
[ClashKing](https://assets.clashk.ing/static_data.json) und sind damit immer aktuell.

## Einrichtung (ca. 10 Minuten)

### 1. Repo anlegen
Neues Repository auf GitHub erstellen (privat oder öffentlich) und alle Dateien dieses Ordners
hochladen. Der Export enthält nur deinen Spielertag und deine Level, nichts Geheimes.

> **Privat oder öffentlich?** Private Repos haben 2000 Gratis-Minuten pro Monat. Das reicht für
> einen Check alle 30 Minuten (Voreinstellung). Bei einem öffentlichen Repo ist es unbegrenzt,
> dann kannst du in `.github/workflows/check.yml` auf `*/10 * * * *` (alle 10 Min.) stellen.

### 2. Benachrichtigungen einrichten (ntfy, am einfachsten)
1. App **ntfy** installieren ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) /
   [iOS](https://apps.apple.com/app/ntfy/id1625396347)).
2. Ein **geheimes, langes Thema** ausdenken, z. B. `clash-max-8f3k2q9z7w`, und in der App abonnieren.
   Wer das Thema kennt, kann mitlesen, also nicht einfach `clash` nehmen.
3. Im Repo: **Settings → Secrets and variables → Actions → New repository secret**
   Name `NTFY_TOPIC`, Wert = dein Thema.

Alternativ oder zusätzlich:

| Kanal | Secrets |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Discord | `DISCORD_WEBHOOK_URL` |
| eigener ntfy-Server | `NTFY_SERVER`, optional `NTFY_TOKEN` |

### 3. Actions erlauben
Tab **Actions** öffnen und Workflows aktivieren, falls GitHub fragt. Falls später beim Speichern
ein Fehler kommt: **Settings → Actions → General → Workflow permissions → Read and write**.

### 4. Ersten Export einspielen
1. Im Spiel: **Einstellungen → Weitere Einstellungen → Datenexport → Kopieren**
2. Im Repo (geht gut in der GitHub-App): **Issues → New issue**, Titel egal (z. B. „Export“),
   den kopierten Text als Beschreibung einfügen → **Submit**.
3. Nach ca. einer Minute: Kommentar mit Status, `PLAN.md` ist aktualisiert, das Issue wird geschlossen.

## Alltag

- **Nach dem Starten neuer Upgrades einen neuen Export als Issue einspielen.** Der Export ist ein
  Schnappschuss: Läuft ein Timer ab, meldet das Repo „frei“, bis es neue Daten bekommt.
  Jede Meldung kommt pro Ereignis nur einmal.
- Nachts (Standard 23–7 Uhr) werden Meldungen bis zum Aufwachen zurückgehalten.
- Gemeldet wird schon **15 Minuten vorher** (einstellbar), weil GitHub-Zeitpläne oft etwas später laufen.
- Den aktuellen Status siehst du auch unter **Actions → Timer-Check → letzter Lauf** (Zusammenfassung).

## Einstellungen (`config.toml`)

| Einstellung | Bedeutung |
|---|---|
| `sleep_start` / `sleep_end` | Deine Schlafenszeit. Der Planer startet nachts nichts und wählt Upgrades so, dass sie möglichst nicht nachts fertig werden. |
| `[boosts]` | Goldpass-Bonus in % für Bauarbeiter/Labor/Begleiterhaus |
| `ahead_minutes` | wie früh vorher benachrichtigt wird |
| `reminder_hours` | Erinnerung, wenn etwas länger frei bleibt (0 = aus) |
| `lab_priority` | deine Wunsch-Reihenfolge fürs Labor, z. B. deine Angriffsarmee |
| `pet_priority` | Wunsch-Reihenfolge fürs Begleiterhaus |
| `[planner.tiers]` | Prioritätsstufe pro Gebäude (1 = zuerst). Voreinstellung: Armee-Gebäude & Labor → Helden → wichtige Verteidigung → Rest → Fallen → Sammler |
| `include_townhall` | Rathaus mit einplanen (ganz zum Schluss) |

Namen in der Config sind **englisch** (so heißen sie in den Spieldaten). Deutsche Anzeigenamen
stehen in `coc/names_de.py` und lassen sich dort ergänzen.

### Wie der Plan entsteht
Der Planer simuliert deine Bauarbeiter, das Labor und das Begleiterhaus in die Zukunft:
- Laufende Upgrades blockieren ihren Slot bis zum Ende.
- Freie Bauarbeiter bekommen das wichtigste Upgrade (Stufe), bei gleicher Stufe zuerst neue
  Gebäude, dann das längste Upgrade. So bleiben die Bauarbeiter am längsten beschäftigt.
- Abhängigkeiten laufen mit: ein fertiges Labor schaltet neue Forschungen frei, eine höhere
  Heldenhalle neue Heldenlevel, ein höheres Begleiterhaus neue Begleiterlevel.

## Lokal ausprobieren

```bash
python -m coc status                 # laufende Upgrades + Empfehlungen
python -m coc plan                   # PLAN.md schreiben
python -m coc check --dry-run        # Benachrichtigung testen, ohne zu senden
python -m coc import export.json     # Export aus Datei übernehmen
python -m unittest discover tests    # Tests (nutzt data/village.example.json)
```
Benötigt nur Python ≥ 3.11, keine weiteren Pakete.

## Grenzen
- Bauarbeiter-/Forschungstränke, Helfer, Juwelen und Goblin-Bauarbeiter fließen nicht in den Plan
  ein. Ein neuer Export korrigiert alles.
- Rohstoffe: Der Plan nimmt an, dass genug da ist, und listet die Gesamtkosten auf.
- Mauern sind nicht im Plan (gehen sofort, ohne Bauarbeiter). Die Bauarbeiterbasis wird nicht überwacht.
- GitHub-Zeitpläne können sich um einige Minuten verzögern. Nach 60 Tagen ohne Aktivität im Repo
  pausiert GitHub sie. Jeder neue Export zählt als Aktivität.

*Inoffizielles Fanprojekt, nicht von Supercell unterstützt oder gesponsert.*
