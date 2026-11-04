# vod-devkit (English)

Collect product feedback from your AI agent's users and deliver it safely
into the VOD voice-of-customer platform. A pure-collection MCP plugin:
one write endpoint, one upstream, tiered trust — aligned with the
engineering skeleton of huaweicloud-devkit, adapted for a service-facing
plugin.

## What it does

- **vod_submit_voices** — submit user feedback (requires per-batch user
  confirmation; content ≤2000 chars; product attribution via
  install-binding > explicit > ask-user, never silently guessed)
- **vod_list_submitted** — local ledger of what this machine submitted
  (agent answers "did my feedback go through?")
- **vod_auth_status** — key fingerprint self-check + 3-step guidance
  (works without a key)
- **vod_devkit_info** — plugin version / commitSHA / host identity

Zero-field anonymous token: on first submission the plugin automatically
requests a token (no registration). Upgrade to a formal key when volume
grows. Skills: VOD problem-classification (6 categories), category
matching, and scoring rules — sourced from engine code, used for
pre-classification at collection time.

## Install

```bash
git clone https://github.com/yangaiwu/vod-devkit.git
cd vod-devkit
bin/vod-devkit install --target auto --product <your-product>   # hermes | opencode | codex
# For any MCP client, see QUICKSTART.md for the manual config snippet
```

Verified hosts: Hermes (official `hermes mcp add`), OpenCode
(`opencode mcp list` → connected), Codex CLI (config recognized).

## Guarantees

- No identity fields in tool schemas — attribution cannot be forged by
  the model; user identity travels as data fields only
- Guardrails: per-batch confirm, batch ≤50, credential/DB-intent deny
  (scoped so legitimate feedback quoting secrets is not killed)
- Provenance: install-manifest + build-info (commitSHA) +
  `vod-devkit verify` tamper detection
- No telemetry. Fail-closed: no traceable credential → no write.

## Quality

25 tests (unit / guardrails / packs / protocol-level real-HTTP lock /
stdio roundtrip / meta cache / ledger) + pre-push gate + GitHub Actions
CI on the mirror + nightly local E2E against the test environment.

Docs: [README.md (中文)](README.md) · QUICKSTART.md · CONTRIBUTING.md ·
SECURITY.md · docs/proposal.md ·
docs/design.md · docs/scheme-overview.md (one-pager) · CHANGELOG.md
