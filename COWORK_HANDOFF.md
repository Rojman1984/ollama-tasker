# COWORK SUPERVISOR HANDOFF — 2026-07-20 evening

New Cowork session bootstrap. Read this + CLAUDE.md + COWORK_PROMPT.md STATUS BLOCK.

## Repo state
- master @ 971d02c (all pushed): fix: enforce cloud concurrency slots on chat direct dispatch
- 943 tests green (independently verified). Working tree clean except this file.

## Infrastructure
- tmux session "tasker" on Designlab1 WSL: window 0 = Claude Code, window 1 = verify shell.
- Window 0 currently runs Claude Code on KIMI backend (ANTHROPIC_BASE_URL=http://localhost:11435,
  ANTHROPIC_AUTH_TOKEN=ollama, --model kimi-k2.7-code:cloud). 3-for-3 verified sprints. Anthropic
  session resumable via `claude-anthropic` (bashrc helper; saved session 232b1fb2-...).
- Bridge: Desktop Commander MCP → `wsl -e bash -li` (keep sleeps <30s per call; MCP times out ~45s).
- tasker-api may still be running on :8555 (background, /tmp/tasker_api.log).
- BRAVE_API_KEY in ~/.bashrc. OLLAMA_BASE_URL=http://127.0.0.1:11435 inside WSL (server rules in
  CLAUDE.md are BINDING — never start/restart Ollama).

## Cost rules (Roland)
- Cowork supervisor: SONNET (Fable bills usage credits post-promo — this is why the session moved).
- Claude Code: Sonnet+medium for implementation on Anthropic; Kimi backend for grunt work (zero Anthropic).
- Credits finish in-flight work, never start new work. Local models default for all live tests.
- Pull-based monitoring: Roland watches tmux; poll git log, not pane captures.

## Today's completed (Jul 20)
- Chat direct dispatch (fast, correct), /model /effort /context /models /transcript, readline,
  research grounding (Brave, citations, [unverified] guard), executors Parts 1-3 (DELEGATE_AGENT,
  TEST_RUNNER, LINTER, CALCULATOR, honest degradation), slot-bypass fix + stress test.
- Stress evidence: 16 concurrent local runs, ZERO empty-content repros (hypothesis nearly falsified);
  cost routing held local under cost_optimized AND capability_first; slot enforcement now at provider
  boundary with regression tests.

## Open items (priority order)
1. SELF-1 milestone (needs Roland's go): harness completes one small task on its OWN repo —
   suggested: implement PROGRESS_REPORT executor + test — via CODE mode on a branch, TEST_RUNNER
   green, committed via its GIT tool. Cowork dispatches via tasker-cli, reviews diff before merge.
2. --verbose should set INFO level (slot logs invisible at WARNING) — one-liner.
3. API server multi-step orchestration (replace _stub_plan) + streaming.
4. TUI 8.4 (SetupWizardScreen, ModelSelectorScreen w/ context slider + VRAM hint) and 8.5 HarnessPanel.
5. Research retrieval quality: planner writes weak search queries; consider query-rewrite step.
6. Budget persistence across restarts; frontier provider wiring (LAST — bills Anthropic API credits).
7. Empty-content bug: park unless it reappears; 8.3 loop guard covers observed symptom.

## Scheduled/memory
- Memory docs current through today in F:\tasker-p1 (STATUS.md has north-star SELF ladder).
- /handoff slash command exists in repo (.claude/commands/handoff.md).
## ADDENDUM 2026-07-20 late: Agent-native deployment requirement added to SDD (normative) — headless parity, JSON event stream matching astream() contract, deterministic exit codes, session-by-id, agent-pilot docs. Applies to ALL interface work incl. streaming sprint and TUI 8.4/8.5.
