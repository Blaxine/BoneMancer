# REQ-003 — Actionable Bones

| Field | Value |
| ----- | ----- |
| ID | REQ-003 |
| Title | Actionable Bones |
| SOLVE | — |
| Status | In Progress |
| Phase | 1.2 (Face template: 1.2.1) |
| Tier | 1 |
| Area | Actionable Bones panel, layout storage, selection, Rigify templates, tests |
| Author | Blaxine |
| Created | 2026-10-22 |
| Last Updated | 2026-10-26 |

> Source PRD: REQ-003-PRD-Actionable-Bones.md
>
> Supersedes the roadmap table in REQ-002's Full Description (see *Full
> Description → Roadmap*). REQ-002 itself is not edited.

## Short Description

Ships Bone Mancer 1.2: an **Actionable Bones** panel, directly under Rig, that
shows the picked rig's animation controls as a grid of buttons laid out like the
character, split into **Layout tabs** (Body, Hands, tabs of your own; Face in
1.2.1). Animators click a cell to select its bone and Shift+click to add or
remove it. Riggers turn on **Edit Layout** to place, move, recolour or clear
cells, or apply a **Layout template** that paints a body silhouette and places a
generated Rigify rig's controls automatically. The layout is stored on the rig,
travels with it through append and link, and is read-only on linked and
overridden rigs. Release 1.2.0 also ships the unreleased sidebar work already on
the branch (redesign, Deform / IK, property and constraint editing).

## User Stories

1. As an animator, I want to select a rig's controls by clicking buttons laid out like the character (body, hands and face), with Shift to add or remove, so that I can reach any control in one click without hunting in the viewport or a long bone list
2. As a rigger, I want to choose which bones are actionable and place, move, recolour or clear them on the layout, including on tabs of my own, so that the panel fits my rig, tails and props included
3. As a rigger working with a Rigify rig, I want to apply a body, hands and face template that places the controls for me, so that setting up the panel takes one click instead of placing every control by hand
4. As an animator working in a shot with a linked rig, I want the layout built in the rig file to come with the rig unchanged, so that every shot uses the same panel and nobody rearranges it by accident

## Constraints

- **Panels can't position or colour widgets.** Layouts only stack rows and
  columns; a button can be pressed (`depress`), greyed (`active`/`enabled`) or
  red (`alert`), never tinted. Colour comes from icons only.
- **A 16-column `grid_flow` fits the default sidebar.** Prototyped on 5.2.2 at the
  default 280 px region: `grid_flow(row_major=True, columns=16, even_columns=True,
  even_rows=True, align=True)` gives ~15 px square cells; disabled empty
  operator buttons paint a grey silhouette; `COLLECTION_COLOR_05` / `_01` / `_03`
  icons read as blue / red / yellow; `depress=True` shows the selected cell blue.
- **Every grid cell must be a button.** Labels or sub-layouts among the cells
  squeeze the real buttons thin and hide their pressed state. Empty cells are a
  never-enabled operator (`poll` False) drawn with `emboss=False`; with
  `emboss=True` the same operator draws the grey silhouette box.
- **A `description()` classmethod on an operator stops its buttons drawing
  pressed** (`depress=True` is ignored; measured on 4.5.4 and 5.2.2). Cell
  buttons use a static description; the panel names the active bone under the
  grid instead of a per-bone tooltip.
- **Generated Rigify human (4.5.4 and 5.2.2): 216 control bones, identical names on
  both.** `rigify` is bundled; `addon_utils.enable("rigify")` works under
  `--factory-startup` with `BLENDER_USER_RESOURCES` isolated; metarig + generate
  takes ~3 s.
- **Rigify's FK spine is filed under "Torso (Tweak)".** `spine_fk`,
  `spine_fk.001`–`.003` sit in that collection beside the `tweak_spine*` bones;
  collection membership alone can't separate FK from tweak controls.
- **The face the 4.2+ Human meta-rig generates uses `lip.T`, `lips.L`,
  `brow.T.L.001`, `jaw_master`, `master_eye.L`, `nose_master`.** The interview
  called such names "legacy super_face"; they are what the current generator
  emits. Only the generated rig's names are targeted; no legacy detection.
