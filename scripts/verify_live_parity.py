# -*- coding: utf-8 -*-
"""Smoke de paridad live / anti-whipsaw / estado Telegram."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tests'))

from test_live_parity import (
    TestAis11Parity,
    TestTelegramStateMachine,
)


def main():
    print("=== verify_live_parity ===")
    from utils.scanner_engine import load_ais11_params
    p = load_ais11_params()
    print(f"AIS11 params: entry={p['entry_th']} exit={p['exit_th']} weights={p['weights']}")

    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAis11Parity))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestTelegramStateMachine))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    print("OK: paridad anti-whipsaw + máquina de estados Telegram")


if __name__ == "__main__":
    main()
