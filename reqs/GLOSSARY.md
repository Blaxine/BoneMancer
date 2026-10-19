# Glossary

The ubiquitous-language reference for BoneMancer. Plans, code, UI strings and
docs use these terms exactly. New terms are added by the plan step that
introduces them, not ad hoc.

| Term | Definition | Notes |
| ---- | ---------- | ----- |
| Bone Picker | The list in the sidebar of every bone in the picked rig, with per-row add / rename / relations buttons. | Backed by the scene settings' bone selection list; rebuilt by the depsgraph handler. |
| Depsgraph handler | The add-on's single `depsgraph_update_post` handler: follows the active armature, rebuilds the Bone Picker, tracks outside renames, mirrors selection, tags redraws. | Skipped during animation playback. |
| Extension | Blender 4.2+ add-on package format: a folder with `__init__.py` and `blender_manifest.toml`, built into a zip. | Installed module name is `bl_ext.<repo>.<id>`. |
| Group | BoneMancer's own named list of bone names stored on a rig, shown in the "Collections" panel with hide / select / rename / inspect controls. | Labelled "Collection" in the current UI; independent of native bone collections. |
| Legacy groups | Bone collection data written by earlier BoneMancer versions: Scene `rmv2_groups_<sanitized armature name>` (≤ 1.0 dev) and Object `rmv2_groups` (commit `ec08568`). | Migrated on file load, then deleted. |
| Library override | A local, editable copy of a rig linked from another .blend. BoneMancer data on it is editable; bone renames and new custom properties are not persisted by Blender. | A linked rig without an override is read-only. |
| Linked rig | A rig object whose `library` is set and that has no library override. | All editing operators refuse on it. |
| Native bone collection | Blender's own armature bone collections (`Armature.collections` / `collections_all`, Blender 4.0+, nestable since 4.1). | Distinct from BoneMancer's groups. |
| Picked rig | The armature the BoneMancer panels operate on; a pointer property on the Scene that follows the viewport's active armature. | Not necessarily the active object (e.g. while sculpting a mesh). |
| Reference key | A mesh's base shape key (`Key.reference_key`), whatever its name. | Excluded from the Shape Key Scanner. |
| Rig | An armature object. | Used interchangeably with "armature" in the UI. |
| Shape Key Scanner | The panel listing shape keys of meshes deformed by the picked rig, with sliders and a keyframe toggle. | "Deformed by" = parented under the rig at any depth, or an Armature modifier targeting it. |