- **Bone visibility has two layers.** `is_hidden(pb)` reads only the bone's own
  Hide flag. Rigify hides FK / tweak controls through bone collections;
  `BoneCollection.is_visible_effectively` (present on 4.5 and 5.2) covers the
  collection and its ancestors. A bone in no collection is visible.
- **`select_bone_in_viewport` unhides the bone and refuses linked rigs.** It
  clears every other selection and calls `set_hidden(pb, False)`; layout picks
  must never reach it for a hidden bone. Its linked-rig refusal ("Rig is linked
  from a library; make a library override first") is reused unchanged.
- **`rig_is_editable` is True for overrides.** Disabling Edit Layout on an
  overridden rig needs `override_library` / `library` checks of its own.
- **Code layout is the package from commit `ddc5f1b`** (`core/`, `operators/`,
  `ui/`), on branch `restructure-addon-layout`, not yet merged to `main`.

## Architectural decisions

- **Storage**: `Object.bonemancer_layout` on the rig — a collection of Layout tabs,
  each with a name, column count, row count, an optional template id, and a
  collection of cells. A cell is bone name + row + column + side (`LEFT`, `RIGHT`,
  `CENTER`). Strings only, never ID pointers. Not `LIBRARY_OVERRIDABLE`: an
  override shows the library file's layout.
- **Session state on the Scene**, in `bonemancer_settings`: the Edit Layout flag,
  the active Layout tab (by name) and the cell being moved. Edit Layout and the
  move state are cleared on file load and when the picked rig changes.
- **Silhouettes are not stored.** A tab created from a template keeps the
  template id; its silhouette is drawn from the add-on's template definition.
  User tabs have no silhouette.
- **One bone per cell; a bone at most once per tab.** The same bone may sit on
  several tabs. Placing a bone already on the tab moves it.
- **Picking**: click = select only that bone and make it active (existing
  select path); Shift+click = toggle that bone, keep the rest, make it active
  when added. Ctrl and Alt behave like a plain click. Picking operators use
  `UNDO`.
- **Hidden for the layout**: the bone's Hide flag is on, or it has collections
  and none is effectively visible. Hidden cells are greyed and their click does
  nothing.
- **Edit Layout** is available only on a local (not linked, not overridden)
  editable rig.
- **Templates**: Body (16 columns) and Hands (20 columns) in 1.2.0, Face (20
  columns) in 1.2.1. Applying creates a missing tab, then places each template
  bone that exists on the rig and isn't on that tab yet, into its cell if the
  cell is empty. Never moves, clears or recolours existing cells.
- **Template control sets** (generated Rigify human): Body = `root`, Torso
  collection, `spine_fk*`, Arm/Leg IK and FK collections, no tweak bones;
  Hands = Fingers and Fingers (Detail); Face = Face and Face (Primary).
- **Side tag** defaults from the bone name on placement (`bpy.utils.flip_name`
  differs → left or right by its marker; otherwise centre); editable per cell.
  Icons: `LEFT` `COLLECTION_COLOR_05`, `RIGHT` `COLLECTION_COLOR_01`, `CENTER`
  `COLLECTION_COLOR_03`.
- **Glossary**: Actionable Bones (panel), Layout, Layout tab, Cell, Edit Layout,
  Layout template. "Bone Picker" keeps its meaning (the Bones panel list).
- **Release**: manifest `1.2.0` after slice 6; `1.2.1` after slice 7.

## Full Description

### Roadmap (replaces REQ-002's)

| Release | Feature |
| ------- | ------- |
| 1.2 | Actionable Bones (this plan) + the unreleased sidebar work |
| 1.2.1 | Face Layout template (this plan, slice 7) |
| 1.3 | Per-bone driver view with jump-to |
| 1.4 | Mirror / symmetry helpers |
| 1.5 | Export Bone Sets to native bone collections |
| 1.6 | Batch actions on a Bone Set |
| 1.7 | Beginner tooltips |

### A layout at a glance

A rig's Layout is a set of Layout tabs. Each tab is a grid of cells; a cell
either holds one bone or is empty. Template tabs draw a grey body silhouette
under their cells. The panel shows one tab at a time; a tab bar switches tabs.

## UI / UX Notes

- **Panel order**: Rig, **Actionable Bones**, Bones, Bone Sets, Rig Check, Shape
  Keys. Actionable Bones starts open; Bones now starts closed.
- **No rig**: the existing no-rig hint.
- **Empty layout**: hint "Lay out this rig's controls to pick them in one click."
  with **Apply Rigify Template** and **New Tab** buttons; on a linked or
  overridden rig, "This rig has no layout. Add one in the rig's own file."
- **Header row**: tab bar (one button per tab, pressed = active), then **Edit
  Layout** toggle (pencil icon; disabled with tooltip on linked/overridden rigs:
  "The layout belongs to the rig's file; open it there to edit").
- **Grid**: cells only, no text. Placed cell = side icon, pressed while the bone
  is selected, greyed while hidden; static tooltip "Select this bone". Under the
  grid, a greyed line names the active bone. Missing bone (renamed or deleted
  outside a tracked path) = `ERROR` icon. Silhouette cells = grey disabled
  boxes. Empty cells = blank.
- **Edit Layout on**: empty cells become clickable; clicking one places the
  viewport's active bone ("Select a bone in the viewport first" when there is
  none). Clicking a filled cell opens a small menu: Left / Right / Centre, Move,
  Clear. While moving, a line above the grid reads "Click an empty cell to move
  <bone>"; clicking the same cell cancels.
