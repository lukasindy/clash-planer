"""Deutsche Anzeigenamen. Alles, was hier fehlt, erscheint mit dem englischen Namen.

Du kannst jederzeit Einträge ergänzen oder ändern – sie dienen nur der Anzeige.
In config.toml werden immer die englischen Namen verwendet.
"""

DE = {
    # Gebäude
    "Army Camp": "Armeelager",
    "Town Hall": "Rathaus",
    "Elixir Collector": "Elixiersammler",
    "Elixir Storage": "Elixierlager",
    "Gold Mine": "Goldmine",
    "Gold Storage": "Goldlager",
    "Barracks": "Kaserne",
    "Laboratory": "Labor",
    "Cannon": "Kanone",
    "Archer Tower": "Bogenschützenturm",
    "Wall": "Mauer",
    "Wizard Tower": "Magierturm",
    "Air Defense": "Luftabwehr",
    "Mortar": "Mörser",
    "Clan Castle": "Clanburg",
    "Builder's Hut": "Bauarbeiterhütte",
    "Hidden Tesla": "Verborgene Tesla",
    "Spell Factory": "Zauberfabrik",
    "X-Bow": "X-Bogen",
    "Dark Elixir Drill": "Dunkler-Elixier-Bohrer",
    "Dark Elixir Storage": "Dunkles-Elixier-Lager",
    "Dark Barracks": "Dunkle Kaserne",
    "Inferno Tower": "Inferno-Turm",
    "Air Sweeper": "Luftfeger",
    "Dark Spell Factory": "Dunkle Zauberfabrik",
    "Eagle Artillery": "Adlerartillerie",
    "Bomb Tower": "Bombenturm",
    "Workshop": "Werkstatt",
    "Pet House": "Begleiterhaus",
    "Blacksmith": "Schmiede",
    "Hero Hall": "Heldenhalle",
    "Spell Tower": "Zauberturm",
    "Monolith": "Monolith",
    # Fallen
    "Bomb": "Bombe",
    "Spring Trap": "Sprungfeder",
    "Air Bomb": "Luftbombe",
    "Giant Bomb": "Riesenbombe",
    "Seeking Air Mine": "Suchende Luftmine",
    "Skeleton Trap": "Skelettfalle",
    "Tornado Trap": "Tornadofalle",
    # Helden
    "Barbarian King": "Barbarenkönig",
    "Archer Queen": "Bogenschützenkönigin",
    "Grand Warden": "Großer Wächter",
    # Zauber
    "Lightning Spell": "Blitzzauber",
    "Healing Spell": "Heilzauber",
    "Rage Spell": "Wutzauber",
    "Jump Spell": "Sprungzauber",
    "Freeze Spell": "Frostzauber",
    "Clone Spell": "Klonzauber",
    "Poison Spell": "Giftzauber",
    "Earthquake Spell": "Erdbebenzauber",
    "Haste Spell": "Eilzauber",
    "Skeleton Spell": "Skelettzauber",
    "Bat Spell": "Fledermauszauber",
    "Invisibility Spell": "Unsichtbarkeitszauber",
    # Truppen
    "Barbarian": "Barbar",
    "Archer": "Bogenschützin",
    "Goblin": "Kobold",
    "Giant": "Riese",
    "Wall Breaker": "Mauerbrecher",
    "Balloon": "Ballon",
    "Wizard": "Magier",
    "Healer": "Heilerin",
    "Dragon": "Drache",
    "Minion": "Lakai",
    "Hog Rider": "Schweinereiter",
    "Valkyrie": "Walküre",
    "Witch": "Hexe",
    "Lava Hound": "Lavahund",
    "Baby Dragon": "Babydrache",
    "Miner": "Schürfer",
    "Electro Dragon": "Elektrodrache",
}


def de_name(name: str) -> str:
    return DE.get(name, name)
