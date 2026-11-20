// Clash-Planer – Widget für Scriptable (iOS)
// Zeigt die laufenden Upgrades mit Countdown. Daten: deine Web-App (wird nach jedem Export aktualisiert).
// Einrichtung: in der Web-App unter "Jetzt" → "Widget einrichten".

const BASE = "https://lukasindy.github.io/clash-planer/";
const C = { bg: new Color("#14110f"), panel: new Color("#201b17"), text: new Color("#f4ece1"),
            mute: new Color("#a8998a"), gold: new Color("#f2c230"), warn: new Color("#ff6b4a") };
const LABEL = { builder: "Bauarbeiter", lab: "Labor", pets: "Begleiterhaus" };
const QK = { builder: "ui_builder", lab: "ui_research", pets: "ui_pets" };

// ---------- Daten ----------
let D;
try {
  D = await new Request(BASE + "data.json?" + Date.now()).loadJSON();
} catch (e) {
  D = null;
}

// Icons zwischenspeichern, damit das Widget schnell lädt
const fm = FileManager.local();
const dir = fm.joinPath(fm.cacheDirectory(), "clash-planer-icons");
if (!fm.fileExists(dir)) fm.createDirectory(dir);
async function icon(key) {
  if (!D || !D.icons || !D.icons[key]) return null;
  const path = fm.joinPath(dir, String(key) + ".png");
  if (fm.fileExists(path)) return fm.readImage(path);
  try {
    const img = await new Request(BASE + "icons/" + D.icons[key]).loadImage();
    fm.writeImage(path, img);
    return img;
  } catch (e) { return null; }
}

// ---------- Was läuft / was ist frei ----------
function rows() {
  const now = Date.now() / 1000, out = [];
  for (const q of ["builder", "lab", "pets"]) {
    const cap = (D.capacity || {})[q] || 0;
    for (let i = 0; i < cap; i++) {
      const r = D.running.find(x => x.q === q && x.slot === i && x.end > now);
      if (r) out.push({ q, name: r.name, id: r.id, end: r.end, lvl: r.to });
      else {
        const rec = (D.steps || []).find(x => x.q === q && x.slot === i);
        out.push({ q, name: rec ? "Frei → " + rec.name : "Frei", id: rec ? rec.id : null, end: null, free: true });
      }
    }
  }
  // freie zuerst, dann nach Ende sortiert
  return out.sort((a, b) => (a.free ? 0 : 1) - (b.free ? 0 : 1) || (a.end || 0) - (b.end || 0));
}

function addTime(stack, end, size) {
  const secs = end - Date.now() / 1000;
  const d = stack.addDate(new Date(end * 1000));
  if (secs < 86400) d.applyTimerStyle(); else d.applyRelativeStyle();
  d.font = Font.boldRoundedSystemFont(size);
  d.textColor = secs < 3600 ? C.gold : C.text;
  d.rightAlignText();
  d.lineLimit = 1;
}

// ---------- Widget bauen ----------
async function build(family) {
  const w = new ListWidget();
  w.backgroundColor = C.bg;
  w.url = BASE;
  w.setPadding(12, 12, 12, 12);

  if (!D) {
    const t = w.addText("Clash-Planer: keine Daten");
    t.textColor = C.mute; t.font = Font.mediumSystemFont(12);
    return w;
  }

  const list = rows();
  const free = list.filter(r => r.free).length;
  const small = family === "small", large = family === "large";
  const max = small ? 4 : large ? 9 : 4;

  // Kopfzeile
  const head = w.addStack();
  head.centerAlignContent();
  const th = await icon("1000001");
  if (th) { const im = head.addImage(th); im.imageSize = new Size(small ? 16 : 20, small ? 16 : 20); head.addSpacer(5); }
  const title = head.addText(small ? "Clash" : "Clash-Planer");
  title.font = Font.heavyRoundedSystemFont(small ? 13 : 15); title.textColor = C.text;
  head.addSpacer();
  const st = head.addText(free ? `${free} frei!` : "alle beschäftigt");
  st.font = Font.boldRoundedSystemFont(11); st.textColor = free ? C.warn : C.mute;
  w.addSpacer(small ? 6 : 8);

  // Zeilen
  for (const r of list.slice(0, max)) {
    const row = w.addStack();
    row.centerAlignContent();
    const img = (await icon(r.id)) || (await icon(QK[r.q]));
    if (img) { const im = row.addImage(img); im.imageSize = new Size(small ? 20 : 22, small ? 20 : 22); row.addSpacer(6); }
    if (!small) {
      const n = row.addText(r.name);
      n.font = Font.semiboldRoundedSystemFont(12); n.textColor = r.free ? C.warn : C.text; n.lineLimit = 1;
      row.addSpacer(6);
    }
    row.addSpacer();
    if (r.free) {
      const f = row.addText("FREI");
      f.font = Font.heavyRoundedSystemFont(small ? 12 : 13); f.textColor = C.warn;
    } else {
      addTime(row, r.end, small ? 12 : 13);
    }
    w.addSpacer(small ? 4 : large ? 6 : 5);
  }

  // Groß: nächster Bücher-Tag
  if (large && D.bookOptions && D.bookOptions.time) {
    w.addSpacer(4);
    const b = w.addStack(); b.centerAlignContent();
    const bi = await icon("book_everything");
    if (bi) { const im = b.addImage(bi); im.imageSize = new Size(20, 20); b.addSpacer(6); }
    const bt = b.addText("Bücher-Tag");
    bt.font = Font.semiboldRoundedSystemFont(12); bt.textColor = C.gold;
    b.addSpacer();
    addTime(b, D.bookOptions.time, 13);
  }

  w.addSpacer();
  // Neu laden: spätestens wenn das nächste Upgrade fertig wird, sonst alle 30 Minuten
  const next = list.filter(r => r.end).map(r => r.end * 1000).sort((a, b) => a - b)[0];
  const in30 = Date.now() + 30 * 60 * 1000;
  w.refreshAfterDate = new Date(next ? Math.min(next + 60000, in30) : in30);
  return w;
}

const family = config.widgetFamily || "large";
const widget = await build(family);
if (config.runsInWidget) {
  Script.setWidget(widget);
} else {
  if (family === "small") await widget.presentSmall();
  else if (family === "medium") await widget.presentMedium();
  else await widget.presentLarge();
}
Script.complete();
