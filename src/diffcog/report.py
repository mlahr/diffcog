from __future__ import annotations

import json
from typing import Any

from diffcog.models import AnalysisResult, Thresholds


def format_text(result: AnalysisResult, thresholds: Thresholds, details: bool = False) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
    ]

    if result.files:
        lines.append(f"Java files changed: {len(result.files)}")
    else:
        lines.append("No Java changes found.")

    lines.extend(
        [
            f"New complexity: +{result.new_complexity}",
            f"Removed complexity: -{result.removed_complexity}",
            f"Net delta: {_format_signed(result.net_delta)}",
        ]
    )

    if details and result.files:
        lines.extend(["", "Changed Java files:"])
        lines.extend(f"  {_format_changed_file(file.status, file.old_path, file.path)}" for file in result.files)

    if result.threshold_failed(thresholds):
        lines.extend(["", "Threshold failed."])

    return "\n".join(lines) + "\n"


def format_json(result: AnalysisResult, thresholds: Thresholds) -> str:
    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "files": [
            {
                "status": file.status,
                "path": file.path,
                "old_path": file.old_path,
            }
            for file in result.files
        ],
        "new_complexity": result.new_complexity,
        "removed_complexity": result.removed_complexity,
        "net_delta": result.net_delta,
        "thresholds": {
            "max_new": thresholds.max_new,
            "max_delta": thresholds.max_delta,
        },
        "threshold_failed": result.threshold_failed(thresholds),
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _format_signed(value: int) -> str:
    if value >= 0:
        return f"+{value}"
    return str(value)


def _format_changed_file(status: str, old_path: str, path: str) -> str:
    if status.startswith("R") or status.startswith("C"):
        return f"{status} {old_path} -> {path}"
    return f"{status} {path}"
