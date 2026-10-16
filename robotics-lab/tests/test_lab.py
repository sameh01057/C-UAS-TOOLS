"""Smoke / invariant tests for the robotics safety lab.

Lock in the properties that make the lab credible and the bugs we hit in the C-UAS lab,
so a future change can't silently break them. Run:  python -m pytest  (or python -m unittest).
"""
import unittest

import robo_lab.components as C
from robo_lab import run as R


def _run(key, n_hostile=8, n_benign=4, design=None, seeds=(7, 11, 19)):
    return R.run_api(key, n_hostile=n_hostile, n_benign=n_benign, design=design, seeds=seeds)["metrics"]


class TestCatalogAndComponents(unittest.TestCase):
    def test_component_catalog_well_formed(self):
        cat = C.catalog()
        self.assertGreater(len(cat), 12)
        groups = {c["group"] for c in cat}
        self.assertEqual(groups, {"lidar", "camera", "ranging", "marine", "response", "c2"})
        for c in cat:
            self.assertIn("id", c); self.assertIn("name", c); self.assertIn("src", c)

    def test_attack_catalog(self):
        atks = R.attack_catalog()
        self.assertGreaterEqual(len(atks), 17)
        for a in atks:
            self.assertTrue(a["key"] and a["name"])
            self.assertTrue(a["desc"], f"{a['key']} missing tooltip description")
            self.assertTrue(a["basis"], f"{a['key']} missing modelling basis")
            self.assertTrue(a["ref"], f"{a['key']} missing standard mapping")

    def test_presets_reference_real_components(self):
        ids = {c["id"] for c in C.catalog()}
        for p in R.presets():
            d = p["design"]
            for group in ("sensors", "responses", "c2"):
                for cid in d.get(group, {}):
                    self.assertIn(cid, ids, f"preset {p['name']} references unknown component {cid}")


class TestEngineInvariants(unittest.TestCase):
    def test_accounting_balances(self):
        n = 10
        m = _run("baseline", n_hostile=n, n_benign=3)
        total = m["Safely handled"] + m["Collisions"] + m["Unresolved"]
        self.assertAlmostEqual(total, n, delta=0.01)

    def test_strong_design_holds(self):
        strong = R.presets()[0]["design"]
        m = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        self.assertLessEqual(m["Collisions"], 1.5)

    def test_weak_design_collides_at_baseline(self):
        weak = R.presets()[-1]["design"]
        m = _run("baseline", n_hostile=8, n_benign=0, design=weak)
        self.assertGreater(m["Collisions"], 3)

    def test_localization_spoof_causes_collisions(self):
        strong = R.presets()[0]["design"]
        base = _run("baseline", n_hostile=10, n_benign=0, design=strong)
        gps = _run("gps", n_hostile=10, n_benign=0, design=strong)
        self.assertLess(gps["Safely handled"], base["Safely handled"])
        self.assertGreater(gps["Track gap %"], 50)

    def test_misclassification_causes_false_stops(self):
        strong = R.presets()[0]["design"]
        m = _run("class_spoof", n_hostile=8, n_benign=6, design=strong)
        self.assertGreater(m["False stops"], 0)

    def test_every_attack_moves_a_metric(self):
        # Each attack must be able to bite a VULNERABLE (standard-controller) design. A hardened
        # stack legitimately shrugs some off (e.g. malformed input is validated away) — that's a
        # defence working, not a dead attack — so we test against the weaker-but-realistic stack.
        design = R.presets()[1]["design"]   # "Warehouse AMR (typical)" — standard ROS 2 controller
        base = _run("baseline", n_hostile=10, n_benign=4, design=design)
        for a in R.attack_catalog():
            m = _run(a["key"], n_hostile=10, n_benign=4, design=design)
            moved = any(abs(m[k] - base[k]) > 1e-6 for k in base)
            self.assertTrue(moved, f"attack {a['key']} changed nothing vs baseline")

    def test_no_attack_improves_safety(self):
        # Physical invariant: an attack can never result in MORE safely-handled hazards than
        # the clean baseline (enforced by the baseline cap).
        strong = R.presets()[0]["design"]
        base = _run("baseline", n_hostile=12, n_benign=0, design=strong)
        for a in R.attack_catalog():
            m = _run(a["key"], n_hostile=12, n_benign=0, design=strong)
            self.assertLessEqual(m["Safely handled"], base["Safely handled"] + 1e-9,
                                 f"attack {a['key']} improved safety vs baseline")

    def test_averaging_is_stable(self):
        strong = R.presets()[0]["design"]
        a = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        b = _run("baseline", n_hostile=8, n_benign=0, design=strong)
        self.assertEqual(a, b)


