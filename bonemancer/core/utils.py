# SPDX-License-Identifier: GPL-3.0-or-later
"""Small helpers shared by the whole add-on."""

import bpy
import re

from .compat import is_hidden


# Blender only borrows the strings returned by dynamic enum callbacks, so they
# must stay referenced from Python or the UI shows garbage / lookups fail.
_enum_items_cache = {}


def keep_enum_items(key, items):
    _enum_items_cache[key] = items
    return items


def path_key(name):
    """'["name"]' with quotes/backslashes escaped, for RNA data paths."""
    return f'["{bpy.utils.escape_identifier(name)}"]'


def get_rig(scene):
    """The armature picked in the panel, or None."""
    obj = scene.bonemancer_rig
    return obj if obj and obj.type == 'ARMATURE' else None


def rig_sets(arm_obj):
    return arm_obj.bonemancer_sets if arm_obj else []


def rig_is_editable(arm_obj):
    """False for rigs linked from a library without a library override."""
    return arm_obj is not None and (arm_obj.library is None or arm_obj.override_library is not None)


def live_bones(arm_obj):
    """The armature's bones in the layer that is live: edit bones in Edit Mode, else bones."""
    return arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones


def armature_poll(self, obj):
    return obj.type == 'ARMATURE' and bpy.context.scene in obj.users_scene


def tag_addon_panels(context):
    # Ensure our 3D View sidebar panels redraw
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def sanitize_name(name):
    safe = re.sub(r'\W', '_', name)
    return '_' + safe if re.match(r'^\d', safe) else safe


def find_set(scene, set_name):
    return next((s for s in rig_sets(get_rig(scene)) if s.name == set_name), None)


def set_is_hidden(arm_obj, group):
    pbs = [arm_obj.pose.bones.get(b.bone_name) for b in group.bones]
    pbs = [pb for pb in pbs if pb]
    return bool(pbs) and all(is_hidden(pb) for pb in pbs)


def library_set(arm_obj, set_name):
    """
    The bone set of that name on the library rig an overridden rig is based on,
    or None. Blender can't remove such sets (or their bones) from the override.
    """
    override = arm_obj.override_library if arm_obj else None
    reference = override.reference if override else None
    if reference is None:
        return None
    return next((s for s in reference.bonemancer_sets if s.name == set_name), None)


def pose_bone_path(bone_name):
    """Path from the context to the picked rig's pose bone, for Blender's wm.properties_* operators."""
    return f"scene.bonemancer_rig.pose.bones{path_key(bone_name)}"


def clear_enum_items():
    _enum_items_cache.clear()
