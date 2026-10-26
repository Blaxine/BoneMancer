# SPDX-License-Identifier: GPL-3.0-or-later
"""The picked rig, the Bone Picker list, and selection between the sidebar and the viewport."""

import bpy

from .compat import bone_is_selected, is_hidden, set_bone_selected, set_hidden
from .layout import rename_layout_cells
from .renaming import rename_set_entries
from .rig_check import clear_rig_check, rename_ignore_entries
from .shape_keys import scan_shape_keys_for_armature
from .utils import get_rig, rig_is_editable


# True while follow_viewport_rig() sets the pick, so on_armature_change
# leaves modes and selection alone
_armature_change_from_viewport = False


# True while the add-on itself moves the Bone Picker highlight, so the move
# isn't mistaken for a click that should select the bone in the viewport
_quiet_picker = False


def armature_bone_names(arm_obj):
    bones = arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones
    return [b.name for b in bones]


def update_bone_list(scene):
    """Rebuild the bone picker for the picked rig; returns True if it changed."""
    settings = scene.bonemancer_settings

    arm_obj = get_rig(scene)
    names = armature_bone_names(arm_obj) if arm_obj else []
    old   = [item.name for item in settings.bone_selection]

    # Skip the rebuild when nothing changed (this runs from depsgraph handlers)
    if names == old and settings.bone_list_owner == arm_obj:
        return False

    # Bones renamed outside the add-on (F2, Outliner, batch rename) keep their
    # position, so carry group entries along. Pure reorders (e.g. switching
    # between Edit and Pose mode) don't count: both names exist in both lists.
    if arm_obj and settings.bone_list_owner == arm_obj and len(names) == len(old) and rig_is_editable(arm_obj):
        old_set, new_set = set(old), set(names)
        for old_name, new_name in zip(old, names):
            if old_name != new_name and old_name not in new_set and new_name not in old_set:
                rename_set_entries(arm_obj, old_name, new_name)
                rename_ignore_entries(arm_obj, old_name, new_name)
                rename_layout_cells(arm_obj, old_name, new_name)

    settings.bone_selection.clear()
    for name in names:
        item = settings.bone_selection.add()
        item.name = name

    settings.bone_list_owner = arm_obj
    set_picker_index(settings, min(settings.bone_selection_index, max(len(names) - 1, 0)))
    return True


def set_picker_index(settings, index):
    """Move the Bone Picker highlight without selecting anything; True if it moved."""
    global _quiet_picker
    if settings.bone_selection_index == index:
        return False
    _quiet_picker = True
    try:
        settings.bone_selection_index = index
    finally:
        _quiet_picker = False
    return True


def viewport_bone(ob):
    """Name of ob's active bone if selected, else its first selected bone, else ''."""
    if ob.mode == 'EDIT':
        bones = ob.data.edit_bones
        active = bones.active
        if active and active.select:
            return active.name
        return next((b.name for b in bones if b.select), "")
    active = ob.data.bones.active
    pb = ob.pose.bones.get(active.name) if active else None
    if pb and bone_is_selected(pb):
        return pb.name
    return next((pb.name for pb in ob.pose.bones if bone_is_selected(pb)), "")


def bone_selected_in_viewport(ob, bone_name):
    """True if ob's bone is selected and visible (edit bone in Edit Mode, pose bone otherwise)."""
    if ob.mode == 'EDIT':
        eb = ob.data.edit_bones.get(bone_name)
        return bool(eb and eb.select and not eb.hide)
    pb = ob.pose.bones.get(bone_name) if ob.pose else None
    return bool(pb and bone_is_selected(pb) and not is_hidden(pb))


def selected_bone_names(ob):
    """ob's selected, visible bones in armature order."""
    if not ob or ob.type != 'ARMATURE':
        return []
    bones = ob.data.edit_bones if ob.mode == 'EDIT' else ob.data.bones
    return [b.name for b in bones if bone_selected_in_viewport(ob, b.name)]


# Selected bones of the picked rig as of the last handler run; a change means
# the Bone Picker must redraw its highlights
_picker_selection = ()


def sync_selected_bone(scene, view_layer):
    """
    Mirror the bone selected in the viewport into scene.bonemancer_selected_bone
    and the Bone Picker highlight; True if either changed.
    """
    ob = view_layer.objects.active if view_layer else None
    if not (ob and ob.type == 'ARMATURE' and ob.mode in {'POSE', 'EDIT'}):
        return False
    selected = viewport_bone(ob)
    changed = scene.bonemancer_selected_bone != selected
    if changed:
        scene.bonemancer_selected_bone = selected

    global _picker_selection
    if ob == get_rig(scene):
        names = tuple(selected_bone_names(ob))
        if names != _picker_selection:
            _picker_selection = names
            changed = True

    settings = scene.bonemancer_settings
    items = settings.bone_selection
    idx = settings.bone_selection_index
    if selected and ob == get_rig(scene) and not (0 <= idx < len(items) and items[idx].name == selected):
        idx = next((i for i, item in enumerate(items) if item.name == selected), -1)
        if idx >= 0:
            changed |= set_picker_index(settings, idx)
    return changed


