# Ollama Tasker — SDD Addendum: Cross-Platform Migration & Dynamic Hardware Detection

**Addendum version:** 1.1.0
**Extends:** SDD.md v0.1.0-draft
**Status:** Draft — pending Phase 7.5 implementation
**Date:** 2026-06-30

---

## A.1 Purpose and Scope

This addendum amends the original SDD following the Phase 7 hardening session.
Two changes are introduced that affect the Configuration System (original
Section 8) and add new components not present in the original 7-phase
roadmap:

1. **Primary development environment changes from Windows/PowerShell to
   Linux/WSL2.** Windows/PowerShell remains a supported secondary environment.
   This is a documentation and tooling reprioritization, not an architecture
   change — the existing `tasker/`, `core/`, and `cli/` Python code is already
   OS-agnostic (pathlib, asyncio, no Windows-only APIs) and required no
   changes to support this beyond verification.

2. **Static per-machine hardware tier YAML files are demoted from default to
   explicit-override-only.** A new standalone detection subsystem
   (`tasker-hardware` applet) probes live hardware at first run, caches the
   result per-machine, and becomes the default source of `HardwareProfile`.
   This directly resolves an observed problem: local models on Designlab1
   were not engaging GPU compute, traced to the harness never having any
   mechanism to detect, verify, or warn about GPU acceleration status — it
   simply trusted whatever static YAML profile was manually selected.

This work is scoped to two real, currently-owned target machines —
**TASKER-P1** (AMD Ryzen 5 3500U, Vega 8 Mobile integrated graphics, gfx902)
and **Designlab1** (NVIDIA GTX 1050 Ti discrete) — plus the general AMD APU
case (other Vega/RDNA2/RDNA3 chips). Other vendors (AMD discrete/ROCm, Intel
Vulkan, Apple Silicon) are explicitly out of scope for implementation but the
architecture is left open for future contributors to add them without
refactoring.

---

## A.2 Summary of Changes to Core SDD

| Original SDD Section | Change |
|---|---|
| 8.1 Configuration Hierarchy | Rewritten — three-source resolution order (explicit override → machine-local cache → live detection fallback) replaces the original flat "Hardware Profile YAML × Mode × Worker Registry" hierarchy |
| 8.2 Hardware Profile Schema | Static YAML files (`tier0_minimal.yaml`, `tier1_tasker.yaml`, `tier2_designlab.yaml`) are retained unchanged but reclassified as **explicit override inputs**, not the default path |
| 5.4 / 5.5 Worker Registry / Selector | New requirement: workers with `requires_gpu=true` must be cross-checked against the *resolved* `HardwareProfile`'s live GPU memory figure at load time, not assumed available from the registry YAML alone |
| 15 References | Add two new AMD APU configuration guides (Section A.9 below) as authoritative troubleshooting references |

No changes to Sections 1–4, 6.1–6.4 (worker/task/result data models), 7
(interface contracts), 9 (session lifecycle), 10 (error handling), 11
(security/privacy), or 12 (testing strategy structure) — those remain as
originally specified. Section 13 (roadmap) gains a new phase, detailed in
A.6 below.

---

## A.3 Revised Section 8 — Configuration System

### A.3.1 Configuration Resolution Order (replaces original 8.1)

```
1. EXPLICIT OVERRIDE (highest priority)
   --profile <name> CLI flag, or TASKER_PROFILE env var set to a non-empty
   value matching a file in config/profiles/*.yaml
        │
        ▼ (if not set)
2. MACHINE-LOCAL CACHE
   .tasker/hardware_profile.json — written by `tasker-hardware detect`,
   read only if its recorded hostname matches the current machine's
   hostname (hostname mismatch = cache invalid, falls through to live
   detection rather than silently applying another machine's profile)
        │
        ▼ (if missing or hostname mismatch)
3. LIVE DETECTION (fallback, with a printed suggestion to cache it)
   tasker.config.detect.detect_hardware_profile() runs inline, same logic
   the `tasker-hardware detect` applet uses, slower per-invocation since
   it re-probes hardware every time
```

All three paths return the same `HardwareProfile` dataclass. Downstream
consumers (`ModeConfigurator`, `build_orchestrator()`) do not need to know
which path was used.

