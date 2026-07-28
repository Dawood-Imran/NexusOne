#!/usr/bin/env python3
"""Run the offline NexusOne quality evaluation without network or services."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.evaluation.evaluator import DEFAULT_DATASET_PATH, run_deterministic_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit a machine-readable bounded report")
    args = parser.parse_args()

    report = run_deterministic_evaluation(args.dataset)
    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"dataset={report.dataset} cases={len(report.cases)} status={'PASS' if report.passed else 'FAIL'}")
        for name, totals in report.dimension_totals().items():
            print(f"{name}: {totals['passed']} passed, {totals['failed']} failed")
        for case in report.cases:
            if not case.passed:
                failed = ", ".join(item.name for item in case.dimensions if not item.passed)
                print(f"FAIL {case.case_id}: {failed}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
