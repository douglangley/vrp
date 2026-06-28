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
| Open Stock Config      | 1         | ☐      |
| Open Recent            | config    | ☑      |
| Save / Save As         | 1         | ☑      |
| Import (from image)    | 8         | ☑      |
| Export (to CSV)        | 8         | ☑      |
| Load Module            | 8         | ☐      |
| Print / Print Preview  | 8         | ✗ (intentional — covered by Export to CSV; native print is inaccessible) |
| Close Image / Exit     | 1 / 0     | ☑      |

## Edit menu

| Feature                         | VRP phase | Status |
|---------------------------------|-----------|--------|
| Copy to / Move to (bulk)        | 3         | ☑      |
| Delete / Delete + shift         | 3         | ☑      |
| Insert / Move / Sort / Arrange  | 3         | ☑      |
| Cut / Paste (clipboard)         | 3         | ☑      |
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
| Query framework + import         | 7         | ☑ (HW/network test owed) |
| Query: AMSAT                     | 7         | ☑      |
| Query: SatNOGS                   | 7         | ☑      |
| Query: DMR-MARC                  | 7         | ☑      |
| Query: mapy73.pl                 | 7         | ☑      |
| Query: RepeaterBook              | 7         | ◐ (needs dynamic country→state cascade) |
| Query: RadioReference            | 7         | ◐ (needs credentials/login form) |
| Query: przemienniki.net / .eu    | 7         | ◐ (needs band/mode code mapping + coords) |
| Auto edits toggle                | 8         | ☐      |
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

- Developer-only items (reload driver/module, interact with driver, serial
  trace, bug report) are lower priority; revisit in Phase 10.
