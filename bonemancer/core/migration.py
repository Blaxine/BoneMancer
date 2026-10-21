# SPDX-License-Identifier: GPL-3.0-or-later
"""
Upgrading data saved by older versions of the add-on.

Up to 1.0-dev, groups lived on the Scene as rmv2_groups_<armature name> and
the picked rig was an enum plus rmv2_rmgr_settings.last_armature. Commit
ec08568 moved groups to the rig as Object.rmv2_groups and the pick to
Scene.rmv2_rig. Both are copied to the bonemancer_* properties on load and
the old data is deleted; groups whose armature can't be found are kept.
"""

import bpy

from .selection import follow_viewport_rig
from .utils import rig_is_editable, sanitize_name


LEGACY_PREFIX = "rmv2_"
LEGACY_GROUPS_PREFIX = "rmv2_groups_"


def legacy_stores(id_data):
    """
    Where older versions' properties live on id_data: its custom properties
    (Blender 4.x) and, since 5.0, its system properties. A 4.x file opened in
    5.x can hold the same data in both.
    """
    stores = [id_data]
    get_system = getattr(id_data, "bl_system_properties_get", None)
    if get_system:
        system = get_system(do_create=False)
        if system is not None:
            stores.append(system)
    return stores


def _legacy_get(id_data, key):
    values = [store.get(key) for store in legacy_stores(id_data)]
    values = [v for v in values if v is not None]
    # Prefer a non-empty value (an empty collection may sit in one store only)
    return next((v for v in values if not hasattr(v, "__len__") or len(v)), values[0] if values else None)


def _legacy_pop(id_data, key):
    for store in legacy_stores(id_data):
        if store.get(key) is not None:
            del store[key]


def _legacy_sets(value):
    """Old group collection as plain dicts in the bonemancer_sets layout."""
    sets = []
    for grp in value or []:
        grp = grp.to_dict() if hasattr(grp, "to_dict") else dict(grp)
        sets.append({
            "name":          grp.get("group_name", ""),
            "show_expanded": bool(grp.get("show_expanded", False)),
            "bones": [{
                "bone_name":         bone.get("bone_name", ""),
                "show_custom_props": bool(bone.get("show_custom_props", False)),
                "show_constraints":  bool(bone.get("show_constraints", False)),
            } for bone in grp.get("bones", [])],
        })
    return sets


def _add_sets(arm_obj, sets):
    for old in sets:
        bone_set = arm_obj.bonemancer_sets.add()
        bone_set.name = old["name"]
        bone_set.show_expanded = old["show_expanded"]
        for old_bone in old["bones"]:
            entry = bone_set.bones.add()
            entry.bone_name = old_bone["bone_name"]
            entry.show_custom_props = old_bone["show_custom_props"]
            entry.show_constraints = old_bone["show_constraints"]


def migrate_legacy_data():
    # Object.rmv2_groups (ec08568)
    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE' or not rig_is_editable(obj):
            continue
        sets = _legacy_sets(_legacy_get(obj, "rmv2_groups"))
        if sets and not len(obj.bonemancer_sets):
            _add_sets(obj, sets)
        _legacy_pop(obj, "rmv2_groups")

    for scene in bpy.data.scenes:
        if scene.library:
            continue

        # Scene.rmv2_groups_<armature name> (up to 1.0-dev)
        rigs_by_key = {}
        for obj in scene.objects:
            if obj.type == 'ARMATURE' and rig_is_editable(obj):
                rigs_by_key.setdefault(LEGACY_GROUPS_PREFIX + sanitize_name(obj.name), []).append(obj)
        for key, rigs in rigs_by_key.items():
            sets = _legacy_sets(_legacy_get(scene, key))
            if not sets:
                continue
            for obj in rigs:
                if not len(obj.bonemancer_sets):
                    _add_sets(obj, sets)
            _legacy_pop(scene, key)

        # The picked rig
        rig = _legacy_get(scene, "rmv2_rig")
        if not isinstance(rig, bpy.types.Object):
            settings = _legacy_get(scene, "rmv2_rmgr_settings")
            rig = settings.get("last_armature") if hasattr(settings, "get") else None
        if scene.bonemancer_rig is None and isinstance(rig, bpy.types.Object) and rig.type == 'ARMATURE':
            follow_viewport_rig(scene, rig)

        # 1.0 development builds also kept the last pick here; the stale pointer
        # would keep that rig in the file even after it's deleted
        settings = scene.bonemancer_settings
        if settings.get("last_armature") is not None:
            del settings["last_armature"]

        # Everything else older versions kept on the Scene
        for store in legacy_stores(scene):
            for key in [k for k in store.keys()
                        if k.startswith(LEGACY_PREFIX) and not k.startswith(LEGACY_GROUPS_PREFIX)]:
                del store[key]
