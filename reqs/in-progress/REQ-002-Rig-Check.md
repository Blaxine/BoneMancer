# REQ-002 — Rig Check

| Field | Value |
| ----- | ----- |
| ID | REQ-002 |
| Title | Rig Check |
| SOLVE | — |
| Status | In Progress |
| Phase | 1.1 |
| Tier | 1 |
| Area | Rig Check panel, checks, ignore storage, tests |
| Author | Blaxine |
| Created | 2026-10-20 |
| Last Updated | 2026-10-20 |

> Supersedes the roadmap paragraph in REQ-001's Full Description (1.1 multi-rig +
> auto-load, 1.2 driver mirroring, and the 500-download / 4★ gate). REQ-001 itself
> is not edited.

## Short Description

Ships BoneMancer 1.1: a **Rig Check** panel that, on a click, lists what is wrong
with the picked rig — broken constraints and drivers, left/right bones with no
partner, deform bones without weights and weighted non-deform bones, and common
setup mistakes (unapplied rig transforms, meshes parented without an Armature
modifier, Armature modifiers aimed at the wrong rig). Each result selects the bone
or object and explains why it matters and how to fix it by hand. Results that are
intentional can be ignored per issue; ignores are saved on the rig. Aimed at
riggers from beginner to hobbyist, and at animators receiving rigs.

## Constraints

- **`driver.is_valid` is only set by an evaluation.** Before the depsgraph evaluates
  the owner, every driver reads valid (verified on 4.5.4 and 5.2.2); the check must
  evaluate before reading it.
- **Python drivers in an untrusted file are skipped, not failed.** Blender sets
  `bpy.app.autoexec_fail` when it skips one; their `is_valid` then says nothing.
  Headless runs always execute them (even with `--disable-autoexec` or
  `use_scripts=False`), so tests simulate the blocked state. Expressions using names
  the driver sandbox forbids (e.g. `__import__`) are genuinely invalid.
- **Deleting a property a driver reads doesn't re-evaluate the driver.** Its owner
  needs `update_tag()` before `view_layer.update()` (verified on both versions).
- **`DriverVariable` has no `is_valid`.** Only `is_name_valid`; which variable broke
  must be found by resolving each target (`targ.id`, `data_path`, `bone_target`).
- **`Constraint.is_valid` already covers** missing target and missing subtarget
  bone (verified on both versions).
- **`bpy.utils.flip_name` handles more than `.L/.R`.** Verified: `arm.L`, `arm_L`,
  `arm-l`, `arm L`, `L_arm`, `Left_arm`, `LeftArm`, `eyeLeft`, `hand.left`,
  `arm.L.001` all flip; `spine`, `Lid` return unchanged.
- **Reading weights is cheap.** One pass over a 50,625-vertex mesh with ~4 groups per
  vertex took 0.064–0.07 s on both versions.
- **ID pointers count as users.** A stored pointer to the rig or a mesh keeps a
  deleted object in the file (fixed for the picked rig in commit `4f42ad6`).
