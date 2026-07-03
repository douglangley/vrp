# KG-UV96M settings — progress log

A dated, append-only log for the **KG-UV96M radio-wide settings** sub-project
(separate from the repo-root `PROGRESS_LOG.md`, which tracks the main driver).
Newest entries at the top. See [`PLAN.md`](PLAN.md) for setup and method.

Record each mapping session here: which settings you changed, the diff result
(address + old→new bytes), the deduced encoding, and the full option list for
any combo you mapped.

---

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