- **Tab menu** (Edit Layout on): New Tab (name, columns, rows), Rename Tab,
  Remove Tab (confirm), Apply Rigify Template.
- **Wording**: no "picker", "group" or "collection" in new labels (the smoke
  wording check flags them).

## Acceptance Criteria

- [ ] **AC1 — Panel.** An "Actionable Bones" panel sits between Rig and Bones,
  starts open, shows the no-rig hint without a rig and the empty-layout state on a
  rig with no tabs; Bones starts closed.
- [ ] **AC2 — Pick.** Clicking a placed cell makes its bone the only selected bone
  and the active bone (entering Pose Mode from Object Mode as the Bones panel does);
  Shift+click adds or removes it and keeps the rest; Ctrl/Alt act as a plain click;
  cells of selected bones show pressed, including after selecting in the viewport;
  each pick is one undo step.
- [ ] **AC3 — Hidden and missing.** A bone hidden by its own flag, or whose
  collections are all hidden (directly or through a parent collection), shows
  greyed and clicking it changes nothing. A cell whose bone no longer exists
  shows as missing.
- [ ] **AC4 — Edit Layout.** With Edit Layout on, clicking an empty cell places
  the viewport's active bone with a side tag from its name; a filled cell offers
  Left / Right / Centre, Move and Clear; placing a bone already on the tab moves
  it; the same bone can be placed on another tab.
- [ ] **AC5 — Renames.** Cells follow a bone renamed with Rename or outside Bone
  Mancer while the rig is picked, on every tab.
- [ ] **AC6 — Libraries.** On an overridden rig the layout from the library file
  shows, picking works, and Edit Layout is disabled with its tooltip; after
  reload the layout is still the library's. On a linked rig without override,
  picking reports the existing linked-rig message.
- [ ] **AC7 — Body and Hands templates.** On a generated Rigify human, Apply
  Rigify Template creates Body and Hands tabs with silhouettes and places every
  control of the agreed sets, no tweak bones; applying again changes nothing; a
  hand-moved or cleared cell survives re-apply except that a cleared bone is
  placed again only if its template cell is empty; on a non-Rigify rig the tabs
  appear with silhouettes and nothing placed, and the report says 0 placed.
- [ ] **AC8 — User tabs.** New Tab creates a tab of the given name and size;
  tabs can be renamed and removed (with confirmation) and switched from the tab
  bar.
- [ ] **AC9 — 1.2.0 release.** All suites green on 4.5 and 5.2 including the new
  suite; manifest `1.2.0`; README, manual checklist, glossary and changelog
  updated; the built zip installs.
