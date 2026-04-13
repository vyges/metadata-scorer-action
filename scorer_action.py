#!/usr/bin/env python3
"""© 2026 Vyges/TrustStix Inc.
Licensed under the Apache License, Version 2.0. See LICENSE/NOTICE.

GitHub Action runner for the Vyges metadata scorer.

Reads inputs from environment variables (set by action.yml), calls
``scorer.score_metadata``, writes a job summary table, exposes outputs
via $GITHUB_OUTPUT, and exits non-zero when score < threshold.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# scorer.py lives next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scorer import DIMENSIONS, score_metadata  # noqa: E402


def _set_output(name: str, value: str) -> None:
    """Set a GitHub Actions output via $GITHUB_OUTPUT."""
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    # Use heredoc form for multi-line/JSON safety
    with open(out, "a") as f:
        f.write(f"{name}<<__EOF__\n{value}\n__EOF__\n")


def _append_summary(text: str) -> None:
    """Append markdown to the job summary panel."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    with open(summary, "a") as f:
        f.write(text + "\n")


def _tier(score: int) -> str:
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Medium"
    return "High-risk"


def main() -> int:
    file_path  = Path(os.environ.get("VYGES_SCORER_FILE", "vyges-metadata.json"))
    threshold  = int(os.environ.get("VYGES_SCORER_THRESHOLD", "0") or "0")
    write_summary = (os.environ.get("VYGES_SCORER_SUMMARY", "true").lower()
                     in ("1", "true", "yes"))

    if not file_path.exists():
        print(f"::error::metadata file not found: {file_path}")
        return 1

    try:
        md = json.loads(file_path.read_text())
    except json.JSONDecodeError as e:
        print(f"::error::failed to parse {file_path}: {e}")
        return 1

    score, breakdown, gaps = score_metadata(md)
    tier = _tier(score)

    # Outputs (always — even on threshold fail, downstream may want to read)
    _set_output("score", str(score))
    _set_output("tier", tier)
    _set_output("breakdown", json.dumps(breakdown))
    _set_output("gaps", json.dumps(gaps))

    # Console output (always visible in the action log)
    print(f"::notice file={file_path}::Vyges metadata score: {score}/100 ({tier})")
    print(f"  breakdown: {breakdown}")
    if gaps:
        print(f"  gaps ({len(gaps)}):")
        for g in gaps:
            print(f"    - {g}")

    # Job summary panel
    if write_summary:
        lines = [
            f"## Vyges metadata score: **{score}/100** ({tier})",
            "",
            f"File: `{file_path}`",
            "",
            "| Dimension | Score | Max |",
            "|---|---:|---:|",
        ]
        for name, _, max_pts in DIMENSIONS:
            lines.append(f"| {name} | {breakdown.get(name, 0)} | {max_pts} |")
        if gaps:
            lines.extend(["", "### Gaps", ""])
            lines.extend(f"- `{g}`" for g in gaps)
        else:
            lines.extend(["", "All dimensions full marks. Nice."])
        _append_summary("\n".join(lines))

    # Threshold gate
    if threshold > 0 and score < threshold:
        print(f"::error file={file_path}::"
              f"score {score} is below threshold {threshold}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
