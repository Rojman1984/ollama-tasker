# Ollama AMD Integrated GPU Configuration Guide
**Target hardware:** AMD Ryzen 5 3500U (Picasso/Raven2) with Radeon Vega 8 Mobile iGPU
**Tested on:** Ubuntu 24.04 LTS, Ollama (systemd service install)
**Last verified:** April 2026

---

## 1. Why This Guide Exists

Older AMD APUs (Raven/Raven2, gfx902 architecture) are **below ROCm's officially supported hardware list**. Attempting to use ROCm on these chips causes Ollama's runner to crash silently during GPU discovery, falling back to CPU-only inference with no clear error message.

**Symptom:**
```
level=INFO msg="offloading 0 repeating layers to GPU"
level=INFO msg="offloaded 0/17 layers to GPU"
```

**Root cause (found in journal logs):**
```
level=INFO msg="failure during GPU discovery" ... error="runner crashed"
```

The fix is to bypass ROCm entirely and force Ollama onto its **Vulkan** compute backend, which has full support for Vega-generation iGPUs via the Mesa RADV driver.

---

## 2. Pre-Flight: Identify Your Hardware

```bash
lspci | grep -i "vga\|display\|amd\|radeon"
cat /proc/cpuinfo | grep "model name" | head -1
lsmod | grep -i "amdgpu"
dpkg -l | grep -i "mesa-vulkan\|libdrm-amdgpu"
```

You need confirmation of three things before proceeding:
- A VGA controller line showing `AMD/ATI [Radeon Vega Series...]` or similar
- The `amdgpu` kernel module loaded
- `mesa-vulkan-drivers` package installed (ships by default on most modern Ubuntu installs)

If `mesa-vulkan-drivers` is missing:
```bash
sudo apt update
sudo apt install -y mesa-vulkan-drivers vulkan-tools
```

Verify Vulkan can see the GPU independently of Ollama:
```bash
vulkaninfo --summary 2>/dev/null | grep -i "gpu\|device\|amd\|radeon"
```

---

## 3. Add User Groups

Both your login user and the `ollama` service account need GPU device access:

```bash
sudo usermod -a -G video,render $USER
sudo usermod -a -G video,render ollama
```

A reboot or fresh login is needed for group changes to take effect for your own shell session. The `ollama` systemd service picks up group membership on next restart, no reboot required for that part.

---

## 4. Configure the Ollama systemd Service

