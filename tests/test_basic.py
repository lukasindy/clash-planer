"""Schnelltest mit dem Beispiel-Export:  python -m unittest discover tests"""
import json
import time
import unittest
from pathlib import Path

from coc.config import load_config
from coc.gamedata import GameData
from coc.planner import make_plan
from coc.report import plan_markdown
from coc.village import parse_export

ROOT = Path(__file__).resolve().parent.parent


class BasicTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gd = GameData.load()
        cls.cfg = load_config(str(ROOT / "config.toml"))
        raw = json.loads((ROOT / "data/village.example.json").read_text("utf-8"))
        cls.now = time.time()
        raw["timestamp"] = int(cls.now) - 3 * 3600  # Export "vor 3 Stunden"
        cls.v = parse_export(raw)

    def test_parse(self):
        self.assertEqual(self.v.th, 14)
        self.assertEqual(self.v.builders, 6)          # 5 Hütten + B.O.B
        self.assertEqual(len(self.v.active("builder")), 4)  # inkl. eines schon abgelaufenen

    def test_plan(self):
        plan = make_plan(self.gd, self.v, self.cfg, self.now)
        self.assertEqual(plan.idle_at_start["builder"], 3)
        self.assertTrue(plan.for_queue("builder"))
        self.assertTrue(plan.for_queue("lab"))
        # Nie zwei Upgrades gleichzeitig auf demselben Bauarbeiter
        by_slot = {}
        for s in plan.steps + plan.running:
            if s.queue == "builder" and s.slot >= 0:
                by_slot.setdefault(s.slot, []).append((s.start, s.end))
        for spans in by_slot.values():
            spans.sort()
            for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
                self.assertLessEqual(a1, b0 + 1)
        # Kein Upgrade startet nachts
        for s in plan.steps:
            self.assertFalse(self.cfg.asleep(s.start) and s.start > plan.start + 1, s)
        self.assertIn("Upgrade-Plan", plan_markdown(self.v, plan, self.cfg, self.now))


if __name__ == "__main__":
    unittest.main()
