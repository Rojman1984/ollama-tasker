# Ollama on AMD APU Hardware — GPU Acceleration Install Guide

**Applies to:** Any AMD Ryzen APU with integrated Radeon graphics — desktop and
mobile, Vega/RDNA2/RDNA3 generations (e.g. 2500U, 3500U, 4600G, 4700U, 5600G,
5700G, 7840U, 8700G, and similar). Mobile "U" series and desktop "G" series
APUs use the same Vulkan path identically.
**Platforms covered:** Windows 11, Linux (Ubuntu/Debian-based)
**Last validated:** 2026-04-27

---

## TL;DR

AMD integrated GPUs are **not supported by ROCm**. Use **Vulkan** instead —
it's a single environment variable, works on both platforms, and requires
no special drivers beyond what's already installed.

```
OLLAMA_VULKAN=1
```

That's the whole fix in most cases.

---

## 1. Why ROCm Doesn't Work

ROCm (AMD's CUDA-equivalent) has essentially no iGPU support. It's built for
discrete Radeon RX/PRO cards. Ryzen APUs are explicitly excluded from the
support matrix.

On **Windows**, ROCm support is even narrower than Linux — it only covers
discrete cards, period. No APU workaround exists on Windows.

On **Linux**, there is a partial ROCm workaround using `HSA_OVERRIDE_GFX_VERSION`
to force-identify the iGPU as a supported chip (see §5), but it's fragile,
requires BIOS changes, and Vulkan is simpler and faster in practice.

**Bottom line: don't fight ROCm on an APU. Use Vulkan.**

---

## 2. Windows 11 Setup

### Step 1 — Set the environment variable

**GUI method:**
1. Start menu → search "Environment Variables" → *Edit the system environment variables*
2. Click **Environment Variables...**
3. Under **System variables**, click **New...**
   - Name: `OLLAMA_VULKAN`
   - Value: `1`
4. Click OK on all dialogs

**PowerShell method (run as your user, no admin needed):**
```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_VULKAN", "1", "User")
```

### Step 2 — Restart Ollama

```powershell
# If running as tray app
Stop-Process -Name "ollama" -Force
Start-Process "ollama" -ArgumentList "serve"

# If running as a Windows service
Restart-Service ollama
```

### Step 3 — Verify

Run any model and check the server log:

```powershell
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 30
```

Look for a line like:
```
level=INFO source=types.go:42 msg="inference compute" library=Vulkan
description="AMD Radeon(TM) Graphics" type=iGPU total="16.2 GiB"
```

`library=Vulkan` and `type=iGPU` confirm it's working. The `total` figure
shown is your unified memory pool (shared system RAM), not dedicated VRAM.

You can also confirm a model is using VRAM directly:
```powershell
curl http://localhost:11434/api/ps
```
Look for `size_vram` > 0 and matching the model's file size.

---

## 3. Linux Setup (Ubuntu/Debian)

### Step 1 — Set the environment variable persistently

```bash
sudo systemctl edit ollama.service
```

In the editor that opens, add:
```ini
[Service]
Environment="OLLAMA_VULKAN=1"
```

Save and exit, then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

**Session-only alternative (testing):**
```bash
OLLAMA_VULKAN=1 ollama serve
```

### Step 2 — Verify Vulkan is installed

Most distros include Vulkan support via Mesa by default. Check with:
```bash
vulkaninfo --summary
```

If not installed:
```bash
sudo apt install mesa-vulkan-drivers vulkan-tools
```

### Step 3 — Verify GPU usage

```bash
# Watch GPU activity live while running a prompt
sudo apt install radeontop
radeontop

# Check Ollama logs
sudo journalctl -fu ollama.service | grep -i vulkan
```

You should see the same `library=Vulkan` / `type=iGPU` confirmation as the
Windows log output.

---

## 4. BIOS Configuration (Both Platforms)

Most modern BIOS implementations use dynamic UMA (Unified Memory Architecture)
allocation, so this step is often unnecessary — but check if you're not seeing
expected VRAM availability.

1. Reboot into BIOS/UEFI setup
2. Find the iGPU memory setting — usually under:
   - **Advanced → UMA Frame Buffer Size**, or
   - **Advanced → AMD CBS → NBIO → GFX Configuration**
3. If set to a fixed small value (512MB, 1GB), either:
   - Set it to **Auto** (lets Windows/Linux dynamically allocate from system RAM), or
   - Increase it manually to **2–4GB** if Auto isn't available
4. Save and exit

**Note:** For Vulkan, this matters less than for ROCm — Vulkan generally
sees the full unified memory pool either way. Increase this primarily if
you're troubleshooting low `available` VRAM in the Ollama logs.

---

## 5. ROCm Workaround (Linux Only — Optional, Not Recommended)

If you specifically need ROCm rather than Vulkan (e.g. for a downstream
tool that requires ROCm directly), there is a fragile workaround:

```bash
sudo systemctl edit ollama.service
```
```ini
[Service]
Environment="HSA_OVERRIDE_GFX_VERSION=9.0.0"
```

The value `9.0.0` works for Vega-generation APUs (mobile 2000U/3000U series and
desktop 4000G/5000G series all use `gfx902`/`gfx903` — both map to the `9.0.0`
override). Confirmed via `rocminfo` on a Ryzen 5 3500U (Vega 8 Mobile): identifies
as `gfx902`. RDNA2/3 APUs (6000G/7000G/8000G series) will need a different
override value matching their actual gfx version — check `rocminfo` output for
the closest supported target.

You'll also need the ROCm-enabled Ollama container if running via Docker:
```bash
docker run -d --device /dev/dri --device /dev/kfd \
  -e HSA_OVERRIDE_GFX_VERSION=9.0.0 \
  -p 11434:11434 ollama/ollama:rocm
```

This path requires the BIOS VRAM carve-out to be set to a non-default value
(§4) or Ollama will refuse to recognize the iGPU at all.

**This does not work on Windows under any configuration** — ROCm on Windows
excludes APUs entirely, regardless of environment variables.

---

## 6. Context Length Tuning

GPU acceleration is half the performance story — context window size also
matters and is auto-calculated based on available VRAM. Check what was
auto-assigned:

```bash
# Linux
journalctl -u ollama | grep "default_num_ctx"

# Windows
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" | Select-String "default_num_ctx"
```

To force a larger context window, create a custom Modelfile:

```
FROM your-model-name
PARAMETER num_ctx 65536
```

```bash
ollama create your-model-64k -f Modelfile
ollama run your-model-64k
```

Smaller/quantized models leave more VRAM headroom for larger contexts — a
1-2B parameter model at Q8_0 quantization can typically support 64k-128k
context comfortably on a modern APU with 16GB+ unified memory.

---

## 7. Quick Troubleshooting Checklist

| Symptom | Likely Cause | Fix |
|---|---|---|
| `library=cpu` in logs instead of Vulkan | Env var not set or Ollama not restarted | Re-check §2/§3, fully restart Ollama process |
| Vulkan detected but `total` VRAM very low | BIOS UMA buffer set too small | Check §4, increase or set to Auto |
| ROCm errors on Windows | ROCm doesn't support Windows APUs at all | Switch to Vulkan — don't pursue ROCm on Windows |
| `ollama show` reports no GPU capability | This is about tool-calling capability flags, unrelated to GPU accel | Not a GPU issue — check model's Ollama capability tags separately |
| Model loads but inference is slow | Context length set too high for available VRAM | Reduce `num_ctx` or use a smaller quantization |
| `vulkaninfo` not found (Linux) | Vulkan tools not installed | `sudo apt install mesa-vulkan-drivers vulkan-tools` |

---

## 8. Summary

| Platform | Method | Complexity |
|---|---|---|
| Windows 11 | `OLLAMA_VULKAN=1` system env var | Trivial — one variable, no drivers |
| Linux | `OLLAMA_VULKAN=1` via systemd override | Trivial — one variable, Vulkan usually pre-installed |
| Linux (ROCm alt.) | `HSA_OVERRIDE_GFX_VERSION` + BIOS VRAM carve-out | Fragile — avoid unless specifically required |
| Windows (ROCm) | Not supported | N/A — don't attempt |

For virtually all use cases on AMD APU hardware, **Vulkan is the correct and
only path worth pursuing.** It's faster to set up, more reliable across
driver updates, and works identically on both platforms.

---

*This guide is hardware-generation agnostic — applicable to any Ryzen
APU with integrated Radeon graphics across Vega, RDNA2, and RDNA3
generations, mobile and desktop alike. Validated on AMD Ryzen 5 4600G
(Vega 7, desktop) under Windows 11, with GPU identification cross-checked
against AMD Ryzen 5 3500U (Vega 8 Mobile, gfx902) — confirming the same
Vulkan path and ROCm override value apply across the mobile/desktop Vega
generation.*
