from __future__ import annotations

import subprocess
import sys


def main() -> int:
    commands = [
        [sys.executable, "-m", "pytest"],
        [sys.executable, "-m", "ruff", "check", "."],
    ]

    for command in commands:
        proc = subprocess.run(command, check=False)
        if proc.returncode != 0:
            return proc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
