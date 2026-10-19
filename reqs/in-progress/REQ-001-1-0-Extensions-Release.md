# REQ-001 — 1.0 Extensions Release

| Field | Value |
| ----- | ----- |
| ID | REQ-001 |
| Title | 1.0 Extensions Release |
| SOLVE | — |
| Status | In Progress |
| Phase | Release |
| Tier | 1 |
| Area | Packaging, data model, Bone Sets UI, tests |
| Author | Blaxine |
| Created | 2026-10-19 |
| Last Updated | 2026-10-19 |

## Short Description

Ships BoneMancer 1.0 as a free extension on extensions.blender.org for Blender
4.2 LTS and later: an animator control hub where a rig's bones are organised into
**Bone Sets** and hidden, shown, selected, renamed and inspected (custom
properties, constraints, shape keys) from one sidebar. The release packages the
add-on as an extension, strips the half-built features, gives every identifier a
permanent `bonemancer` name with migration for existing files, adds a one-click
import of a rig's native bone collections, and commits a headless test suite that
runs against Blender 4.2, 4.5 LTS and the latest 5.x before every release.

## Constraints

- **Extensions cannot be a single `.py` file.** The package is a folder with
  `__init__.py` and `blender_manifest.toml`, built to a zip by
  `blender --command extension build`.
- **The manifest validator enforces `tagline` ≤ 64 characters** (a 69-character
  draft was rejected by `extension validate` on 4.5).
- **`--factory-startup` does not isolate extension repos.** An install from a
  test lands in the developer's real `%APPDATA%\Blender Foundation\Blender\<ver>\extensions\user_default`
  unless `BLENDER_USER_RESOURCES` points at a temp folder (verified on 4.5 and 5.2).
- **The dev machine has no system Python** (`python` is the Microsoft Store stub).
  The runner executes under Blender's bundled Python and spawns the other
  Blender versions as subprocesses.
- **Blender 4.2 LTS is not installed** and has never run this code. 4.2 predates
  slotted actions (4.4); `get_anim_fcurves` takes its legacy `action.fcurves`
  branch there.
- **Blender 5.x stores Python-defined properties as system properties**, invisible
  to `ID.keys()` / `ID.get()`. Migration reads them through a temporarily
  registered RNA property; a 4.x file opened in 5.x can hold the same data in
  both places.
- **`BoneCollection.bones` holds direct bones only.** `Armature.collections` lists
  root collections; `Armature.collections_all` lists every collection flat
  (4.1+; verified on 4.5 and 5.2).
- **Blender does not persist new custom properties on library-overridden pose
  bones.** The add-on refuses that case with a message.
- **In background mode, an operator's `{'ERROR'}` report raises `RuntimeError`.**
  Tests treat it as a refusal and then assert on state.
- **Installed as an extension, the module is `bl_ext.<repo>.bonemancer`.** Tests
  must not assume the module name `BoneMancer`.

## Architectural decisions

- **Package**: `bonemancer/` containing `__init__.py` (today's `BoneMancer.py`,
  moved as-is) and `blender_manifest.toml`. Manifest: `id = "bonemancer"`,
  `type = "add-on"`, `blender_version_min = "4.2.0"`, no `blender_version_max`,
  `license = ["SPDX:GPL-3.0-or-later"]`, tags `Rigging` and `Animation`, no
  permissions. No `bl_info`.
- **Stored data names**: Bone Sets live on the rig object as
  `Object.bonemancer_sets` (library-overridable, insertion allowed). Scene-level:
  `bonemancer_rig` (picked-rig pointer), `bonemancer_settings` (Bone Picker
  list + last armature), `bonemancer_shape_keys` (scanner state),
  `bonemancer_selected_bone`.
- **Operator and class naming**: every operator is `bonemancer.<verb_noun>`;
  classes are `BONEMANCER_OT_*`, `BONEMANCER_PT_*`, `BONEMANCER_UL_*`. The stray
  `bi.` and `rm.` prefixes go.