**Rationale for the cache layer:** detection involves subprocess calls
(`nvidia-smi`, `lspci`, optionally `journalctl`) and `psutil` polling, which
adds real latency if run on every `tasker` invocation. The cache makes
detection a one-time cost per machine, re-run on demand via `tasker-hardware
detect` or implicitly when the cache is absent/stale.

**Rationale for hostname-scoping:** this repository is developed and run
across multiple physical machines with different hardware (TASKER-P1,
Designlab1, and potentially others in the future). A committed or
copied-without-checking cache file would cause one machine's GPU/tier
profile to silently apply on a different machine after a `git pull` or
file copy. The cache file is git-ignored; hostname verification is the
runtime safety net for the case where it gets copied manually anyway.

### A.3.2 Static Profile YAML (retained, reclassified)

`config/profiles/tier0_minimal.yaml`, `tier1_tasker.yaml`,
`tier2_designlab.yaml` are **unchanged in content and schema** from the
original SDD Section 8.2. Their role changes from "the default
configuration source" to "an explicit, reproducible override" — useful for:

- Testing a specific tier's behavior without needing that tier's physical
  hardware present
- CI environments simulating constrained hardware
- Deliberately running a machine at a lower tier than its detected hardware
  would suggest (e.g. throttling Designlab1 to tier1 behavior for a test)

### A.3.3 Cache File Schema

`.tasker/hardware_profile.json`:

```json
{
  "hostname": "string",
  "detected_at": "ISO-8601 timestamp",
  "cpu_cores": "int",
  "ram_gb": "float",
  "gpu_vendor": "nvidia | amd_apu | none",
  "gpu_name": "string | null",
  "gpu_memory_mb": "int | null",
  "gpu_is_unified_memory": "bool",
  "amd_vulkan_enabled": "bool | null",
  "amd_rocm_disabled": "bool | null",
  "amd_vulkan_warning": "string | null",
  "amd_group_warning": "string | null",
  "gpu_verified_during_inference": "bool | null",
  "gpu_verified_size_vram_mb": "int | null",
  "gpu_verified_offload_status": "full | partial | unknown | null",
  "computed_profile": {
    "orchestrator_tier_max": "int",
    "max_concurrent_local": "int",
    "load_strategy": "sequential | resident"
  }
}
```

Fields prefixed `amd_` are populated only when `gpu_vendor == "amd_apu"`;
left `null` otherwise. `gpu_verified_*` fields are populated only after
`tasker-hardware verify` has been run at least once; `detect` alone leaves
them `null`.

### A.3.4 Worker VRAM Cross-Check (new, extends original 5.4)

At `WorkerRegistry` load time, any `WorkerManifest` with `requires_gpu=true`
must be cross-checked against the resolved `HardwareProfile`'s
`gpu_memory_mb`:

- **NVIDIA (discrete, `is_unified_memory=False`):** check directly against
  `gpu_memory_mb` (true dedicated VRAM figure from `nvidia-smi`).
- **AMD APU (`is_unified_memory=True`):** `gpu_memory_mb` for this vendor is
  set to *total system RAM* (per A.4.2 below, not a small BIOS UMA
  carve-out), so the check must subtract a reserved-for-system-overhead
  margin (recommended 4–8GB) before comparing against a worker's declared
  `vram_mb` requirement, since the full system memory pool is never actually
  available to one process.

Workers failing this check are marked `available=false` in the registry —
**visible** via `tasker workers` with a logged reason, never silently
dropped from output.

---

## A.4 New Architecture — GPU Backend System

### A.4.1 GPUBackend Abstract Base

```python
class GPUBackend(ABC):
    @abstractmethod
    def detect(self) -> GPUInfo | None:
        """
        Return GPUInfo if this backend's hardware/tooling is present on
        this machine, else None. MUST NOT raise — catch all subprocess
        and filesystem errors internally and return None on failure.
        MUST check tooling/platform preconditions (shutil.which, platform
        .system()) BEFORE attempting any subprocess call, so irrelevant
        backends short-circuit immediately on the wrong platform/hardware.
        """
```

### A.4.2 GPUInfo Data Model

```python
@dataclass
class GPUInfo:
    vendor: Literal["nvidia", "amd_apu", "none"]
    name: str | None
    memory_mb: int | None
    is_unified_memory: bool

    # AMD-APU-specific (None for other vendors)
    vulkan_enabled: bool | None = None
    rocm_disabled: bool | None = None
    vulkan_warning: str | None = None
    group_warning: str | None = None
```

