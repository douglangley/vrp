# KG-UV96M settings — progress log

A dated, append-only log for the **KG-UV96M radio-wide settings** sub-project
(separate from the repo-root `PROGRESS_LOG.md`, which tracks the main driver).
Newest entries at the top. See [`PLAN.md`](PLAN.md) for setup and method.

Record each mapping session here: which settings you changed, the diff result
(address + old→new bytes), the deduced encoding, and the full option list for
any combo you mapped.

---

## ▶ RESUME HERE (state as of 2026-07-02, branch `kg-uv96m-driver`, 6 commits)

**Done:** 12 settings mapped AND implemented in `kguv96m.py`
(`get_settings`/`set_settings`, `has_settings=True`, tests passing, editable in
VRP's Settings dialog). Channel read/write + CTCSS/TSQL/DTCS all
hardware-verified. Radio was restored to original (`uv96m-live.img`).

**Goal:** map + implement the remaining ~24 settings. They're documented below
(encodings + candidate address clusters) but their exact addresses aren't pinned
— one 39-setting change-pass was too ambiguous (small option ranges → identical
byte deltas). Finish via **targeted passes**.

**Method for each pass** (no USBPcap needed):
1. Baseline is `uv96m-live.img` (original) — the radio is currently in that state.
   If unsure, `read_image.py COM4 baseline.img` first.
2. In RT Systems change a **batch chosen so every setting's (old→new) BYTE delta
   is unique** (see Pass-2 example below — that's the whole trick; small enums
   compete for the few low values, so only a handful of same-range settings per
   pass).
3. Upload from RT. Then:
   `read_image.py COM4 passN.img` and
   `diff_images.py uv96m-live.img passN.img`.
4. Match each changed address to a setting by its (old→new) value, using the
   option lists below. Add mapped fields to `_MEM_FORMAT_96M` + `get_settings`/
   `set_settings` (copy the existing 12 as the pattern) + a test. Log it here.
5. Repeat. The **9 checkboxes are slowest** (only 0/1): at most ~2 per pass (one
   `1→0` + one `0→1` are distinguishable); or map them by struct-order guess and
   verify. Their 5 `1→0` candidate addresses are `0x0420,0421,0428,0429,042e`.

**NEXT — Pass 2 (ready-to-run; maps 9, all deltas unique).** From the original
state, change in RT then upload:
| Setting | Change to | expected byte delta |
|---|---|---|
| VOX | 9 Level | 0→9 |
| Ring Time | 10 seconds | 5→10 |
| TOT Pre-Alert | 2 seconds | 5→2 |
| VOX Delay | 5 seconds | 1→5 |
| Priority Channel | CH-055 | low byte 1→55 |
| Startup Display | Batt-V | 0→1 |
| Battery Indicator | Percent | 0→2 |
| Roger | Both | 0→3 |
| Beep | uncheck | 1→0 |
(Startup Display is very likely `0x049a` already — 0→1 right before the startup
message; Pass 2 will confirm.)

Baselines/tools: `uv96m-live.img` (original), `uv96m-set-base2.img` /
`uv96m-set-changed.img` (the big ambiguous pass, kept for reference),
`tools/kg-uv96m/{read_image,diff_images,decode_capture}.py`. Settings struct is
`0x0420`–`0x04bf` (+`0x4000` mirror the radio self-maintains — never write it).

---

## 2026-07-02 — Clarifying encodings/option lists for the 8 mapped settings

Confirmed encodings (address, type, meaning) from NVDA-read option lists:

- **`0x0423` Time-Out Timer** — `u8`, value **1–60**, seconds = value × 15
  (15 s … 900 s, 15 s steps; no "Off"). e.g. 60 s → `0x04`, 165 s → `0x0b`.

- **`0x042b` Backlight Time** — `u8`, index over list **On, 1 s … 20 s, Off**:
  `0` = On (always), `1`–`20` = seconds, `21` = Off. (10 s → `0x0a`, 4 s →
  `0x04`; On=0 / Off=21 inferred from list order, confirm by capture if desired.)

- **`0x042c` Brightness (Active)** — `u8`, **1–10** literal (min 1 … max 10).

- **`0x042d` Brightness (Standby)** — `u8`, **`0` = Off**, `1`–`10` = level
  (list: Off, 1 … 10). Differs from Active (no Off there).

- **`0x047b` Squelch** — `u8`, **0–9** literal.

- **`0x0474` Work Channel B** — `ul16` LE, value = **channel number 1–400**
  (CH-001 … CH-400). (Work Channel A is the sibling at `0x0476`, same encoding —
  verify in a settings pass.)

- **`0x049b` Startup Message** — **16-char ASCII**, space-padded
  (`0x049b`–`0x04aa`). Max length 16 confirmed in RT.

- **`0x04af` Area Message** — **8-char ASCII**, space-padded
  (`0x04af`–`0x04b6`). Max length 8 confirmed in RT.

All 8 originally-mapped settings are now fully specified (address + type + option
list/range).

**+3 more mapped** by matching option-list index deltas against the base↔changed
diff (unique matches):
- **`0x0431` PTT-ID Delay** — `u8`, `ms = value × 100` (100 … 3000 ms).
- **`0x0437` Auto Lock** — `u8`, index over `[Off, 10, 20, 30, 40, 50, 60 s]`.
- **`0x0479` Step** — `u8`, index over
  `[2.5, 5, 6.25, 8.33, 10, 12.5, 25, 50, 100, 1000 K]`.
- **`0x0476` Work Channel A** — `ul16` LE, channel 1–400 (sibling of `0x0474`).

**12 settings now have addresses** (the 8 above + these 4). Ready to implement.

### Encodings known, ADDRESS still TBD (need targeted single-setting diffs)

The one 39-setting pass moved these to non-unique byte values, so their address
is one of a candidate cluster. Change ONE at a time (or a few to distinct values),
`read_image.py` + `diff_images.py`, to pin each. Option lists / encodings:

- Checkboxes (`1`=checked/`0`): **Beep, Battery Save, LED (Standby), Voice
  Guide, Menu Enable** — candidate addrs `0x0420, 0x0421, 0x0428, 0x0429,
  0x042e` (all went 1→0; assignment unknown).
- Checkboxes (`0`→`1` in the pass): **Wx Mode, Wx Alert, Scan Detect, RPT Tone**.
- Enums (0-based index into their list):
  - **Battery Indicator** `[Icon, Voltage, Percent]`
  - **Lock Mode** `[Key, Key+PTT, Key+ENC]`
  - **Priority Scan** `[Off, RX Off, Always On]`
  - **PTT-ID** `[Off, BOT, EOT]`
  - **Roger** `[Off, BOT, EOT, Both]`
  - **Scan Mode** `[TO, CO, SE]`
  - **Startup Display** `[MSG, Batt-V]`
  - **Tone Burst** `[1750, 2100, 1000, 1450 Hz]`
  - **Tone Save** `[RX, TX, RX & TX]` (verify — the `0→2` cluster is over-subscribed,
    so one of these enums has an unexpected encoding/base)
  - **VOX** `[Off, 1 Level … 10 Level]`
  - **VOX Delay** `[Off, 1 … 5 s]`
  - **Ring Time** `[Off, 1 … 10 s]`  (candidate `0x0424` / `0x0435`)
  - **TOT Pre-Alert** `[Off, 1 … 10 s]`  (candidate `0x0424` / `0x0435`)
  - **Work Mode A / B** (options not captured — VFO / CH Num / CH Name …)
  - **Wx Notification** (options not captured)
- **Priority Channel** — `ul16` 1–400 (candidate `0x0426` / `0x0439` / `0x0472`).
- **Wx Frequency** — weather channel (option list not captured).

### IMPLEMENTED — the 12 mapped settings are now editable in VRP

Added a `settings` region to `_MEM_FORMAT_96M` and `get_settings`/`set_settings`
to `kguv96m.py`, `has_settings = True`. Groups: Basic (squelch, time-out timer,
PTT-ID delay, auto-lock, step, work channel A/B), Display (backlight, brightness
active/standby), Messages (startup 16-char, area 8-char). Encodings per the map
above; `_set_str` space-pads to match RT; strings use `autopad=False`. Verified:
`get_settings` reads the baseline image to the exact NVDA-captured values;
`set_settings` writes only the mapped bytes; VRP backend reports `has_settings`
+ 12 settings in 3 groups. Tests: `test_kguv96m_settings_roundtrip`,
`test_kguv96m_settings_addresses`. Full suite 187 pass.

Next: targeted single-setting diff passes to map + add the remaining ~24
(candidate clusters + encodings listed above).

## 2026-07-02 — Project set up; settings struct located; 8 settings mapped

Kicked off as a sub-project so others can help add settings. The channel driver
(read/write/CTCSS/TSQL/DTCS) is complete and hardware-verified on `main`'s
`kg-uv96m-driver` branch; this log tracks only the settings layer.

**Established:**
- All radio-wide settings live in one struct at **`0x0420`–`0x04bf`** (with an
  identical `+0x4000` firmware mirror the radio self-maintains — write only the
  primary; the upload `_CONFIG_MAP` already does).
- Encodings observed: plain integer, small enum index, `seconds ÷ 15`, and
  fixed-length space-padded ASCII (message strings).
- **Mapped with high confidence** (unique-value diff): Time-Out Timer `0x0423`
  (sec ÷ 15), Backlight Time `0x042b` (literal sec), Brightness Active `0x042c`
  / Standby `0x042d` (literal), Squelch `0x047b` (literal), Work Channel B
  `0x0474` (literal ch#), Startup Message `0x049b` (~16 B ASCII space-padded),
  Area Message `0x04af` (~8 B ASCII).

**Not yet mapped (~30):** the checkbox settings (Beep, Battery Save, Voice
Guide, Menu Enable, Scan Detect, RPT Tone, LED Standby, Wx Mode/Alert, …) and
several combos (VOX, VOX Delay, Step, Scan Mode, Roger, PTT-ID, PTT-ID Delay,
Priority Channel/Scan, Lock Mode, Battery Indicator, Ring Time, TOT Pre-Alert,
Tone Burst, Tone Save Scan, Startup Display, Work Mode A/B, Work Channel A, Auto
Lock, Wx Notification/Frequency). A single 39-setting pass could not separate
these because many changed to identical values.

**Lesson / method fix:** change only a **few settings per pass, each to a
distinct value** (see PLAN "Method"), so every diff is unambiguous. Text fields
make ideal anchors.

**Created:** `docs/kg-uv96m-settings/PLAN.md`, this log, and repo tools
`tools/kg-uv96m/{read_image,diff_images,decode_capture}.py`.

**Next:** map the checkboxes first (one small distinct batch per pass), capturing
each combo's full option list as you go; then implement `get_settings`/
`set_settings` + `has_settings=True` in the driver.
