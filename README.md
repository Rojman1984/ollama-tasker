# Ollama Tasker

Provider-agnostic, hardware-aware multi-agent orchestration for tool-capable LLMs.

## Documentation

- `docs/SDD.md` -- Software Design Document (authoritative spec, read first)
- `docs/COWORK_PROMPT.md` -- Cowork/Code session bootstrap prompt
- `docs/TASKER_CHECKLIST.md` -- Feature checklist
- `docs/TESTING_GUIDE.md` -- Test commands organized by surface

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then fill in API keys
```

## Running Tests

```powershell
python -m unittest discover -s tests -v
```

## Hardware Profiles

| Profile | Machine | Tier |
|---------|---------|------|
| tier0_minimal | Any / no model needed | 0 |
| tier1_tasker | TASKER-P1 (Ryzen 5 3500U, CPU-only) | 1 |
| tier2_designlab | Designlab1 (Ryzen 5/7, GTX 1050 Ti) | 2 |

## Status

Phase 1 -- in progress. See `docs/TASKER_CHECKLIST.md`.