**Critical semantic note, documented here because it is the single most
important nuance in this subsystem:** for `vendor == "nvidia"`, `memory_mb`
is true dedicated VRAM reported by `nvidia-smi`. For `vendor == "amd_apu"`,
`memory_mb` is set to **total system RAM**, not any GPU-reported figure —
AMD APUs dynamically allocate graphics memory from system RAM via GTT on top
of a small, often misleading, fixed BIOS UMA carve-out (typically 512MB–2GB,
queryable at `/sys/class/drm/card*/device/mem_info_vram_total` but NOT
representative of the true usable pool). Treating that sysfs number as "the
VRAM" would dramatically understate what's actually available to Ollama via
Vulkan. `is_unified_memory=True` is the flag downstream tier-computation and
worker-VRAM-cross-check logic must branch on before doing any
VRAM-vs-system-RAM arithmetic.

### A.4.3 Concrete Backends — Scope for This Phase

| Backend | Status | Detection method |
|---|---|---|
| `NvidiaBackend` | **Implemented, verified on real hardware (Designlab1)** | `nvidia-smi --query-gpu=name,memory.total --format=csv` |
| `AmdApuBackend` | **Implemented, verified on real hardware (TASKER-P1)** | Vulkan-based; see A.4.4 |
| `NoGpuBackend` | **Implemented** | Always returns `None` — final fallback |
| `AmdDiscreteBackend` (ROCm, discrete Radeon/Instinct) | **Out of scope** | Future extension point |
| `IntelBackend` (Vulkan-based, Intel integrated/Arc) | **Out of scope** | Future extension point |
| `AppleSiliconBackend` (`sysctl`/Metal-based) | **Out of scope** | Future extension point |

Detection chain order: `NvidiaBackend` → `AmdApuBackend` → `NoGpuBackend`.
On a machine with both an AMD APU and a discrete NVIDIA card present, NVIDIA
is treated as the primary detected GPU — a documented judgment call (the
more capable, more cleanly measurable device wins), not an oversight.

Out-of-scope backends are documented as architecture extension points only:
implement `GPUBackend`, register in the detection chain in
`tasker/config/gpu_backends.py`'s `detect_gpu()` function. Not claimed as
working anywhere in user-facing documentation.

### A.4.4 AmdApuBackend — Detailed Design

This is the one genuinely nontrivial detection backend in this addendum.
AMD integrated graphics are **not supported by ROCm** (confirmed across two
independently validated reference guides, A.9 below) — the correct and only
practical path is Ollama's Vulkan compute backend via Mesa RADV.

**`detect()` — fast, side-effect-free, no running-Ollama dependency:**

1. **Presence check** (OS-aware):
   - Linux: `lspci -nn`, look for AMD/ATI vendor ID `1002` on a
     VGA/Display controller.
   - Windows: `Get-CimInstance Win32_VideoController` (or equivalent),
     look for a controller name containing "AMD" or "Radeon".
   - Return `None` immediately if no AMD device found, before any further
     checks. This backend does not attempt to disambiguate APU vs. discrete
     Radeon by codename matching (fragile, incomplete) — any AMD GPU found
     is treated as in-scope; disambiguation is deferred to a future
     `AmdDiscreteBackend`.
2. **Vulkan tooling check** (informational only, not a hard gate):
   - Linux: if `vulkaninfo` is on `PATH`, optionally run
     `vulkaninfo --summary` to confirm an AMD device is listed.
   - Windows: Vulkan ships with the GPU driver stack; no CLI confirmation
     attempted at this stage — deferred to live verification.
3. **Environment variable check** — three variables, not one:
   - `OLLAMA_VULKAN == "1"` → sets `vulkan_enabled`
   - `ROCR_VISIBLE_DEVICES == "-1"` and `HIP_VISIBLE_DEVICES == "-1"` →
     sets `rocm_disabled`
   - If `vulkan_enabled=True` but `rocm_disabled=False`: set
     `vulkan_warning` to a specific advisory message (not a hard block —
     some hardware works fine with `OLLAMA_VULKAN=1` alone; on older
     gfx902-class chips specifically, the ROCm-disable variables are
     required to prevent a silent runner crash — see A.9.2). This flag is
     advisory at `detect()` time; `verify_live()` gives the authoritative
     diagnosis if the crash symptom actually appears in logs.
   - If `vulkan_enabled=False`: hardware presence is still reported
     (`vendor="amd_apu"` etc.), but downstream tier computation treats this
     identically to `NoGpuBackend` — Ollama will fall back to CPU without
     the env var, regardless of physical hardware.
