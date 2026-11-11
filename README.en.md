# vod-devkit (English)

[中文](README.md) | English

Deliver your AI-agent users' **verbatim feedback** into the VOD (Voice of
Developer) intake channel: MCP server + skills + declarative guardrails.
Collection only — analysis and operations live in the vod-system frontend.

Three rules that matter more than the skeleton:

- **Collect only**: the plugin's single write action is an engine HTTP call
  (`POST /external/voices`). Persistence, quotas, audit and identity checks all
  live server-side; there is no database code path in this repo.
- **Identity travels with the request**: stdio uses the local anonymous token;
  the remote face reads Bearer from the request header and **never mints an
  identity** (missing key = reject).
- **Attribution never asks the user**: the product is parsed from the user's own
  words against the engine catalog aliases; only an unambiguous single hit is
  accepted, multiple hits become UNKNOWN for a human to resolve. `--product` at
  install time is an optional prior only.

## Prerequisites

| Dependency | Requirement | Notes |
|---|---|---|
| Node | >= 18 | `npx` bootstrap; the dsh host needs Node 24.9+ per its own docs |
| Python | >= 3.10 | installer + MCP server; point `VOD_PYTHON` at an interpreter if needed |
| Host | hermes / opencode / codeartsdoer / codex / dsh | `--target auto` probes, or name one explicitly |
| Network | reachable VOD engine | defaults to `https://vod-dev.topxtopx.com`, override with `--java-api-base` |

The remote face additionally needs the official MCP SDK:
`pip install 'vod-devkit[remote]'` (stdio has zero third-party deps).

## Quick start

```bash
npx -y vod-devkit@latest install --target auto
```

**Restart the session** afterwards (hosts read MCP config at startup), then:

```bash
npx -y vod-devkit@latest doctor   # config + skill roster + build-info
npx -y vod-devkit@latest status   # install-manifest: version / source / host / transport
```

`--product <name>` is an optional prior (used only when there is no literal
evidence and no memory); when given it is validated against the catalog and a
typo exits 2.

## Per-host install

`install` takes `--target`; `doctor` / `status` / `verify` / `update` /
`uninstall` operate on the installed instance (they read `install-manifest`) and
take no target.

### Hermes

```bash
npx -y vod-devkit@latest install --target hermes
npx -y vod-devkit@latest doctor && npx -y vod-devkit@latest status
npx -y vod-devkit@latest uninstall      # removes the managed MCP entry only
```

Writes `hermes mcp add` into `~/.hermes/config.yaml` plus
`~/.hermes/mcp/vod-devkit.json`; skills go to `~/.hermes/skills/devops/vod-devkit`.

### OpenCode

```bash
npx -y vod-devkit@latest install --target opencode
npx -y vod-devkit@latest uninstall
```

Merges `mcp.vod-devkit` into `~/.config/opencode/opencode.json` (your provider
keys are preserved); skills go to `~/.config/opencode/skills`. Uninstall removes
only our entry and the skill dirs we installed.

### Codex

```bash
npx -y vod-devkit@latest install --target codex
npx -y vod-devkit@latest uninstall      # removes the native plugin, keeps config.toml
```

Uses the codex native plugin path (`codex plugin marketplace add` + `plugin add`),
with `.mcp.json` running `vod-devkit serve` over stdio. If the collection circuit
breaker is tripped, install refuses the collect pack until `--ack-suspension`.

### CodeArts Agent (codeartsdoer)

CodeArts Agent is an OpenCode fork (`SCENARIO=codeartsdoer`, config at
`~/.codeartsdoer/codearts_cli.json`), so the MCP entry uses the opencode schema:
`{"type":"local","command":[...],"enabled":true,"environment":{...}}`. Skills go to
`~/.codeartsdoer/skills`. `doctor` runs `codearts mcp list` as a smoke check.
Do **not** write `~/.codeartsdoer/mcp/mcp_settings.json` — that path is project-level;
the user-level mcp_settings lives under `~/.config/opencode/mcp/`.

### DeepSeek Harness (dsh)

```bash
npx -y vod-devkit@latest install --target dsh --profile <name>
```

`--profile` is required; installs the `dsh-vod-devkit` shell package and writes a
profile `cordis.patch.yml` override. The dsh shell does not speak MCP:
`--mcp-url` / `--skills-only` exit 2.

## Other MCP hosts (generic layer)