- **UI term**: "Bone Set" / "Bone Sets" everywhere a user reads BoneMancer's
  groups; "Bone Collection" only ever means Blender's native collections.
- **Migration chain** (load_post and a first-tick timer after register):
  Scene `rmv2_groups_<sanitized name>` → Object `bonemancer_sets`; Object
  `rmv2_groups` → Object `bonemancer_sets`; Scene `rmv2_rig` /
  `rmv2_rmgr_settings.last_armature` → Scene `bonemancer_rig`. Legacy data is
  deleted only after a successful copy and left untouched when no target rig is
  found.
- **Import semantics**: one Bone Set per ticked native collection holding that
  collection's direct bones; re-import merges by set name (adds missing bones,
  creates missing sets, never removes or reorders); collections with zero direct
  bones are listed unticked.
- **Editing posture**: linked rigs are read-only to every operator; overridden
  rigs accept Bone Set edits and hide/select, refuse bone renames and new custom
  properties.
- **Test contract**: `blender -b --python tests/run.py -- <blender.exe> [<blender.exe> …]`
  runs every automated suite in each given Blender, each suite in its own
  process with `BLENDER_USER_RESOURCES` set to a fresh temp folder, prints a
  pass/fail table per version, and exits non-zero on any failure.
- **Repository layout**: `bonemancer/` (shipped), `tests/` (never shipped),
  `reqs/`, plus `README.md`, `LICENSE`, `.github/ISSUE_TEMPLATE/` at the root.

## Full Description

1.0 is the lean hub. The driver-mirroring helpers, the multi-rig
manager properties and the auto-load setting leave the shipped code; 1.1
(multi-rig + auto-load) and 1.2 (driver mirroring) are separate plans.

Work on 1.1 starts only after 1.0 reaches 500 downloads, an average rating of
4 stars or more, and no open data-loss or crash issues on GitHub.

Support runs through public GitHub Issues with a bug template asking for the
Blender version, BoneMancer version and a sample rig.

## UI / UX Notes

