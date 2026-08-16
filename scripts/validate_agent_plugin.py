#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Validate the canonical portable package.

Three independent checks, in the order the specifications layer:

  1. Agent Plugins v1.0.0  - the root `plugin.json` and the fixed component
     locations, per https://agent-plugins.org/specification
  2. Agent Skills          - every `skills/*/SKILL.md`, per
     https://agentskills.io/specification
  3. Weave's own rules     - the skills stay provider-neutral, and the
     collaboration safety model they exist to protect is actually stated

Standard library only, so it runs anywhere Python 3 does.

    python scripts/validate_agent_plugin.py [plugin-root]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

# The only permitted top-level manifest fields in Agent Plugins 1.0.0. The
# schema is closed: anything else is a validation error, not a warning.
ALLOWED_TOP_LEVEL = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
REQUIRED_TOP_LEVEL = {"$schema", "name"}
ALLOWED_AUTHOR = {"name", "email", "url"}

# 1-64 chars, lowercase alphanumeric plus `-` and `.`, no consecutive `--` or
# `..`, must start and end alphanumeric.
PLUGIN_NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
# Agent Skills is stricter: lowercase alphanumeric and hyphens only.
SKILL_NAME_RE = re.compile(r"^(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
# Reverse-domain namespace, e.g. `com.example.client`.
NAMESPACE_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")

# Agent Skills frontmatter.
SKILL_REQUIRED = {"name", "description"}
SKILL_OPTIONAL = {"license", "compatibility", "metadata", "allowed-tools"}

# Weave's collaboration safety model (Weave V1 specification sections 13, 165).
FORBIDDEN_GIT = [
    "git add",
    "git commit",
    "git pull",
    "git push",
    "git merge",
    "git rebase",
    "git cherry-pick",
    "git reset",
    "git checkout",
    "git switch",
    "git stash",
]
ALLOWED_GIT = ["git status", "git diff", "git log", "git show"]
# Skills that must spell out that only the host builds canonical Git objects
# (Weave V1 specification section 169).
HOST_ONLY_SKILLS = ["weave-collaboration", "weave-commit"]
# A skill must be reusable by any compatible agent, so none may name a vendor.
VENDORS = [
    "Codex",
    "OpenAI",
    "ChatGPT",
    "Claude",
    "Anthropic",
    "Cursor",
    "Copilot",
    "Gemini",
]


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.errors.append(message)
        return condition


def normalized(text: str) -> str:
    """Lowercase and collapse whitespace, so a phrase assertion does not depend
    on where Markdown happened to wrap a line."""
    return " ".join(text.lower().split())


# ---------------------------------------------------------------------------
# 1. Agent Plugins v1.0.0
# ---------------------------------------------------------------------------


def validate_agent_plugins_manifest(root: Path, report: Report) -> None:
    manifest_path = root / "plugin.json"
    if not report.check(
        manifest_path.is_file(), "the portable manifest `plugin.json` is missing from the root"
    ):
        return

    raw = manifest_path.read_text(encoding="utf-8")
    report.check(
        not raw.startswith("﻿"), "plugin.json must not start with a byte order mark"
    )
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        report.check(False, f"plugin.json is not valid JSON: {exc}")
        return
    if not report.check(isinstance(manifest, dict), "plugin.json must be a JSON object"):
        return

    unknown = sorted(set(manifest) - ALLOWED_TOP_LEVEL)
    report.check(
        not unknown,
        f"plugin.json has fields the Agent Plugins schema does not permit: {unknown}",
    )
    missing = sorted(REQUIRED_TOP_LEVEL - set(manifest))
    report.check(not missing, f"plugin.json is missing required fields: {missing}")

    report.check(
        manifest.get("$schema") == SCHEMA_URL,
        f"plugin.json `$schema` must be exactly {SCHEMA_URL}",
    )

    # A Codex-style `skills` declaration is meaningless here: Agent Plugins
    # discovers skills from the fixed `skills/` directory.
    report.check(
        "skills" not in manifest,
        "plugin.json must not declare `skills`; Agent Plugins discovers them from `skills/`",
    )
    report.check("mcpServers" not in manifest, "plugin.json must not declare `mcpServers`")
    report.check("interface" not in manifest, "plugin.json must not carry client presentation data")

    name = manifest.get("name")
    if report.check(isinstance(name, str) and name, "plugin.json `name` must be a non-empty string"):
        report.check(len(name) <= 64, "plugin.json `name` must be at most 64 characters")
        report.check(
            PLUGIN_NAME_RE.match(name) is not None,
            f"plugin.json `name` does not match the Agent Plugins pattern: {name}",
        )

    for field in ("version", "description", "homepage", "repository", "license"):
        if field in manifest:
            report.check(
                isinstance(manifest[field], str) and manifest[field].strip(),
                f"plugin.json `{field}` must be a non-empty string",
            )

    if "keywords" in manifest:
        keywords = manifest["keywords"]
        report.check(
            isinstance(keywords, list) and all(isinstance(k, str) for k in keywords),
            "plugin.json `keywords` must be an array of strings",
        )

    if "author" in manifest:
        author = manifest["author"]
        if report.check(isinstance(author, dict), "plugin.json `author` must be an object"):
            unknown = sorted(set(author) - ALLOWED_AUTHOR)
            report.check(not unknown, f"plugin.json `author` has unpermitted fields: {unknown}")

    if "extensions" in manifest:
        extensions = manifest["extensions"]
        if report.check(
            isinstance(extensions, dict), "plugin.json `extensions` must be an object"
        ):
            for namespace, value in extensions.items():
                report.check(
                    NAMESPACE_RE.match(namespace) is not None,
                    f"extension namespace `{namespace}` must be reverse-domain",
                )
                report.check(
                    isinstance(value, dict),
                    f"extension namespace `{namespace}` must map to an object",
                )
                for key, path in value.items():
                    if isinstance(path, str) and ("/" in path or path.startswith(".")):
                        report.check(
                            path.startswith("./"),
                            f"extensions.{namespace}.{key} must be a plugin-relative `./` path",
                        )
                        report.check(
                            ".." not in Path(path).parts,
                            f"extensions.{namespace}.{key} must stay inside the plugin root",
                        )
                        report.check(
                            (root / path).exists(),
                            f"extensions.{namespace}.{key} points at a missing path: {path}",
                        )

    # `mcp.json` is optional and Weave V1 needs no MCP component.
    report.check(
        not (root / "mcp.json").exists(),
        "Weave declares no MCP server, so `mcp.json` should not be present",
    )

    skills_dir = root / "skills"
    report.check(skills_dir.is_dir(), "`skills/` must be a directory")


# ---------------------------------------------------------------------------
# 2. Agent Skills
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict[str, str], str] | None:
    """Return (frontmatter, body). Only the flat scalar keys Agent Skills
    defines are needed, so this avoids a YAML dependency; nested blocks such as
    `metadata` are recorded as present without parsing their values."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    block, body = text[4:end], text[end:]
    fields: dict[str, str] = {}
    current: str | None = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in " \t" and ":" in line:
            key, _, value = line.partition(":")
            current = key.strip()
            fields[current] = value.strip().strip('"').strip("'")
        elif current is not None:
            # Continuation or nested mapping; keep the key, ignore the shape.
            fields[current] = (fields[current] + " " + line.strip()).strip()
    return fields, body


def skill_dirs(root: Path) -> list[Path]:
    skills = root / "skills"
    if not skills.is_dir():
        return []
    # Only immediate children of `skills/` are skills; clients do not recurse.
    return sorted(p for p in skills.iterdir() if p.is_dir() and not p.name.startswith("."))


def validate_agent_skills(root: Path, report: Report) -> None:
    dirs = skill_dirs(root)
    if not report.check(bool(dirs), "the plugin ships no skills"):
        return

    for skill in dirs:
        label = skill.name
        skill_md = skill / "SKILL.md"
        if not report.check(skill_md.is_file(), f"skill `{label}` has no SKILL.md"):
            continue

        text = skill_md.read_text(encoding="utf-8")
        parsed = parse_frontmatter(text)
        if not report.check(
            parsed is not None, f"skill `{label}` must open with closed YAML frontmatter"
        ):
            continue
        fields, body = parsed

        missing = sorted(SKILL_REQUIRED - set(fields))
        report.check(not missing, f"skill `{label}` frontmatter is missing: {missing}")
        unknown = sorted(set(fields) - SKILL_REQUIRED - SKILL_OPTIONAL)
        report.check(
            not unknown,
            f"skill `{label}` frontmatter has fields Agent Skills does not define: {unknown}",
        )

        name = fields.get("name", "")
        report.check(name == label, f"skill `{label}` frontmatter `name` must match its directory")
        report.check(
            1 <= len(name) <= 64, f"skill `{label}` name must be 1-64 characters"
        )
        report.check(
            SKILL_NAME_RE.match(name) is not None,
            f"skill `{label}` name must be lowercase alphanumeric and hyphens, "
            "with no leading, trailing or consecutive hyphen",
        )

        description = fields.get("description", "")
        report.check(bool(description.strip()), f"skill `{label}` description must be non-empty")
        report.check(
            len(description) <= 1024,
            f"skill `{label}` description must be at most 1024 characters",
        )
        # The description is the trigger: the body only loads after it fires.
        report.check(
            "use when" in description.lower() or description.lower().startswith("use "),
            f"skill `{label}` description must say when to use the skill",
        )

        if "compatibility" in fields:
            report.check(
                1 <= len(fields["compatibility"]) <= 500,
                f"skill `{label}` compatibility must be 1-500 characters",
            )

        report.check(bool(body.strip()), f"skill `{label}` has no instructions")
        report.check(
            len(text.splitlines()) <= 500,
            f"skill `{label}` SKILL.md should stay under 500 lines",
        )


# ---------------------------------------------------------------------------
# 3. Weave's own rules
# ---------------------------------------------------------------------------


def validate_weave_rules(root: Path, report: Report) -> None:
    for skill in skill_dirs(root):
        label = skill.name
        skill_md = skill / "SKILL.md"
        if not skill_md.is_file():
            continue
        raw = skill_md.read_text(encoding="utf-8")
        text = normalized(raw)

        for vendor in VENDORS:
            report.check(
                vendor not in raw,
                f"skill `{label}` names `{vendor}`; skills must stay provider-neutral",
            )

        for command in FORBIDDEN_GIT:
            report.check(
                command in text,
                f"skill `{label}` must name `{command}` in the raw Git prohibition",
            )
        report.check(
            "host agents and participant agents alike" in text,
            f"skill `{label}` must state that the Git rule applies to hosts too",
        )
        for command in ALLOWED_GIT:
            report.check(
                command in text, f"skill `{label}` should still permit `{command}`"
            )

    for label in HOST_ONLY_SKILLS:
        skill_md = root / "skills" / label / "SKILL.md"
        if not report.check(skill_md.is_file(), f"expected skill `{label}` is missing"):
            continue
        text = normalized(skill_md.read_text(encoding="utf-8"))
        report.check(
            "only the host" in text or "host coordinator" in text,
            f"skill `{label}` must say that only the host builds the canonical commit",
        )
        report.check(
            "canonical" in text,
            f"skill `{label}` must name the host-built commit as canonical",
        )
        for duty in ("branch", "push"):
            report.check(
                duty in text, f"skill `{label}` must describe the host's `{duty}` responsibility"
            )

    # The publication workflow itself must survive edits to the skill.
    commit_skill = root / "skills" / "weave-commit" / "SKILL.md"
    if commit_skill.is_file():
        text = normalized(commit_skill.read_text(encoding="utf-8"))
        for command in ("weave commit prepare", "weave commit create"):
            report.check(command in text, f"weave-commit must document `{command}`")
    conflict_skill = root / "skills" / "weave-conflict" / "SKILL.md"
    if conflict_skill.is_file():
        text = normalized(conflict_skill.read_text(encoding="utf-8"))
        for command in ("weave conflict show", "weave conflict resolve"):
            report.check(command in text, f"weave-conflict must document `{command}`")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    report = Report()

    validate_agent_plugins_manifest(root, report)
    validate_agent_skills(root, report)
    validate_weave_rules(root, report)

    if report.errors:
        print(f"Portable package validation FAILED ({len(report.errors)} problem(s)):")
        for error in report.errors:
            print(f"  - {error}")
        return 1
    print(f"Agent Plugins v1.0.0 : ok   ({root / 'plugin.json'})")
    print(f"Agent Skills         : ok   ({len(skill_dirs(root))} skills)")
    print("Weave safety rules   : ok")
    print("Provider neutrality  : ok")
    print(f"{report.checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
