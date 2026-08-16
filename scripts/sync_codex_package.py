#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Regenerate the skills inside the Codex distribution package.

The canonical skills live once, at `skills/`. Codex installs plugins through a
marketplace, and a marketplace entry cannot point at the repository root
(openai/codex#17066), so the Codex package has to be a subdirectory with its own
copy of the skill files.

That copy is a build artifact, not a second source of truth: this script writes
it, and `scripts/validate_codex_plugin.py` fails if it ever differs from the
canonical skills. Edit `skills/`, never the copy.

    python scripts/sync_codex_package.py          # write the copy
    python scripts/sync_codex_package.py --check  # verify only, change nothing
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

CANONICAL = Path("skills")
CODEX_PACKAGE = Path("com.openai.codex") / "weave"


def relative_files(root: Path) -> set[Path]:
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


def main() -> int:
    check_only = "--check" in sys.argv
    root = Path(__file__).resolve().parent.parent
    source = root / CANONICAL
    target = root / CODEX_PACKAGE / "skills"

    if not source.is_dir():
        print(f"canonical skills directory is missing: {source}")
        return 1

    wanted = relative_files(source)
    present = relative_files(target) if target.is_dir() else set()

    differences: list[str] = []
    for relative in sorted(wanted):
        src, dst = source / relative, target / relative
        if not dst.is_file() or not filecmp.cmp(src, dst, shallow=False):
            differences.append(f"out of date: {CODEX_PACKAGE / 'skills' / relative}")
    for relative in sorted(present - wanted):
        differences.append(f"stale: {CODEX_PACKAGE / 'skills' / relative}")

    if check_only:
        if differences:
            print("The Codex package copy does not match the canonical skills:")
            for line in differences:
                print(f"  - {line}")
            print("\nRun: python scripts/sync_codex_package.py")
            return 1
        print(f"Codex package skills match the canonical skills ({len(wanted)} files).")
        return 0

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    if differences:
        print(f"Regenerated {CODEX_PACKAGE / 'skills'} from {CANONICAL} ({len(wanted)} files).")
    else:
        print(f"{CODEX_PACKAGE / 'skills'} was already up to date ({len(wanted)} files).")
    print(f"Edit {CANONICAL}; the copy is generated. See com.openai.codex/README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
