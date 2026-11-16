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

## Submissions to the project (verbatim)

Recorded here because VRP maintains an out-of-tree CHIRP driver
(`chirp_backend/extra_drivers/kguv96m.py`) that is intended to be submittable
upstream as-is.

### The project's own rules

`chirp/.github/pull_request_template.md`, verbatim:

> # CHIRP PR Guidelines
>
> The following must be true before PRs can be merged:
>
> 1. All tests must be passing. The "PR Checks" job is speculative and failure doesn't always indicate a critial problem, but generally it needs to pass as well.
> 1. Commits should be rebased (or simply rebase-able in the web UI) on current master. Do not put merge commits in a PR.
> 1. Commits in a single PR should be related. Squash intermediate commits into logical units (i.e. "fix tests" commits need not survive on their own). Keep cleanup commits separate from functional changes.
> 1. Major new features or bug fixes should reference a [CHIRP issue](https://chirpmyradio.com/projects/chirp/issues) _in the commit message_. Do this with the pattern `Fixes #1234` or `Related to #1234` so that the ticket system links the commit to the issue.
> 1. Please write a reasonable commit message, especially if making some change that isn't totally obvious (such as adding a new model, adding a feature, etc). The first line of every commit is emailed to the users' list after each build. It should be short, but meaningful for regular users (examples: "thd74: Fixed tone decoding" or "uv5r: Added settings support"). There should be a blank line after the first, followed by additional text so that it gets formatted properly for the mailing list.
> 1. New drivers should be accompanied by a test image in `tests/images` (except for thin aliases where the driver is sufficiently tested already). All new drivers must use `MemoryMapBytes`.
> 1. All files must be GPLv3 licensed or contain no license verbiage. No additional restrictions can be placed on the usage (i.e. such as noncommercial).
> 1. Do not add new py2-compatibility code (No new uses of `six`, `future`, etc).

Note the direct implications for a KG-UV96M submission: **a test image in
`tests/images` is required**, the driver **must use `MemoryMapBytes`**, the first
commit line is **emailed to the users' list**, and a feature should reference a
chirpmyradio.com issue number in the commit message.

### The author, Deniz Sincar, on his own submission

From the pull request description, verbatim:

> I'm blind and use NVDA on Windows daily; this is based on real usage and
> confirmed against NVDA's developer-info dumps to identify exactly which widgets
> were reporting raw/unhelpful accessibility info. I've tested all three changes
> manually with NVDA.

> ## Why no test image / new driver
>
> No new radio drivers are added; this is purely GUI accessibility plumbing, so
> the "new drivers need a test image" requirement doesn't apply.

> ## Not covered (left as follow-up)
>
> The Browser tab's raw memory editor (`developer.py`) uses a hand-rolled
> `wx.lib.scrolledpanel.ScrolledPanel` layout rather than `PropertyGrid`/`Grid`,
> so it needs separate treatment — it's a developer-facing tool rather than a
> regular Settings page, so I left it out of scope here.

> ## Testing
>
> - Manually tested with NVDA on Windows across all three grids (memory grid,
>   settings grid incl. live edit announcements, radio info grids).
> - `tools/cpep8.py` and `mypy --config-file .mypy.ini` pass clean on all changed
>   files.
> - Branch is rebased on current `master`, no merge commits.
>
> There's no existing CHIRP issue tracker ticket for this yet — happy to file one
> if maintainers prefer that before merge.

On keeping accessibility in-tree rather than in a separate module, which the
maintainer initially asked about:

> However, I think making accessibility a separate module may actually increase
> the maintenance burden rather than reduce it.
>
> An accessibility fork or separate implementation effectively creates two
> applications to maintain. Any future UI change would need to be implemented
> twice, and the two versions would inevitably drift apart over time.
>
> The goal of these changes is not to introduce an alternative UI, but to make
> the existing one expose information in a way that screen readers can consume.
> For sighted users, nothing changes.
>
> Keeping accessibility integrated also avoids user confusion ("which CHIRP
> should I install?") and reduces the chance that accessibility breaks because a
> new feature was added to the main UI but not to the accessibility module.
>
> Ironically, making accessibility a separate module may increase the risk of it
> falling into disrepair, because it becomes something that can be forgotten,
> skipped, or left unsynchronized with the main UI.
>
> From a maintenance perspective, I believe a small amount of accessibility code
> living alongside the existing UI is actually less work than maintaining a
> separate accessibility implementation.
>
> I'm also happy to keep the changes isolated, well documented, and as
> non-invasive as possible so they're easy to understand and maintain in the
> future.

(This was a misunderstanding — kk7ds meant a separate *file in the same repo*,
not a fork, and clarified so. The exchange is still worth reading before opening
anything upstream, because it shows what the maintainer's concerns actually are.)

### The maintainer, kk7ds, on accepting accessibility work

Worth reading before submitting anything in this area. Verbatim:

> Thanks for doing this. I'll be honest, this is a topic that I have avoided for
> a long time, mostly because the people that want (no, DEMAND) it are extremely
> intolerant of answers like "I don't have the time or desire to work on this".
> It has been a touchy subject for years to the point that I'm almost loathe to
> accept this because I'll have to maintain it going forward. That said, it's
> pretty understandable as it is, so if it really works and the libraries
> required remain available, it seems like a win.
>
> My ask for putting it into a separate module are partially because I think it
> makes sense and partially because I want to make sure it's easily
> rip-out-able if it falls into disrepair.

And on the cross-platform requirement, which is the constraint that killed the
prism approach:

> Either way, CHIRP is a cross-platform app, so anything that is merged here
> needs to work for all three platforms, which I'm sure is possible.

On 2026-07-31, after merging:

> @denizsincar29 can you create a user account on the main site
> https://chirpmyradio.com/projects/chirp/wiki/Home so I can cc you on any bugs
> that are reported for this stuff? Thanks!

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
      currently VRP's only macOS evidence, it is second-hand, and it is now being
      cited upstream.
- [ ] Decide whether a Windows `wx.Accessible` layer over `DataViewListCtrl` is
      worth adding to the roadmap.
- [ ] Consider whether VRP has anything to contribute upstream, and note that
      there is now one active blind contributor there working the same problem.

## Sources

- [kk7ds/chirp#1597](https://github.com/kk7ds/chirp/pull/1597) — the pull request,
  its description, and its full review thread
- `chirp/wxui/accessibility.py`, `common.py`, `memedit.py`, `radioinfo.py` at pin
  `5b1bba6`, vendored locally
- `chirp/.github/pull_request_template.md` at the same pin
- `wx_accessible_grid/grid.py` (0.8.0) and `vrp/native/channel_grid.py`
- prism backend registry and feature flags, probed on this machine 2026-08-08
