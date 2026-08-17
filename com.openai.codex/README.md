# `com.openai.codex` — generated, do not edit

This directory is the **Codex compatibility layer**. It is not the plugin.

`weave/skills/` in here is a **generated copy** of the canonical skills at the
repository root. Editing anything under `weave/skills/` will be overwritten and will
fail validation.

## Edit `skills/` at the repository root instead

```
skills/<name>/SKILL.md          ← the only source of truth
com.openai.codex/weave/skills/  ← generated from it
```

After changing a skill:

```bash
python scripts/sync_codex_package.py
```

`scripts/validate_codex_plugin.py` fails if this copy ever differs from `skills/`,
and CI runs that check on Linux, macOS and Windows, so the two cannot drift apart
silently.

## Why a copy exists at all

Agent Plugins is the portable standard, and the portable package is the repository
root: `plugin.json` plus `skills/`. Codex needs two extra things that are not part
of that standard — a manifest at `.codex-plugin/plugin.json`, and installation
through a marketplace.

A Codex marketplace entry cannot point at a repository root
([openai/codex#17066](https://github.com/openai/codex/issues/17066)), so the Codex
package has to live in a subdirectory, and a Codex plugin loads its skills from
`<plugin-root>/skills/`. Those two facts together mean the Codex package needs its
own copy of the skill files.

The alternatives were worse: a symlink would break on Windows checkouts, and
dropping the marketplace would mean the plugin could not be installed from
`Quentin-BRG/weave-plugin` at all. A generated copy with an enforced drift check
keeps one source of truth and a working install.

This directory name is the reverse-domain extension namespace the
[Agent Plugins specification](https://agent-plugins.org/specification) reserves for
exactly this purpose, so a portable client ignores everything in here.

## What is hand-written here

`weave/.codex-plugin/plugin.json` — the Codex-native manifest, which carries the
presentation metadata (`interface`) that the portable manifest deliberately does not.

And `weave/assets/weave-icon.png` — the plugin icon, referenced as `composerIcon` by
both manifests. It is not drawn here: it is a byte-for-byte copy of the 512×512
rasterisation the Weave CLI repository already ships for every platform, at
`assets/icons/linux/hicolor/512x512/apps/weave.png`, itself generated from
`docs/assets/weave-icon.svg`. Copying the existing rasterisation rather than making a
new one is what keeps the plugin icon identical to the application icon instead of
merely similar to it. `brandColor` in the Codex manifest is `#0044FE`, the accent
colour of that same image.