def select_bone_in_viewport(context, obj, bone_name):
    """
    Make bone_name the only selected bone of obj, and its active bone, showing
    it if hidden. In armature Edit Mode the edit bone is selected; otherwise obj
    becomes active in Pose Mode. Returns an error message, or '' on success.
    """
    if not obj:
        return "No valid armature"
    if context.view_layer.objects.get(obj.name) != obj:
        return f"'{obj.name}' is not in the current view layer"
    if not rig_is_editable(obj):
        return "Rig is linked from a library; make a library override first"

    if obj.mode == 'EDIT':
        eb = obj.data.edit_bones.get(bone_name)
        if not eb:
            return f"Bone '{bone_name}' not found"
        for b in obj.data.edit_bones:
            b.select = b.select_head = b.select_tail = False
        eb.hide = False
        eb.select = eb.select_head = eb.select_tail = True
        obj.data.edit_bones.active = eb
        return ""

    pb = obj.pose.bones.get(bone_name)
    if not pb:
        return f"Bone '{bone_name}' not found"

    enter_pose_mode(context, obj)
    for p in obj.pose.bones:
        set_bone_selected(p, False)
    set_hidden(pb, False)
    set_bone_selected(pb, True)
    obj.data.bones.active = pb.bone
    return ""


def enter_pose_mode(context, obj):
    """Show obj and make it the active object in Pose Mode, unless it already is."""
    obj.hide_set(False)
    obj.hide_viewport = False
    if not (obj.mode == 'POSE' and context.view_layer.objects.active == obj):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')


def toggle_bone_in_viewport(context, obj, bone_name):
    """
    Add bone_name to obj's bone selection, or remove it, keeping the rest; an
    added bone becomes active. Unlike select_bone_in_viewport it never unhides
    the bone. Returns an error message, or '' on success.
    """
    if not obj:
        return "No valid armature"
    if context.view_layer.objects.get(obj.name) != obj:
        return f"'{obj.name}' is not in the current view layer"
    if not rig_is_editable(obj):
        return "Rig is linked from a library; make a library override first"

    if obj.mode == 'EDIT':
        eb = obj.data.edit_bones.get(bone_name)
        if not eb:
            return f"Bone '{bone_name}' not found"
        add = not eb.select
        eb.select = eb.select_head = eb.select_tail = add
        if add:
            obj.data.edit_bones.active = eb
        return ""

    pb = obj.pose.bones.get(bone_name)
    if not pb:
        return f"Bone '{bone_name}' not found"
    enter_pose_mode(context, obj)
    add = not bone_is_selected(pb)
    set_bone_selected(pb, add)
    if add:
        obj.data.bones.active = pb.bone
    return ""


def on_picker_index(settings, context):
    """A click in the Bone Picker selects that bone in the viewport."""
    if _quiet_picker:
        return
    idx = settings.bone_selection_index
    if not 0 <= idx < len(settings.bone_selection):
        return
    scene = settings.id_data
    # Like picking a rig: don't pull the user out of sculpt/paint/other edit modes
    if scene != context.scene or context.mode not in {'OBJECT', 'POSE', 'EDIT_ARMATURE'}:
        return
    arm_obj = get_rig(scene)
    if context.mode == 'EDIT_ARMATURE' and arm_obj and arm_obj.mode != 'EDIT':
        return
    try:
        error = select_bone_in_viewport(context, arm_obj, settings.bone_selection[idx].name)
    except RuntimeError as e:
        error = str(e)
    if error:
        print(f"Bonemancer: {error}")


def select_object_in_viewport(context, obj):
    """Make obj the only selected object and the active one. Returns an error message, or ''."""
    if not obj:
        return "Object not found"
    if context.view_layer.objects.get(obj.name) != obj:
        return f"'{obj.name}' is not in the current view layer"
    if context.mode != 'OBJECT':
        return f"Switch to Object Mode to select '{obj.name}'"
    for other in context.view_layer.objects:
        if other.select_get():
            other.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    return ""


def follow_viewport_rig(scene, rig):
    """Pick rig (or None) as following the viewport does: lists refresh, modes and selection stay."""
    global _armature_change_from_viewport
    _armature_change_from_viewport = True
    try:
        scene.bonemancer_rig = rig
    finally:
        _armature_change_from_viewport = False


def on_armature_change(self, context):
    """
    Handler called when the user picks a new armature in the UI
    or when the active armature changes in the viewport.

    - From viewport: refresh lists only (no mode/selection changes).
    - From dropdown: also activate the armature and enter Pose Mode, but only
      from Object/Pose/armature Edit mode, so paint or sculpt sessions on a
      mesh aren't interrupted.
    """
    scene = self  # the Scene that owns bonemancer_rig (may differ from context.scene)
    arm_obj = get_rig(scene)
    # Rig Check results describe the previous rig
    clear_rig_check(scene)

    # Bail if invalid
    if not arm_obj:
        update_bone_list(scene)
        scan_shape_keys_for_armature(scene, None)   # empties the list
        return

    view_layer = context.view_layer
    can_activate = (
        not _armature_change_from_viewport
        and scene == context.scene
        and context.mode in {'OBJECT', 'POSE', 'EDIT_ARMATURE'}
        and view_layer is not None
        and view_layer.objects.get(arm_obj.name) == arm_obj
        and rig_is_editable(arm_obj)
    )
    if can_activate:
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            arm_obj.select_set(True)
            view_layer.objects.active = arm_obj
            bpy.ops.object.mode_set(mode='POSE')
        except RuntimeError as e:
            print(f"Bonemancer: could not enter Pose Mode on {arm_obj.name}: {e}")

    update_bone_list(scene)
    scan_shape_keys_for_armature(scene, arm_obj)
