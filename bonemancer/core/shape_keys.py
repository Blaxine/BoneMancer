# SPDX-License-Identifier: GPL-3.0-or-later
"""The Shape Key Scanner: which meshes a rig deforms and their shape keys."""

import bpy

from .utils import get_rig, path_key


# True while the scanner rebuilds its list, so restoring slider values
# doesn't write to the shape keys
_suppress_shape_key_update = False


def ensure_shape_keys_action(sk_data, obj_name):
    if not sk_data.animation_data:
        sk_data.animation_data_create()
    if not sk_data.animation_data.action:
        action = bpy.data.actions.new(name=f"{obj_name}_ShapeKeyAction")
        sk_data.animation_data.action = action
    return sk_data.animation_data.action


def tag_shape_key_editors(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in {'DOPESHEET_EDITOR', 'GRAPH_EDITOR', 'TIMELINE'}:
                area.tag_redraw()


def is_deformed_by(obj, arm_obj):
    """True if obj is parented under arm_obj (at any depth) or has an Armature modifier on it."""
    parent = obj.parent
    while parent:
        if parent == arm_obj:
            return True
        parent = parent.parent
    return any(mod.type == 'ARMATURE' and mod.object == arm_obj for mod in obj.modifiers)


def _scanned_meshes(scene, arm_obj):
    """(mesh object, (shape key names…)) for each mesh the scanner should list, reference key excluded."""
    if arm_obj is None:
        return
    for obj in scene.objects:
        if obj.type != 'MESH' or not obj.data.shape_keys or not is_deformed_by(obj, arm_obj):
            continue
        reference = obj.data.shape_keys.reference_key
        yield obj, tuple(kb.name for kb in obj.data.shape_keys.key_blocks if kb != reference)


def scanned_shape_keys(scene, arm_obj):
    return tuple((obj.name, key_names) for obj, key_names in _scanned_meshes(scene, arm_obj))


def listed_shape_keys(scene):
    """The same shape as scanned_shape_keys(), for what the scanner list shows now."""
    return tuple((grp.object_name, tuple(item.key_name for item in grp.shape_keys))
                 for grp in scene.bonemancer_shape_keys.object_groups)


def scan_shape_keys_for_armature(scene, arm_obj):
    """Rebuild the scanner list, keeping the highlighted mesh and shape keys."""
    global _suppress_shape_key_update
    settings = scene.bonemancer_shape_keys
    active_key = {grp.object_name: grp.shape_keys[grp.shape_keys_index].key_name
                  for grp in settings.object_groups if 0 <= grp.shape_keys_index < len(grp.shape_keys)}
    groups = settings.object_groups
    active_mesh = groups[settings.object_groups_index].object_name \
        if 0 <= settings.object_groups_index < len(groups) else ""
    settings.object_groups.clear()

    # Mirroring the current values must not run BONEMANCER_PG_ShapeKey.on_value,
    # which would insert keyframes when auto-keying is on.
    _suppress_shape_key_update = True
    try:
        for obj, key_names in _scanned_meshes(scene, arm_obj):
            mesh_name = obj.name
            key_blocks = obj.data.shape_keys.key_blocks
            grp = settings.object_groups.add()
            grp.object_name = mesh_name
            for key_name in key_names:
                item = grp.shape_keys.add()
                item.object_name = mesh_name
                item.key_name    = key_name
                item.value       = key_blocks[key_name].value
            if active_key.get(mesh_name) in key_names:
                grp.shape_keys_index = key_names.index(active_key[mesh_name])
    finally:
        _suppress_shape_key_update = False

    names = [grp.object_name for grp in settings.object_groups]
    settings.object_groups_index = names.index(active_mesh) if active_mesh in names else 0


def refresh_shape_keys(scene):
    """Rebuild the scanner list if the picked rig's meshes or shape keys changed; True if it did."""
    arm_obj = get_rig(scene)
    if scanned_shape_keys(scene, arm_obj) == listed_shape_keys(scene):
        return False
    scan_shape_keys_for_armature(scene, arm_obj)
    return True


def keyframes_at(fcurve, frame):
    # Same tolerance Blender uses when looking up a keyframe on a frame
    return [kp for kp in fcurve.keyframe_points if abs(kp.co.x - frame) < 0.01]


def set_shape_key_value(item, context):
    """A scanner slider moved: set the shape key, and key it when Auto Keying is on."""
    if _suppress_shape_key_update:
        return
    obj = bpy.data.objects.get(item.object_name)
    if not obj or obj.type != 'MESH' or not obj.data.shape_keys:
        return
    sk_data  = obj.data.shape_keys
    sk_block = sk_data.key_blocks.get(item.key_name)
    if not sk_block:
        return
    sk_block.value = item.value
    if context.scene.tool_settings.use_keyframe_insert_auto:
        ensure_shape_keys_action(sk_data, obj.name)
        sk_data.keyframe_insert(
            data_path=f'key_blocks{path_key(item.key_name)}.value',
            frame=context.scene.frame_current,
        )
        tag_shape_key_editors(context)