class TestProfiles(unittest.TestCase):
    def test_default_profile_unchanged(self):
        # passing no profile and the explicit 'amr' profile must give identical results
        import robo_lab.run as RR
        amr = RR.get_profile("amr")
        none = RR.run_api("baseline", 8, 0, None, seeds=(7, 11))["metrics"]
        expl = RR.run_api("baseline", 8, 0, None, seeds=(7, 11), profile=amr)["metrics"]
        self.assertEqual(none, expl)

    def test_builtin_fishing_boat_runs_with_marine_terms(self):
        import robo_lab.run as RR
        boat = RR.get_profile("fishing_boat")
        res = RR.run_api("gps", 10, 3, boat["default_design"], seeds=(7, 11), profile=boat)
        self.assertEqual(res["terms"]["leaked"], "Collisions at sea")
        self.assertGreater(res["metrics"]["Collisions"], 0)   # spoof causes collisions at sea

    def test_register_new_robot_then_run(self):
        # a robot the lab has never seen can be added as data and run immediately
        import robo_lab.run as RR
        pid = RR.register_profile_api({"id": "test_bot", "name": "Test bot",
                                       "terms": {"leaked": "Boom"}})
        self.assertEqual(pid, "test_bot")
        prof = RR.get_profile("test_bot")
        res = RR.run_api("gps", 8, 2, None, seeds=(7, 11), profile=prof)
        self.assertEqual(res["terms"]["leaked"], "Boom")

    def test_profile_filters_components(self):
        import robo_lab.run as RR
        boat = RR.get_profile("fishing_boat")
        ids = {c["id"] for c in RR.component_catalog(boat)}
        self.assertIn("marine_radar", ids)
        self.assertNotIn("ouster_os1", ids)   # LiDAR not offered to the boat profile

    def test_import_system_with_custom_hardware(self):
        # The "import your system" path: a profile carries the customer's OWN component specs
        # inline (not in the library), and the lab runs that actual system.
        import robo_lab.run as RR
        RR.register_profile_api({
            "id": "acme_test", "name": "ACME",
            "terms": {"leaked": "ACME impact"},
            "custom_components": [
                {"id": "acme_radar", "kind": "radar", "range_m": 6000, "fov_az": 360, "min_rcs": 0.02},
                {"id": "acme_estop", "kind": "estop", "range_m": 800, "defeat": "hard"},
                {"id": "acme_c2", "kind": "c2", "resilience": 0.4},
            ],
            "default_design": {"sensors": {"acme_radar": 2}, "responses": {"acme_estop": 2}, "c2": {"acme_c2": 1}},
        })
        prof = RR.get_profile("acme_test")
        # custom components are resolvable + appear in the catalog
        ids = {c["id"] for c in RR.component_catalog(prof)}
        self.assertIn("acme_radar", ids)
        # the imported system actually runs on its own parts, and an attack bites it
        base = RR.run_api("baseline", 10, 0, prof["default_design"], seeds=(7, 11), profile=prof)["metrics"]
        gps = RR.run_api("gps", 10, 0, prof["default_design"], seeds=(7, 11), profile=prof)["metrics"]
        self.assertLessEqual(base["Collisions"], 1.5)          # sound at baseline
        self.assertGreater(gps["Collisions"], base["Collisions"])  # spoof causes impacts


if __name__ == "__main__":
    unittest.main()
