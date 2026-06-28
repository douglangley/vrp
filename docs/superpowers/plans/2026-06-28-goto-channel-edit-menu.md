# Plan — Go to Channel on the Edit menu (Ctrl+G)

> **Status:** ✅ COMPLETE 2026-06-28 (NVDA-verified, commit `0a945b0`).
> **Revised from the original title:** Go to channel **stays on the Channels
> menu** (the user changed their mind — *not* the Edit menu), rekeyed from
> `Ctrl+Shift+G` to **`Ctrl+G`**; Find next moved to **`F3`** to free `Ctrl+G`.
> The `Ctrl+Shift+G` alias was dropped. (The user mentioned more Channels-menu
> additions — those are a separate, not-yet-specified follow-up.)

---

## What already exists (reuse, don't rebuild)

`MainWindow.on_goto` (`vrp/native/main_window.py`) is already a complete,
accessible Go-to-channel command: it prompts with a native `wx.GetNumberFromUser`
dialog (clamped to `memory_bounds`), then **selects + focuses** the channel and
announces "Channel N". Today it lives in the **Channels** menu as
`&Go to channel…\tCtrl+Shift+G`, and in the row context menu.

So "implement go to channel" = **surface the existing handler on the Edit menu
under `Ctrl+G`** and sort out the key clash.

## The conflict: `Ctrl+G` is taken

`Ctrl+G` is currently **Find next** (`_build_channels_menu` → `find_next`, and
`APP_SHORTCUTS`). We can't have it mean two things. Resolution:

- **Move Find next to `F3`** — the standard Windows "find next" key. This frees
  `Ctrl+G` for Go to Channel and is more idiomatic than `Ctrl+G` anyway. (Find
  stays `Ctrl+F`.)

## Decisions

- **D1 — Go to Channel's home is the Edit menu** (per the request), keyed
  `Ctrl+G`. It's a single command surface, so it **moves** there (the `_add` key
  `"goto"` can only register one menu item). *Note:* the Edit menu is otherwise
  undo/clipboard/selection; goto is navigation, but we're honoring the explicit
  request to put it there.
- **D2 — Find next → `F3`** (frees `Ctrl+G`). Find stays `Ctrl+F`.
- **D3 — Drop the old `Ctrl+Shift+G`** Go-to accelerator (one key per command).
  *Open question:* keep `Ctrl+Shift+G` working as a legacy alias via a frame
  `wx.AcceleratorTable` entry (like the `Ctrl+Shift+Z` redo alias)? Default:
  **no** — `Ctrl+G` is the key. Easy to add if you want both.

## Changes (all in `vrp/native/main_window.py` unless noted)

1. **Edit menu** (`_build_edit_menu`): add a navigation group after Paste —
   a separator then `self._add(m, "goto", "&Go to Channel…\tCtrl+G", self.on_goto,
   needs_radio=True)`.
2. **Channels menu** (`_build_channels_menu`): **remove** the existing
   `self._add(m, "goto", …\tCtrl+Shift+G, …)` line (the command now lives on Edit).
   Change `find_next` accelerator `Ctrl+G` → `F3`.
3. **Context menu** (`on_grid_context_menu`): update the Go-to item's accelerator
   label `Ctrl+Shift+G` → `Ctrl+G` (still calls `on_goto`).
4. **`APP_SHORTCUTS`** (F1 list): replace `("Ctrl+Shift+G", "Go to channel")` with
   `("Ctrl+G", "Go to channel")`, and `("Ctrl+G", "Find next match")` with
   `("F3", "Find next match")`.
5. **Docs:** `docs/keyboard-map.md` — move Go to channel to the Edit-menu table at
   `Ctrl+G`, change Find next to `F3` (menu table + the Reorganizing keys table +
   any prose). `docs/chirp-feature-coverage.md` already lists Goto ☑.

## Edge cases / accessibility

- The existing flow is already correct: focus moves to the chosen row so NVDA
  reads it, plus the "Channel N" announce; `GetNumberFromUser` is a native,
  focus-trapped, Esc-cancellable dialog (Accessibility Rules #3/#4/#6). No new
  dialog needed.
- Gate on a loaded radio (`needs_radio=True`) — kept enabled so the accelerator
  fires; out-of-range input is already clamped by the dialog, and `-1` (cancel) is
  handled.
- No empty-history/clipboard concerns — goto is read-only navigation (not
  undoable, correctly).

## Tests

- Menu structure smoke (like `test_edit_menu_has_clipboard_items`): the Edit menu
  contains "Go to Channel"; `_menu_items["goto"]` is enabled when loaded; Find
  next's accelerator is now `F3` (assert the Channels item label contains "F3").
- Headless handler smoke is hard (the prompt is modal) — monkeypatch
  `wx.GetNumberFromUser` to return a channel and assert `on_goto` selects/focuses
  it (mirrors the clipboard tests' dialog monkeypatching).

## Steps (sequenced)

1. Rewire menus + accelerators (changes 1–4) and update tests.
2. Docs (change 5).
3. NVDA hand pass: `Ctrl+G` opens the prompt and lands focus on the channel;
   `F3` does Find next; menu items read correctly. macOS/VoiceOver follow-up as
   usual (menu item works regardless).

## Open question

- **D3** — keep `Ctrl+Shift+G` as a legacy Go-to alias, or drop it? (Default: drop.)
