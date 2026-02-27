# Task Plan

## Goal
- Reproduce and fix `OpenRouter` API key write failure (`config set failed`) in EasyClaw TUI using OpenClaw official flow.

## Phases
- [completed] Phase 1: Reproduce failure and capture exact stderr from `openclaw config set`.
- [completed] Phase 2: Add/adjust failing tests for root cause.
- [completed] Phase 3: Implement minimal fix aligned with official OpenClaw provider/config behavior.
- [completed] Phase 4: Verify in local + `easyclaw-web` container with reproducible command sequence.

## Errors Encountered
- `config set failed` root cause: `openclaw config set models.providers {...}` for `openrouter` failed schema validation (`baseUrl` required).
- Added tests initially failed due missing new helpers (`resolve_api_key_auth_choice`, `apply_official_api_key_via_onboard`), then passed after implementation.
