# TIER A DIRECTIVES -- 2026-07-21b (daily verification re-run)

From: Planning workspace (Roland + Fable, automated Tier A run). To: Cowork
supervisor (Tier B). Independent re-verification of the 2026-07-21 status
report: git log HEAD confirmed at 903fb81 as claimed; git status -s matches
the report's two flagged uncommitted items exactly; full suite re-run fresh
in WSL reproduced 985 tests, OK (17.6s). No discrepancies -- report stands
as accurate. No new architectural directives; standing directives below
(Phase 8.5 GO / SELF-1 greenlit) are unchanged and still open, since neither
has started yet.

## New directive -- repo hygiene (docs/config only)

6. Clean up two stray uncommitted files in the working tree: .claude/plan.md
   (scratch plan, appears to be from the merged Phase 8.4 work 7d567b5 --
   confirm it is not a live in-progress plan before deleting) and
   Ollama_Tasker_Status_Update_2026-07-21.docx at repo root (duplicate of
   the report already filed under
   F:\tasker-p1\memory\projects\ollama-tasker\status-reports\, outside the
   intended pipeline). Delete both if confirmed stale, and add
   .claude/plan.md to .gitignore. Tier A attempted this directly and was
   blocked by the WSL shell's own auto-mode safety classifier on both files
   (tmux window 0's live Claude Code session may hold a lock/expectation on
   plan.md) -- routing to Tier B/Claude Code, which has write access.

---

# TIER A DIRECTIVES — 2026-07-21 (response to Status Update 2026-07-21)

From: Planning workspace (Roland + Fable). To: Cowork supervisor (Tier B).
Status report reviewed and approved — supervision quality noted as exemplary
(independent verification, pacing decision, honest infra reporting).

## Directives

1. **Phase 8.5 — GO** as queued (live harness panel on the event stream).
2. **SELF-1 — GREENLIT by Roland, slot immediately after 8.5:** the harness
   implements the PROGRESS_REPORT executor + unit test ON ITS OWN REPO via
   CODE mode (Ollama Cloud code worker), on a branch, TEST_RUNNER green,
   committed via its own GIT tool. Supervisor dispatches via the agent-native
   CLI, reviews the diff independently before merge to master. This is the
   north-star milestone — document the run as evidence (transcript + diff)
   in TASKER_CHECKLIST under "SELF-1".
3. **Streaming decisions confirmed** (already implemented per report):
   astream() contract, synthesis-only token streaming, tasker.paused event +
   honest delta. No changes.
4. **Model Selector text-selection UX check:** pending Roland's 5-minute
   hands-on test; leave the checklist item open until he confirms.
5. **Daily rhythm established:** place daily status reports in
   F:\tasker-p1\memory\projects\ollama-tasker\status-reports\ (filename
   YYYY-MM-DD prefix). A scheduled Tier A review reads them daily, resolves
   standing items, and answers via this file (TIER_A_DIRECTIVES.md, repo
   root — newest directives at top, superseded ones pruned).

## Standing guidance (unchanged)
Ollama server rules binding; credits finish work, never start it; zero-cloud
default for tests; escalate design forks to Roland via the planning workspace;
independent verification at every tier boundary.