- **Panels** (sidebar tab "Bonemancer"): rig picker + Bone Picker; **Bone Sets**
  (today's "Collections"); Shape Key Scanner.
- **Import Bone Collections**: a button in the Bone Sets panel, and the panel's
  empty state ("No Bone Sets yet" + the Import button) when the picked rig has
  none. Opens a dialog listing every native collection of the picked rig — name,
  direct-bone count, checkbox (ticked by default, unticked when the count is 0),
  indented to show nesting. OK imports the ticked ones.
- **Strings to rename**: panel title "Collections"; "Add Bone to Collection" /
  "Add to Collection"; "New Collection Name"; "Collection" enum label; "Create
  New?"; "(no collections)"; "Delete this collection…"; "Hide every bone in this
  collection…"; the `'<bone>' already in '<group>'` report; "No collection to add
  to; create a new one".
- **Error states**: linked rig → "Rig is linked from a library; make a library
  override first"; no native collections → Import button disabled with a tooltip;
  no picked rig → existing "Select an armature".

## Acceptance Criteria

- [ ] **AC1 — Installable extension.** `blender --command extension validate`
  passes on `bonemancer/`, `extension build` produces `bonemancer-1.0.0.zip`, and
  that zip installs and enables cleanly on Blender 4.2 LTS, 4.5 LTS and the latest
  5.x.
- [ ] **AC2 — One-command test suite.** The documented runner command executes
  every automated suite against each Blender passed to it without touching the
  developer's own Blender config, prints a per-version pass/fail table, exits
  non-zero on failure, and is all-green on 4.2, 4.5 and the latest 5.x.
- [ ] **AC3 — Lean core.** No half-built feature code ships, and the registered
  Scene/Object properties are exactly the set the add-on reads.
- [ ] **AC4 — Permanent identifiers with migration.** Every operator, class and
  stored property uses the `bonemancer` naming. Files saved by the ≤ 1.0-dev
  format and by the `ec08568` format open with every group intact as Bone Sets,
  with the picked rig restored and no legacy data left, including a 4.x file
  opened in 5.x.
- [ ] **AC5 — Bone Sets naming.** No user-visible string calls BoneMancer's groups
  a "collection"; "Bone Collection" appears only for native collections.
- [ ] **AC6 — Import Bone Collections.** From the Bone Sets panel (button or empty
  state), the dialog lists every native collection with its direct-bone count;
  confirming creates one Bone Set per ticked collection containing exactly its
  direct bones; zero-bone collections start unticked.
- [ ] **AC7 — Safe re-import.** Importing again adds missing bones to same-named
  sets and creates missing sets, never removes or reorders bones or sets, leaves
  user-created sets untouched, is undoable, works on an overridden rig and is
  refused on a linked rig.
- [ ] **AC8 — Release-ready repository.** README (features, install, usage), GPL-3.0
  LICENSE, GitHub bug-report template, written manual UI checklist, and a manifest
  whose `website` points at the public GitHub repo and whose `version` is `1.0.0`.

## Technical Notes

### Current layout (commit `ec08568`)

Single file `BoneMancer.py` (~1,990 lines, CRLF line endings). Key symbols:

| Symbol | Kind | Role |
| ------ | ---- | ---- |
| `bone_is_selected`, `set_bone_selected`, `is_hidden`, `set_hidden`, `toggle_hidden` | helpers | 4.x/5.x pose-bone select/hide compatibility |
| `get_anim_fcurves` | helper | F-curves of an action, legacy or slotted (`bpy_extras.anim_utils.action_get_channelbag_for_slot`) |
| `keep_enum_items`, `_enum_items_cache` | helper/global | keeps dynamic-enum strings referenced |
| `path_key`, `bone_data_path` | helpers | escaped `["name"]` / `pose.bones["name"]` paths |
| `get_rig`, `rig_groups`, `rig_is_editable`, `armature_poll` | helpers | picked rig, its groups, linked/override check, picker poll |
| `RMV2_Bone`, `RMV2_Group` | PropertyGroups | group entries; fields carry `override={'LIBRARY_OVERRIDABLE'}` (+ `USE_INSERTION` on `bones`) |
| `RMV2_RmgrSettings` | PropertyGroup | `bone_selection`, `bone_selection_index`, `bone_list_owner`, `last_armature`, plus unused fields |
| `update_bone_list(scene)` | function | rebuilds the Bone Picker; positional rename tracking |
| `sync_selected_bone(scene, view_layer)` | function | mirrors selection into `rmv2_selected_bone`; its change flag drives redraws |
| `rmv2_depsgraph_handler(scene, depsgraph)` | handler | the only depsgraph handler |
| `on_armature_change(self, context)` | update cb | `self` is the owning Scene; activates + Pose Mode only from OBJECT/POSE/EDIT_ARMATURE |
| `_read_legacy_groups(scene, key)`, `migrate_legacy_groups()` | migration | system-property-aware reader; copies then deletes |
| `on_load_post`, `_deferred_init` | handler/timer | run migration on load and once after register |
| `register` / `unregister` | entry points | register `Scene.rmv2_rig`, `Object.rmv2_groups`, settings pointers, handlers |

Operators today: `rmv2.scan_shape_keys`, `rmv2.toggle_shape_keys`,
`rmv2.key_shape_value`, `bi.show_bone_relations`, `rmv2.add_to_group`,
`rmv2.select_bone`, `rmv2.toggle_bone`, `rmv2.toggle_group`, `rmv2.remove_bone`,
`rmv2.remove_group`, `rmv2.toggle_constraints_bone`, `rmv2.rename_bone`,
`rmv2.add_custom_prop`, `rmv2.add_bone_to_collection`,
`rmv2.toggle_group_foldout`, `rmv2.show_constraint_error`.
Panels: `RMV2_PT_ArmaturePicker`, `RMV2_PT_Collections`, `RMV2_PT_ShapeKeyScanner`.
UILists: `RMV2_UL_ConstraintList`, `RMV_2_BONE_UL_selection_list`,
`RMV2_UL_CustomPropsList`, `RMV2_UL_ObjectGroupList`, `RMV2_UL_ShapeKeyList`.

### Removal inventory (Slice 2)

- **Functions**: `update_active_armature`, `duplicate_driver`,
  `get_all_driver_sources`, `get_all_driver_sources_two`,
  `get_object_driver_info`, `get_object_driver_variable_paths`,
  `get_constraint_bone_items`, `get_constraint_bones`, `get_bones`,
  `sync_armature_entry`, `safe_unregister_prop`; global `mirrored_drivers`.
- **Classes**: `BoneItem`, `SINGLE_BONES_ACTIONS`, `ArmatureGroup`,
  `RMV2_RMGR_ArmatureItem`, `RMV2_CustomPropItem`, `RMV2_UL_CustomPropsList`,
  `RMV2_OT_AddToGroup` (`rmv2.add_to_group`, duplicate of
  `rmv2.add_bone_to_collection`).
- **Scene properties**: `rmv2_bone`, `rmv2_constr_bone`, `rmv2_groups`,
  `rmv2_index`, `rmv2_active_bone_name`, `rmv2_bone_list`,
  `rmv2_armature_groups`, `rmv2_active_armature`.
- **PropertyGroup fields**: `RMV2_RmgrSettings.auto_load`, `.groups`,
  `.groups_index`, `.armature_items`, `.armature_index`;
  `RMV2_Bone.custom_props_display`, `.custom_props_index`, `.is_selected`;
  `RMV2_Group.bone_index`, `.show_bones`.
- **Kept**: `sanitize_name` (migration), `RMV2_Bone.constraint_index` (active
  index of the constraint list), `rmv2_selected_bone` (redraw trigger),
  `last_armature` (migration fallback).

### Rename map (Slice 3)

| Today | 1.0 |
| ----- | --- |
| `Object.rmv2_groups` | `Object.bonemancer_sets` |
| `Scene.rmv2_rig` | `Scene.bonemancer_rig` |
| `Scene.rmv2_rmgr_settings` | `Scene.bonemancer_settings` |
| `Scene.rmv2_shape_key_scanner` | `Scene.bonemancer_shape_keys` |
| `Scene.rmv2_selected_bone` | `Scene.bonemancer_selected_bone` |
| `rmv2.*`, `bi.show_bone_relations` | `bonemancer.*` |
| `RMV2_*`, `RMV_2_BONE_UL_selection_list` | `BONEMANCER_OT_* / _PT_* / _UL_*` |
| `rmv2_depsgraph_handler` | name free; stays the single handler |

`_read_legacy_groups` is the pattern for reading any legacy property in 5.x:
register a same-named RNA property, read, unregister; delete through
`scene.pop(key)` **and** `property_unset` after re-registering. Object-level
`rmv2_groups` needs the same treatment on `bpy.types.Object`.

### Native collections API (Slice 5)

`arm_obj.data.collections_all` (flat), `collection.parent` / `.children`
(nesting depth for the dialog indent), `collection.bones` (direct bones),
`collection.name`. An operator's checklist is a `CollectionProperty` of small
PropertyGroups (name, count, ticked) filled in `invoke` and drawn in `draw`.

### Test suites to commit (Slice 1)

There are no tests in the repo yet. The session that produced commit `ec08568`
validated it with throwaway headless scripts (possibly still in that session's
scratchpad: `verify.py`, `make_legacy.py` + `load_new.py`, `make_lib.py` +
`override_test.py`). The committed suites must cover at least:

- **Smoke**: register; dropdown pick enters Pose Mode; Bone Picker contents; add /
  toggle / toggle-group / foldout / constraints toggle / select / custom prop /
  rename / remove bone / remove group; missing-group operators cancel; shape-key
  scan and keyframe insert→remove→insert; the handler runs; Collections,
  ArmaturePicker and ShapeKeyScanner panels and shape-key list items draw against
  a mock layout (including a missing-bone row and a custom prop named with a `"`);
  a foreign `depsgraph_update_post` handler survives; unregister leaves no
  `rmv2_*`/`bonemancer_*` props and no add-on handlers; re-register works.
- **Pitfall regressions**: rename onto an existing name / empty name / empty Find
  are refused with no change; rename retargets only this rig's drivers; picking or
  scanning with auto-key inserts no keys; reference key skipped by identity;
  mesh parented through another object found; pick survives deleting another
  armature and clears when the picked one is deleted; 63-character and non-ASCII
  armature names; non-ASCII bone in a dynamic enum; `Rig.001`/`Rig_001` don't share
  sets; sets survive armature rename; outside single and batch bone renames
  followed; Edit↔Pose switches don't fake renames; dropdown pick doesn't leave
  Sculpt; select on an excluded rig cancels; dropdown pick of an excluded rig
  doesn't raise; rename in Edit Mode sticks; escaped custom-prop path resolves;
  add-to-set enabled while a mesh is active; keyframe toggle on a shape key with
  `"`; group toggle unifies visibility; data-changing operators carry `UNDO` and
  remove-set confirms; existing custom prop not overwritten; viewport active
  armature followed; a subframe key is not treated as on-frame.
- **Migration**: generate a legacy file **in the Blender under test** with a
  vendored copy of the old module (commit `04883fb` for the Scene format, `ec08568`
  for the Object format), reopen it with the current package, assert sets, flags,
  picked rig and no leftover legacy data; plus the 4.x-file-in-5.x case when both
  are given to the runner.
- **Library**: build a library .blend with a rig; linked rig → add/toggle refused;
  `override_hierarchy_create` → add set + bones and foldout persist across
  save/reload, rename and custom prop refused.
- **Package**: validate, build, install into the isolated user repo, enable,
  assert registration, uninstall.

## Implementation Steps

| Phase | Meaning |
| ----- | ------- |
| F | Foundation (packaging, tooling, environment) |
| P | Persistence (stored properties, migration) |
| S | Service (operators, handlers, logic) |
| U | UX (panels, dialogs, strings) |
| D | Docs |
| T | Tests |
| X | Cleanup |

### Slice 1 — Extension package with a green test suite

**Demoable when:** the runner command builds, validates and installs the package
in isolation and prints all-green for 4.2, 4.5 and the latest 5.x.
**Satisfies:** AC1, AC2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ⏭️ | S001 | F | Install Blender 4.2 LTS | Portable 4.2 LTS build on the dev machine for testing only. **Skipped 2026-10-19: download declined; 4.2 stays unverified until the suite is run on it.** | — | — |
| ✅ | S002 | F | Create extension package | `git mv BoneMancer.py bonemancer/__init__.py`; remove `bl_info`; add `blender_manifest.toml` per Architectural decisions (version `1.0.0`, tagline ≤ 64 chars). | — | `bonemancer/__init__.py`, `bonemancer/blender_manifest.toml` |
| ✅ | S003 | F | Ignore build output | `.gitignore` for built zips, `__pycache__/`, test temp output. | S002 | `.gitignore` |
| ✅ | S004 | T | Test runner | Orchestrator run under Blender's Python; for each Blender path × suite, spawn `blender -b --factory-startup --python <suite>` with `BLENDER_USER_RESOURCES` set to a fresh temp dir; collect results; print table; non-zero exit on failure. | S002 | `tests/run.py` |
| ✅ | S005 | T | Smoke + pitfall suite (new) | Port the checks listed under *Test suites to commit*; load the package from the repo's `bonemancer/` folder; leftover-handler check by add-on module, not by a hard-coded name. | S004 | `tests/` |
| ✅ | S006 | T | Migration suite (new) | Vendor the `04883fb` module; generate a legacy file in the Blender under test, reopen with the package, assert. | S004 | `tests/` |
| ✅ | S007 | T | Library suite (new) | Linked and overridden rig checks listed under *Test suites to commit*. | S004 | `tests/` |
| ✅ | S008 | T | Package suite (new) | `extension validate`, `extension build`, install into the isolated user repo, enable, assert registration, uninstall. | S004 | `tests/` |
| ⏭️ | S009 | S | Make 4.2 green | Run the runner on 4.2/4.5/5.x; fix any 4.2-only failure in the add-on. **4.5 and 5.2 green; 4.2 pending S001.** | S001, S005, S006, S007, S008 | `bonemancer/__init__.py` |

### Slice 2 — Lean core

**Demoable when:** the suite is green on all three versions and the registered
properties match an explicit allow-list.
**Satisfies:** AC3

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S010 | X | Remove half-built code | Delete the functions and classes in *Removal inventory*. | S009 | `bonemancer/__init__.py` |
| ✅ | S011 | P | Remove unused properties | Delete the Scene properties and PropertyGroup fields in *Removal inventory*, and their `unregister` entries. | S010 | `bonemancer/__init__.py` |
| ✅ | S012 | T | Extend smoke suite: property allow-list | Assert registered `Scene`/`Object` add-on properties equal the expected set; drop the `add_to_group` check. | S011 | `tests/` |

### Slice 3 — Permanent `bonemancer` identifiers

**Demoable when:** a file saved with either legacy format opens with every set
intact under the new names, on all three versions.
**Satisfies:** AC4

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S013 | P | Rename stored properties | Apply the *Rename map* to stored properties and settings PropertyGroups. | S012 | `bonemancer/__init__.py` |
|  | S014 | S | Rename operators and classes | `bonemancer.*` operator ids, `BONEMANCER_*` classes, panel/UIList ids; update every `layout.operator`, `template_list` and `bpy.ops` reference. | S013 | `bonemancer/__init__.py` |
|  | S015 | P | Extend migration | Add Object `rmv2_groups` → `bonemancer_sets` and Scene `rmv2_rig` → `bonemancer_rig` to the migration chain using the system-property-aware reader; keep the Scene `rmv2_groups_<name>` path. | S013 | `bonemancer/__init__.py` |
|  | S016 | T | Extend migration suite | Vendor the `ec08568` module; cover both legacy formats and a 4.x file opened in 5.x. | S015 | `tests/` |
|  | S017 | T | Fix other suites for new names | Update smoke, pitfall and library suites to the new identifiers. | S014 | `tests/` |

### Slice 4 — Bone Sets naming

**Demoable when:** every BoneMancer panel, dialog, tooltip and report says "Bone
Set", and the suite's string check passes.
**Satisfies:** AC5

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S018 | U | Rename UI strings | Apply the *Strings to rename* list in UI / UX Notes. | S017 | `bonemancer/__init__.py` |
|  | S019 | D | Glossary: Bone Set | Add **Bone Set** to `reqs/GLOSSARY.md`; update the **Group** entry to point at it. | S018 | `reqs/GLOSSARY.md` |
|  | S020 | T | String check (new) | Scan registered operator `bl_label`/`bl_description` and panel labels for "collection" outside native-collection wording. | S018 | `tests/` |

### Slice 5 — Import Bone Collections

**Demoable when:** on a Rigify-style rig with nested native collections, Import
creates the ticked sets, and a second import merges without losing user edits.
**Satisfies:** AC6, AC7

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S021 | S | Import operator | `bonemancer.*` operator with `UNDO`: `invoke` fills the checklist from `collections_all` (name, direct-bone count, ticked unless 0, nesting depth); `execute` applies *Import semantics*; refuses linked rigs; disabled when the rig has no native collections. | S020 | `bonemancer/__init__.py` |
|  | S022 | U | Import entry points | Button in the Bone Sets panel; empty state with the button when the picked rig has no sets; indented checklist dialog. | S021 | `bonemancer/__init__.py` |
|  | S023 | D | Glossary: Import Bone Collections | Add **Import Bone Collections** to `reqs/GLOSSARY.md`. | S021 | `reqs/GLOSSARY.md` |
|  | S024 | T | Import suite (new) | Fresh import; nested collections → one set each, direct bones only; zero-bone unticked; re-import adds missing bones / sets and keeps user edits, order and user sets; overridden rig works; linked rig refused; dialog draw against a mock layout. | S022 | `tests/` |

### Slice 6 — Release-ready repository

**Demoable when:** a stranger can read the README, install the built zip, and file
a bug with the template; the full runner is green and the manual checklist is
signed off.
**Satisfies:** AC8

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
|  | S025 | D | README | What BoneMancer is (control hub), features, install from Extensions / zip, quick start incl. Import, supported versions, support link. | S024 | `README.md` |
|  | S026 | D | License | GPL-3.0-or-later text. | — | `LICENSE` |
|  | S027 | D | Bug-report template | Asks for Blender version, BoneMancer version, OS, steps, sample rig. | — | `.github/ISSUE_TEMPLATE/` |
|  | S028 | D | Manual UI checklist | Click-through for things headless tests can't see: panel layout, dialogs, icons, undo in the UI, viewport sync, empty states. | S024 | `tests/` |
|  | S029 | F | Finalise manifest | `website` = public GitHub repo URL, final `maintainer`, `version = "1.0.0"`. | S025 | `bonemancer/blender_manifest.toml` |
|  | S030 | T | Release candidate run | Full runner on 4.2/4.5/latest 5.x + manual checklist; build the zip for upload. | S028, S029 | — |

### Dependency graph

```
S001 ───────────────────────────────┐
S002 → S003                         │
S002 → S004 → S005 ─┐               │
            → S006 ─┤               │
            → S007 ─┼→ S009 ←───────┘
            → S008 ─┘    │
                         ↓
               S010 → S011 → S012
                               ↓
               S013 → S014 → S017 → S018 → S019
                 └──→ S015 → S016        └→ S020 → S021 → S022 → S024 → S025 → S029 ─┐
                                                     └→ S023          └→ S028 ───────┼→ S030
S026, S027 (independent)                                                             │
```

## Dependencies

| REQ ID | Title | Reason |
| ------ | ----- | ------ |
| — | — | First plan in this repository; no prior REQs. |

## Out of Scope

- Multi-rig manager, auto-load last rig (1.1) and driver mirroring (1.2).
- Splitting `__init__.py` into modules.
- CI (GitHub Actions) for the test suite.
- Automated UI/interaction testing beyond the mock-layout draw checks.
- Live sync of Bone Sets with native collections after import.
- Screenshots and marketing artwork for the Extensions listing beyond what the
  README needs.
- Removing orphaned ID-properties that old builds left in users' files for the
  fields deleted in Slice 2.

## Open Questions

- [x] **Q1 — Resolved.** Re-import merges by set name; never removes or reorders. *(Blaxine)*
- [x] **Q2 — Resolved.** Import picks collections through a checklist dialog; one set per collection, direct bones only. *(Blaxine)*
- [x] **Q3 — Resolved.** Identifiers renamed to `bonemancer` before 1.0, with migration. *(Blaxine)*
- [x] **Q4 — Resolved.** Code moves as-is into `bonemancer/__init__.py`. *(Blaxine)*
- [x] **Q5 — Resolved.** Runner takes Blender paths on the command line. *(Blaxine)*
- [ ] **Q6 — Public repository URL.** Which GitHub owner/name hosts the public repo
  (the manifest `website`)? Deferred until the repo is made public in Slice 6.
- [ ] **Q7 — Public maintainer identity.** Name and contact shown as `maintainer`
  in the manifest (handle "Blaxine" or a real name/email)? Deferred until S029.
- [ ] **Q8 — Icons for Bone Sets.** Keep `OUTLINER_COLLECTION` or switch to an icon
  that doesn't read as a native collection? Deferred until S018 is reviewed in the
  UI via the manual checklist.

## Smoke Test

> Developer runs the app; the agent does not self-run.

1. `blender -b --python tests/run.py -- <4.2 blender.exe> <4.5 blender.exe> <5.x blender.exe>`
   → all suites green for all three.
2. In Blender 4.5: Preferences → Get Extensions → Install from Disk → the built
   `bonemancer-1.0.0.zip`; the **Bonemancer** sidebar tab appears.
3. Add a Rigify human, generate the rig, pick it in the Armature field → Pose
   Mode; Bone Picker lists its bones.
4. Bone Sets panel shows the empty state → **Import Bone Collections** → untick
   the ORG/DEF/MCH collections → OK → one set per ticked collection.
5. Hide/show a set, select a bone from a set, rename a bone through the set row,
   remove a bone, remove a set (confirm dialog), then Ctrl+Z through each.
6. Run Import again → no set loses a bone; a set you created manually is
   unchanged.
7. Open a .blend saved with the pre-1.0 add-on → its groups appear as Bone Sets.
8. Repeat 2–4 in Blender 4.2 and the latest 5.x.

## Size

| T-Shirt Size | Estimated Hours | Notes |
| ------------ | --------------- | ----- |
| L | 30–40 | Slice 1 (runner + four suites + 4.2) and Slice 5 (import) carry most of it; Slices 2–4 are mechanical but touch every operator. |

## Considered And Rejected

Nothing here is built. Each entry names the alternative, then why it lost.

- **Keep "Collections" as the UI term.** Collides with scene collections and native
  Bone Collections; "Import Bone Collections into Collections" reads as nonsense.
- **"Groups" / "Selection Sets" as the UI term.** "Bone Groups" is the pre-4.0
  feature native collections replaced; "Selection Sets" implies selection only.
- **Show native collections live instead of importing.** Removes drift but needs a
  second storage model in the hub before 1.0.
- **Custom sets only, no import.** First run on a Rigify rig is an empty panel.
- **Automatic import on first pick.** Writes data into the user's file unasked.
- **Replace imported sets on re-import.** Wipes user edits to those sets.
- **Ask Merge/Replace on every import.** Two code paths to test and a decision per
  import.
- **Skip existing set names on re-import.** Changes to the rig's collections never
  reach existing sets.
- **Import every collection without a dialog.** Floods the hub with Rigify's
  ORG/DEF/MCH internals, each removal needing a confirmation.
- **Import only visible collections.** Surprises users who hid a collection
  temporarily.
- **Parent set absorbs children's bones.** A bone ends up in several sets.
- **Top-level collections only.** Can't import e.g. "Arm.L (IK)" on its own.
- **Rename operators only, keep `rmv2_groups` storage.** Leaves a mixed naming
  scheme permanently.
- **Keep all `rmv2_*` identifiers.** Users see `rmv2.add_bone_to_collection` in
  tooltips and F3; stray `bi.`/`rm.` prefixes remain.
- **Split into feature modules now / before 1.1.** A large move-diff mixed into
  release work, or a guaranteed churn-heavy start to 1.1.
- **Git-ignored local config for Blender paths.** One more file to document for a
  three-path list.
- **Auto-discover Blender installs.** Platform-specific; fails for portable builds
  such as the 4.2 one this plan installs.
- **Runner on system Python.** The dev machine has none.
- **Committed legacy `.blend` fixtures.** A file saved in 4.5/5.x isn't a faithful
  4.2 input; generating fixtures inside each Blender under test is.
- **GitHub Actions CI.** Multi-GB Blender downloads and URL upkeep per release for a
  single maintainer.
- **Merge slices 3 and 4.** Bundles the migration-risky rename with cosmetic string
  changes in one review.
- **Split Slice 1 into package and tests.** The package slice would have no
  automated proof it works.
- **Import before the identifier rename.** The import operator would be renamed
  twice.

## Revision History

| Date | Author | Summary of Change |
| ---- | ------ | ----------------- |
| 2026-10-19 | Blaxine | Initial plan. |