- [ ] **AC10 — Face template (1.2.1).** Applying on a generated Rigify human adds
  a Face tab with silhouette and the Face + Face (Primary) controls; manifest
  `1.2.1`.
- [ ] **AC11 — Persistence.** The layout survives save and reopen; Edit Layout
  and a pending move are off after reopening and after picking another rig.

## Technical Notes

### Existing code the plan builds on (package layout of `ddc5f1b`)

| Symbol | File | Use |
| ------ | ---- | --- |
| `BONEMANCER_PG_SetBone`, `BONEMANCER_PG_BoneSet`, `classes`, `OBJECT_PROPS`, `register` | `bonemancer/properties.py` | pattern for stored PropertyGroups; add the layout PGs and `Object.bonemancer_layout` |
| `BONEMANCER_PG_Settings` | `bonemancer/properties.py` | home for Edit Layout flag, active tab, move state |
| `select_bone_in_viewport(context, obj, bone_name)` | `bonemancer/core/selection.py` | plain click; refuses linked rigs; unhides (never call for hidden bones) |
| `bone_selected_in_viewport`, `selected_bone_names` | `bonemancer/core/selection.py` | pressed state; active bone for placement |
| `update_bone_list(scene)` | `bonemancer/core/selection.py` | outside-rename loop calls `rename_set_entries` and `rename_ignore_entries`; layout renaming goes beside them |
| `on_armature_change(self, context)` | `bonemancer/core/selection.py` | clear Edit Layout and move state on pick change |
| `sync_selected_bone`, `on_depsgraph_update` | `bonemancer/core/selection.py`, `bonemancer/handlers.py` | already tag panel redraws on selection change |
| `is_hidden`, `set_bone_selected`, `bone_is_selected` | `bonemancer/core/compat.py` | 4.x / 5.x selection and hide |
| `rig_is_editable`, `get_rig`, `tag_addon_panels` | `bonemancer/core/utils.py` | picked rig, linked check, redraw |
| `BONEMANCER_OT_select_bone`, `BONEMANCER_OT_rename_bone` (rename hook at `rename_set_entries` call) | `bonemancer/operators/bones.py` | pattern for an `UNDO` pick operator; rename following |
| `on_load_post` | `bonemancer/handlers.py` | clear Edit Layout on load |
| `BONEMANCER_PT_rig`, `BONEMANCER_PT_bones` | `bonemancer/ui/panels.py` | new panel class goes between them; `bl_options = {'DEFAULT_CLOSED'}` on Bones |
| `classes` (panel order) | `bonemancer/ui/__init__.py`, `bonemancer/operators/__init__.py` | register new panel/operators; panel order = tuple order |
| `hint`, `wrapped_label`, `sub_panel` | `bonemancer/ui/common.py` | empty states |

### Blender API facts used

- Grid: `UILayout.grid_flow(row_major=True, columns=N, even_columns=True,
  even_rows=True, align=True)`; `operator(..., text="", icon=..., depress=...)`;
  a sub-row with `enabled = False` for silhouette boxes.
- Modifier keys: an operator's `invoke(self, context, event)` gets `event.shift`
  / `event.ctrl` / `event.alt` from a panel button click.
- Tooltips: `@classmethod description(cls, context, properties)` returns the
  bone name.
- Collections: `Bone.collections`, `BoneCollection.is_visible_effectively`,
  `is_solo`, `Armature.collections_all`.
- Pairing: `bpy.utils.flip_name(name)` (REQ-002 verified the conventions it
  flips).
- Rigify in tests: `addon_utils.enable("rigify", default_set=True)`,
  `bpy.ops.object.armature_human_metarig_add()`, `bpy.ops.pose.rigify_generate()`;
  the generated rig is the new armature object other than the metarig.

### Tests

- Runner `tests/run.py` runs every `tests/test_*.py`; a new suite needs no runner
  change. Helpers: `check`, `finish`, `load_addon`, `refused`, `make_arm`,
  `clear_data`, `tmp_dir`, `FakePanel`, `MockLayout`, `RecordingLayout` / `record`
  in `tests/helpers.py`. `MockLayout` / `RecordingLayout` need `grid_flow`
  support if they lack it.
