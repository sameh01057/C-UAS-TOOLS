"""Smoke / invariant tests for the C-UAS lab.

These lock in the properties that make the lab credible and the bugs we actually hit,
so a future change can't silently break them. Run:  python -m pytest  (or python -m unittest).
"""
import unittest

import cuas_lab.components as C
from cuas_lab import run as R


def _run(key, n_hostile=8, n_benign=4, design=None, seeds=(7, 11, 19)):
    """Thin wrapper: always keyword args (positional arg-order was a recurring foot-gun)."""
    return R.run_api(key, n_hostile=n_hostile, n_benign=n_benign, design=design, seeds=seeds)["metrics"]


class TestCatalogAndComponents(unittest.TestCase):
    def test_component_catalog_nonempty_and_well_formed(self):
        cat = C.catalog()
        self.assertGreater(len(cat), 20)                       # library is substantial
        groups = {c["group"] for c in cat}
        self.assertEqual(groups, {"radar", "rf", "eo_acoustic", "effector", "c2"})
        for c in cat:
            self.assertIn("id", c)
            self.assertIn("name", c)
            self.assertIn("src", c)                            # every entry must cite a source

    def test_attack_catalog(self):
        atks = R.attack_catalog()
        self.assertGreaterEqual(len(atks), 17)
        for a in atks:
            self.assertTrue(a["key"] and a["name"])
            self.assertTrue(a["desc"], f"{a['key']} missing tooltip description")

    def test_presets_reference_real_components(self):
        ids = {c["id"] for c in C.catalog()}
        for p in R.presets():
            self.assertIn("name", p)
            d = p["design"]
            for group in ("sensors", "effectors", "c2"):
                for cid in d.get(group, {}):
                    self.assertIn(cid, ids, f"preset {p['name']} references unknown component {cid}")


class TestEngineInvariants(unittest.TestCase):
    def test_accounting_balances(self):
        # Neutralised + Leaked + In flight must equal the hostile count (the "19 not 20" bug).
        n_hostile = 10
        m = _run("baseline", n_hostile=n_hostile, n_benign=3)
        total = m["Neutralised"] + m["Leaked"] + m["In flight"]
        self.assertAlmostEqual(total, n_hostile, delta=0.01)

    def test_baseline_sound_design_holds(self):
        # A strong layered design should neutralise ~everything at baseline (no attack).
        strong = R.presets()[0]["design"]            # "Strong (layered)"
        m = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        self.assertLessEqual(m["Leaked"], 1.5)

    def test_weak_design_leaks_even_at_baseline(self):
        # The weak preset (120deg radar + nets + legacy C2) should fail on its own.
        weak = R.presets()[-1]["design"]             # "Weak (single narrow radar)"
        m = _run("baseline", n_hostile=8, n_benign=0, design=weak)
        self.assertGreater(m["Leaked"], 3)

    def test_gps_spoof_breaks_the_kill_chain(self):
        # The headline result: GPS/position offset must devastate a sound design.
        strong = R.presets()[0]["design"]
        base = _run("baseline", n_hostile=10, n_benign=0, design=strong)
        gps = _run("gps", n_hostile=10, n_benign=0, design=strong)
        self.assertLess(gps["Neutralised"], base["Neutralised"])   # fewer kills
        self.assertGreater(gps["Track gap %"], 50)                 # tracking collapses

    def test_flood_generates_false_tracks(self):
        strong = R.presets()[0]["design"]
        flood = _run("flood", n_hostile=10, n_benign=0, design=strong)
        self.assertGreater(flood["False tracks"], 0)

    def test_every_attack_moves_a_metric(self):
        # No attack should be a no-op: each must change at least one metric vs baseline.
        strong = R.presets()[0]["design"]
        base = _run("baseline", n_hostile=10, n_benign=4, design=strong)
        for a in R.attack_catalog():
            m = _run(a["key"], n_hostile=10, n_benign=4, design=strong)
            moved = any(abs(m[k] - base[k]) > 1e-6 for k in base)
            self.assertTrue(moved, f"attack {a['key']} changed nothing vs baseline")

    def test_no_attack_improves_the_defence(self):
        # Physical invariant: an attack can only ever HARM the defence. No attack may show
        # more real neutralisations than the clean baseline (enforced by the baseline cap).
        strong = R.presets()[0]["design"]
        base = _run("baseline", n_hostile=12, n_benign=0, design=strong)
        for a in R.attack_catalog():
            m = _run(a["key"], n_hostile=12, n_benign=0, design=strong)
            self.assertLessEqual(m["Neutralised"], base["Neutralised"] + 1e-9,
                                 f"attack {a['key']} increased real kills vs baseline")

    def test_averaging_is_stable(self):
        # Seed-averaged baseline should not swing wildly between calls (determinism).
        strong = R.presets()[0]["design"]
        a = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        b = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        self.assertEqual(a, b)   # same seeds -> identical result


if __name__ == "__main__":
    unittest.main()
