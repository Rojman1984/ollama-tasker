Generate a compact session handoff block for continuing work in a fresh session
(any backend: Anthropic, Ollama-hosted, or Cowork supervisor).

Produce a single fenced markdown block titled HANDOFF containing, tersely:

1. Repo state: current branch, last 3 commits (hash + one-line), dirty files if any.
2. Current phase + task per COWORK_PROMPT.md STATUS BLOCK (one line each).
3. In-flight work: what is mid-implementation, what is committed, what remains.
4. Open findings/bugs from the most recent live-testing notes in CLAUDE.md
   Current Session Notes (bullet per finding, one line each).
5. Binding constraints (one line each): Ollama server rules (never spawn a
   server; 11434 Windows / 11435 WSL; OLLAMA_BASE_URL); zero-cloud-spend
   default for tests; SDD-first; session-end protocol.
6. Next action: the single most specific next task.

Keep the whole block under 40 lines. No prose outside the block. Do not modify
any files — this is read-only synthesis.
