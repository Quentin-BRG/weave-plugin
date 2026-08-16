# Contributing

## The layering, in one paragraph

The repository root is the **canonical portable package**: an
[Agent Plugins v1.0.0](https://agent-plugins.org/specification) `plugin.json` plus
[Agent Skills](https://agentskills.io/specification) under `skills/`. Everything
Codex-specific is a **compatibility layer wrapped around it** — the manifest under
`com.openai.codex/weave/`, and the marketplace under `.agents/plugins/`. The Codex
layer never defines the plugin; it repackages it.

If a change makes the Codex layer authoritative, it is the wrong change.

## Where to edit

| To change | Edit | Never edit |
| --- | --- | --- |
| A skill's instructions | `skills/<name>/SKILL.md` | `com.openai.codex/weave/skills/**` |
| Portable manifest metadata | `plugin.json` | — |
| Codex presentation | `skills/<name>/agents/openai.yaml`, `com.openai.codex/weave/.codex-plugin/plugin.json` | — |
| Codex install entry | `.agents/plugins/marketplace.json` | — |

`com.openai.codex/weave/skills/` is generated. After touching `skills/`:

```bash
python scripts/sync_codex_package.py
```

## Before you commit

```bash
python scripts/validate_agent_plugin.py .
python scripts/validate_codex_plugin.py .
```

The two run independently on purpose. The Codex validator passing tells you nothing
about portable conformance, and the portable validator passing tells you nothing
about whether Codex can install the result. Both must pass.

Optionally, run OpenAI's own validator the way CI does:

```bash
pip install pyyaml
curl -fsSL -o /tmp/validate_plugin.py \
  https://raw.githubusercontent.com/openai/codex/main/codex-rs/skills/src/assets/samples/plugin-creator/scripts/validate_plugin.py
python /tmp/validate_plugin.py com.openai.codex/weave
```

## Writing skills

- **Stay provider-neutral.** Never name a vendor or say "this assistant must…".
  Say what to run: *"Run `weave status --json` before modifying shared files."*
  Validation fails on vendor names.
- **The `description` is the trigger.** It is the only part loaded before the skill
  fires, so it must say both what the skill does and when to use it.
- **Keep `SKILL.md` under 500 lines.** Move detail into `references/`.
- **Do not weaken the safety rules.** Every skill must carry the raw Git
  prohibition, and `weave-collaboration` and `weave-commit` must state that only the
  host coordinator builds canonical Git objects, updates the branch, distributes
  them and pushes. These are load-bearing: they are what stops an agent from
  silently overwriting a collaborator. Validation enforces their presence.

## Keeping in step with the CLI

These skills describe the `weave` CLI in
[Quentin-BRG/weave](https://github.com/Quentin-BRG/weave). When a command, a flag or
a `--json` field changes there, check whether a skill here describes it.
