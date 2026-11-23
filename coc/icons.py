"""Icons der Upgrades aus dem Clash-of-Clans-Wiki laden (einmalig) → docs/icons/<id>.<ext>

Die Bilder sind Supercell-Assets und werden unverändert für diese nicht-kommerzielle
Fan-App genutzt (Supercell Fan Content Policy). Aufruf: python -m coc icons

Auswahl je Art (feste Dateinamen im Wiki, damit es echte Icons statt Screenshots sind):
  Truppen/Helden/Begleiter: Avatar_<Name>.png → <Name>_info.png
  Zauber:                   <Name>_info.png
  Gebäude/Fallen/Wächter:   höchstes Level-Bild <Name><Level>.png (bzw. _Ground/_Single/…)
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://clashofclans.fandom.com/api.php"
UA = {"User-Agent": "clash-planer (private fan project)"}
KIND = {"buildings": "building", "traps": "building", "guardians": "building",
        "troops": "unit", "heroes": "unit", "pets": "unit", "spells": "spell"}


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _api(**params) -> dict:
    params.update(format="json")
    return json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}"))


def _file_urls(files: list[str], size: int) -> dict[str, str]:
    """Datei-Titel → Vorschau-URL (nur existierende Dateien)."""
    out = {}
    for i in range(0, len(files), 40):
        chunk = files[i:i + 40]
        d = _api(action="query", titles="|".join("File:" + f for f in chunk), prop="imageinfo",
                 iiprop="url", iiurlwidth=size)["query"]
        back = {n["to"]: n["from"] for n in d.get("normalized", [])}
        for p in d.get("pages", {}).values():
            info = (p.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            if url and "missing" not in p:
                t = back.get(p["title"], p["title"])
                out[t.replace("File:", "", 1)] = url
    return out


def _level_image(name: str) -> str | None:
    """Höchstes Level-Bild eines Gebäudes, z. B. Inferno_Tower11_Single.png."""
    base = name.replace(" ", "_")
    d = _api(action="query", list="allimages", aiprefix=base, ailimit=500)
    if not d.get("query", {}).get("allimages"):
        base = base.replace("'", "")
        d = _api(action="query", list="allimages", aiprefix=base, ailimit=500)
    best = None
    pat = re.compile(rf"^{re.escape(base)}_?(\d+)(?:_([A-Za-z0-9]+))?\.png$")
    prefer = {None: 0, "Ground": 1, "Single": 1, "Dormant": 1, "Stage1": 1, "Long": 2, "Rage": 2}
    for img in d.get("query", {}).get("allimages", []):
        m = pat.match(img["name"])
        if m and "Depleted" not in img["name"] and "pre_" not in img["name"]:
            lvl = int(m.group(1))
            pref = prefer.get(m.group(2), 3)
            key = (lvl, -pref)
            if best is None or key > best[0]:
                best = (key, img["name"])
    return best[1] if best else None


def _ext(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


ITEMS = {"book_building": "Book_of_Building.png", "book_heroes": "Book_of_Heroes.png",
         "book_fighting": "Book_of_Fighting.png", "book_spells": "Book_of_Spells.png",
         "book_everything": "Book_of_Everything.png",
         "hammer_building": "Hammer_of_Building.png", "hammer_heroes": "Hammer_of_Heroes.png",
         "hammer_fighting": "Hammer_of_Fighting.png", "hammer_spells": "Hammer_of_Spells.png",
         # Themen-Icons für die Oberfläche
         "res_gold": "Gold.png", "res_elixir": "Elixir.png", "res_dark": "Dark_Elixir.png", "res_gem": "Gem.png",
         "ui_builder": "Builder.png", "ui_research": "Research_Potion.png", "ui_pets": "Pet_Potion.png",
         "ui_builder_potion": "Builder_Potion.png", "ui_clock": "Clock_Tower10.png", "ui_wall_ring": "Wall_Ring.png",
         # Helfer
         "93000000": "Builder's_Apprentice_info.png", "93000001": "Lab_Assistant_info.png",
         "93000002": "Alchemist_info.png", "93000003": "Prospector_info1.png"}


def download_items(out_dir: str = "docs/icons", size: int = 96) -> dict:
    """Icons der Bücher und Hämmer."""
    out = Path(out_dir)
    urls = _file_urls(list(ITEMS.values()), size)
    index = {}
    for key, f in ITEMS.items():
        url = urls.get(f.replace("_", " ")) or urls.get(f)
        if not url:
            continue
        data = _get(url)
        ext = _ext(data)
        if ext:
            (out / f"{key}.{ext}").write_bytes(data)
            index[key] = f"{key}.{ext}"
    return index


def download_icons(raw: dict, out_dir: str = "docs/icons", size: int = 96) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wanted: dict[str, tuple[str, list[int]]] = {}
    for sec, kind in KIND.items():
        for obj in raw.get(sec, []):
            if obj.get("village", "home") != "home" or obj.get("is_seasonal") or obj.get("super_troop"):
                continue
            wanted.setdefault(obj["name"], (kind, []))[1].append(obj["_id"])

    # Kandidaten-Dateien je Name, in Wunschreihenfolge
    cands: dict[str, list[str]] = {}
    for name, (kind, _) in wanted.items():
        n = name.replace(" ", "_")
        if kind == "unit":
            cands[name] = [f"Avatar_{n}.png", f"Avatar_Hero_{n}.png", f"{n}_info.png", f"{n}_Icon.png"]
        elif kind == "spell":
            cands[name] = [f"{n}_info.png", f"{n}_Icon.png", f"Icon_{n}.png"]
        else:
            lvl = _level_image(name)
            cands[name] = ([lvl] if lvl else []) + [f"{n}_info.png", f"{n}.png"]
    urls = _file_urls(sorted({f for fs in cands.values() for f in fs}), size)

    for old in out.glob("*"):
        if old.suffix in (".png", ".webp", ".jpg") and old.stem[:1].isdigit():
            old.unlink()
    index, misses = {}, []
    for name, (kind, ids) in wanted.items():
        for f in cands[name]:
            url = urls.get(f.replace("_", " ")) or urls.get(f)
            if not url:
                continue
            try:
                data = _get(url)
            except Exception:  # noqa: BLE001
                continue
            ext = _ext(data)
            if not ext:
                continue
            for _id in ids:
                (out / f"{_id}.{ext}").write_bytes(data)
                index[str(_id)] = f"{_id}.{ext}"
            break
        else:
            misses.append(name)
    try:
        index.update(download_items(out_dir, size))
    except Exception:  # noqa: BLE001
        pass
    (out / "index.json").write_text(json.dumps(index, indent=0), "utf-8")
    return {"wanted": len(wanted), "found": len(wanted) - len(misses), "missing": misses}