4. **Group membership check** (Linux only, informational):
   - Use Python's `grp` module (no subprocess) to check current user
     membership in `video` and `render` groups.
   - Missing either → `group_warning` set, pointing to remediation. Not a
     hard block (the `ollama` *service* account's group membership matters
     more than the interactive shell user's, depending on install method).
   - Windows: skip entirely, `group_warning=None`.
5. **Static memory estimate:** `memory_mb` = total system RAM (`psutil`),
   `is_unified_memory=True`, unconditionally for this backend.

**`verify_live(ollama_base_url)` — separate method, requires running
Ollama, called only by `tasker-hardware verify`:**

1. **Primary, cross-platform method:** `GET {base_url}/api/ps`. Find the
   loaded model entry's `size_vram` field. `size_vram > 0` confirms real
   Vulkan/iGPU offload for that specific model. Preferred over log parsing
   since this endpoint's location/format is identical on both platforms,
   while log file location differs (Windows:
   `$env:LOCALAPPDATA\Ollama\server.log`; Linux: `journalctl` or a
   configured file).
2. **Linux supplementary check:** `journalctl -u ollama -n 200 --no-pager`
   (read-only, bounded, non-blocking), parsed in priority order for:
   - `"failure during GPU discovery"` + `"runner crashed"` → the specific
     gfx902-class ROCm-enumeration crash. Report `verified=False` with a
     precise remediation pointing to A.9.2 section 4.
   - `"offloaded N/M layers to GPU"`, `N == M` → `offload_status="full"`,
     `verified=True`.
   - `"offloaded N/M layers to GPU"`, `N < M` → `offload_status="partial"`,
     `verified=True` (GPU is engaged, just not fully), remediation message
     pointing to context-length tuning.
   - None found in the available window → fall through to the `/api/ps`
     result alone; absence of a matching log line is not treated as
     failure (log may have rotated, `journalctl` access may be restricted).
   - If `journalctl` itself is unavailable (non-systemd system, permission
     denied, command not found) — catch, skip silently, rely on `/api/ps`
     alone.
3. If neither method confirms engagement and `vulkan_enabled` was `False`
   from `detect()`: report the specific guidance — env var not set or
   Ollama not restarted after setting it.

---

## A.5 Standalone Detection Applet — `tasker-hardware`

A separate CLI entry point from the main `tasker` command, since detection
is a distinct, infrequent operation (run once per machine, or on-demand),
not something that should add latency to every harness invocation.

```toml
# pyproject.toml
[project.scripts]
tasker = "cli.shell:main"
tasker-hardware = "tasker.config.detect:cli_main"
```

| Subcommand | Behavior |
|---|---|
| `tasker-hardware detect` | Runs full live detection (`detect()` only, no `verify_live()`), prints a human-readable report, writes `.tasker/hardware_profile.json` |
| `tasker-hardware verify` | Runs `detect()`, then `verify_live()` against a real running Ollama + loaded model. Reports GPU engagement during actual inference, offload status, and specific remediation if not engaged. Populates the `gpu_verified_*` cache fields. |
| `tasker-hardware show` | Reads and prints the current cache without re-running detection (fast path) |
| `tasker-hardware clear` | Deletes the cache file, forcing redetection on next use |

`ModeConfigurator`'s `resolve_hardware_profile()` consumes the cache via the
three-source order in A.3.1 — it never calls `verify_live()` itself, since
that requires a running Ollama instance and meaningfully more latency;
`verify` is a manually-invoked diagnostic step, not part of the normal
startup path.

---

## A.6 Phase 7.5 — Roadmap Addition

Inserted between the original Phase 7 (Hardening) and "core roadmap
complete," reflecting the actual sequence this work was done in.

| Sub-phase | Description | Real-hardware verification |
|---|---|---|
| 7.5.1 | Linux/WSL2 primary dev environment migration; audit and fix any Windows-only path/string assumptions; `.gitattributes` line-ending normalization | Full suite + 3 smoke tests (CHAT/CODE/COWORK) run from WSL2 |
| 7.5.2 | `tasker-hardware` applet scaffold; cache schema; `ModeConfigurator` three-source resolution order; `GPUBackend` ABC + `NoGpuBackend` | Unit only (no real GPU needed) |
| 7.5.3 | `NvidiaBackend` — detect + verify | **Designlab1** |
| 7.5.4 | `AmdApuBackend` — general Vulkan-based detect + verify (per general dual-platform guide, A.9.1) | **TASKER-P1** (first pass) |
| 7.5.5 | `AmdApuBackend` refinement — gfx902-specific ROCm-disable env vars, group-membership check, journalctl offload-status verification (per A.9.2) | **TASKER-P1** (refined pass — confirms `offload_status="full"`, not just GPU presence) |
| 7.5.6 | Worker VRAM cross-check (NVIDIA discrete + AMD unified-memory-with-reserve); orchestrator-to-provider factory wiring confirmed live (carried over from the pre-existing live-verification gap identified before this addendum) | Both machines, full 3-stage smoke test with no `--profile` flag |

This addendum's prompts (A.7) implement 7.5.1 through 7.5.6 in that order.
Each sub-phase's unit tests must pass before proceeding to the next; live
hardware verification happens only at the sub-phase boundaries noted above,
not after every individual file change.

---

## A.7 Implementation Prompts (Cowork/Code Session Reference)

The actual phase-by-phase prompts used to implement 7.5.1–7.5.6 are
preserved in full in this conversation's history and should be used
verbatim when resuming work in a new session. They are summarized here for
the phase tracker; do not re-derive them from scratch — copy from the
session transcript or `docs/COWORK_PROMPT.md` once added there (see A.8).

Summary of what each sub-phase's prompt covers:

- **7.5.1:** WSL2 migration audit (path handling, `DesktopNotifier`
  cross-platform fallback, CLI help text), `.gitattributes`, dual
  Windows+Linux setup docs in `CLAUDE.md`, full suite + smoke tests from
  WSL2.
- **7.5.2:** `GPUBackend` ABC, `GPUInfo` dataclass, `NoGpuBackend`,
  `tasker-hardware` applet scaffold (detect/verify/show/clear), cache
  read/write with hostname-scoping, `ModeConfigurator` resolution order
  rewrite, `.gitignore` covering `.tasker/`.
- **7.5.3:** `NvidiaBackend`, mocked unit tests, live verify on Designlab1.
- **7.5.4:** `AmdApuBackend` v1 (env var check, static memory estimate,
  `/api/ps`-based `verify_live()`), per the general dual-platform guide.
- **7.5.5:** `AmdApuBackend` refinement — three-variable env check,
  `rocm_disabled` flag, `grp`-module group check, `journalctl`-based
  offload-status parsing, per the gfx902-specific guide.
- **7.5.6:** Worker VRAM cross-check implementation, confirmation that the
  orchestrator factory (built in the pre-addendum live-verification
  session) correctly consumes the now-dynamic `HardwareProfile`, final
  paired live verification on both machines.

---

## A.8 Documentation Additions

Two new reference documents, copied verbatim from validated external
sources into the repository as authoritative troubleshooting material:

- `docs/Ollama_AMD_APU_Install_Guide.md` — general dual-platform
  (Windows + Linux) AMD APU + Ollama Vulkan setup guide. Covers Vega 8
  Mobile through RDNA3-generation APUs broadly. Use as the default
  reference for any AMD APU machine.
- `docs/ollama-amd-igpu-config-guide.md` — gfx902/Raven2-specific guide,
  validated directly against TASKER-P1's exact chip (Ryzen 5 3500U). Use
  as the authoritative reference when the general guide's
  `OLLAMA_VULKAN=1`-only fix is insufficient (silent runner crash via
  ROCm enumeration on hardware below ROCm's supported list).

`CLAUDE.md` must reference both, noting which one ended up being load-bearing
for TASKER-P1 specifically (recorded after 7.5.5's live verification).

---

## A.9 Reference Document Index

| Document | Scope | Authoritative for |
|---|---|---|
| `docs/Ollama_AMD_APU_Install_Guide.md` | Windows + Linux, Vega/RDNA2/RDNA3 generations broadly | General AMD APU setup; first guide to consult |
| `docs/ollama-amd-igpu-config-guide.md` | Linux/systemd, gfx902 (Raven/Raven2) specifically | TASKER-P1; any hardware below ROCm's supported list exhibiting silent crash-to-CPU-fallback |

---

## A.10 Testing Strategy Additions

Extends original SDD Section 12.2/12.3 test matrix:

| Surface | Unit | Real-hardware verification |
|---|---|---|
| `GPUBackend` ABC + chain priority | ✓ (mocked) | — |
| `NvidiaBackend` | ✓ (mocked `nvidia-smi`) | ✓ Designlab1 |
| `AmdApuBackend.detect()` | ✓ (mocked `lspci`/CIM, env vars, `grp`) | ✓ TASKER-P1 |
| `AmdApuBackend.verify_live()` | ✓ (mocked `/api/ps`, mocked `journalctl`) | ✓ TASKER-P1 |
| `tasker-hardware` CLI (detect/verify/show/clear) | ✓ (mocked backend) | ✓ both machines |
| Cache hostname-scoping | ✓ (mocked hostname/filesystem) | — |
| `ModeConfigurator` 3-source resolution | ✓ | ✓ both machines (no `--profile` flag) |
| Worker VRAM cross-check (NVIDIA + AMD unified) | ✓ (mocked `HardwareProfile`) | — |
| Linux/WSL2 full suite parity | — | ✓ (suite run count/pass parity vs. prior Windows runs) |

New test files: `tests/unit/test_gpu_backends.py`,
`tests/unit/test_hardware_detect.py` (extended from Phase 7's version),
`tests/unit/test_hardware_cli.py`,
`tests/unit/test_worker_availability_vram.py`.

No live-hardware-dependent assertions belong in `tests/unit/` — anything
requiring a real GPU, real `nvidia-smi`/`journalctl` output, or a real
running Ollama instance is a manual verification step (A.6 table), not an
automated test.

---

## A.11 Checklist Additions (`docs/TASKER_CHECKLIST.md`)

```
## Phase 7.5 -- Cross-Platform Migration + Dynamic Hardware Detection
- [ ] 7.5.1 Linux/WSL2 verified as primary dev environment (full suite + 3 smoke tests from WSL2)
- [ ] .gitattributes added, line-ending drift normalized
- [ ] 7.5.2 GPUBackend ABC + GPUInfo + NoGpuBackend
- [ ] tasker-hardware applet (detect/verify/show/clear) scaffolded
- [ ] Cache schema + hostname-scoping implemented
- [ ] ModeConfigurator 3-source resolution order implemented
- [ ] .tasker/ fully gitignored (not just checkpoints/sessions)
- [ ] 7.5.3 NvidiaBackend implemented + unit tested
- [ ] NvidiaBackend verified on real hardware (Designlab1)
- [ ] 7.5.4 AmdApuBackend v1 (general guide) implemented + unit tested
- [ ] AmdApuBackend v1 verified on real hardware (TASKER-P1, first pass)
- [ ] 7.5.5 AmdApuBackend refined (gfx902 env vars, group check, journalctl offload parsing)
- [ ] AmdApuBackend refined version verified on real hardware (TASKER-P1, offload_status="full" confirmed)
- [ ] 7.5.6 Worker VRAM cross-check implemented + unit tested
- [ ] Orchestrator factory confirmed consuming dynamic HardwareProfile correctly
- [ ] Final paired live verification: both machines, no --profile flag, 3-stage smoke test each
- [ ] docs/Ollama_AMD_APU_Install_Guide.md added to repo
- [ ] docs/ollama-amd-igpu-config-guide.md added to repo
- [ ] CLAUDE.md updated: Linux/WSL2 primary, Windows secondary, both AMD guides referenced
- [ ] AMD discrete / Intel / Apple Silicon explicitly documented as out-of-scope extension points
```

---

*This addendum should be merged into SDD.md proper (Section 8 replaced,
Section 13's roadmap table gaining the 7.5 row, Section 15's references
gaining A.9's two documents) once Phase 7.5 is complete and verified on
both machines — at that point this file can be deleted and its content
considered absorbed into the canonical spec.*
