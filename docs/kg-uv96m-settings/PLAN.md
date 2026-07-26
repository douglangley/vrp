# KG-UV96M radio-wide settings — mapping & implementation plan

A **separate sub-project**: reverse-engineer the Wouxun KG-UV96M's radio-wide
settings (squelch, timers, backlight, VOX, beep, priority channel, boot message,
…) and expose them as editable settings in VRP. The channel driver
(`chirp_backend/extra_drivers/kguv96m.py`) — read, write, and tones — is already
**done and hardware-verified**; this project only adds the settings layer.

Track progress in [`PROGRESS_LOG.md`](PROGRESS_LOG.md) (this project's own log,
separate from the repo-root `PROGRESS_LOG.md`).

---

## What's already known

- The driver reads/writes the whole 32 KiB image and is registered in VRP
  (model **Wouxun KG-UV96M**). It talks the kg935g protocol at **9600 baud**.
- **All radio-wide settings live in a compact struct at `0x0420`–`0x04bf`**
  (~160 bytes). There is an identical **mirror at `+0x4000`** (`0x4420`…) that
  the radio maintains itself — the driver's upload `_CONFIG_MAP` writes only the
  primary at `0x0420`, and the radio copies it. **Do not add the mirror to the
  write map.**
- Encodings seen so far: plain integer, small enum index, `seconds ÷ 15`, and
  fixed-length space-padded ASCII (the two message strings).
- **Confidently mapped already** (from a first diff pass):

  | Address | Setting | Encoding |
  |---|---|---|
  | `0x0423` | Time-Out Timer | seconds ÷ 15 |
  | `0x042b` | Backlight Time | literal seconds |
  | `0x042c` | Brightness (Active) | literal |
  | `0x042d` | Brightness (Standby) | literal |
  | `0x047b` | Squelch | literal |
  | `0x0474` | Work Channel B | literal channel number |
  | `0x049b` | Startup Message | ASCII, space-padded (~16 B) |
  | `0x04af` | Area Message | ASCII, space-padded (~8 B) |

  The remaining ~30 settings (many checkboxes + combos) are **not yet located**,
  because a first attempt changed them all at once to overlapping values and the
  diff couldn't tell identical changes apart. See "Method" for how to avoid that.

- **Gotcha:** `0x049b` (the model name "KG-UV96M") is the *editable* Startup
  Message. Identify/match key on the immutable `WOUXUN` block at `0x0340`
  instead — don't reintroduce a dependency on `0x049b`.

---

## Prerequisites / setup

### 1. The repo + Python env

```bash
git clone <this repo> && cd vrp
git clone --depth=1 https://github.com/kk7ds/chirp.git   # driver base
# check out the pinned CHIRP commit (run-win.bat / run-mac.sh do this for you)
uv sync --extra dev
```
Verify: `uv run python tools/kg-uv96m/read_image.py --help` runs (well, it takes
`PORT OUT`; just confirm it imports).

### 2. Radio + cable

- A **Wouxun KG-UV96M** and its **USB programming cable** on a COM port
  (an FTDI USB-serial adapter shows up as e.g. `COM4`).
- Confirm the port: Device Manager → Ports (COM & LPT) → "USB Serial Port (COMx)".

### 3. RT Systems KG-UV96 programmer

The OEM software. It's the ground truth: you change a setting there, upload, and
the radio stores the "correct" bytes. (You do **not** commit any RT files or
radio images — they contain personal channel data and are gitignored.)

### 4. USBPcap (USB capture driver) — **required for protocol captures**

Only needed when you must see *what RT actually sends* (verifying an encoding,
or if a setting turns out to live outside the region the driver already
read/writes). The settings-diff method below does **not** need it, but install
it up front so you're ready.

1. Download from **<https://desowin.org/usbpcap/>** and install.
2. **Reboot** after installing (the driver loads at boot).
3. No Wireshark needed — capture with the bundled
   `C:\Program Files\USBPcap\USBPcapCMD.exe` straight to a `.pcap`, then decode
   with `tools/kg-uv96m/decode_capture.py`.
4. Verify: `& 'C:\Program Files\USBPcap\USBPcapCMD.exe' --extcap-interfaces`
   lists `\\.\USBPcap1`, `\\.\USBPcap2`, …

### 5. NVDA (accessible value capture)