Hosts without a dedicated adapter are no longer "unsupported":

```bash
# Known config shapes (Claude Code / Cursor / Windsurf / Cline):
npx -y vod-devkit@latest install --target generic --mcp-config ~/.claude.json

# No path given: print a paste-ready snippet, write nothing
npx -y vod-devkit@latest install --target generic
```

- Surgical merge: only `mcpServers.vod-devkit` is written, other servers and user
  keys are preserved, first touch leaves a `.bak`
- Invalid JSON / non-object top level → refuse and leave bytes untouched
- `--target auto` auto-picks the generic path only when exactly one known host is
  detected; otherwise it asks you to be explicit
- The generic layer installs the MCP entry only (skill dirs are host-private)

Manual snippet (replace `<repo>`):

```jsonc
{ "mcpServers": { "vod-devkit": {
    "command": "python3", "args": ["<repo>/vod_mcp/server.py"] } } }
```

## Remote deployment: standalone MCP + host attach

One endpoint serves many hosts; identity comes from request headers:

```bash
pip install 'vod-devkit[remote]'
vod-devkit serve --transport remote --port 9528 --host 127.0.0.1   # put TLS/identity in front
```

Attach a host (token required — the remote face never mints anonymous identity):

```bash
npx -y vod-devkit@latest install --target hermes   --mcp-url https://<gateway>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target opencode --mcp-url https://<gateway>/mcp --mcp-token <key>
npx -y vod-devkit@latest install --target codex    --mcp-url https://<gateway>/mcp --mcp-token <key>
```

Liveness is probed before any write: `initialize` + `tools/list` must equal the
remote tool set, otherwise the install is refused with zero side effects. The
remote face withholds machine-local tools (`vod_draft_voices`,
`vod_commit_voices`, `vod_list_submitted`) — a shared process has no "local".
There is no built-in auth: bind to loopback and front it with TLS + identity.

## Telemetry and data

- **Collected**: nothing. No telemetry, no analytics, no usage counters.
- **Not collected**: everything. Feedback content goes only to the engine you
  configure, and only after the user agrees.
- **Transport**: stdio calls the engine directly; the remote face identifies the
  caller from the request header, nothing is stored server-side.
- **How to opt out**: nothing to opt out of. To disconnect entirely, `uninstall`
  or point `--java-api-base` at your own instance.

## Tool surface (single source: contract/tools.schema.json)

| Tool | pack | Type | Guardrail |
|---|---|---|---|
| vod_submit_voices | collect | write | per-batch confirm; batch <= 50; Java `/external/voices` |
| vod_draft_voices | collect | write (staging) | local cap 10 / TTL 600s; verbatim echo; no upstream call |
| vod_commit_voices | collect | write | one-time token + payloadSha256; reuses submit chain |
| vod_list_submitted | collect | read | local ledger (cap 200) |
| vod_devkit_info | core | read | version / commitSHA / host clientInfo |
| vod_auth_status | core | read | fingerprint self-check + 3-step guidance |
| vod_check_update | core | read | npm latest (24h cache, silent on failure); never self-upgrades |
| vod_list_skills / vod_retrieve_skill | knowledge | read | rule-skill disclosure (pack filtering refuses with a fix hint) |

Security: `safety/policy.json` denies DB-direct intent and credential reads;
text rules only inspect structural fields, so feedback quoting a secret is not
misfired (quoting vs reading are different acts).

## Quality

```bash
python3 -m pytest tests/ -q        # full: unit + guardrails + packs + installer matrix + real-HTTP + stdio
python3 -m pyflakes vod_mcp/*.py tests/*.py scripts/*.py bin/vod-devkit
python3 -m mypy                    # scope in pyproject [tool.mypy]
python3 scripts/secret_scan.py
python3 scripts/sync_case_roster.py --check
python3 scripts/rules_provenance.py
```

Gates: pre-push hook (pytest + pyflakes + secret_scan) + GitHub Actions on the
mirror + byte-identical package mirrors + description budget + install-manifest
roster checks + outward-doc claim checks. Counts are never hand-written into
docs; measure them.

## Docs

docs/proposal.md · docs/design.md · docs/scheme-overview.md ·
docs/safety-model.md · docs/decisions.md · docs/rules-provenance.json ·
QUICKSTART.md · INSTALL.md · CONTRIBUTING.md · SECURITY.md

## License

MIT (see LICENSE.txt). Third-party notices in NOTICE.