- `tests/test_smoke.py`: `EXPECTED_PROPS` (line ~1007) gains `bonemancer_layout`;
  `ui6` (line ~759) pins panel order and default-closed flags; `ui4` validates
  every icon string in the package; `wrong_set_terms()` wording check.
- `tests/test_library.py`: library rig + `override_hierarchy_create`; extend with
  a layout in the library file.
- `tests/test_package.py` pins `"1.1.0"` in the manifest check and zip name.

## Implementation Steps

| Phase | Meaning |
| ----- | ------- |
| P | Persistence (stored properties) |
| S | Service (operators, core logic) |
| U | UX (panel, menus, strings) |
| D | Docs |
| T | Tests |
| F | Foundation (manifest, release) |

### Slice 1 — Tracer: place a bone, click it, it's selected

**Demoable when:** on a plain rig, New Tab makes a Body tab, Edit Layout + a click
on an empty cell places the active bone, and with Edit Layout off clicking that
cell selects the bone; the layout survives save and reopen.
**Satisfies:** AC1, AC4 (place), AC11 (persist) · **Covers:** US1, US2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S001 | P | Layout storage | Tab and cell PropertyGroups per *Architectural decisions*; `Object.bonemancer_layout`; Edit Layout flag and active tab on `BONEMANCER_PG_Settings`; register / unregister; `OBJECT_PROPS`. | — | `bonemancer/properties.py` |
| ✅ | S002 | S | New Tab (minimal) | `UNDO` operator adding a named tab with columns / rows on an editable local rig; sets it active. | S001 | `bonemancer/operators/` |
| ✅ | S003 | S | Place on empty cell | Edit Layout click on an empty cell stores the viewport's active bone there; refuses without an active bone. | S001 | `bonemancer/operators/`, `bonemancer/core/` |
| ✅ | S004 | S | Pick (plain click) | `UNDO` operator: plain click selects through `select_bone_in_viewport`; reports its error messages. | S001 | `bonemancer/operators/` |
| ✅ | S005 | U | Actionable Bones panel | Panel between Rig and Bones; no-rig and empty-layout states; tab buttons; Edit Layout toggle; `grid_flow` grid of cells; Bones gets `DEFAULT_CLOSED`. | S002, S003, S004 | `bonemancer/ui/panels.py`, `bonemancer/ui/__init__.py` |
| ✅ | S006 | T | Actionable Bones suite (new) | New suite: new tab, place, pick selects the bone, save + reopen keeps the layout, panel draws with and without a rig/layout via `record`. | S005 | `tests/test_actionable_bones.py`, `tests/helpers.py` |
| ✅ | S007 | T | Extend smoke | `EXPECTED_PROPS` + `bonemancer_layout`; `ui6` order Rig, Actionable Bones, Bones (closed), Bone Sets, Rig Check, Shape Keys. | S005 | `tests/test_smoke.py` |

### Slice 2 — Picking that matches the viewport

**Demoable when:** Shift+click builds a multi-selection, pressed cells follow
viewport selection, FK cells grey out when the FK collection is hidden, and a
bone renamed with F2 keeps its cell.
**Satisfies:** AC2, AC3, AC5 · **Covers:** US1

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S008 | S | Shift toggle | Shift+click toggles the bone without clearing others (pose and armature Edit Mode); added bone becomes active; Ctrl/Alt = plain click. | S004 | `bonemancer/operators/`, `bonemancer/core/selection.py` |
|  | S009 | S | Hidden for the layout | Rule per *Architectural decisions* (own flag, or collections none effectively visible); pick operators do nothing on hidden bones. | S004 | `bonemancer/core/` |
|  | S010 | U | Cell states | Pressed for selected, greyed for hidden, `ERROR` for missing. | S008, S009 | `bonemancer/ui/` |
|  | S011 | S | Rename following | Rewrite cell bone names on every tab beside `rename_set_entries` in `update_bone_list` and `BONEMANCER_OT_rename_bone`. | S001 | `bonemancer/core/selection.py`, `bonemancer/operators/bones.py`, `bonemancer/core/` |
|  | S012 | T | Extend suite | Shift add/remove, active bone, Ctrl as plain click; hidden by flag, by collection, by hidden parent collection, by a soloed other collection; missing cell; Rename and outside-rename following; undo per pick. | S010, S011 | `tests/test_actionable_bones.py` |