- **`select_bone_in_viewport` refuses linked rigs** ("Rig is linked from a library;
  make a library override first"); Select on a linked rig's result inherits that.
- **Library-defined collection items can't be removed on an override.**
  `remove()` raises `TypeError`; `library_set()` + a `TypeError` net is the
  established refusal pattern.
- **The smoke suite's wording check flags every "group(s)" and non-"Bone"
  "collection(s)"** in registered labels, descriptions and property names; "vertex
  group" and "bone collection" in registered strings need the pattern widened.

## Architectural decisions

- **Scope**: the check runs on the picked rig only, on demand (a Check Rig
  operator with `UNDO`). Nothing runs in the depsgraph handler.
- **Skinned mesh**: a mesh object with an Armature modifier whose object is the rig,
  or with `parent_type == 'ARMATURE'` and the rig as parent. Weight and driver
  checks use skinned meshes; the Shape Key Scanner keeps its own "deformed by" rule.
- **Check ids** (stored in ignores, permanent): `constraint`, `driver`, `unpaired`,
  `deform_unweighted`, `nondeform_weighted`, `rig_transform`, `mesh_no_modifier`,
  `modifier_wrong_rig`.
- **Results**: `Scene.bonemancer_rig_check`, a PropertyGroup holding the issue list,
  its active index and the "show ignored" toggle. Issues store strings only — check
  id, bone name, detail (constraint name; driver owner name + data path + index;
  mesh name) — never ID pointers. Results are cleared when the picked rig changes.
- **Ignores**: `Object.bonemancer_ignored_issues` on the rig, a collection of
  `{check, bone, detail}` entries, `LIBRARY_OVERRIDABLE` with `USE_INSERTION`, same
  as `bonemancer_sets`. An issue is ignored when all three fields match.
- **Rename following**: wherever Bone Set entries follow a bone rename (the Rename
  operator and the Bone Picker's outside-rename tracker), ignore entries do too:
  the `bone` field, and `pose.bones["old"]` inside `detail`.
- **Driver scope**: drivers on the rig object, its armature data, each skinned mesh
  and each skinned mesh's shape-key datablock.
- **Python drivers with Auto Run off** are not reported as issues; the panel shows
  one note with their count.
- **Weights**: `deform_unweighted` = a deform bone with no non-zero weight in any
  skinned mesh; `nondeform_weighted` = a non-deform bone whose group has a non-zero
  weight in a skinned mesh.
- **Setup checks**: `rig_transform` = the rig's `matrix_basis` rotation/scale part
  differs from identity beyond 1e-4; `mesh_no_modifier` = a mesh with
  `parent_type == 'OBJECT'` under the rig and no Armature modifier at all;
  `modifier_wrong_rig` = a mesh parented to the rig (object or armature parenting)
  with Armature modifiers, none of them using the rig: one issue per such modifier
  (no object, or another object). Bone-parented meshes are never flagged.
- **Report-only**: no result changes the rig. Actions are Select, Explain, Ignore /
  Un-ignore.
- **Re-verification**: each drawn row re-tests its issue cheaply (subject exists and
  still fails); for weight issues only the bone's Deform flag and the group's
  existence are re-tested. Fixed rows grey out.
- **Library posture**: linked rigs are checked; Ignore is disabled there. On an
  override, ignores are editable; ignores defined in the library file are shown and
  cannot be un-ignored.
- **Release**: manifest `version = "1.1.0"`; no new permissions.

## Full Description

### Roadmap (replaces REQ-001's)

All features are free on extensions.blender.org; a donation link lives in the
listing description, README and GitHub repo, never inside Blender. Each release is
its own plan, grilled when it is next:

| Release | Feature |
| ------- | ------- |
| 1.1 | Rig Check (this plan) |
| 1.2 | Per-bone driver view with jump-to |
| 1.3 | Mirror / symmetry helpers (reuse `flip_name` pairing) |
| 1.4 | Export Bone Sets to native bone collections |
| 1.5 | Batch actions on a Bone Set (reuse 1.4's collection writing) |
| 1.6 | Beginner tooltips |

Multi-rig manager, auto-load and driver mirroring leave the roadmap. There is no
download gate.

### What a result looks like

Every issue has a check id, a subject (bone, constraint, driver or mesh), a one-line
message ("`hand.L`: Copy Rotation has no target"), and an explanation looked up by
check id: what the problem does to the rig, and the manual steps to fix it.

## UI / UX Notes

- **Panel** "Rig Check" in the Bonemancer tab, `DEFAULT_CLOSED`, after Bone Sets.
  Header shows the count of non-ignored issues once a check has run.
- **Top of panel**: Check Rig button; "Select an armature" when nothing is picked;
  a one-line note that new problems appear on the next check.
- **Results**: a UIList grouped by check, one row per issue — icon, message, Select,
  Explain (info icon, opens a dialog like the constraint error popup), Ignore.
  Fixed rows are greyed with "fixed — check again to update".
- **Empty state** after a check: "No issues found" with a check-mark icon.
- **Show ignored** toggle: ignored issues appear with Un-ignore.
- **Python-driver note** (Auto Run off): "N drivers use Python expressions and
  can't be checked while Auto Run Python Scripts is off".
- **Linked rig**: Ignore disabled, tooltip "Rig is linked from a library; make a
  library override to ignore issues".

## Acceptance Criteria

- [ ] **AC1 — Panel and check.** A collapsed "Rig Check" panel runs Check Rig on the
  picked rig, lists results grouped by check, shows the issue count in its header,
  shows "No issues found" for a clean rig and "Select an armature" with no pick.
- [ ] **AC2 — Broken links.** Constraints on the rig's pose bones with no target or a
  missing subtarget bone are listed per bone + constraint. Drivers in the driver
  scope that are invalid after evaluation are listed per owner + path; Python
  expressions while Auto Run is off are not listed and are counted in one note.
- [ ] **AC3 — Unpaired bones.** A bone whose `flip_name` differs from its name and
  for which no bone of that flipped name exists is listed once.
- [ ] **AC4 — Weight mismatch.** Deform bones with no non-zero weight on any skinned
  mesh, and non-deform bones with non-zero weights on a skinned mesh, are listed.
- [ ] **AC5 — Setup mistakes.** A rig with unapplied rotation or scale, a mesh
  object-parented to the rig with no Armature modifier for it, and a mesh parented to
  the rig whose Armature modifier has no or another object are listed; bone-parented
  meshes are not.
- [ ] **AC6 — Select and explain, never change.** Each result's Select makes its bone
  (or object) selected and active; Explain shows why it matters and how to fix it.
  Running the check and every result action leave the rig's data unchanged.
- [ ] **AC7 — Ignore.** Ignoring an issue removes it from the list and the count;
  Show ignored lists it with Un-ignore; ignores survive save and reopen and follow a
  bone renamed with Rename or outside BoneMancer while the rig is picked.
- [ ] **AC8 — Libraries.** On a linked rig the check lists results, Ignore is
  disabled with a tooltip and Select reports the existing linked-rig refusal. On an
  override, ignores persist across reload; an ignore from the library file is shown
  and its Un-ignore is refused with a message, no traceback.
- [ ] **AC9 — Stale results.** After fixing a listed problem, its row is greyed as
  fixed without re-running; problems introduced after the check appear only after
  Check Rig; reopening a file shows the saved results with the same re-verification.
- [ ] **AC10 — Speed.** Check Rig on a generated Rigify human with a ~50k-vertex
  skinned mesh finishes in under ~1 s (manual measurement).
- [ ] **AC11 — 1.1 release.** All suites green on 4.5 and 5.2 including the new rig
  check suite; manifest `1.1.0`; README, manual checklist and glossary updated; the
  built zip installs.

## Technical Notes

### Existing code the plan builds on (`bonemancer/__init__.py`, CRLF)

| Symbol | Line (at `4f42ad6`) | Use |
| ------ | ------------------- | --- |
| `get_rig(scene)`, `rig_is_editable(arm_obj)` | 57, 65 | picked rig; linked check |
| `BONEMANCER_PG_SetBone`, `BONEMANCER_PG_BoneSet` | 73, 95 | pattern for overridable stored PropertyGroups |
| `is_deformed_by(obj, arm_obj)` | 174 | scanner's rule; skinned-mesh rule is stricter and separate |
| `BONEMANCER_OT_scan_shape_keys` | 212 | pattern for an on-demand, `UNDO` scan into a Scene collection |
| `BONEMANCER_PT_shape_keys` | 321 | pattern for a collapsed panel with a UIList |
| `rename_set_entries(arm_obj, old, new)` | 451 | called from `update_bone_list` (outside renames) and `BONEMANCER_OT_rename_bone.execute`; ignore renaming hooks in beside it |
| `bone_data_path(name)` / `path_key(name)` | 458 / 53 | escaped `pose.bones["…"]` for detail rewriting |
| `update_bone_list(scene)` | 525 | outside-rename tracking (picked, editable rig only) |
| `select_bone_in_viewport(context, obj, bone)` | 607 | Select for bone issues |
| `on_depsgraph_update` | 675 | unchanged; unpicks a rig that left the scene (clears results through `on_armature_change`) |
| `library_set(arm_obj, set_name)` | 774 | pattern for "defined in the library file" lookups via `override_library.reference` |
| `BONEMANCER_UL_constraints.draw_item` | 1474 | current per-constraint validity heuristics (`is_valid`, target, subtarget) |
| `BONEMANCER_OT_show_constraint_error` | 1520 | pattern for the Explain dialog (`invoke_props_dialog`) |
| `on_armature_change(self, context)` | 1622 | clear results on pick change |
| `classes`, `SCENE_PROPS`, `OBJECT_PROPS`, `register`, `unregister` | 1572, 1802–1803, 1806, 1846 | registration of new classes and properties |

### Blender API facts used

- Constraints: `pose_bone.constraints`, `Constraint.is_valid`, `.name`, `.target`,
  `.subtarget`.
- Drivers: `id.animation_data.drivers` → `FCurve.data_path`, `.array_index`,
  `.driver.is_valid`, `.driver.is_simple_expression`, `.driver.variables[*].targets[*]`
  (`id`, `data_path`, `bone_target`). Evaluate first (the probe used
  `view_layer.update()`); `bpy.app.autoexec_fail` tells whether Python is blocked.
- Shape keys: `mesh.data.shape_keys` is a `Key` ID with its own `animation_data`.
- Weights: `obj.vertex_groups` (name → index), `mesh.vertices[*].groups[*]`
  (`group`, `weight`); `bone.use_deform`.
- Parenting: `Object.parent`, `parent_type` ∈ `OBJECT`, `ARMATURE`, `LATTICE`,
  `VERTEX`, `VERTEX_3`, `BONE`; modifiers `type == 'ARMATURE'`, `.object`.
- Pairing: `bpy.utils.flip_name(name)`.

### Tests

- Runner `tests/run.py` picks up any `tests/test_*.py`; a new suite needs no runner
  change. Helpers in `tests/helpers.py`: `check`, `finish`, `load_addon`, `refused`,
  `make_arm`, `clear_data`, `tmp_dir`. `refused()` maps tracebacks to `CANCELLED`
  too; assert "Traceback" is absent where a clean refusal matters (see
  `refusal()` in `tests/test_library.py`).
- `tests/test_smoke.py`: `EXPECTED_PROPS` allow-list (gains the two new properties),
  `wrong_set_terms()` wording pattern.
- `tests/test_package.py` pins `"1.0.0"` in the manifest check and the zip name.
- `tests/test_library.py`: library rig with collection "RigColl", override via
  `override_hierarchy_create`; extend for ignores.

## Implementation Steps

| Phase | Meaning |
| ----- | ------- |
| P | Persistence (stored properties) |
| S | Service (operators, checks) |
| U | UX (panels, dialogs, strings) |
| D | Docs |
| T | Tests |
| F | Foundation (manifest, release) |

### Slice 1 — Tracer: broken constraints end to end

**Demoable when:** on a rig with a constraint missing its target, Check Rig lists it,
Select selects the bone, Explain opens the explanation, and a clean rig shows "No
issues found".
**Satisfies:** AC1, AC6, AC2 (constraints)

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S001 | P | Results storage | `Scene.bonemancer_rig_check` per *Architectural decisions* (issues of check / bone / detail / message strings, active index, show-ignored toggle); register/unregister; add to `SCENE_PROPS`. | — | `bonemancer/__init__.py` |
| ✅ | S002 | S | Check Rig operator + constraint check | `UNDO` operator on the picked rig: clear results, run each check, store issues. First check: `constraint` from `Constraint.is_valid` with the target/subtarget message used by `BONEMANCER_UL_constraints`. | S001 | `bonemancer/__init__.py` |
| ✅ | S003 | S | Clear results on pick change | `on_armature_change` empties the results. | S001 | `bonemancer/__init__.py` |
| ✅ | S004 | U | Rig Check panel + results list | Collapsed panel with button, header count, empty and no-rig states, UIList grouped by check. | S002 | `bonemancer/__init__.py` |
| ✅ | S005 | U | Select and Explain | Per-row Select (bone issues via `select_bone_in_viewport`; object issues make the object selected and active from Object Mode, otherwise report) and Explain dialog with per-check-id text. | S004 | `bonemancer/__init__.py` |
| ✅ | S006 | T | Rig check suite (new) | New suite: clean rig → zero issues; missing target and missing subtarget → one `constraint` issue each; Select selects the bone; check leaves the rig unchanged (compare constraints, bones, props before/after); results cleared on pick change; panel draws against `MockLayout` with and without results. | S005 | `tests/test_rig_check.py` |
| ✅ | S007 | T | Extend smoke: allow-list | Add `bonemancer_rig_check` to `EXPECTED_PROPS`. | S001 | `tests/test_smoke.py` |

### Slice 2 — Broken drivers

**Demoable when:** a driver reading a missing property on the rig, and one on a
skinned mesh's shape key, are listed; a Python-expression driver with Auto Run off is
counted in the note instead.
**Satisfies:** AC2

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S008 | S | Skinned-mesh finder | Skinned meshes of the rig per *Architectural decisions*. | S002 | `bonemancer/__init__.py` |
| ✅ | S009 | S | `driver` check | Evaluate, then walk the driver scope; list invalid drivers with owner + data path + index; name the failing variable by resolving its targets; skip and count non-simple expressions when `bpy.app.autoexec_fail`. | S008 | `bonemancer/__init__.py` |
| ✅ | S010 | U | Python-driver note | Note line with the count. | S009 | `bonemancer/__init__.py` |
| ✅ | S011 | T | Extend rig check suite: drivers | Missing variable path on rig and on a skinned mesh's shape key → listed; valid driver → not listed; Python expression while scripts are blocked (simulated) → counted, not listed; a driver on an unrelated object → not listed. | S010 | `tests/test_rig_check.py` |

### Slice 3 — Unpaired left/right bones

**Demoable when:** deleting `arm.R` from a rig makes `arm.L` appear as unpaired.
**Satisfies:** AC3

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S012 | S | `unpaired` check | For each bone with `flip_name(name) != name` and no bone named `flip_name(name)`, one issue. | S002 | `bonemancer/__init__.py` |
| ✅ | S013 | T | Extend rig check suite: pairing | `arm.L` alone → listed; `arm.L` + `arm.R` → none; `L_hand` alone → listed; `spine`, `Lid` → none; `arm.L.001` without `arm.R.001` → listed. | S012 | `tests/test_rig_check.py` |

### Slice 4 — Weight mismatch

**Demoable when:** on a skinned mesh, an unweighted deform bone and a weighted
non-deform bone are listed, and the check stays under the time budget on a Rigify
human.
**Satisfies:** AC4, AC10

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S014 | S | Weight checks | One pass per skinned mesh collecting groups with non-zero weight; `deform_unweighted` and `nondeform_weighted` per *Architectural decisions*. | S008 | `bonemancer/__init__.py` |
| ✅ | S015 | T | Extend rig check suite: weights | Deform bone with no group / empty group → listed; with weights → not; non-deform bone with weighted group → listed, with empty group → not; bone-parented prop mesh ignored. | S014 | `tests/test_rig_check.py` |
| ✅ | S016 | T | Timing run (manual) | Rigify human + ~50k-vertex skinned mesh, time Check Rig on 4.5 and 5.2; record the numbers in this plan's Revision History. | S014 | — |

### Slice 5 — Setup mistakes

**Demoable when:** a rig scaled to 0.5, a mesh object-parented without a modifier,
and a mesh whose modifier targets another rig are each listed.
**Satisfies:** AC5

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S017 | S | Setup checks | `rig_transform`, `mesh_no_modifier`, `modifier_wrong_rig` per *Architectural decisions*. | S008 | `bonemancer/__init__.py` |
| ✅ | S018 | T | Extend rig check suite: setup | Scale 0.5 and rotation 90° → listed, identity → not; object-parented mesh without modifier → listed, with modifier → not; bone-parented mesh → not; modifier with no object / other rig → listed. | S017 | `tests/test_rig_check.py` |

### Slice 6 — Ignore

**Demoable when:** ignoring an issue removes it from the list and count, Show
ignored brings it back with Un-ignore, and the ignore survives save/reopen and a
bone rename.
**Satisfies:** AC7

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S019 | P | Ignore storage | `Object.bonemancer_ignored_issues` per *Architectural decisions*; register/unregister; add to `OBJECT_PROPS`. | S002 | `bonemancer/__init__.py` |
| ✅ | S020 | S | Ignore / Un-ignore operators | `UNDO` operators adding / removing the matching entry on the picked rig; refused on linked rigs. | S019 | `bonemancer/__init__.py` |
| ✅ | S021 | S | Rename following | Rewrite ignore entries next to each `rename_set_entries` call. | S019 | `bonemancer/__init__.py` |
| ✅ | S022 | U | Ignore in the panel | Ignore button per row, Show ignored toggle, header count excludes ignored. | S020 | `bonemancer/__init__.py` |
| ✅ | S023 | T | Extend rig check suite: ignore | Ignore → hidden and not counted; Show ignored → listed; Un-ignore → back; save/reopen keeps it; Rename operator and an outside rename (picked rig) keep it matched; ignore of one constraint doesn't hide another on the same bone. | S022, S021 | `tests/test_rig_check.py` |
| ✅ | S024 | T | Extend smoke: allow-list | Add `bonemancer_ignored_issues` to `EXPECTED_PROPS`. | S019 | `tests/test_smoke.py` |

### Slice 7 — Linked and overridden rigs

**Demoable when:** a linked rig shows its issues with Ignore disabled, and on an
override a new ignore survives reload while a library-defined ignore can't be
removed.
**Satisfies:** AC8

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S025 | S | Library-defined ignores | Lookup of ignores present on `override_library.reference`; Un-ignore refuses them with a message; `TypeError` net around removal (same pattern as `library_set`). | S020 | `bonemancer/__init__.py` |
| ✅ | S026 | U | Linked-rig states | Ignore disabled with tooltip on linked rigs; library-defined ignores shown read-only. | S025 | `bonemancer/__init__.py` |
| ✅ | S027 | T | Extend library suite: rig check | Library rig carries a broken constraint and one ignore; linked: check lists, Ignore refused, Select refused; override: new ignore persists across reload, library ignore's Un-ignore refused without traceback. | S026 | `tests/test_library.py` |

### Slice 8 — Re-verification of listed issues

**Demoable when:** fixing a listed constraint greys its row as fixed without
re-running, and a newly broken one only appears after Check Rig.
**Satisfies:** AC9

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S028 | S | Per-issue re-test | Cheap re-test per check id per *Architectural decisions* (weights: Deform flag and group existence only). | S017, S014, S012, S009 | `bonemancer/__init__.py` |
| ✅ | S029 | U | Fixed rows | UIList greys fixed rows with the "check again" hint. | S028 | `bonemancer/__init__.py` |
| ✅ | S030 | T | Extend rig check suite: re-verify | Fix each check's case after a run → re-test reports fixed; break something new → not listed until re-run; save/reopen → results present and re-tested. | S029 | `tests/test_rig_check.py` |

### Slice 9 — 1.1 release

**Demoable when:** the full runner is green on 4.5 and 5.2, the 1.1.0 zip installs,
and the manual checklist's Rig Check section is signed off.
**Satisfies:** AC10, AC11

| Done | # | Phase | Title | Description | Depends on | Primary files |
| ---- | - | ----- | ----- | ----------- | ---------- | ------------- |
| ✅ | S031 | T | Fix wording check | Widen `wrong_set_terms()` to accept "vertex group(s)" and "bone collection(s)" in any case if registered Rig Check strings use them; keep flagging bare "group"/"collection". **No change needed: no registered Rig Check string uses them; smoke stays green.** | S029 | `tests/test_smoke.py` |
| ✅ | S032 | D | Glossary | Add **Rig Check**, **Issue**, **Ignored issue**, **Skinned mesh** to `reqs/GLOSSARY.md`. | S029 | `reqs/GLOSSARY.md` |
| ✅ | S033 | D | README and checklist | README feature bullet and quick-start line for Rig Check; donation link (**not added: platform undecided, Q9**); `tests/MANUAL_CHECKLIST.md` Rig Check section (each check, Select/Explain, ignore, linked/override, fixed rows, light/dark theme). | S029 | `README.md`, `tests/MANUAL_CHECKLIST.md` |
| ✅ | S034 | F | Version 1.1.0 | Manifest `version = "1.1.0"`. | S033 | `bonemancer/blender_manifest.toml` |
| ✅ | S035 | T | Fix package suite | Expect `1.1.0` and `bonemancer-1.1.0.zip`. | S034 | `tests/test_package.py` |
|  | S036 | T | Release candidate run | Full runner on 4.5 and 5.2, timing run (S016), manual checklist, build the zip. **Runner green on 4.5.4 and 5.2.2, timing done, `bonemancer-1.1.0.zip` built (2026-10-20); manual checklist pending.** | S035, S031, S027, S030, S016 | — |

### Dependency graph

```
S001 → S002 → S004 → S005 → S006
  │      │
  │      ├→ S008 → S009 → S010 → S011
  │      │     ├→ S014 → S015
  │      │     │     └→ S016 ─────────────────────────────┐
  │      │     └→ S017 → S018                             │
  │      ├→ S012 → S013                                   │
  │      └→ S019 → S020 → S022 → S023                     │
  │             ├→ S021 ──────────┘                       │
  │             ├→ S024                                   │
  │             └ (S020) → S025 → S026 → S027 ────────────┤
  ├→ S003                                                 │
  └→ S007                                                 │
S009, S012, S014, S017 → S028 → S029 → S030 ──────────────┤
                                 ├→ S031 ─────────────────┤
                                 ├→ S032                  │
                                 └→ S033 → S034 → S035 ───┴→ S036
```

## Dependencies

| REQ ID | Title | Reason |
| ------ | ----- | ------ |
| REQ-001 | 1.0 Extensions Release | Builds on the 1.0 package, test runner, Bone Set storage pattern and override posture. Supersedes its roadmap paragraph (1.1/1.2 and the 500-download gate). |

## Out of Scope

- Fix buttons of any kind.
- Checking rigs other than the picked one, or several rigs at once.
- Drivers outside the driver scope (materials, other objects reading the rig).
- Re-reading weights on redraw.
- Automated timing tests; the budget is checked by hand.
- Blender 4.2 verification (still pending REQ-001 S001).
- Translations of messages and explanations.
- The 1.2–1.6 features; each gets its own plan.

## Open Questions

- [x] **Q1 — Resolved.** All features free on extensions.blender.org; donation link outside Blender only. *(Blaxine)*
- [x] **Q2 — Resolved.** One feature per 1.x release; Rig Check first. *(Blaxine)*
- [x] **Q3 — Resolved.** Four check families; report and explain only; on demand. *(Blaxine)*
- [x] **Q4 — Resolved.** Per-issue ignores on the rig, keyed check + bone + detail, following renames. *(Blaxine)*
- [x] **Q5 — Resolved.** Results saved on the Scene; listed issues re-verified on redraw. *(Blaxine)*
- [x] **Q6 — Resolved.** REQ-002 supersedes REQ-001's roadmap and download gate. *(Blaxine)*
- [ ] **Q7 — Explanation wording.** Final why/how-to-fix text per check id. Deferred
  until the Explain dialog is reviewed in the UI at the end of Slice 1; later checks
  add their text as they land.
- [ ] **Q8 — Rotated rigs.** Is `rig_transform` on rotation (not just scale) noisy on
  real rigs (e.g. Y-up imports)? Deferred until the S016 timing run on real rigs;
  split rotation into its own check id if so.
- [ ] **Q9 — Donation platform.** Ko-fi, GitHub Sponsors or other. Deferred until
  S033; only the README/listing line depends on it.

## Smoke Test

> Developer runs the app; the agent does not self-run.

1. `blender -b --factory-startup --python tests/run.py -- <4.5 blender.exe> <5.2 blender.exe>`
   → all suites green, including the rig check suite.
2. Install `bonemancer-1.1.0.zip` in 4.5; add a Rigify human, generate, parent a
   mesh with Automatic Weights; pick the rig.
3. Open Rig Check → Check Rig: results appear grouped, count in the header; note
   the time.
4. Clear a constraint's target in Bone Properties → Check Rig → it's listed; Select
   selects the bone; Explain shows the text; set the target again → row greys as
   fixed.
5. Ignore one unpaired-bone issue → gone from the list and count; Show ignored →
   back with Un-ignore; rename that bone with F2 → still ignored after Check Rig.
6. Save, reopen: results and ignores are there.
7. Link the rig into a new file: Check Rig works, Ignore is disabled; make a library
   override: Ignore works and survives save/reopen.
8. Repeat 2–4 in 5.2.

## Size

| T-Shirt Size | Estimated Hours | Notes |
| ------------ | --------------- | ----- |
| L | 30–40 | Slice 1 (new panel, storage, operator, suite) and Slices 6–8 (ignore storage, rename following, override rules, re-verification) carry most of it; each check slice is small. |

## Considered And Rejected

Nothing here is built. Each entry names the alternative, then why it lost.

- **Paid Pro tier (two builds, an add-on to Free, or a single paid product).** GPL
  lets buyers redistribute; a second package doubles release work, and a paid-only
  product loses extensions.blender.org reach.
- **One big 2.0, or two themed waves.** Months without a release and no feedback on
  whether the rig check is what users want.
- **Keep REQ-001's roadmap and download gate, or insert Rig Check before it.** The
  gate could delay 1.1 indefinitely; keeping both lists makes an eight-release
  roadmap with features nobody re-validated.
- **Fewer checks in 1.1.** All four families were chosen; the false-positive risk is
  handled by per-issue ignores.
- **Toggle whole checks instead of per-issue ignores.** Silencing one prop bone hides
  every real unpaired bone.
- **No dismissal.** Valid rigs never reach "No issues found".
- **Ignore a whole bone/object from all checks.** Hides later, unrelated problems on
  that subject.
- **Ignore keys that don't follow renames.** Every rename of an ignored bone
  resurfaces its issue.
- **Live checks (all, or cheap ones in the handler).** Weight reads on every update;
  two behaviours in one panel; selection and posing fire the same updates.
- **Handler-set "stale" flag.** Selection and posing trigger it constantly, so the
  warning stops meaning anything.
- **Timestamp only.** A fixed issue stays listed as broken until re-run.
- **Fix buttons (safe-only or all).** Apply-scale on an animated rig changes its
  animation; each fix needs its own safety rule and tests.
- **Warning icons in the Bone Picker and Bone Sets.** More drawing in the hottest
  list, stale between checks.
- **Popup report.** Results vanish when the dialog closes.
- **Results in Python memory.** Lost on reload and undo; no scrolling list.
- **Results on the rig object.** A linked rig couldn't show any.
- **ID pointers in results.** They count as users and would keep deleted objects in
  the file.
- **Local rigs only.** Broken links are most likely right after linking.
- **Session-only ignores on overrides.** The panel never stays clean on an
  overridden rig.
- **Driver scope: rig object only, or every driver reading the rig.** The first
  misses shape-key correctives; the second reports objects the user doesn't consider
  part of the rig and slows big scenes.
- **Reporting Python drivers as broken when Auto Run is off.** Blender never
  evaluated them, so the list would claim drivers are broken that may work.
- **Weight check by group names only.** An empty group passes; an empty non-deform
  group is flagged.
- **Scanner's "deformed by" rule for weights.** It includes bone-parented props,
  which are rigid on purpose.
- **Extra side-name rules or a user setting.** Would disagree with Symmetrize and
  X-Axis Mirror; `flip_name` already covers prefixes, suffixes and Left/Right.
- **Merge the driver, pairing and setup slices.** One larger diff mixing three
  unrelated detectors.
- **Ignore before the checks.** Each check would add its key format to a data model
  designed before any check existed.

## Revision History

| Date | Author | Summary of Change |
| ---- | ------ | ----------------- |
| 2026-10-20 | Blaxine | Initial plan. |
| 2026-10-20 | Blaxine | Slices 1–4 implemented. S016 timing (generated Rigify human, 706 bones / 160 deform, 50,946-vertex skinned mesh, 4 weights per vertex): 0.01–0.03 s on 4.5.4 and 5.2.2; worst case with one empty deform group (full weight pass) 0.07–0.10 s. No issues reported on the generated Rigify rig. Driver notes corrected: Python drivers in untrusted files are skipped (not invalid) and owners need `update_tag()`. |
| 2026-10-20 | Blaxine | Slices 5–9 implemented. `mesh_no_modifier` narrowed to meshes with no Armature modifier at all (a modifier on another rig is `modifier_wrong_rig` only). Check Rig re-reads the pick after its evaluation, since the depsgraph handler may switch it. S031 needed no change; the donation link waits on Q9; S036 awaits the manual checklist. |
| 2026-10-20 | Blaxine | Sidebar redesign: the Explain dialog and per-row icon buttons are replaced by a details box under the issue list (heading, full message, why, fix, Select and Ignore / Stop Ignoring) for the highlighted issue; the check button reads Check Again after the first run. AC6 holds with Explain shown inline. |
