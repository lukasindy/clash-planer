# 🏰 Clash of Clans – Upgrade-Planer & Timer-Wächter

Läuft komplett gratis auf GitHub Actions:

- **Plan:** berechnet die beste Reihenfolge für Bauarbeiter, Labor und Begleiterhaus
  (➜ [`PLAN.md`](PLAN.md)), inklusive Startzeiten, Kosten und wann alles für dein Rathaus fertig ist.
- **Timer:** zeigt, wie lange jedes laufende Upgrade noch braucht.
- **Benachrichtigung:** Push aufs Handy, sobald ein **Bauarbeiter**, das **Labor** oder das
  **Begleiterhaus** frei wird, zusammen mit einer Empfehlung, was du als Nächstes starten solltest.
- **Web-App:** <https://lukasindy.github.io/clash-planer/>, mit Live-Countdowns, Fortschrittsbalken,
  Zeitleiste und nächsten Schritten. Am iPhone in Safari öffnen → Teilen → *Zum Home-Bildschirm*.
- **Plan-folgen-Modus:** Das Repo geht davon aus, dass du die Empfehlung startest, und rechnet
  selbst weiter. Einen neuen Export brauchst du nur, wenn du vom Plan abweichst.

## Wie es funktioniert

Die offizielle Clash-of-Clans-API liefert **keine** Gebäudelevel und Upgrade-Timer. Das Spiel hat
aber einen eingebauten **Dorf-Export**, der alles enthält (Level + Restzeiten). Den kopierst du und
legst ihn als Issue an. Den Rest erledigt das Repo:

```
Spiel → Datenexport kopieren → iPhone-Rückseite doppelt antippen (Kurzbefehl legt das Issue an)
      → Plan wird berechnet
      → alle 10 Min. prüft GitHub die Timer → Push „Bauarbeiter frei – Empfehlung: …“
      → du startest die Empfehlung im Spiel → das Repo rechnet selbst weiter
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

### 4. Kurzbefehl einrichten & ersten Export senden
Anleitung: [`KURZBEFEHL-iOS.md`](KURZBEFEHL-iOS.md). Danach:
1. Im Spiel: **Einstellungen → Weitere Einstellungen → Datenexport → Kopieren**
2. iPhone-Rückseite doppelt antippen
3. Nach ca. einer Minute: `PLAN.md` ist aktualisiert, freie Bauarbeiter werden sofort gemeldet.

Ohne Kurzbefehl geht es auch von Hand: **Issues → New issue**, Export als Beschreibung einfügen.

## Alltag

- **Push kommt → Empfehlung im Spiel starten → fertig.** Das Repo nimmt an, dass du genau das
  gestartet hast, und meldet sich, wenn es fertig ist. Im Plan steht es als *(angenommen)*.
- **Abgewichen?** Etwas anderes gebaut, Trank oder Juwelen benutzt: Export kopieren und Kurzbefehl
  tippen. Der Export ersetzt alle Annahmen, danach ist alles wieder exakt.
- Nach 7 Tagen ohne Export erinnert dich das Repo an einen Abgleich (einstellbar).
- Jede Meldung kommt pro Ereignis nur einmal.
- Meldungen kommen rund um die Uhr. Mit `quiet_at_night = true` werden sie in der Schlafenszeit bis zum Aufwachen zurückgehalten.
- Gemeldet wird schon **15 Minuten vorher** (einstellbar), weil GitHub-Zeitpläne oft etwas später laufen.
- Den aktuellen Status siehst du auch unter **Actions → Timer-Check → letzter Lauf** (Zusammenfassung).

## Einstellungen (`config.toml`)

| Einstellung | Bedeutung |
|---|---|
| `sleep_start` / `sleep_end` | Deine Schlafenszeit. Der Planer startet nachts nichts und wählt Upgrades so, dass sie möglichst nicht nachts fertig werden. |
| `[boosts]` + `[[boosts.schedule]]` | Goldpass-Boost (senkt Zeit + Kosten), auch als Zeitplan „ab Tag X“. Gilt für Upgrades, die ab dann starten |
| `follow_plan` | Plan-folgen-Modus an/aus |
| `stale_export_days` | Erinnerung an einen Abgleich-Export nach X Tagen |
| `ahead_minutes` | wie früh vorher benachrichtigt wird |
| `reminder_hours` | Erinnerung, wenn etwas länger frei bleibt (0 = aus) |
| `lab_priority` | deine Wunsch-Reihenfolge fürs Labor, z. B. deine Angriffsarmee |
| `pet_priority` | Wunsch-Reihenfolge fürs Begleiterhaus |
| `[planner.tiers]` | Prioritätsstufe pro Gebäude (1 = zuerst). Voreinstellung: Armee-Gebäude & Labor → Helden → wichtige Verteidigung → Rest → Fallen → Sammler |
| `include_townhall` | Rathaus mit einplanen (ganz zum Schluss) |
| `[planner.cwl]` | Helden nie während der CWL im Upgrade (Standard: 1.–11. jedes Monats) |
| `[planner.books]` | Bücher-Tag: 1 Bauarbeiter + Labor sind am 1. frei, Bücher für deine Wünsche (`builder_picks`, `lab_picks`) oder sonst die längsten Upgrades, Push um 7:00 |
| `[hammers]` | Hämmer, die du hast (+ optional Ziel). Werden am Bücher-Tag eingeplant und danach automatisch abgezogen |

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
- Ein vollautomatisches Auslesen ohne Export gibt es nicht. Die offizielle API kennt keine Gebäude
  und keine Timer, und Tools, die das Spiel fernsteuern, verstoßen gegen Supercells Regeln.
- Bauarbeiter-/Forschungstränke, Helfer, Juwelen und Goblin-Bauarbeiter fließen nicht in den Plan
  ein. Ein neuer Export korrigiert alles.
- Im Plan-folgen-Modus nimmt das Repo als Startzeit den Moment der Benachrichtigung. Startest du
  deutlich später, kommt die nächste Meldung entsprechend etwas zu früh.
- Rohstoffe: Der Plan nimmt an, dass genug da ist, und listet die Gesamtkosten auf.
- Mauern sind nicht im Plan (gehen sofort, ohne Bauarbeiter). Die Bauarbeiterbasis wird nicht überwacht.
- GitHub-Zeitpläne können sich um einige Minuten verzögern. Nach 60 Tagen ohne Aktivität im Repo
  pausiert GitHub sie. Jeder neue Export zählt als Aktivität.

*Dieses Material ist nicht offiziell und nicht von Supercell bewilligt. Weitere Informationen finden Sie in Supercells
Richtlinien für Fan-Content unter https://supercell.com/en/fan-content-policy/de. Icons: Clash of Clans © Supercell,
unverändert über das Clash of Clans Wiki (`python -m coc icons`, monatlich automatisch).*
