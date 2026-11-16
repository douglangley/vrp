# Upstream CHIRP now has screen-reader accessibility — what it did, and what it means for VRP

**Date:** 2026-08-08
**Trigger:** the CHIRP pin bump `c2e70ff` → `5b1bba6` (2026-08-02) brought in a new
file, `chirp/wxui/accessibility.py` (+429 lines), plus accessibility changes to
`common.py`, `memedit.py`, and `radioinfo.py`.
**Evidence:** the merged source, now vendored locally at the new pin, and
[kk7ds/chirp#1597](https://github.com/kk7ds/chirp/pull/1597) read in full via
`gh` (the chirpmyradio.com tracker returns HTTP 403 to automated fetches; the
GitHub mirror does not).

## Summary

Upstream CHIRP merged its first screen-reader accessibility work on
**2026-07-29**. It is the work of one blind NVDA user, it is **Windows-only by
construction**, and — most relevant to us — **its first version used prism, the
same library VRP depends on, and that approach was rejected and rewritten.**

Three things follow for VRP, and they are not all comfortable:

1. VRP's choice of `DataViewListCtrl` over `wx.grid.Grid` is **vindicated**.
   Upstream cannot reach macOS with its approach; VRP's architecture can, and
   grid navigation and channel editing have now been run there under VoiceOver by
   two people.
2. VRP has a **concrete, verified gap for braille users** in the channel grid.
3. VRP does **not** suffer the double-speech that got prism rejected upstream,
   and the reason is structural rather than lucky — but `announce.py` records the
   wrong reason for it, which makes the protection easy to delete by accident.

## What upstream shipped

[Pull request #1597](https://github.com/kk7ds/chirp/pull/1597), "a11y: fix screen
reader access to memory grid, settings grid, and radio info pages", by **Deniz
Sincar** (`denizsincar29`). Opened 2026-06-22, merged 2026-07-29. 23 files,
+4,439 / −2,539, 6 commits, 12 comments, 3 reviews. It is his only pull request
to CHIRP, and the only accessibility pull request in the project.

Six commits:

- Support Shift+F10 convention for context menu in memedit
- a11y: Add base accessibility module for MSW
- a11y: Enable accessibility hints for settings and radioinfo
- a11y: Enable accessibility hints for memedit
- Make CONF.get_bool() case insensitive
- Update locale for accessibility changes

The scope is the three places CHIRP uses controls that paint their own rows, and
therefore expose one opaque pane to MSAA with no children:

| Area | Control | What it gained |
|---|---|---|
| Memory grid | `wx.grid.Grid` | Per-cell accessible name; Apps key / Shift+F10 context menu |
| Settings pages | `wx.propgrid.PropertyGrid` | Per-row name, value, type, locked/unspecified state; pending-value speech while editing |
| Radio Info | `wx.propgrid.PropertyGrid` | Same row-level treatment, read-only |

### The arc that matters: prism was tried, then removed

The first version announced rows by pushing speech through
[prismatoid](https://github.com/ethindp/prism) — the library VRP uses. The
maintainer (kk7ds) tested it on macOS and found two defects:

> Okay, installed `prismatoid` locally on my mac dev environment. The voiceover
> "works" but I'm pretty sure not properly. There's a loud voice that already
> announces a lot of the regular UI elements (the tab, the memory/settings tab
> group, etc) and a second quieter voice that announces your new stuff. The
> primary voice is loud, the second voice is soft, and they talk all over the top
> of each other.

> Another comment here - with this patch applied the narration voice happens
> _all the time_ on macos, not just when enabled at the system level. That would
> obviously be a problem as it forces all the sighted users to hear constant
> narration during navigation (mouse or keyboard). Moving to a proper
> `wx.Accessible` mechanism should solve that as well.

The rewrite implements `wx.Accessible` and calls `NotifyEvent()` so the screen
reader re-queries the OS layer itself. No speech is pushed by CHIRP at all. The
merged module's own docstring records this history explicitly.

### And it only works on Windows

`wx.Accessible` is implemented for MSW only. The author confirmed this against
the wxWidgets docs and a wxGTK maintainer, and wrote:

> So right now this PR is Windows-only by construction ... arrow-key navigation
> through these grids stays silent for Orca/VoiceOver users, same as before this
> PR (and before prismatoid).

## The two grids, side by side

This is the substance. Both projects solved "a screen reader must read a cell",
and they solved it in opposite directions.

### CHIRP: `GridAccessible` over `wx.grid.Grid`

Mechanism, from `chirp/wxui/accessibility.py`:

- Exposes **one virtual child per cell**, `childId` 1-based and row-major
  (`divmod(child_id - 1, cols)`), as IAccessible requires.
- `GetName()` returns `"<column header> <value>, row <N>"`, with `_('empty')`
  substituted for a blank cell.
- `GetRole()` reports `ROLE_SYSTEM_TABLE` for the control and
  `ROLE_SYSTEM_CELL` per child; `GetState()` adds `FOCUSED`/`SELECTED` when the
  child is the grid cursor.
- `attach_grid_accessible()` binds `EVT_GRID_SELECT_CELL` and calls
  `NotifyEvent(ACC_EVENT_OBJECT_FOCUS | ..._SELECTION)` so Windows re-queries.
- Availability is probed by **actually constructing** `wx.Accessible()` and
  catching `NotImplementedError` — see "Traps worth stealing" below.
- A `disable_accessibility` / `state` config key kills the whole thing at
  runtime.

The screen reader remains the only thing that speaks. CHIRP supplies data, not
audio.

### VRP: `AccessibleGrid` over `wx.dataview.DataViewListCtrl`

Mechanism, from `wx_accessible_grid/grid.py` and `vrp/native/channel_grid.py`:

- The control is a real `NSTableView` on macOS and wx's generic control on
  Windows, so rows are exposed to the platform accessibility API without help.
- With `cell_cursor=True`, the grid **owns all four arrow keys**:
  - Left/Right move an app-owned `_current_col` and speak `"<value>, <column>"`.
  - Up/Down move an app-owned `_cur_row`, call `EnsureVisible()` to scroll, and
    speak `"<row label>, <value>"` — column-locked, so moving down a column reads
    one cell, not the whole row.
- **Crucially, arrowing does not move the native selection or current item.**
  The library docstring is explicit about why: "arrowing does not change the
  native selection, so the screen reader does not fire its automatic full-row
  read". The host calls `sync_selection_to_cursor()` at *action* time instead.
- All of that speech goes out through prism (`vrp/speech.py`), with
  `always_speak=True` so the `speak_messages` preference cannot silence it.

### The comparison

| | CHIRP (merged 2026-07-29) | VRP |
|---|---|---|
| Underlying control | `wx.grid.Grid` (custom-drawn) | `wx.dataview.DataViewListCtrl` (native) |
| Who speaks | The screen reader, via OS queries | VRP, via prism |
| Per-cell granularity | `wx.Accessible` virtual children | App-owned cursor + pushed speech |
| Native selection while arrowing | Moves; `NotifyEvent` follows it | **Deliberately does not move** |
| Windows / NVDA | Works | Works (user-confirmed) |
| macOS / VoiceOver | **Nothing** — `wx.Accessible` is MSW-only | Navigation + channel editing run by two people, no double speech; **wider app pass still owed** |
| Linux / Orca | Nothing | Cell cursor not wired; native rows only |
| Fails if speech library absent | No — no speech library involved | **Yes — grid navigation goes silent** |
| Braille display follows navigation | Yes, focus-driven | **No — see below** |
| Honours screen-reader verbosity/rate/punctuation settings | Yes | Only partly (prism's NVDA backend inherits voice, not verbosity) |

## Finding 1: VRP's channel grid is silent on a braille display

This is the one to act on, and it is verified, not inferred.

VRP suppresses the native current-item move during arrowing by design. Across the whole
channel-grid path, `SetCurrentItem()` is called in exactly three places —
`channel_grid.py:177` (`set_state`, row 0 at load), `grid.py:182`
(`sync_selection_to_cursor`, action time), and `grid.py:269` (`focus_row`, go-to
/ find / post-edit). It is **not** called by `_move_row()` or by the Left/Right
handler.

So while the user arrows around, the OS accessibility layer's idea of the current
row is stale — it still points at whatever row was last synced. Anything that
follows OS focus rather than VRP's speech is out of step with what the user is
hearing. A braille display is exactly such a thing.

And VRP never sends braille itself. Probed on this machine:

```
backend: NVDA
  supports_braille: True
  supports_speak:   True
```

prism's NVDA backend **does** support braille — `Backend.braille()` exists and
the feature flag is true. But `grep -rn "braille" vrp/ chirp_backend/ tests/`
returns **nothing**. `vrp/speech.py` calls only `speak()` and `stop()`.

Net effect: a braille user arrowing the channel grid sees a stale row on the
display while hearing the correct cell. Under CHIRP's `NotifyEvent` model this
cannot happen, because braille follows the same focus event the speech does.

**Not yet verified on hardware.** The API surface and the code path are certain;
what a physical display actually shows needs a display to confirm. That is a
hand check, like the other owed passes.

**Likely fix**, in rough order of effort: have `Speaker` call `backend.braille(text)`
alongside `speak()` when `features.supports_braille`, gated so it degrades
silently like everything else in that module.

## Finding 2: prism is a single point of failure that CHIRP no longer has

`CLAUDE.md` already states this plainly — "a prism-less build navigates cells
silently" — and `build.py` bundles prism specifically to prevent it. That is a
sound mitigation for the packaging failure mode.

It does not cover the runtime one. `Speaker._ensure_backend()` gates only on
`backends_count <= 0` and then takes `create_best()`. Enumerating the registry on
this machine shows 14 backends, and below the screen readers sit plain TTS
engines:

| Priority | Backend |
|---|---|
| 103 | NVDA |
| 100–101 | JAWS, ZDSR, Orca, PCTalker, SystemAccess, ZoomText, ... |
| 98 | OneCore |
| 97 | SAPI, Speech Dispatcher, UIA |

`create_best()` is built to fall through to OneCore or SAPI when no screen reader
is running. Those are present on every Windows machine. That is the shape of the
defect kk7ds rejected upstream — speech for users who did not ask for it.

I could not prove the runtime behaviour here, because NVDA is running on this
machine and confirming it would mean stopping the user's screen reader. **The
check is: run VRP with no screen reader active and arrow across cells.** If it
speaks, VRP has upstream's macOS bug on every platform.

## Finding 3: the "never doubles up" premise holds in the grid, on both platforms

**Revised after the fact — the original version of this finding was wrong, and
the correction is worth keeping visible.**

`vrp/native/announce.py` justifies `always_speak=True` for the cell cursor:

> It never doubles up with the screen reader precisely because nothing else
> announces it.

On first reading, that argument looked Windows-specific. It is plainly true where
wx's generic `DataViewCtrl` announces no per-cell cursor; on macOS, `NSTableView`
is a real native table that VoiceOver reads directly, so the premise appeared
untested there — and CHIRP's maintainer had heard exactly that failure with
prism.

**In practice it does not occur.** Grid navigation and channel editing have been
run on macOS under VoiceOver by two people (see Finding 4), and the double speech
has never appeared — nor on Windows under NVDA in daily use.

The reason is structural, and it is the substantive difference from CHIRP's first
attempt. VRP's cell cursor **does not move the native selection or current item
while arrowing** — `_move_row()` scrolls with `EnsureVisible()` and speaks, and
`SetCurrentItem()` is only called at action time. The screen reader therefore
never fires its own automatic row read, so there is nothing for prism's speech to
collide with. CHIRP's rejected version pushed speech *on top of* an unmodified
`wx.grid.Grid` whose selection was still moving underneath — two sources, one
event. Column-locked Up/Down speech helps further by keeping each utterance to a
row label plus one cell.

So the premise in `announce.py` is sound, but its stated *reason* is incomplete:
it is not that "nothing else announces it" by luck of platform, it is that the
grid deliberately suppresses the thing that otherwise would. That distinction is
worth preserving in the docstring, because the suppression is load-bearing and
someone could remove it as an apparent redundancy — which is exactly how Finding
1's braille gap arises.

**Still open:** the announcer also speaks outside the grid — dialogs, menus, the
settings editor, banks, the serial flows — and those have not had a macOS pass.
The remaining double-voicing risk sits there, not in the grid.

## Finding 4: the architecture choice was right, and upstream proves it

CHIRP is bolting IAccessible onto a custom-drawn grid and can only do it on
Windows. VRP picked a control that is natively accessible on both platforms and
so is not blocked there. The thing upstream currently *cannot* do — read a
channel grid under VoiceOver — is the thing VRP is built to do.

This is more than a design argument. **Grid navigation and channel editing have
been run on macOS under VoiceOver by two people** — the VRP author, and payown,
who maintains the fork VRP pins (`payown/wx-accessible-grid@494103f`) and did the
more thorough pass. That is real-hardware use on two setups, covering the core
workflow rather than just row reading.

Editing being in scope matters more than it first appears. `CLAUDE.md` records
that the cell cursor is wired on macOS specifically so F2 can edit the *focused
cell* instead of falling back to a field picker — that behaviour depends on plain
Left/Right reaching the `NSTableView` and the cursor tracking the current column.
That chain is the fragile-looking part of the design, and it is the part that was
exercised.

It does not close the owed macOS pass, which covers the rest of the application —
dialogs, menus, the settings editor, banks, the serial flows. But the piece
upstream cannot currently reach *at all* is now verified rather than merely
designed. That raises the value of finishing the wider pass rather than lowering
it: it is the differentiator, not just an unfinished checkbox.

## What VRP could take from this

**A `wx.Accessible` layer on Windows would fix Findings 1 and 2 together.**
CHIRP's approach gets per-cell granularity *through* the OS layer. VRP gets it
out-of-band. If VRP implemented `wx.Accessible` over the `DataViewListCtrl` on
Windows — virtual children per cell, `NotifyEvent` on cursor move — then braille,
verbosity settings, review cursor, and speech rate all follow for free, and prism
stops being load-bearing for navigation. prism would go back to being what
`vrp/speech.py`'s docstring says it is: supplemental.

That is a real piece of work, not a tweak, and it is Windows-only (macOS keeps
the current path). It belongs on the roadmap for discussion, not in a patch.

**Cheaper, immediately:** call `backend.braille()` alongside `speak()`.

**Already ahead:** VRP has had Shift+F10 on the grid since the native-grid work.
Upstream only just added it, and kk7ds's reaction is worth noting — "Still
surprised they didn't wire that into the grid, but cool, a benefit for even the
sighted users."

## Traps worth stealing

Real bugs upstream hit, all of which VRP would hit too:

- **`hasattr(wx, 'Accessible')` is true on every platform and means nothing.**
  Constructing it raises `NotImplementedError` on GTK/Cocoa. Shipping that check
  **crashed CHIRP's startup on macOS**. Probe by construction.
- **The kill switch silently did not work**, because
  `ChirpConfigProxy.get_bool()` compared `val == "True"`. Fixed to
  `val.lower() == 'true'` in the same merge — it is in this pin bump.
- **`GetFocus()` is unresolved in merged code.** kk7ds, four days before merging:
  "The `GetFocus()` routine still seems to be wrong, as it seems like that always
  needs to return a `Window` as the second item of the tuple." If VRP implements
  `wx.Accessible`, expect to solve this properly.
- mypy rejects a conditional base class (`wx.Accessible if HAS else object`).
- CHIRP's test shim `sys.modules['wx'] = MagicMock()` breaks on a module-level
  `import wx.grid`; reference `wx.grid.*` as attributes at call time instead.
- GitHub Copilot refused to review the PR — over 20,000 changed lines, mostly
  regenerated locale files.

## Open items

- [ ] **Verify the braille gap** on a physical display (Finding 1).
- [ ] **Verify no-screen-reader behaviour** — run VRP with no screen reader
      active and arrow the grid; confirm it does not speak through SAPI/OneCore
      (Finding 2).
- [ ] **Listen for double-voicing** in the parts of the app payown's testing did
      not cover (Finding 3) — dialogs, menus, the settings editor, banks, and the
      serial flows, where the announcer also speaks. Navigation and editing came
      through clean, so the remaining risk sits outside the grid.
- [ ] Capture payown's macOS testing durably: revision tested, VoiceOver and
      macOS versions, and the specific checks run. Scope is known (grid
      navigation + channel editing); the surrounding detail is not. It is
      currently VRP's only macOS evidence, and it is second-hand.
- [ ] Decide whether a Windows `wx.Accessible` layer over `DataViewListCtrl` is
      worth adding to the roadmap.

## Sources

- [kk7ds/chirp#1597](https://github.com/kk7ds/chirp/pull/1597) — the pull request,
  its description, and its full review thread
- `chirp/wxui/accessibility.py`, `common.py`, `memedit.py`, `radioinfo.py` at pin
  `5b1bba6`, vendored locally
- `wx_accessible_grid/grid.py` (0.8.0) and `vrp/native/channel_grid.py`
- prism backend registry and feature flags, probed on this machine 2026-08-08