### Slice 3 — Editing the layout

**Demoable when:** a rigger moves, recolours and clears cells, a duplicate
placement on the same tab moves the bone, and reopening the file turns Edit
Layout off.
**Satisfies:** AC4, AC11 · **Covers:** US2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S013 | S | Cell menu actions | Left / Right / Centre, Clear, Move (arms the move state; next empty-cell click moves; same cell cancels). | S003 | `bonemancer/operators/` |
|  | S014 | S | Once per tab + side default | Placing a bone already on the tab moves it; side from the bone name on placement. | S003 | `bonemancer/core/` |
|  | S015 | S | Reset session state | Clear Edit Layout and move state in `on_load_post` and `on_armature_change`. | S013 | `bonemancer/handlers.py`, `bonemancer/core/selection.py` |
|  | S016 | U | Edit visuals | Filled-cell menu, "Click an empty cell to move <bone>" line, empty cells clickable only in Edit Layout. | S013 | `bonemancer/ui/` |
|  | S017 | T | Extend suite | Move / cancel move, recolour, clear, duplicate-on-tab moves, same bone on two tabs, side defaults (`.L`, `_R`, centre), state reset on reload and pick change. | S014, S015, S016 | `tests/test_actionable_bones.py` |

### Slice 4 — Linked and overridden rigs

**Demoable when:** a shot that overrides a linked rig shows the rig file's
layout, picks bones, and refuses Edit Layout.
**Satisfies:** AC6 · **Covers:** US4

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S018 | S | Edit Layout posture | Edit Layout and every layout-editing operator refuse on linked or overridden rigs with the tooltip text as the message. | S013 | `bonemancer/operators/`, `bonemancer/core/utils.py` |
|  | S019 | U | Read-only states | Disabled toggle with tooltip; read-only empty-layout hint. | S018 | `bonemancer/ui/panels.py` |
|  | S020 | T | Extend library suite | Library rig with a layout; override shows it, picks select, editing refused without traceback, layout unchanged after save + reload; linked rig pick reports the linked message. | S019 | `tests/test_library.py` |

### Slice 5 — Body and Hands Rigify templates

**Demoable when:** on a freshly generated Rigify human, Apply Rigify Template
fills Body and Hands tabs over silhouettes, and applying again changes nothing.
**Satisfies:** AC7 · **Covers:** US3

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S021 | S | Template definitions | Body (16 wide) and Hands (20 wide): silhouette mask, rows, and Rigify bone → cell + side for the agreed control sets. Shipped as add-on data in `core/`. | S014 | `bonemancer/core/` |
|  | S022 | S | Apply Rigify Template | `UNDO` operator: create missing tabs with template id, fill-gaps merge per *Architectural decisions*, report "N controls placed". | S021 | `bonemancer/operators/` |
|  | S023 | U | Silhouette drawing + entry points | Draw silhouette boxes from the tab's template id; Apply button in empty state and tab menu. | S022 | `bonemancer/ui/` |
|  | S024 | T | Template tests | Generate a Rigify human once in the suite; every template bone name exists on it (guards Rigify renames); apply counts; no tweak bone placed; re-apply idempotent; hand edits survive; non-Rigify rig → silhouettes, 0 placed. | S023 | `tests/test_actionable_bones.py` |

### Slice 6 — User tabs and the 1.2.0 release

