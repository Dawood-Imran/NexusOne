#!/usr/bin/env python3
"""Refuse by default; document the explicit future live-evaluation contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.evaluator import LiveEvaluationRefused, assert_live_evaluation_enabled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-provider-run",
        action="store_true",
        help="acknowledge that a future caller has supplied an injected provider runner",
    )
    parser.parse_args()
    try:
        assert_live_evaluation_enabled()
    except LiveEvaluationRefused as exc:
        print(f"live evaluation refused: {exc}")
        return 2
    print("live evaluation contract enabled; inject a provider runner through tests.evaluation.evaluator.run_live_evaluation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