RT Systems' settings dialog isn't easily screenshot-verified without sight, so
read it with an **NVDA speech capture** (NVDA+F to review, or the speech-history
add-on) — this gives every setting name + current value as text, and lets you
read each combo's full list of options (needed to build dropdowns).

---

## Method — mapping settings by diff (primary workflow)

**No USBPcap needed here.** You use the driver to read images and diff them.

**Always back up first:** read the radio and *keep that image* — it's your
restore point (`read_image.py` → `original.img`; to restore, upload it back with
`restore_image.py`-style logic, or just re-upload your normal RT file).

1. **Baseline read**
   ```bash
   uv run python tools/kg-uv96m/read_image.py COM4 baseline.img
   ```
2. **Capture current values** — NVDA-read the RT settings dialog; save the text.
3. **Change settings — a FEW at a time, to DISTINCT values.**
   The cardinal rule (learned the hard way): if two settings change to the same
   value, the diff can't separate them. Change **one setting**, or a small batch
   where every new value is unique. Text fields (Startup/Area message) are great
   anchors — set them to something distinctive.
4. **Upload** the change from RT Systems to the radio.
5. **After read**
   ```bash
   uv run python tools/kg-uv96m/read_image.py COM4 after.img
   ```
6. **Diff**
   ```bash
   uv run python tools/kg-uv96m/diff_images.py baseline.img after.img
   ```
   Changed bytes at `0x0420`–`0x04bf` are the setting(s) you touched.
7. **Correlate** address ↔ setting ↔ encoding from the old→new value
   (integer? index? `÷15`? ASCII?). Record it in `PROGRESS_LOG.md`.
8. **Option lists:** for each combo you map, NVDA-read *all* its dropdown options
   in order — you'll need the full list to build the VRP setting.

### When to reach for USBPcap

- To confirm exactly which bytes/blocks RT writes for a setting (capture an RT
  upload, `decode_capture.py capture.pcap`, look at the `WRITE addr=…` lines).
- If a setting appears to live outside `0x0420`–`0x04bf` / isn't round-tripping.

Capture recipe (PowerShell):
```powershell
# 1. find the FTDI "USB Serial Converter" device address on a root hub:
& 'C:\Program Files\USBPcap\USBPcapCMD.exe' --extcap-interface \\.\USBPcap1 --extcap-config
# 2. capture just that device (address 12 in our setup) to a file:
$p = Start-Process 'C:\Program Files\USBPcap\USBPcapCMD.exe' `
     -ArgumentList '-d','\\.\USBPcap1','--devices','12','-o','capture.pcap' `
     -PassThru -WindowStyle Hidden
# 3. do the RT read/upload, then stop:
Stop-Process -Id $p.Id -Force
```
```bash
uv run python tools/kg-uv96m/decode_capture.py capture.pcap
```

---

## Implementation target (once enough settings are mapped)

In `chirp_backend/extra_drivers/kguv96m.py`:

1. Extend `_MEM_FORMAT_96M` with a `settings` struct at `0x0420` naming the
   mapped fields (use `ul16`/`u8` etc. per the encoding).
2. Implement `get_settings()` → a `chirp.settings.RadioSettings` /
   `RadioSettingGroup` tree (see kg935g's `_get_settings` for the pattern), and
   `set_settings()` to write them back.
3. Flip `get_features().has_settings = True`.
4. VRP already renders `RadioSettings` in an accessible `settings_dialog.py`
   Treebook, so the settings appear in the app automatically.
5. Add tests to `tests/test_extra_drivers.py`: each mapped setting round-trips
   through `get_settings`/`set_settings` on a synthetic image with no drift.

---

## Tools (in `tools/kg-uv96m/`)

| Script | Purpose |
|---|---|
| `read_image.py PORT OUT` | Read the radio to a `.img` via the driver (baseline/after). |
| `diff_images.py A B` | Show settings-struct byte changes between two images. |
| `decode_capture.py FILE.pcap` | Decode a USBPcap capture into READ/WRITE frames + FTDI control. |

## Safety notes

- **Back up before every upload.** Keep a known-good image; you can always write
  it back to recover.
- Uploading writes only the driver's `_CONFIG_MAP` regions; it never touches
  reserved areas. Still, treat the radio's data as precious.
- Personal data (`*.img`, `*.pcap`, RT files, screenshots) is gitignored — keep
  it local, never commit it.
