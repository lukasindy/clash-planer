# 📲 Export mit einem Tipp senden (iPhone)

Danach geht ein Export so: **Im Spiel „Datenexport → Kopieren“ → Rückseite vom iPhone doppelt antippen.**
Fertig. Du musst das Spiel nicht einmal verlassen.

## 1. GitHub-Token anlegen (einmalig, 2 Min.)

1. Öffne <https://github.com/settings/personal-access-tokens/new> (Fine-grained token).
2. **Token name:** `Clash Export` · **Expiration:** so lang wie möglich (z. B. 1 Jahr)
3. **Repository access:** *Only select repositories* → dein Clash-Repo auswählen
4. **Permissions → Repository permissions → Issues:** *Read and write*
5. **Generate token** und den Token (`github_pat_…`) kopieren. Er wird nur einmal angezeigt.

Der Token darf nur Issues in diesem einen Repo anlegen, sonst nichts.

## 2. Kurzbefehl bauen

In der App **Kurzbefehle** → **+** (neuer Kurzbefehl), dann diese Aktionen hinzufügen:

**① Zwischenablage abrufen**

**② Inhalte von URL abrufen**
- URL: `https://api.github.com/repos/lukasindy/clash-planer/issues`
- Auf den Pfeil **›** tippen, um die Optionen zu öffnen:
  - **Methode:** `POST`
  - **Header** hinzufügen:
    | Schlüssel | Text |
    |---|---|
    | `Authorization` | `Bearer github_pat_…` (dein Token) |
    | `Accept` | `application/vnd.github+json` |
  - **Anfragetext:** `JSON`, dann zwei Felder vom Typ *Text*:
    | Schlüssel | Wert |
    |---|---|
    | `title` | `Export` |
    | `body` | Variable **Zwischenablage** (antippen → „Zwischenablage“ auswählen) |

**③ Mitteilung anzeigen**: Text `Export gesendet ✅`

Oben den Namen **Clash Export** vergeben und sichern.

## 3. Auf die Rückseite legen

**Einstellungen → Bedienungshilfen → Tippen → Auf Rückseite tippen → Doppeltippen → Clash Export**

Alternativ: Kurzbefehl auf den Home-Bildschirm legen (Teilen → Zum Home-Bildschirm),
oder „Hey Siri, Clash Export“.

## Testen

Im Spiel exportieren, Rückseite doppelt antippen. Nach etwa einer Minute ist im Repo unter
**Issues** (geschlossen) ein Kommentar mit deinem Status, und `PLAN.md` ist neu.
Hat der Kurzbefehl einen Fehler gemeldet, prüfe Token, Repo-Name und Leerzeichen bei `Bearer `.
