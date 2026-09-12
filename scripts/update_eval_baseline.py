"""Regenerate the evaluation baseline from the current scenario behavior.

Run: npm run eval:update  (deliberate behavior changes only; the diff IS the
model-facing behavior change record).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "tests" / "eval"))

from test_eval_scenarios import BASELINE, SCENARIOS


def main() -> int:
    results = []
    for factory in SCENARIOS:
        with tempfile.TemporaryDirectory() as td:
            results.append(factory(Path(td)))
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps({"scenarios": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {BASELINE} ({len(results)} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