Create a clean drop-in override (this avoids editing the main unit file directly, so updates won't clobber your config):

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d/
sudo bash -c 'cat > /etc/systemd/system/ollama.service.d/override.conf << EOF
[Service]
Environment="OLLAMA_VULKAN=1"
Environment="ROCR_VISIBLE_DEVICES=-1"
Environment="HIP_VISIBLE_DEVICES=-1"
Environment="OLLAMA_FLASH_ATTENTION=1"
EOF'
```

**What each variable does:**

| Variable | Purpose |
|---|---|
| `OLLAMA_VULKAN=1` | Enables the experimental Vulkan compute backend |
| `ROCR_VISIBLE_DEVICES=-1` | Disables ROCm device enumeration entirely — prevents the crash |
| `HIP_VISIBLE_DEVICES=-1` | Belt-and-suspenders disable for the HIP runtime layer |
| `OLLAMA_FLASH_ATTENTION=1` | Enables flash attention for better throughput on longer contexts |

Apply the config:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

---

## 5. Verify GPU Discovery

Watch the journal in real time while the service restarts:
```bash
sudo journalctl -u ollama -f | grep -i "vulkan\|gpu\|layer\|offload\|compute"
```

**You're looking for this line** — confirmation Vulkan found your iGPU:
```
msg="inference compute" library=Vulkan name=Vulkan0 description="AMD Radeon Vega Mobile Gfx (RADV RAVEN)" type=iGPU total="9.3 GiB" available="8.4 GiB"
```

If you instead see `failure during GPU discovery ... error="runner crashed"`, the ROCm disable variables didn't take. Re-check the override file:
```bash
cat /etc/systemd/system/ollama.service.d/override.conf
systemctl show ollama | grep -i environment
```

---

## 6. Load a Model and Confirm Full Offload

```bash
ollama run <your-model> "hello"
```

In the journal, confirm **all** layers offloaded (not partial):
```
msg="offloading 16 repeating layers to GPU"
msg="offloading output layer to GPU"
msg="offloaded 17/17 layers to GPU"
```

If you see something like `offloaded 12/17`, the model is too large for available VRAM and is partially falling back to CPU — see the VRAM budgeting section below.

---

## 7. Benchmark Token Throughput

```bash
curl -s http://localhost:11434/api/generate -d '{
  "model": "<your-model>",
  "prompt": "count from 1 to 10",
  "stream": false
}' | jq '{eval_count: .eval_count, tokens_per_sec: (.eval_count / .eval_duration * 1e9)}'
```

**Reference numbers for Vega 8 Mobile (gfx902) via Vulkan:**

| Backend | Typical Throughput |
|---|---|
| CPU only (4 threads) | 2–4 tokens/sec |
| Vulkan (this guide) | 30–40 tokens/sec |
| Dedicated discrete GPU (reference) | 80–120+ tokens/sec |

A roughly 10x improvement over CPU-only is the expected, realistic outcome on this hardware class. Vulkan on an iGPU will not match a discrete GPU, but it's a meaningful and free performance unlock.

---

## 8. VRAM Budgeting for Multi-Agent / Concurrent Model Use

Vega Mobile iGPUs use **shared system memory**, allocated at the BIOS/UEFI level (commonly called UMA frame buffer). Check your current allocation:

```bash
cat /sys/class/drm/card*/device/mem_info_vram_total
```

If running multiple small models concurrently (e.g., a planner + coder agent split), budget conservatively:

```
Per-instance overhead:     ~700 MB
Small model weights (1-2B): ~900 MB–1.6 GB
Two concurrent instances:   ~3.2 GB
```

Compare against your total iGPU allocation (commonly 2–8 GB depending on BIOS settings) before assuming both models will fit on GPU simultaneously. If you exceed available VRAM, Ollama will silently spill the overflow to system RAM rather than failing outright — slower, but it won't crash.

---

## 9. Common Failure Modes & Fixes

**Problem: `runner crashed` persists after adding override.conf**
```bash
sudo systemctl daemon-reload
sudo systemctl stop ollama
sudo systemctl start ollama
```
A `restart` sometimes doesn't fully reload environment drop-ins on some systemd versions — explicit `stop` then `start` forces a clean reload.

**Problem: Vulkan shows `compute=0.0` and never offloads**
Confirm the override file actually applied:
```bash
systemctl show ollama | grep -i "environment\|vulkan"
```
If `OLLAMA_VULKAN` isn't listed, the file wasn't read — check file permissions and exact path (`/etc/systemd/system/ollama.service.d/override.conf`, not `/etc/ollama/`).

**Problem: `vulkaninfo` shows no AMD device at all**
Mesa Vulkan drivers may be missing or the kernel `amdgpu` module isn't bound to the GPU:
```bash
sudo apt install --reinstall mesa-vulkan-drivers
lsmod | grep amdgpu
```

**Problem: Partial layer offload (e.g., `12/17`) despite available VRAM**
Lower the context window to free headroom:
```bash
# Add to override.conf
Environment="OLLAMA_CONTEXT_LENGTH=2048"
```

---

## 10. Quick Reference — Full Working Config

```ini
# /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_VULKAN=1"
Environment="ROCR_VISIBLE_DEVICES=-1"
Environment="HIP_VISIBLE_DEVICES=-1"
Environment="OLLAMA_FLASH_ATTENTION=1"
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo journalctl -u ollama -f | grep -i "vulkan\|offload"
```

That's the complete, minimal config to get a ROCm-unsupported AMD iGPU running LLM inference via Vulkan on Ollama.
