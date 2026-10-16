#!/usr/bin/env python
"""One-command pre-demo check for the robotics safety lab.

    python check.py            # fast smoke check (quick subset) — run this before any demo
    python check.py --full     # the whole invariant suite (slower; what CI runs)

Exits non-zero on any failure so it can gate a demo or a commit.
"""
import sys
import unittest


def main():
    full = "--full" in sys.argv
    loader = unittest.TestLoader()
    if full:
        suite = loader.loadTestsFromName("tests.test_lab")
        label = "FULL invariant suite"
    else:
        from tests.test_lab import TestCatalogAndComponents, TestEngineInvariants
        names = [
            (TestCatalogAndComponents, "test_component_catalog_well_formed"),
            (TestCatalogAndComponents, "test_attack_catalog"),
            (TestCatalogAndComponents, "test_presets_reference_real_components"),
            (TestEngineInvariants, "test_accounting_balances"),
            (TestEngineInvariants, "test_localization_spoof_causes_collisions"),
        ]
        suite = unittest.TestSuite(cls(method) for cls, method in names)
        label = "FAST pre-demo check"

    print(f"\nRobotics Safety Lab — {label}\n" + "-" * 40)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    ok = result.wasSuccessful()
    print("\n" + ("PASS — safe to demo." if ok else "FAIL — do not demo until fixed."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
