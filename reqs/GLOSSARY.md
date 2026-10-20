# Glossary

The ubiquitous-language reference for BoneMancer. Plans, code, UI strings and
docs use these terms exactly. New terms are added by the plan step that
introduces them, not ad hoc.

| Term | Definition | Notes |
| ---- | ---------- | ----- |
| Bone Picker | The list in the sidebar of every bone in the picked rig, with per-row add / rename / relations buttons. | Backed by the scene settings' bone selection list; rebuilt by the depsgraph handler. |
| Bone Set | A named list of bones stored on a rig (`Object.bonemancer_sets`), shown in the Bone Sets panel with hide / select / rename / inspect controls. | Independent of native bone collections; a bone can be in several sets. |
| Depsgraph handler | The add-on's single `depsgraph_update_post` handler: follows the active armature, rebuilds the Bone Picker, tracks outside renames, mirrors selection, tags redraws. | Skipped during animation playback. |
| Extension | Blender 4.2+ add-on package format: a folder with `__init__.py` and `blender_manifest.toml`, built into a zip. | Installed module name is `bl_ext.<repo>.<id>`. |
| Group | Former name of a **Bone Set**; still used in the legacy storage keys `rmv2_groups*`. | Not used in the UI or new code. |
| Ignored issue | A Rig Check **Issue** the user chose to stop listing for one rig, stored on the rig (`Object.bonemancer_ignored_issues`) as check + bone + detail. | Travels with the rig; follows bone renames like Bone Set entries. Ignores from a library file can't be removed on an override. |
| Import Bone Collections | The Bone Sets panel action that creates one Bone Set per ticked native bone collection of the picked rig, holding that collection's direct bones. | Re-import merges by set name: adds missing bones and sets, never removes or reorders. Empty collections start unticked. |
| Issue | One problem found by **Rig Check**: a check id, the bone it's about (if any), a detail (constraint name, driver path, mesh…) and a message. | Stored on the Scene with names only, never ID pointers; re-tested cheaply on redraw and greyed when fixed. |
| Legacy groups | Bone Set data written by earlier BoneMancer versions: Scene `rmv2_groups_<sanitized armature name>` (≤ 1.0 dev) and Object `rmv2_groups` (commit `ec08568`). | Migrated on file load, then deleted. |
| Library override | A local, editable copy of a rig linked from another .blend. BoneMancer data on it is editable; bone renames and new custom properties are not persisted by Blender. | A linked rig without an override is read-only. |
| Linked rig | A rig object whose `library` is set and that has no library override. | All editing operators refuse on it. |
| Native bone collection | Blender's own armature bone collections (`Armature.collections` / `collections_all`, Blender 4.0+, nestable since 4.1). | Distinct from Bone Sets. |
| Picked rig | The armature the BoneMancer panels operate on; a pointer property on the Scene that follows the viewport's active armature. | Not necessarily the active object (e.g. while sculpting a mesh). |
| Reference key | A mesh's base shape key (`Key.reference_key`), whatever its name. | Excluded from the Shape Key Scanner. |
| Rig | An armature object. | Used interchangeably with "armature" in the UI. |
| Rig Check | The panel that, on demand, lists **Issues** with the picked rig: broken constraints and drivers, unpaired left/right bones, weight mismatches and setup mistakes. Report-only; it never changes the rig. | Results are cleared when another rig is picked. |
| Shape Key Scanner | The panel listing shape keys of meshes deformed by the picked rig, with sliders and a keyframe toggle. | "Deformed by" = parented under the rig at any depth, or an Armature modifier targeting it. |
| Skinned mesh | A mesh deformed by the rig's bones: it has an Armature modifier using the rig, or armature parenting to it. | Stricter than the Shape Key Scanner's "deformed by": bone-parented props are not skinned. Used by the Rig Check weight and driver checks. |