**Demoable when:** a rigger adds a "Tail" tab, renames and removes tabs, and the
1.2.0 zip installs with every suite green on 4.5 and 5.2.
**Satisfies:** AC8, AC9 · **Covers:** US2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S025 | S | Tab management | New Tab dialog (name, columns, rows), Rename Tab, Remove Tab with confirm; active tab falls back to the first. | S002 | `bonemancer/operators/` |
|  | S026 | U | Tab menu | Tab menu in the header row while Edit Layout is on. | S025 | `bonemancer/ui/` |
|  | S027 | T | Extend suite | Add / rename / remove / switch; removing the active tab; name clashes refused. | S026 | `tests/test_actionable_bones.py` |
|  | S028 | D | Glossary | Add Actionable Bones, Layout, Layout tab, Cell, Edit Layout, Layout template. | S026 | `reqs/GLOSSARY.md` |
|  | S029 | D | README, checklist, changelog | README feature + quick-start step; manual checklist section (click, Shift, hidden, edit, templates, overrides, themes, sidebar widths); CHANGELOG `[1.2.0]`. | S026 | `README.md`, `tests/MANUAL_CHECKLIST.md`, `CHANGELOG.md` |
|  | S030 | F | Version 1.2.0 | Manifest `1.2.0`; package suite pin. | S029 | `bonemancer/blender_manifest.toml`, `tests/test_package.py` |
|  | S031 | T | Release run | Full runner on 4.5 and 5.2; zip builds and installs; sidebar screenshot at default and wide widths. | S030 | — |

### Slice 7 — Face template (1.2.1)

**Demoable when:** Apply Rigify Template on a generated Rigify human adds a Face
tab with its silhouette and 36 controls.
**Satisfies:** AC10 · **Covers:** US3

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S032 | S | Face definition | Face (20 wide): silhouette and Face + Face (Primary) bone → cell + side. | S021 | `bonemancer/core/` |
|  | S033 | T | Face tests | Names exist on the generated rig; apply places 36; Face (Secondary) bones never placed. | S032 | `tests/test_actionable_bones.py` |
|  | S034 | F | Version 1.2.1 | Manifest, package pin, changelog, checklist Face step. | S033 | `bonemancer/blender_manifest.toml`, `tests/test_package.py`, `CHANGELOG.md`, `tests/MANUAL_CHECKLIST.md` |

### Dependency graph

```
S001 → S002 ─┐
     → S003 ─┼→ S005 → S006, S007
     → S004 ─┘
S004 → S008 ─┐
S004 → S009 ─┴→ S010 ─┐
S001 → S011 ──────────┴→ S012
S003 → S013 → S015 ─┐
S003 → S014 ────────┼→ S017
S013 → S016 ────────┘
S013 → S018 → S019 → S020
S014 → S021 → S022 → S023 → S024
S002 → S025 → S026 → S027
              S026 → S028, S029 → S030 → S031
S021 → S032 → S033 → S034
```

## Dependencies

| REQ ID | Title | Reason |
| ------ | ----- | ------ |
| REQ-001 | 1.0 Extensions Release | Extension packaging, test runner, legacy fixtures |
| REQ-002 | Rig Check | Roadmap table superseded here; rename-following and library-refusal patterns |

## Out of Scope

- Merging `restructure-addon-layout` into `main`; this plan builds on that branch.
- Verifying on Blender 4.2 (pending REQ-001 S001/S009); 4.5 and 5.2 only.
- Migrating Bone Sets into a layout, or a layout into Bone Sets.
- Import / export of layouts between rigs or files.
- Detecting which Rigify features a rig was generated with beyond bone-name
  presence.

## Open Questions

- [x] **Q1 — SOLVE.** None; `—`. *(Blaxine)*
- [x] **Q2 — Release.** 1.2.0 after slice 6 with the unreleased sidebar work;
  Face as 1.2.1. *(Blaxine)*
- [ ] **Q3 — Solo collections.** Does `is_visible_effectively` turn false for
  collections hidden by another collection's solo, or does the rule need
  `Armature.is_solo_active` / `is_solo` too? Deferred until S012's solo test.
- [x] **Q4 — Dim isolated cells — Resolved.** Labels between cells squeezed the
  buttons; empty cells are now disabled buttons (see *Constraints*). *(Blaxine)*
- [ ] **Q5 — Cell size on Hands / Face.** Whether 20 columns stay clickable at
  280 px. Deferred until S023's screenshot; widen the sidebar hint or reduce
  columns if not.

## Smoke Test

> Developer runs the app; the agent does not self-run.

