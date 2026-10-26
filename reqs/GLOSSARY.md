# Glossary

The ubiquitous-language reference for BoneMancer. Plans, code, UI strings and
docs use these terms exactly. New terms are added by the plan step that
introduces them, not ad hoc.

| Term | Definition | Notes |
| ---- | ---------- | ----- |
| Actionable Bones | The sidebar panel, between Rig and Bones, that shows the picked rig's **Layout**: click a cell to select its bone, Shift+click to add or remove it. | Not "picker": **Bone Picker** is the Bones panel list. |
| Bone Picker | The list in the Bones panel of every bone in the picked rig. Rows are names only; Add Selected, Rename and Relations sit below the list. | Backed by the scene settings' bone selection list; rebuilt by the depsgraph handler. |
| Bone Set | A named list of bones stored on a rig (`Object.bonemancer_sets`), shown in the Bone Sets panel with hide / select / rename / inspect controls. | Independent of native bone collections; a bone can be in several sets. |
| Cell | One square of a **Layout tab**'s grid. It is empty, or holds one bone's name and a side (left, right or centre) that colours its button. | A bone sits at most once per tab, but may sit on several tabs. Cells store names only and follow bone renames. |
| Depsgraph handler | The add-on's single `depsgraph_update_post` handler: follows the active armature, rebuilds the Bone Picker, tracks outside renames, mirrors selection, tags redraws. | Skipped during animation playback. |
| Edit Layout | The pencil toggle of **Actionable Bones**: while on, clicking an empty **Cell** places the viewport's active bone and a filled cell offers Left / Right / Centre, Move and Clear. | Off after reopening the file and after picking another rig. Locked on linked and overridden rigs. |
| Extension | Blender 4.2+ add-on package format: a folder with `__init__.py` and `blender_manifest.toml`, built into a zip. | Installed module name is `bl_ext.<repo>.<id>`. |
| Group | Former name of a **Bone Set**; still used in the legacy storage keys `rmv2_groups*`. | Not used in the UI or new code. |
| Ignored issue | A Rig Check **Issue** the user chose to stop listing for one rig, stored on the rig (`Object.bonemancer_ignored_issues`) as check + bone + detail. | Travels with the rig; follows bone renames like Bone Set entries. Ignores from a library file can't be removed on an override. |
| Import Bone Collections | The Bone Sets panel action that creates one Bone Set per ticked native bone collection of the picked rig, holding that collection's direct bones. | Re-import merges by set name: adds missing bones and sets, never removes or reorders. Empty collections start unticked. |
| Issue | One problem found by **Rig Check**: a check id, the bone it's about (if any), a detail (constraint name, driver path, mesh…) and a message. | Stored on the Scene with names only, never ID pointers; re-tested cheaply on redraw and greyed when fixed. |
| Layout | A rig's set of **Layout tabs**, stored on the rig (`Object.bonemancer_layout`) and shown in **Actionable Bones**. | Not overridable: an overridden rig shows the layout from its library file. |
| Layout tab | A named grid of **Cells** (columns × rows) in a **Layout**; the panel shows one at a time. | Made with New Tab, or by a **Layout template** (which also records the template's id for its silhouette). |
| Layout template | A ready-made **Layout tab** for a generated Rigify human (Body, Hands): its size, a grey body silhouette and the cell of each control. Applying it only fills empty cells. | Shipped with the add-on; silhouettes are never saved in the file. |
| Legacy groups | Bone Set data written by earlier BoneMancer versions: Scene `rmv2_groups_<sanitized armature name>` (≤ 1.0 dev) and Object `rmv2_groups` (commit `ec08568`). | Migrated on file load, then deleted. |
| Library override | A local, editable copy of a rig linked from another .blend. BoneMancer data on it is editable; bone renames and new custom properties are not persisted by Blender. | A linked rig without an override is read-only. |
| Linked rig | A rig object whose `library` is set and that has no library override. | All editing operators refuse on it. |
| Native bone collection | Blender's own armature bone collections (`Armature.collections` / `collections_all`, Blender 4.0+, nestable since 4.1). | Distinct from Bone Sets. |
| Picked rig | The armature the BoneMancer panels operate on; a pointer property on the Scene that follows the viewport's active armature. | Not necessarily the active object (e.g. while sculpting a mesh). |
| Reference key | A mesh's base shape key (`Key.reference_key`), whatever its name. | Excluded from the Shape Key Scanner. |
| Rig | An armature object. | Used interchangeably with "armature" in the UI. |
| Rig Check | The panel that, on demand, lists **Issues** with the picked rig: broken constraints and drivers, unpaired left/right bones, weight mismatches and setup mistakes. Report-only; it never changes the rig. | Results are cleared when another rig is picked. |
| Shape Key Scanner | The Shape Keys panel: the meshes deformed by the picked rig, and the highlighted mesh's shape keys with sliders and a keyframe toggle. | "Deformed by" = parented under the rig at any depth, or an Armature modifier targeting it. |
| Skinned mesh | A mesh deformed by the rig's bones: it has an Armature modifier using the rig, or armature parenting to it. | Stricter than the Shape Key Scanner's "deformed by": bone-parented props are not skinned. Used by the Rig Check weight and driver checks. |
