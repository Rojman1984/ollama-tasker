Compact the in-repo CLAUDE.md by archiving its full current contents and replacing historical session-note blocks with a Session Archive Index.

Procedure:

1. Determine `project-name` from the repository root directory name (or git origin remote URL as fallback) and today's date as `YYYY-MM-DD`.

2. Ensure the archive directory exists:
   `/mnt/f/tasker-p1/memory/projects/<project-name>/archive/`

3. Copy the current full `CLAUDE.md` verbatim to:
   `/mnt/f/tasker-p1/memory/projects/<project-name>/archive/CLAUDE_ARCHIVE_<date>.md`
   Do not modify the archived copy.

4. Edit the in-repo `CLAUDE.md` in place. Always preserve exactly these sections, in order:
   - `## What This Project Is`
   - `## What This Project Does`
   - `## Repository Layout`
   - `## Tech Stack`
   - `## Non-Negotiable Constraints`
   - `## Development Rules`
   - `## Phase Tracker`
   - `## Key Design Decisions (Summary)`
   - `## Environment Variables`
   - `## Running Tests`
   - `## Current Session Notes` (keep in full)
   - `## Ollama server rules — DO NOT VIOLATE` (keep in full, do not touch wording)

5. Remove every `## Previous Session Notes` block and every `## Diagnostic session` / `## Follow-up diagnostic session` block that appears between `## Current Session Notes` and the Ollama server rules section.

6. If `CLAUDE.md` already contains a `## Session Archive Index` section, append new rows to its table. Otherwise insert a new `## Session Archive Index` section immediately after `## Current Session Notes` (before the Ollama server rules section). The section must contain:
   - A pointer line: `Full historical session notes archived at: <archive-path>`
   - A markdown table with columns `| Date | Sprint / Session |`
   - One row per removed archived block, containing the date and a one-line description derived from the block's heading. Strip leading labels such as "Previous Session Notes", "Diagnostic session", and "Follow-up diagnostic session" and any trailing "kept for reference" marker.

7. Verify the resulting `CLAUDE.md` is under 40,000 bytes with `wc -c`. If it exceeds the limit, surface that explicitly to the user instead of silently truncating.

8. Run the full test suite (`python -m unittest discover -s tests`) and commit both the compacted `CLAUDE.md` and any newly created command file together if the suite is green. End the commit message with `Co-Authored-By: Claude <noreply@anthropic.com>`.
