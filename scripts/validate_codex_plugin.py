#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Validate the Codex compatibility layer.

This is the distribution layer, not the portable package: it checks
`com.openai.codex/weave/.codex-plugin/plugin.json`, the repository marketplace
at `.agents/plugins/marketplace.json`, and that the packaged skills still match
the canonical ones.

The rules mirror the validator that ships with Codex (`plugin-creator`), so this
can run offline and on every platform. `.github/workflows/codex-official.yml`
additionally runs OpenAI's own validator against the same directory; this script
is a fast local stand-in for it, never a replacement.

    python scripts/validate_codex_plugin.py [repo-root]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

CODEX_PACKAGE = Path("com.openai.codex") / "weave"
MARKETPLACE = Path(".agents") / "plugins" / "marketplace.json"

ALLOWED_TOP_LEVEL = {
    "id",
    "name",
    "version",
    "description",
    "skills",
    "apps",
    "mcpServers",
    "interface",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
}
ALLOWED_AUTHOR = {"name", "email", "url"}
ALLOWED_INTERFACE = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "brandColor",
    "composerIcon",
    "logo",
    "logoDark",
    "screenshots",
    "defaultPrompt",
    "default_prompt",
}
REQUIRED_INTERFACE = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
}
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
INSTALLATION_POLICIES = {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}
AUTHENTICATION_POLICIES = {"ON_INSTALL", "ON_USE"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.errors.append(message)
        return condition


def load_json(path: Path, report: Report) -> dict | None:
    if not report.check(path.is_file(), f"{path} is missing"):
        return None
    raw = path.read_text(encoding="utf-8")
    report.check(not raw.startswith("﻿"), f"{path} must not start with a byte order mark")
    report.check("[TODO:" not in raw, f"{path} still contains a placeholder")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        report.check(False, f"{path} is not valid JSON: {exc}")
        return None
    if not report.check(isinstance(payload, dict), f"{path} must be a JSON object"):
        return None
    return payload


def require_string(payload: dict, key: str, report: Report, where: str) -> str:
    value = payload.get(key)
    ok = isinstance(value, str) and value.strip()
    report.check(bool(ok), f"{where} `{key}` must be a non-empty string")
    return value if ok else ""


def optional_https(payload: dict, key: str, report: Report, where: str) -> None:
    if key not in payload:
        return
    value = payload[key]
    parsed = urlparse(value) if isinstance(value, str) else None
    report.check(
        parsed is not None and parsed.scheme == "https" and bool(parsed.netloc),
        f"{where} `{key}` must be an absolute https:// URL",
    )


def validate_codex_manifest(package_root: Path, report: Report) -> None:
    manifest = load_json(package_root / ".codex-plugin" / "plugin.json", report)
    if manifest is None:
        return
    where = "codex plugin.json"

    unknown = sorted(set(manifest) - ALLOWED_TOP_LEVEL)
    report.check(not unknown, f"{where} has fields plugin validation rejects: {unknown}")

    name = require_string(manifest, "name", report, where)
    report.check(
        package_root.name == name,
        "the Codex package directory name must match the manifest `name` "
        f"({package_root.name} vs {name})",
    )
    version = require_string(manifest, "version", report, where)
    report.check(
        SEMVER_RE.match(version) is not None, f"{where} `version` must be strict semver"
    )
    require_string(manifest, "description", report, where)

    author = manifest.get("author")
    if report.check(isinstance(author, dict), f"{where} `author` is required"):
        report.check(
            not sorted(set(author) - ALLOWED_AUTHOR), f"{where} `author` has unpermitted fields"
        )
        require_string(author, "name", report, f"{where} author")
        optional_https(author, "url", report, f"{where} author")

    # `skills` is a path that must resolve to `skills`, never a list.
    skills = manifest.get("skills")
    report.check(
        isinstance(skills, str), f"{where} `skills` must be a path string, not a list"
    )
    if isinstance(skills, str):
        report.check(
            skills.lstrip("./").rstrip("/") == "skills", f"{where} `skills` must resolve to `skills`"
        )
    report.check((package_root / "skills").is_dir(), f"{where} `skills/` directory is missing")

    # Weave ships no MCP server and no app, deliberately.
    for field in ("mcpServers", "apps", "hooks"):
        report.check(field not in manifest, f"{where} must not declare `{field}`")
    report.check(not (package_root / ".mcp.json").exists(), "the Codex package must not ship .mcp.json")
    report.check(not (package_root / ".app.json").exists(), "the Codex package must not ship .app.json")

    interface = manifest.get("interface")
    if not report.check(isinstance(interface, dict), f"{where} `interface` is required"):
        return
    unknown = sorted(set(interface) - ALLOWED_INTERFACE)
    report.check(not unknown, f"{where} interface has unpermitted fields: {unknown}")
    for field in sorted(REQUIRED_INTERFACE):
        require_string(interface, field, report, f"{where} interface")

    capabilities = interface.get("capabilities")
    report.check(
        isinstance(capabilities, list)
        and bool(capabilities)
        and all(isinstance(c, str) and c.strip() for c in capabilities),
        f"{where} `interface.capabilities` must be a non-empty array of strings",
    )

    prompts = interface.get("defaultPrompt", interface.get("default_prompt"))
    if report.check(prompts is not None, f"{where} `interface.defaultPrompt` is required"):
        report.check(isinstance(prompts, list), f"{where} `interface.defaultPrompt` must be an array")
        if isinstance(prompts, list):
            report.check(1 <= len(prompts) <= 3, "at most three starter prompts are allowed")
            for prompt in prompts:
                report.check(
                    isinstance(prompt, str) and prompt.strip() and len(prompt) <= 128,
                    "starter prompts must be non-empty and at most 128 characters",
                )

    for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
        optional_https(interface, field, report, f"{where} interface")
    optional_https(manifest, "homepage", report, where)
    optional_https(manifest, "repository", report, where)

    if "brandColor" in interface:
        report.check(
            isinstance(interface["brandColor"], str)
            and HEX_COLOR_RE.match(interface["brandColor"]) is not None,
            f"{where} `interface.brandColor` must use #RRGGBB",
        )

    # An asset path is only valid when the file actually ships.
    for field in ("composerIcon", "logo", "logoDark"):
        if field in interface:
            check_asset(package_root, interface[field], f"{where} interface.{field}", report)
    for index, shot in enumerate(interface.get("screenshots", []) or []):
        check_asset(package_root, shot, f"{where} interface.screenshots[{index}]", report)


def check_asset(root: Path, raw: str, where: str, report: Report) -> None:
    if not report.check(isinstance(raw, str) and raw.strip(), f"{where} must be a path"):
        return
    relative = raw[2:] if raw.startswith("./") else raw
    report.check(
        not raw.startswith("/") and ".." not in Path(relative).parts,
        f"{where} must be a relative path inside the package",
    )
    report.check((root / relative).is_file(), f"{where} points at a file that does not ship: {raw}")


def validate_codex_skills(package_root: Path, report: Report) -> None:
    skills = package_root / "skills"
    if not skills.is_dir():
        return
    for skill in sorted(p for p in skills.iterdir() if p.is_dir() and not p.name.startswith(".")):
        skill_md = skill / "SKILL.md"
        if not report.check(skill_md.is_file(), f"skill `{skill.name}` is missing SKILL.md"):
            continue
        text = skill_md.read_text(encoding="utf-8")
        if not report.check(
            text.startswith("---\n"), f"skill `{skill.name}` must start with YAML frontmatter"
        ):
            continue
        report.check(
            text.find("\n---", 4) != -1, f"skill `{skill.name}` frontmatter is not closed"
        )
        report.check(
            "disable-model-invocation: true" not in text
            and "disable_model_invocation: true" not in text,
            f"skill `{skill.name}` must stay model-invocable",
        )

        # The optional Codex presentation sidecar, when present, must be valid.
        sidecar = skill / "agents" / "openai.yaml"
        if sidecar.is_file():
            side_text = sidecar.read_text(encoding="utf-8")
            report.check(
                side_text.startswith("interface:"),
                f"skill `{skill.name}` agents/openai.yaml must define `interface`",
            )
            for field in ("display_name", "short_description"):
                report.check(
                    any(
                        line.startswith(f"  {field}:") and len(line) > len(f"  {field}:")
                        for line in side_text.splitlines()
                    ),
                    f"skill `{skill.name}` agents/openai.yaml needs a non-empty `interface.{field}`",
                )


def validate_marketplace(root: Path, report: Report) -> None:
    marketplace = load_json(root / MARKETPLACE, report)
    if marketplace is None:
        return
    where = "marketplace.json"

    report.check(
        not sorted(set(marketplace) - {"name", "interface", "plugins"}),
        f"{where} has unexpected top-level fields",
    )
    require_string(marketplace, "name", report, where)
    if "interface" in marketplace:
        interface = marketplace["interface"]
        if report.check(isinstance(interface, dict), f"{where} `interface` must be an object"):
            require_string(interface, "displayName", report, f"{where} interface")

    plugins = marketplace.get("plugins")
    if not report.check(
        isinstance(plugins, list) and bool(plugins), f"{where} `plugins` must be a non-empty array"
    ):
        return

    for index, entry in enumerate(plugins):
        label = f"{where} plugins[{index}]"
        if not report.check(isinstance(entry, dict), f"{label} must be an object"):
            continue
        report.check(
            not sorted(set(entry) - {"name", "source", "policy", "category"}),
            f"{label} has unexpected fields",
        )
        name = require_string(entry, "name", report, label)
        require_string(entry, "category", report, label)

        source = entry.get("source")
        if not report.check(isinstance(source, dict), f"{label} `source` is required"):
            continue
        report.check(
            source.get("source") == "local", f"{label} `source.source` must be `local`"
        )
        path = require_string(source, "path", report, f"{label} source")

        # Codex resolves source.path relative to the marketplace root, which is
        # the directory passed to `codex plugin marketplace add` - the
        # repository root - not the `.agents/plugins/` folder.
        report.check(path.startswith("./"), f"{label} `source.path` must start with `./`")
        parts = Path(path).parts
        report.check(".." not in parts, f"{label} `source.path` must stay inside the marketplace root")
        report.check(
            len([p for p in parts if p not in (".", "")]) >= 1,
            f"{label} `source.path` cannot resolve to the marketplace root itself",
        )
        resolved = (root / path).resolve()
        report.check(
            (resolved / ".codex-plugin" / "plugin.json").is_file(),
            f"{label} `source.path` does not resolve to a Codex plugin: {resolved}",
        )
        if (resolved / ".codex-plugin" / "plugin.json").is_file():
            manifest = json.loads(
                (resolved / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
            )
            report.check(manifest.get("name") == name, f"{label} `name` must match the manifest")
            report.check(resolved.name == name, f"{label} directory name must match the plugin name")

        policy = entry.get("policy")
        if report.check(isinstance(policy, dict), f"{label} `policy` is required"):
            report.check(
                policy.get("installation") in INSTALLATION_POLICIES,
                f"{label} `policy.installation` must be one of {sorted(INSTALLATION_POLICIES)}",
            )
            report.check(
                policy.get("authentication") in AUTHENTICATION_POLICIES,
                f"{label} `policy.authentication` must be one of {sorted(AUTHENTICATION_POLICIES)}",
            )


def validate_mirror(root: Path, report: Report) -> None:
    """The packaged skills are a build artifact of the canonical ones."""
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "sync_codex_package.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    report.check(
        result.returncode == 0,
        "the Codex package skills have drifted from the canonical skills:\n"
        + (result.stdout or result.stderr).strip(),
    )


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    report = Report()
    package_root = root / CODEX_PACKAGE

    if not report.check(package_root.is_dir(), f"the Codex package is missing: {CODEX_PACKAGE}"):
        print("Codex layer validation FAILED:")
        for error in report.errors:
            print(f"  - {error}")
        return 1

    validate_codex_manifest(package_root, report)
    validate_codex_skills(package_root, report)
    validate_marketplace(root, report)
    validate_mirror(root, report)

    # The Codex layer must never displace the portable one.
    report.check(
        (root / "plugin.json").is_file(),
        "the portable Agent Plugins manifest must remain at the repository root",
    )
    report.check(
        not (root / ".codex-plugin").exists(),
        "the repository root must not be a Codex plugin; the Codex package is a subdirectory",
    )

    if report.errors:
        print(f"Codex layer validation FAILED ({len(report.errors)} problem(s)):")
        for error in report.errors:
            print(f"  - {error}")
        return 1
    print(f"Codex plugin manifest : ok   ({CODEX_PACKAGE / '.codex-plugin' / 'plugin.json'})")
    print(f"Codex marketplace     : ok   ({MARKETPLACE})")
    print("Packaged skills       : ok   (identical to the canonical skills)")
    print(f"{report.checks} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