1. Install the built zip in Blender 4.5 and 5.2; open the Bonemancer tab.
2. Add > Armature > Human (Meta-Rig), Generate Rig; pick the generated rig.
3. Actionable Bones: click Apply Rigify Template. Body and Hands tabs appear
   over silhouettes.
4. Click `hand_ik.L`'s cell: it alone is selected and active. Shift+click
   `foot_ik.R`: both selected. Shift+click `hand_ik.L` again: deselected.
5. Hide the "Arm.L (FK)" collection: its cells grey out and do nothing.
6. Turn on Edit Layout; select `tweak_spine` in the viewport; click an empty
   cell: placed. Click it: set Right, Move it, Clear it.
7. Rename `head` with F2: its cell still selects it.
8. Save, reopen: layout kept, Edit Layout off.
9. In a new file, link the rig's collection, make a library override: the
   layout shows, picking works, Edit Layout is disabled.
10. Light and dark themes; sidebar at default and doubled width.

## Size

| T-Shirt Size | Estimated Hours | Notes |
| ------------ | --------------- | ----- |
| L | 45–60 | Slices 1–4 ~20 h; templates ~12 h (cell placement design); user tabs + release ~8 h; Face ~8 h. |

## Considered And Rejected

Nothing here is built. Each entry names the alternative, then why it lost.

- **Retarget-style humanoid tagging.** The first reference image is Omniverse's
  retargeting panel; tagging joints to fixed slots serves animation transfer,
  not posing, and doesn't fit non-human rigs.
- **Auto-detected controls.** Custom-shape / non-deform heuristics misfire on
  Rigify tweak and hidden mechanism bones and need overrides anyway.
- **A Bone Set as the layout's contents.** Sets are flat lists with no position.
- **Floating GPU overlay in the 3D View.** Hand-built hit-testing, scaling,
  theming and navigation conflicts, and headless tests can't see it.
- **Drawing in a spare editor.** Same drawing cost as the overlay, plus taking
  over an editor type Blender doesn't expect.
- **Positions projected from the rig.** Fingers and face controls collapse into
  overlapping piles without manual nudging.
- **Fixed rows by body region.** A structured list, not the body-shaped map
  the references show.
- **Blank canvas only, no template.** Every rig starts from nothing.
- **Typed row / column fields per button.** ~120 numbers to set up a body.
- **Template slots only.** Loses free placement for tails and props.
- **Group buttons (a bone list or a Bone Set per cell).** Duplicates Bone Sets
  and adds a second cell kind; Shift+click covers multi-select.
- **Overridable layout on overrides.** Each shot drifts from the rig file.
- **Layouts in preset files.** Can go missing, don't travel with link/append.
- **Replace the tab on re-apply.** One click wipes hand placement.
- **Ask Merge or Replace on every apply.** A decision per apply, more UI.
- **All Rigify tweak controls in templates.** Doubles body cells; smaller cells.
- **All three face collections.** 88 cells; unreadable at sidebar width.
- **Face masters only.** No lips or brows.
- **Two face mappings (legacy + current).** The deep-dive found the current
  generator emits the names the interview attributed to the legacy face.
- **Click unhides and selects.** Silently flips collection visibility.
- **Hidden cells disappear.** Layout shifts as collections toggle.
- **Resizable tabs / one size for all tabs.** Templates break on resize; one
  size wastes body cells or makes the face coarse.
- **Renaming "Bone Picker" to free the word.** Churn in glossary, docs and code
  identifiers unrelated to the feature.
- **Storing silhouettes in the file.** Larger saves; shipped silhouettes could
  never be improved for existing layouts.
- **One release with the face; templates-first ordering.** The release waits on
  the riskiest slice; auto-placement mistakes can't be fixed before the editor
  exists.

## Revision History

| Date | Author | Summary of Change |
| ---- | ------ | ----------------- |
| 2026-10-22 | Blaxine | Initial plan. |
| 2026-10-26 | Blaxine | Slice 1 implemented. Empty cells are a disabled no-op button (labels squeezed the cell buttons); cell buttons have no per-bone `description()` (it stops `depress` drawing), so the panel names the active bone under the grid instead of a tooltip. Q4 resolved. |
