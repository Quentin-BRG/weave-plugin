# Weave plugin

Agent skills for working safely inside a [Weave](https://github.com/Quentin-BRG/weave)
live collaboration session.

Weave keeps several local copies of one Git repository in sync in real time while a
single authoritative host maintains the canonical state. These four skills teach an
agent that model: check whether a session is active, describe intent with Tasks,
reconcile conflicts without ever writing Git conflict markers, and publish to Git
*through Weave* rather than around it.

## Requires the Weave CLI

This package contains instructions, not an implementation. It is useless on its own.

Install the `weave` binary first: **https://github.com/Quentin-BRG/weave**

Every skill drives that CLI. Nothing here needs an MCP server, an API key or a
network service.

---

## What is in here

Three things live in this repository, and it is worth being precise about which is
which, because only the first is the portable standard:

```
weave-plugin/
├── plugin.json                          ← Agent Plugins v1.0.0 manifest (canonical)
├── skills/                              ← Agent Skills (canonical, provider-neutral)
│   ├── weave-collaboration/SKILL.md
│   ├── weave-task/SKILL.md
│   ├── weave-conflict/SKILL.md
│   └── weave-commit/SKILL.md
│
├── com.openai.codex/                    ← client extension namespace
│   └── weave/                             a Codex-native package built from skills/
│       ├── .codex-plugin/plugin.json
│       └── skills/
├── .agents/plugins/marketplace.json     ← Codex repository marketplace
│
├── scripts/                             ← independent validators for each layer
└── LICENSE
```

### 1. The portable Agent Plugins package — the source of truth

The repository root is a package in the vendor-neutral
[Agent Plugins v1.0.0](https://agent-plugins.org/specification) format:

- `plugin.json` targets
  `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`;
- it declares only the ten permitted top-level fields — the schema is closed;
- it does **not** declare skills, because Agent Plugins discovers them from the
  fixed `skills/` directory;
- it carries no client presentation data. Client-specific material goes in the
  standard `extensions` map, keyed by reverse-domain namespace.

Any Agent Plugins client can consume this directly.

### 2. Agent Skills — one canonical copy

Each `skills/<name>/SKILL.md` follows the
[Agent Skills specification](https://agentskills.io/specification): `name` and
`description` frontmatter, then instructions.

**The skills are provider-neutral and there is exactly one copy of each.** No skill
names a vendor, and none says "this assistant must…". They say what to run:

> Run `weave status --json` before modifying shared files.

That is what makes them reusable. To use them outside a plugin client, copy the
directories anywhere skills are read from:

```bash
cp -r skills/* .claude/skills/       # this project
cp -r skills/* ~/.claude/skills/     # everywhere
```

No edits are needed. The `SKILL.md` files are the whole contract.

### 3. Codex packaging — a compatibility layer, not the standard

Codex reads a manifest at `.codex-plugin/plugin.json` and installs plugins through a
marketplace. Neither is part of Agent Plugins, so both live in the
`com.openai.codex` extension namespace and in `.agents/plugins/`, wrapped around the
same canonical skills.

The Codex package needs its own copy of the skill files under
`com.openai.codex/weave/skills/`, because a Codex marketplace entry cannot point at
a repository root ([openai/codex#17066](https://github.com/openai/codex/issues/17066)).
That copy is a **build artifact, never a second source of truth**:

```bash
python scripts/sync_codex_package.py           # regenerate it
python scripts/sync_codex_package.py --check   # verify it, change nothing
```

Validation fails if it ever differs from `skills/`. Edit `skills/`; never edit the
copy.

Each skill also carries an optional `agents/openai.yaml` sidecar with Codex display
metadata. It is purely additive — other clients ignore it, and it does not alter the
portable representation.

---

## Install

### Any Agent Plugins client

Point it at this repository, or at a checkout of it. The root `plugin.json` and
`skills/` are all it needs.

### Codex

```bash
codex plugin marketplace add Quentin-BRG/weave-plugin
# or, from a local checkout:
codex plugin marketplace add .
```

Then install **Weave** from the plugins directory. A repository marketplace is not
discovered automatically; it has to be added once, deliberately.

### Anything that reads SKILL.md directly

Copy `skills/*` into that agent's skills directory, as above.

---

## The safety model these skills carry

Weave exists to stop collaborators from silently overwriting each other, and the
skills carry the rules that make that hold. They are not decoration — the validators
fail if they go missing.

**While a Weave session is active, Weave owns every Git-writing operation** — for
host agents and participant agents alike. The skills explicitly prohibit:

```
git add        git merge        git reset
git commit     git rebase       git checkout
git pull       git cherry-pick  git switch
git push                        git stash
```

Read-only Git stays allowed: `git status`, `git diff`, `git log`, `git show`.

The intended workflow, which the skills preserve end to end:

- describe intent with **Weave Tasks** (advisory soft locks, never enforcement);
- reconcile with **Weave conflict handling**, never with Git conflict markers;
- publish with **`weave commit prepare`** then
  **`weave commit create <prepare_id>`**.

Any participant may *request* a publication. **Only the Weave host coordinator**
constructs the canonical Git objects, updates the canonical branch, distributes those
objects to participants, and performs the push. A participant machine never builds
the canonical commit, even when it is the one running the command.

---

## Validation

The two formats are validated **independently**, because one passing says nothing
about the other:

```bash
python scripts/validate_agent_plugin.py .   # Agent Plugins v1.0.0 + Agent Skills
                                            # + neutrality + Weave safety rules
python scripts/validate_codex_plugin.py .   # Codex manifest + marketplace + mirror
```

Both are standard library only, so they run anywhere Python 3 does, and both run in
CI on Linux, macOS and Windows.

`.github/workflows/codex-official.yml` additionally downloads and runs **OpenAI's own
plugin validator** against `com.openai.codex/weave`. It is scheduled and manually
triggerable rather than blocking, so an upstream change cannot redden an unrelated
pull request — but it is the check that proves the compatibility layer is genuinely
compatible.

---

## License

Mozilla Public License 2.0. See [LICENSE](LICENSE).
