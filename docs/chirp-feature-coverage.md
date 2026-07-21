# CHIRP Feature Coverage Checklist

Tracks every function exposed in CHIRP's own UI (`chirp/chirp/wxui`) against
VRP's accessible implementation, so nothing is missed. Update the Status column
as phases land. Status: ☐ not started · ◐ in progress · ☑ done · ✗ intentionally
not implemented.

Config/recent-files subsystem is DONE (Preferences dialog + Open Recent +
persistent JSON config). Still deferred (CHIRP-GUI editor behaviors or need a
model picker): Open Stock Config, Select bandplan, Auto edits, New (empty
image), New Window.

Derived from CHIRP's menubar and editor modules. Re-derive after each CHIRP
update (`git pull` ./chirp) in case new dialogs appear.

## File menu

| Feature                | VRP phase | Status |
|------------------------|-----------|--------|
| New (empty image)      | 1         | ☐      |
| New Window             | 8         | ☐      |
| Open Image File        | 1         | ☑      |
| Open Stock Config      | 1         | ☑ (as an **import**: Radio ▸ Query Source ▸ Frequency lists… imports a CHIRP stock config into the loaded radio, rather than opening it as its own document) |
| Open Recent            | config    | ☑      |
| Save / Save As         | 1         | ☑      |
| Import (image / CSV)   | 8         | ☑ (generic CHIRP cross-model conversion, overwrite/skip, partial success + accessible per-channel report) |
| Export (to CSV)        | 8         | ☑ (whole image via File ▸ Export; a selected subset via the row context menu + Bulk operations dialog; no synthetic channel 0) |
| Load Module            | 8         | ☐      |
| Print / Print Preview  | 8         | ✗ (intentional — covered by Export to CSV; native print is inaccessible) |
| Close Image / Exit     | 1 / 0     | ☑      |

## Edit menu

| Feature                         | VRP phase | Status |
|---------------------------------|-----------|--------|
| Copy to / Move to (bulk)        | 3         | ☑      |
| Delete / Delete + shift         | 3         | ☑      |
| Insert / Move / Sort / Arrange  | 3         | ☑ (Sort: any column + synthetic Transmit frequency, non-contiguous-safe; also a quick Sort submenu in the row context menu) |
| Cut / Paste (clipboard)         | 3         | ☑ (same-image move/make-room; cross-image Paste uses generic migration and cross-image Cut safely becomes Copy) |
| Undo / Redo (channel ops)       | —         | ☑      |
| Find / Find Next                | 3         | ☑      |
| Goto channel                    | 3         | ☑      |
| Preferences                     | config    | ☑      |

## View menu

| Feature                | VRP phase | Status |
|------------------------|-----------|--------|
| Font size / large font | 8         | ☐      |
| Language               | 8         | ☐      |

## Radio menu

| Feature                          | VRP phase | Status |
|----------------------------------|-----------|--------|
| Download from Radio              | 4         | ☑ (verified on real hardware — Baofeng UV-5R Mini, COM4, 2026-06-23) |
| Upload to Radio                  | 4         | ☑ (verified on real hardware — Baofeng UV-5R Mini, COM4, 2026-06-24) |
| Query framework + import         | 7         | ☐ (removed 2026-07-05; import-destination dialog kept for Import from File) |
| Query: RepeaterBook              | 7         | ◐ (wired via CHIRP's mirror — Radio ▸ Query Source ▸ RepeaterBook; direct API pending VRP User-Agent) |
| Query: RadioReference            | 7         | ☐ (to be added purpose-built after RepeaterBook) |
| Import: Frequency lists (stock configs) | 7   | ☑ (Radio ▸ Query Source ▸ Frequency lists… — filterable chooser, imports a CHIRP stock config into the loaded radio; `chirp_backend/stock_configs.py`) |
| Auto edits toggle                | 8         | ☑ (offset always-on; mode/step/tone via Preferences ▸ Apply band-plan defaults; duplex intentionally manual) |
| Select bandplan                  | 8         | ☐      |

## Editors / dialogs

| Feature                          | VRP phase | Status |
|----------------------------------|-----------|--------|
| Memory editor grid (read)        | 1         | ☑      |
| Memory editor grid (edit fields) | 2         | ☑      |
| Radio settings editor            | 5         | ☑ (NVDA pass owed) |
| Banks editor (assign membership) | 6         | ☑ (NVDA pass owed) |
| Radio info                       | 8         | ☑      |
| About                            | 0         | ☑      |

## Notes

- **Cross-radio channel migration (VRP-only integration):** Phase 1 is complete
  (2026-07-21). `chirp_backend/migration.py` routes ordinary numbered
  `Memory`/`DVMemory` objects through CHIRP `import_logic`, clears foreign
  driver-private extras, validates/writes compatible rows, and reports every
  occupied/incompatible/failed/out-of-space row. File Import, RepeaterBook,
  Frequency lists, and cross-image clipboard Paste share the same undoable
  engine. Audit baseline: 385 targets from 358 pinned images, zero unexpected
  failures. Still open: bank membership, special memories, source/active
  subdevice-selection UX, D-STAR call-list side-effect tests, and screen-reader
  hand passes. See
  `docs/superpowers/plans/2026-07-21-cross-radio-migration.md`.
- **Favorite radios (VRP-only, not a CHIRP feature):** Radio ▸ Favorite radios…
  manages a starred-radio list (`vrp/serial_dialogs.py` `FavoritesDialog`,
  `vrp/config.py` favorites); the Download dialog gains a **Show: All radios /
  Favorites** toggle (default All). Lets users who program a few radios browse a
  short list instead of ~552.
- Developer-only items (reload driver/module, interact with driver, serial
  trace, bug report) are lower priority; revisit in Phase 10.
- **Auto edits (offset suggestion):** a partial form of CHIRP's "auto edits" is
  implemented — the channel editor auto-fills the **Offset** field with the
  band's standard repeater shift (from CHIRP's band plan) when you enter a
  frequency and Offset is blank (`chirp_backend/bandplan.py`,
  `EditChannelDialog._on_frequency_changed`). VRP fills the *magnitude only* and
  leaves the +/- **Duplex** direction to the user (deliberately unlike CHIRP,
  which also sets duplex). The band plan is chosen in **File ▸ Preferences ▸ Band
  plan (region)** (North America / Australia / IARU R1–R2–R3; default North
  America). The *other* band-plan fields — **mode / tuning step / tone** — are
  filled too when **File ▸ Preferences ▸ Apply band-plan defaults** is on
  (default off); see `chirp_backend.bandplan.suggest_band_defaults`. Duplex is
  never auto-set in either case.
