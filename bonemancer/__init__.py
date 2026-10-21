# SPDX-License-Identifier: GPL-3.0-or-later
"""Bone Mancer: Rig Central. Animator control hub for bone sets, custom properties, constraints and shape keys."""

import bpy
import math
import re
import textwrap
from bpy.app.handlers import persistent
from bpy.props import StringProperty, IntProperty,FloatProperty,BoolProperty, CollectionProperty, EnumProperty, PointerProperty
from bpy.types import UIList, Operator, Panel, PropertyGroup

_armature_change_from_viewport = False
_suppress_shape_key_update = False
# True while the add-on itself moves the Bone Picker highlight, so the move
# isn't mistaken for a click that should select the bone in the viewport
_quiet_picker = False
# Blender only borrows the strings returned by dynamic enum callbacks, so they
# must stay referenced from Python or the UI shows garbage / lookups fail.
_enum_items_cache = {}


# --- Blender 4.x / 5.x compatibility -------------------------------------
# Blender 5.0 moved pose-mode selection/visibility from Bone to PoseBone
# and removed Action.fcurves in favour of slotted actions (channelbags).

def bone_is_selected(pb):
    return pb.select if hasattr(pb, "select") else pb.bone.select

def set_bone_selected(pb, value):
    if hasattr(pb, "select"):
        pb.select = value
    else:
        pb.bone.select = value

def get_anim_fcurves(anim_data):
    """Return the F-curves of the action assigned to anim_data (any Blender version)."""
    action = anim_data.action if anim_data else None
    if not action:
        return []
    slot = getattr(anim_data, "action_slot", None)
    if slot is not None:
        from bpy_extras import anim_utils
        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        return channelbag.fcurves if channelbag else []
    # Pre-5.0 legacy API; on 5.x an action without an assigned slot has no curves yet
    return getattr(action, "fcurves", [])


# --- Shared helpers --------------------------------------------------------

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

def armature_poll(self, obj):
    return obj.type == 'ARMATURE' and bpy.context.scene in obj.users_scene


class BONEMANCER_PG_SetBone(PropertyGroup):
    bone_name: StringProperty(name="Bone Name", override={'LIBRARY_OVERRIDABLE'})
    show_custom_props: BoolProperty(
        name="Show Custom Props",
        default=False,
        description="Expand the custom properties of this bone",
        override={'LIBRARY_OVERRIDABLE'}
    )
    show_constraints: BoolProperty(
        name="Show Constraints",
        default=False,
        description="Expand the constraints of this bone",
        override={'LIBRARY_OVERRIDABLE'}
    )
    show_details: BoolProperty(
        name="Show Details",
        default=False,
        description="Show this bone's actions, properties and constraints",
        override={'LIBRARY_OVERRIDABLE'}
    )
    # Active row of the constraint list drawn for this bone
    constraint_index: IntProperty(default=0)


class BONEMANCER_PG_PickerBone(PropertyGroup):
    """Holds a single bone name for selection."""
    name: StringProperty(name="Bone Name")


class BONEMANCER_PG_BoneSet(PropertyGroup):
    # Overridable so groups can be edited on library-overridden rigs
    name: StringProperty(name="Name", override={'LIBRARY_OVERRIDABLE'})
    bones: CollectionProperty(type=BONEMANCER_PG_SetBone, override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'})
    show_expanded: BoolProperty(
        name="Expand Bone Set",
        description="Toggle bone list visibility",
        default=False,
        override={'LIBRARY_OVERRIDABLE'}
    )


class BONEMANCER_PG_Settings(PropertyGroup):
    # The bone picker list
    bone_selection: CollectionProperty(type=BONEMANCER_PG_PickerBone)
    # Clicking a row selects that bone in the viewport
    bone_selection_index: IntProperty(
        name="Index", default=0,
        update=lambda self, ctx: on_picker_index(self, ctx),
    )
    # Armature the bone_selection list was built from (for rename tracking)
    bone_list_owner: PointerProperty(type=bpy.types.Object)

class BONEMANCER_PG_ShapeKey(bpy.types.PropertyGroup):
    object_name: StringProperty(name="Mesh Object Name")
    key_name:    StringProperty(name="Shape Key Name")
    value: FloatProperty(
        name="Value", default=0.0, min=0.0, max=1.0, subtype='FACTOR',
        update=lambda self, ctx: BONEMANCER_PG_ShapeKey.on_value(self, ctx),
    )

    def on_value(self, context):
        if _suppress_shape_key_update:
            return
        obj = bpy.data.objects.get(self.object_name)
        if not obj or obj.type != 'MESH' or not obj.data.shape_keys:
            return
        sk_data  = obj.data.shape_keys
        sk_block = sk_data.key_blocks.get(self.key_name)
        if not sk_block:
            return
        sk_block.value = self.value
        if context.scene.tool_settings.use_keyframe_insert_auto:
            ensure_shape_keys_action(sk_data, obj.name)
            sk_data.keyframe_insert(
                data_path=f'key_blocks{path_key(self.key_name)}.value',
                frame=context.scene.frame_current,
            )
            tag_shape_key_editors(context)

class BONEMANCER_PG_ShapeKeyMesh(bpy.types.PropertyGroup):
    object_name:      StringProperty(name="Mesh Object Name")
    shape_keys:       CollectionProperty(type=BONEMANCER_PG_ShapeKey)
    shape_keys_index: IntProperty(default=0)

class BONEMANCER_PG_ShapeKeyScanner(bpy.types.PropertyGroup):
    object_groups:       CollectionProperty(type=BONEMANCER_PG_ShapeKeyMesh)
    object_groups_index: IntProperty(default=0)


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

class BONEMANCER_OT_scan_shape_keys(bpy.types.Operator):
    bl_idname      = "bonemancer.scan_shape_keys"
    bl_label       = "Refresh Shape Keys"
    bl_description = ("Rebuild the list of meshes the rig deforms and their shape keys now. "
                      "It also refreshes on its own when meshes or shape keys change")
    bl_options     = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm = get_rig(context.scene)
        if not arm:
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        scan_shape_keys_for_armature(context.scene, arm)
        return {'FINISHED'}

def keyframes_at(fcurve, frame):
    # Same tolerance Blender uses when looking up a keyframe on a frame
    return [kp for kp in fcurve.keyframe_points if abs(kp.co.x - frame) < 0.01]

class BONEMANCER_OT_toggle_shape_keyframe(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_shape_keyframe"
    bl_label  = "Toggle Shape Key Keyframe"
    bl_options = {'REGISTER', 'UNDO'}

    object_name:    StringProperty()
    shape_key_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not obj or obj.type != 'MESH' or not obj.data.shape_keys:
            return {'CANCELLED'}

        frame   = context.scene.frame_current
        sk_data = obj.data.shape_keys
        if not sk_data.key_blocks.get(self.shape_key_name):
            self.report({'WARNING'}, f"Shape key '{self.shape_key_name}' not found; rescan the rig")
            return {'CANCELLED'}
        path    = f'key_blocks{path_key(self.shape_key_name)}.value'
        ensure_shape_keys_action(sk_data, obj.name)

        fcurves = get_anim_fcurves(sk_data.animation_data)
        fcu = next((fc for fc in fcurves if fc.data_path == path), None)
        if fcu and keyframes_at(fcu, frame):
            sk_data.keyframe_delete(data_path=path, frame=frame)
            tag_shape_key_editors(context)
            tag_addon_panels(context)
            return {'FINISHED'}

        sk_data.keyframe_insert(data_path=path, frame=frame)
        tag_shape_key_editors(context)
        return {'FINISHED'}
class BONEMANCER_UL_shape_key_meshes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.object_name, icon='MESH_DATA')
        count = row.row(align=True)
        count.alignment = 'RIGHT'
        count.active = False
        count.label(text=plural(len(item.shape_keys), "key"))

class BONEMANCER_UL_shape_keys(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        # Bind slider directly to the actual Shape Key Block
        obj = bpy.data.objects.get(item.object_name)
        kb = None
        if obj and obj.type == 'MESH' and obj.data.shape_keys:
            kb = obj.data.shape_keys.key_blocks.get(item.key_name)

        if kb:
            row.prop(kb, "value", slider=True, text=item.key_name)
        else:
            # Fallback to the mirrored value if the key block is missing
            row.prop(item, "value", slider=True, text=item.key_name)

        # Keyframe icon at current frame
        icon = 'KEY_HLT'
        if kb and obj and obj.data.shape_keys.animation_data:
            fcurves = get_anim_fcurves(obj.data.shape_keys.animation_data)
            path = f'key_blocks{path_key(item.key_name)}.value'
            if any(keyframes_at(fc, context.scene.frame_current)
                   for fc in fcurves if fc.data_path == path):
                icon = 'KEY_DEHLT'

        op = row.operator("bonemancer.toggle_shape_keyframe", text="", icon=icon)
        op.object_name    = item.object_name
        op.shape_key_name = item.key_name

def tag_addon_panels(context):
    # Ensure our 3D View sidebar panels redraw
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class BONEMANCER_PT_shape_keys(bpy.types.Panel):
    bl_label      = "Shape Keys"
    bl_idname     = "BONEMANCER_PT_shape_keys"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = 'Bonemancer'
    bl_options    = {'DEFAULT_CLOSED'}

    def draw_header_preset(self, context):
        # The list refreshes on its own; this is for when it seems out of date
        self.layout.operator("bonemancer.scan_shape_keys", text="", icon='FILE_REFRESH', emboss=False)

    def draw(self, context):
        layout   = self.layout
        settings = context.scene.bonemancer_shape_keys
        if not get_rig(context.scene):
            hint(layout, context, NO_RIG_HINT)
            return
        if not settings.object_groups:
            hint(layout, context, "No mesh that follows this rig has shape keys yet. "
                                  "They show up here as soon as one does.")
            return

        layout.template_list(
            "BONEMANCER_UL_shape_key_meshes", "",
            settings, "object_groups",
            settings, "object_groups_index",
            rows=min(max(len(settings.object_groups), 2), 4)
        )
        # The highlighted mesh's shape keys
        idx = settings.object_groups_index
        if 0 <= idx < len(settings.object_groups):
            grp = settings.object_groups[idx]
            if not grp.shape_keys:
                hint(layout, context, f"{grp.object_name} only has its Basis key.")
                return
            layout.template_list(
                "BONEMANCER_UL_shape_keys", "",
                grp, "shape_keys",
                grp, "shape_keys_index",
                rows=min(max(len(grp.shape_keys), 3), 8)
            )

class BONEMANCER_OT_show_bone_relations(bpy.types.Operator):
    bl_idname = "bonemancer.show_bone_relations"
    bl_label = "Show Bone Relations"
    bl_description = "Display the selected bone’s parent and children in a dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    bone_name: StringProperty(name="Bone Name")  # Passed from UIList row

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return (
            get_rig(scene) is not None and
            len(scene.bonemancer_settings.bone_selection) > 0
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        armature_obj = get_rig(context.scene)

        if not armature_obj:
            layout.label(text="Armature not found")
            return

        bone = armature_obj.data.bones.get(self.bone_name)
        if not bone:
            layout.label(text=f"Bone '{self.bone_name}' not found")
            return

        layout.label(text=f"Bone: {bone.name}", icon='BONE_DATA')

        # Parent
        if bone.parent:
            layout.label(text=f"Parent: {bone.parent.name}")
        else:
            layout.label(text="Parent: None")

        # Children
        if bone.children:
            layout.label(text="Children:")
            for child in bone.children:
                layout.label(text=f"  • {child.name}")
        else:
            layout.label(text="Children: None")

    def execute(self, context):
        return {'FINISHED'}

def sanitize_name(name):
    safe = re.sub(r'\W', '_', name)
    return '_' + safe if re.match(r'^\d', safe) else safe

def is_hidden(pb):
    if not pb:
        return False
    # Blender 5.0+ stores pose-mode visibility on the PoseBone
    return pb.hide if hasattr(pb, "hide") else pb.bone.hide


def set_hidden(pb, value):
    if not pb:
        return
    if hasattr(pb, "hide"):
        pb.hide = value
    else:
        pb.bone.hide = value


def toggle_hidden(pb):
    if pb:
        set_hidden(pb, not is_hidden(pb))

def remove_handlers(handlers):
    """
    Remove each function in `handlers` from Blender's handler lists
    (depsgraph_update_post and load_post).
    """
    for handle in handlers:
        if handle in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(handle)
        if handle in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(handle)



def unregister_properties(base_type, props):
    for p in props:
        if hasattr(base_type, p):
            delattr(base_type, p)


def find_set(scene, set_name):
    return next((s for s in rig_sets(get_rig(scene)) if s.name == set_name), None)


def rename_set_entries(arm_obj, old_name, new_name):
    for grp in rig_sets(arm_obj):
        for entry in grp.bones:
            if entry.bone_name == old_name:
                entry.bone_name = new_name


def bone_data_path(bone_name):
    return f'pose.bones{path_key(bone_name)}'


def update_driver_variable_paths(arm_obj, old_name, new_name):
    """
    Replace references to pose.bones["old_name"] in driver variables that
    target arm_obj, and update their bone_target fields. Drivers targeting
    other rigs (which may have a bone with the same name) are left alone.
    """
    bone_ref_old = bone_data_path(old_name)
    bone_ref_new = bone_data_path(new_name)
    count = 0

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if not ad or not ad.drivers:
            continue

        for fc in ad.drivers:
            for var in fc.driver.variables:
                for targ in var.targets:
                    if targ.id != arm_obj:
                        continue
                    # 1) Update data_path string
                    if targ.data_path and bone_ref_old in targ.data_path:
                        targ.data_path = targ.data_path.replace(bone_ref_old, bone_ref_new)
                        count += 1

                    # 2) Update bone_target property
                    if targ.bone_target == old_name:
                        targ.bone_target = new_name
                        count += 1

    return count


def count_bone_references(arm_obj, bone_name):
    """(drivers, constraints) in the file that point at this bone of arm_obj."""
    bone_ref = bone_data_path(bone_name)
    drivers = 0
    constraints = 0

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if ad:
            for fc in ad.drivers:
                if any(
                    targ.id == arm_obj and
                    ((targ.data_path and bone_ref in targ.data_path) or targ.bone_target == bone_name)
                    for var in fc.driver.variables for targ in var.targets
                ):
                    drivers += 1

        owners = [obj] + (list(obj.pose.bones) if obj.pose else [])
        for owner in owners:
            for con in owner.constraints:
                if getattr(con, "target", None) == arm_obj and getattr(con, "subtarget", "") == bone_name:
                    constraints += 1

    return drivers, constraints


def _armature_bone_names(arm_obj):
    bones = arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones
    return [b.name for b in bones]

def update_bone_list(scene):
    """Rebuild the bone picker for the picked rig; returns True if it changed."""
    settings = scene.bonemancer_settings

    arm_obj = get_rig(scene)
    names = _armature_bone_names(arm_obj) if arm_obj else []
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

    obj.hide_set(False)
    obj.hide_viewport = False
    if not (obj.mode == 'POSE' and context.view_layer.objects.active == obj):
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')

    for p in obj.pose.bones:
        set_bone_selected(p, False)
    set_hidden(pb, False)
    set_bone_selected(pb, True)
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


@persistent
def on_depsgraph_update(scene, depsgraph):
    """Single depsgraph handler: viewport → picker sync, bone list and selection refresh."""
    global _armature_change_from_viewport

    screen = bpy.context.screen
    if screen and screen.is_animation_playing:
        return

    # 1) Drop a picked rig that left the scene (deleted with X, unlinked). Our
    # pointers count as users, so keeping them would keep a deleted rig in the
    # file for good.
    rig = scene.bonemancer_rig
    if rig is not None and scene not in rig.users_scene:
        _armature_change_from_viewport = True
        try:
            scene.bonemancer_rig = None
        finally:
            _armature_change_from_viewport = False

    # 2) Follow the active armature in the viewport (cheap: one lookup)
    view_layer = depsgraph.view_layer
    active = view_layer.objects.active if view_layer else None
    if active and active.type == 'ARMATURE' and scene.bonemancer_rig != active:
        _armature_change_from_viewport = True  # mark source of change
        try:
            scene.bonemancer_rig = active
        finally:
            _armature_change_from_viewport = False

    # 3) Only armature/object updates can change bone names or selection
    redraw = False
    if depsgraph.id_type_updated('ARMATURE') or depsgraph.id_type_updated('OBJECT'):
        changed = update_bone_list(scene)
        changed |= sync_selected_bone(scene, view_layer)
        redraw = changed or depsgraph.id_type_updated('ARMATURE')
    if depsgraph.id_type_updated('KEY'):
        redraw = True

    # 4) Shape Key Scanner: meshes parented/unparented, shape keys added,
    # renamed or removed. Moving a slider changes neither, so this stays a
    # comparison while posing or sculpting.
    if any(depsgraph.id_type_updated(t) for t in ('OBJECT', 'KEY', 'MESH')):
        redraw |= refresh_shape_keys(scene)

    if redraw:
        tag_addon_panels(bpy.context)


def get_set_items(self, context):
    groups = rig_sets(get_rig(context.scene))
    return keep_enum_items("groups", [(g.name, g.name, "") for g in groups])


class BONEMANCER_OT_select_bone(bpy.types.Operator):
    bl_idname = "bonemancer.select_bone"
    bl_label  = "Select Bone"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        error = select_bone_in_viewport(context, get_rig(context.scene), self.bone_name)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}

class BONEMANCER_OT_toggle_bone(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_bone"
    bl_label = "Toggle Bone"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = get_rig(context.scene)
        if not rig_is_editable(obj):
            self.report({'WARNING'}, "No editable armature")
            return {'CANCELLED'}
        toggle_hidden(obj.pose.bones.get(self.bone_name))
        return {'FINISHED'}


def set_is_hidden(arm_obj, group):
    pbs = [arm_obj.pose.bones.get(b.bone_name) for b in group.bones]
    pbs = [pb for pb in pbs if pb]
    return bool(pbs) and all(is_hidden(pb) for pb in pbs)


class BONEMANCER_OT_toggle_set(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_set"
    bl_label = "Toggle Bone Set Visibility"
    bl_description = "Hide every bone in this bone set, or show them all if all are hidden"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()

    def execute(self, context):
        sc = context.scene
        obj = get_rig(sc)
        group = find_set(sc, self.set_name)
        if not rig_is_editable(obj) or not group:
            self.report({'WARNING'}, f"Bone set '{self.set_name}' not found")
            return {'CANCELLED'}
        # Mixed visibility hides all; only a fully hidden group is shown again
        hide = not set_is_hidden(obj, group)
        for b in group.bones:
            set_hidden(obj.pose.bones.get(b.bone_name), hide)
        return {'FINISHED'}


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


class BONEMANCER_OT_remove_bone_from_set(bpy.types.Operator):
    bl_idname = "bonemancer.remove_bone_from_set"
    bl_label = "Remove Bone from Set"
    bl_description = "Remove this bone from the bone set (the bone itself is kept)"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        arm = get_rig(context.scene)
        group = find_set(context.scene, self.set_name)
        if not group or not rig_is_editable(arm):
            self.report({'WARNING'}, f"Bone set '{self.set_name}' not found")
            return {'CANCELLED'}
        lib = library_set(arm, self.set_name)
        if lib and any(b.bone_name == self.bone_name for b in lib.bones):
            self.report({'ERROR'}, f"'{self.bone_name}' is in '{self.set_name}' in the rig's library file; remove it there")
            return {'CANCELLED'}
        for i, b in enumerate(group.bones):
            if b.bone_name == self.bone_name:
                try:
                    group.bones.remove(i)
                except TypeError:
                    self.report({'ERROR'}, "This bone can't be removed from an overridden rig")
                    return {'CANCELLED'}
                break
        return {'FINISHED'}


class BONEMANCER_OT_remove_set(bpy.types.Operator):
    bl_idname = "bonemancer.remove_set"
    bl_label = "Remove Bone Set"
    bl_description = "Delete this bone set (the bones themselves are kept)"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        arm = get_rig(context.scene)
        if not rig_is_editable(arm):
            return {'CANCELLED'}
        if library_set(arm, self.set_name):
            self.report({'ERROR'}, f"Bone set '{self.set_name}' comes from the rig's library file; remove it there")
            return {'CANCELLED'}
        groups = arm.bonemancer_sets
        for i, g in enumerate(groups):
            if g.name == self.set_name:
                try:
                    groups.remove(i)
                except TypeError:
                    self.report({'ERROR'}, "This bone set can't be removed from an overridden rig")
                    return {'CANCELLED'}
                return {'FINISHED'}
        return {'CANCELLED'}

class BONEMANCER_OT_rename_bone(bpy.types.Operator):
    bl_idname = "bonemancer.rename_bone"
    bl_label = "Rename Bone"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name:  StringProperty()

    mode: EnumProperty(
        name="Mode",
        items=[
            ('EXACT',   "Exact",   "Type the full new name"),
            ('PREFIX',  "Prefix",  "Add text before the old name"),
            ('SUFFIX',  "Suffix",  "Add text after the old name"),
            ('REPLACE', "Replace", "Find & replace in the old name"),
        ],
        default='EXACT'
    )

    # Exact
    new_name: StringProperty(name="New Bone Name", default="")

    # Prefix presets + custom
    preset_prefix: EnumProperty(
        name="Preset",
        items=[
            ('NONE',   "None",   "No preset prefix"),
            ('DEF',    "DEF_",   "Default prefix"),
            ('ORG',    "ORG_",   "Original prefix"),
            ('MCH',    "MCH_",   "Match prefix"),
            ('CUSTOM', "Custom", "Type your own prefix"),
        ],
        default='NONE'
    )
    affix_text: StringProperty(name="Custom Prefix", default="")

    # Suffix
    suffix_text: StringProperty(name="Text", default="")

    # Replace
    find_text:    StringProperty(name="Find",    default="")
    replace_text: StringProperty(name="Replace", default="")

    # Preview + counts
    preview:            StringProperty(name="Preview", default="")
    drivers_count:      IntProperty(default=0)
    constraints_count:  IntProperty(default=0)

    def invoke(self, context, event):
        # Initialize fields
        self.new_name       = self.bone_name
        self.preset_prefix  = 'NONE'
        self.affix_text     = ""
        self.suffix_text    = ""
        self.find_text      = ""
        self.replace_text   = ""
        self.preview        = ""
        self.mode           = 'EXACT'

        # Count drivers / constraints pointing at this bone (Blender retargets them)
        arm_obj = get_rig(context.scene)
        if arm_obj:
            self.drivers_count, self.constraints_count = count_bone_references(arm_obj, self.bone_name)
        else:
            self.drivers_count = self.constraints_count = 0

        # Compute initial preview
        self.update_preview()
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)

        if self.mode == 'EXACT':
            layout.prop(self, "new_name")

        elif self.mode == 'PREFIX':
            layout.prop(self, "preset_prefix", text="Preset")
            if self.preset_prefix == 'CUSTOM':
                layout.prop(self, "affix_text", text="Custom Prefix")

        elif self.mode == 'SUFFIX':
            layout.prop(self, "suffix_text", text="Text")

        else:  # REPLACE
            layout.prop(self, "find_text")
            layout.prop(self, "replace_text")

        layout.separator()
        layout.label(text=f"{self.drivers_count} driver(s) will update")
        layout.label(text=f"{self.constraints_count} constraint(s) will update")
        layout.separator()
        layout.label(text="Result Preview:")
        error = self.validate(context)
        layout.box().label(text=error or self.preview, icon='ERROR' if error else 'BONE_DATA')

    def update_preview(self):
        name = self.bone_name

        if self.mode == 'EXACT':
            out = self.new_name

        elif self.mode == 'PREFIX':
            # decide which prefix to use
            if self.preset_prefix == 'DEF':
                prefix = "DEF_"
            elif self.preset_prefix == 'ORG':
                prefix = "ORG_"
            elif self.preset_prefix == 'MCH':
                prefix = "MCH_"
            elif self.preset_prefix == 'CUSTOM':
                prefix = self.affix_text
            else:
                prefix = ""
            out = prefix + name

        elif self.mode == 'SUFFIX':
            out = name + self.suffix_text

        else:  # REPLACE
            # An empty Find would insert the replacement between every character
            out = name.replace(self.find_text, self.replace_text) if self.find_text else name

        self.preview = out

    def validate(self, context):
        """Return an error message for the current preview, or ''."""
        arm_obj = get_rig(context.scene)
        if not arm_obj:
            return "No valid armature selected"
        if arm_obj.data.library or arm_obj.data.override_library:
            return "Bones of a linked/overridden rig can't be renamed"
        if self.mode == 'REPLACE' and not self.find_text:
            return "Find text is empty"
        if not self.preview.strip():
            return "New name is empty"
        if self.preview != self.bone_name and self.preview in _armature_bone_names(arm_obj):
            return f"A bone named '{self.preview}' already exists"
        return ""

    def execute(self, context):
        # 1) Compute the final name from your preview logic
        self.update_preview()
        error = self.validate(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        new_name = self.preview
        if new_name == self.bone_name:
            return {'FINISHED'}

        # 2) Rename the bone in the layer that is live in the current mode
        arm_obj = get_rig(context.scene)
        bones = arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones
        bone = bones.get(self.bone_name)
        if not bone:
            self.report({'ERROR'}, f"Bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        bone.name = new_name
        new_name = bone.name  # Blender may still adjust it (e.g. length limit)

        # 3) Update group entries, driver variables on this rig, and the picker
        rename_set_entries(arm_obj, self.bone_name, new_name)
        rename_ignore_entries(arm_obj, self.bone_name, new_name)
        update_driver_variable_paths(arm_obj, self.bone_name, new_name)
        update_bone_list(context.scene)
        arm_obj.update_tag()

        return {'FINISHED'}

    def check(self, context):
        # Live-preview on any property change
        self.update_preview()
        return True


class BONEMANCER_OT_add_custom_prop(bpy.types.Operator):
    bl_idname = "bonemancer.add_custom_prop"
    bl_label = "Add Custom Property"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()
    prop_name: StringProperty(name="Property Name", default="")
    prop_type: EnumProperty(
        name="Type",
        items=[
            ('FLOAT',   "Float",   ""),
            ('INT',     "Integer", ""),
            ('BOOLEAN', "Boolean",""),
            ('STRING',  "String",  "")
        ],
        default='FLOAT'
    )
    default_float:  FloatProperty(name="Default Float",    default=0.0)
    default_int:    IntProperty(name="Default Integer",   default=0)
    default_bool:   BoolProperty(name="Default Boolean",  default=False)
    default_string: StringProperty(name="Default String",  default="")

    def invoke(self, context, event):
        self.prop_name = ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "prop_name")
        layout.prop(self, "prop_type")
        if self.prop_type == 'FLOAT':
            layout.prop(self, "default_float")
        elif self.prop_type == 'INT':
            layout.prop(self, "default_int")
        elif self.prop_type == 'BOOLEAN':
            layout.prop(self, "default_bool")
        else:
            layout.prop(self, "default_string")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        pb = arm_obj and arm_obj.pose.bones.get(self.bone_name)
        if not pb:
            self.report({'ERROR'}, "Bone not found")
            return {'CANCELLED'}
        if arm_obj.library or arm_obj.override_library:
            # Blender doesn't keep new custom properties on overridden pose bones
            self.report({'ERROR'}, "Add custom properties in the rig's library file")
            return {'CANCELLED'}
        if not self.prop_name.strip():
            self.report({'ERROR'}, "Property name cannot be empty")
            return {'CANCELLED'}
        if self.prop_name in pb.keys():
            self.report({'ERROR'}, f"'{self.prop_name}' already exists on {pb.name}")
            return {'CANCELLED'}

        if self.prop_type == 'FLOAT':
            pb[self.prop_name] = self.default_float
        elif self.prop_type == 'INT':
            pb[self.prop_name] = self.default_int
        elif self.prop_type == 'BOOLEAN':
            pb[self.prop_name] = self.default_bool
        else:
            pb[self.prop_name] = self.default_string

        # Keep the value editable when this rig is later linked with a library override
        pb.property_overridable_library_set(path_key(self.prop_name), True)
        return {'FINISHED'}


# Blender's Edit Property dialog converts a float property's range to int when
# its Type is switched to Integer, and fails on the unlimited (±3.4e38) range
# a property made by a script has.
INT_RANGE = (-2**31, 2**31 - 1)


def make_ui_range_int_safe(owner, key):
    """Clamp a float custom property's min/max/soft limits to what an int can hold.

    Only out-of-range limits change, so a property with a real range keeps it."""
    try:
        ui = owner.id_properties_ui(key)
    except TypeError:
        return   # strings, groups and data-blocks have no numeric range
    limits = {k: v for k, v in ui.as_dict().items() if k in ("min", "max", "soft_min", "soft_max")}
    clamped = {k: min(max(v, INT_RANGE[0]), INT_RANGE[1]) for k, v in limits.items() if isinstance(v, float)}
    if any(clamped[k] != limits[k] for k in clamped):
        ui.update(**clamped)


class BONEMANCER_OT_edit_custom_prop(bpy.types.Operator):
    """Change a custom property's name, type, range, default or description"""
    bl_idname = "bonemancer.edit_custom_prop"
    bl_label = "Edit Property"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    bone_name: StringProperty()
    prop_name: StringProperty()

    def pose_bone(self, context):
        rig = get_rig(context.scene)
        if not rig or rig.library or rig.override_library:
            return None   # Blender refuses to edit properties of linked or overridden data
        pb = rig.pose.bones.get(self.bone_name)
        return pb if pb and self.prop_name in pb.keys() else None

    def execute(self, context):
        pb = self.pose_bone(context)
        if not pb:
            return {'CANCELLED'}
        make_ui_range_int_safe(pb, self.prop_name)
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.execute(context) != {'FINISHED'}:
            return {'CANCELLED'}
        # Blender's own dialog does the editing
        bpy.ops.wm.properties_edit('INVOKE_DEFAULT', data_path=pose_bone_path(self.bone_name),
                                   property_name=self.prop_name)
        return {'FINISHED'}


class BONEMANCER_OT_add_bone_to_set(bpy.types.Operator):
    bl_idname = "bonemancer.add_bone_to_set"
    bl_label = "Add Bone to Bone Set"
    bl_description = "Add this bone to a new or existing bone set"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty(options={'HIDDEN'})
    # Add every selected bone of the picked rig instead of bone_name
    use_selected: BoolProperty(name="Selected Bones", default=False, options={'HIDDEN', 'SKIP_SAVE'})
    set_enum: EnumProperty(name="Bone Set", items=get_set_items)
    create_new: BoolProperty(name="New Bone Set", default=False)
    new_set_name: StringProperty(name="Bone Set Name", default="")

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    @classmethod
    def description(cls, context, properties):
        if properties.use_selected:
            return "Add every selected bone to a new or existing bone set"
        return cls.bl_description

    def bone_names(self, context):
        if self.use_selected:
            return selected_bone_names(get_rig(context.scene))
        return [self.bone_name]

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


    def draw(self, context):
        layout = self.layout
        if self.use_selected:
            names = self.bone_names(context)
            layout.label(text=f"{len(names)} selected bone{'s' if len(names) != 1 else ''}", icon='GROUP_BONE')
        else:
            layout.label(text=self.bone_name, icon='BONE_DATA')
        layout.prop(self, "create_new")
        if self.create_new:
            layout.prop(self, "new_set_name", text="Name")
        else:
            layout.prop(self, "set_enum", text="Bone Set")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        bone_names = self.bone_names(context)
        if not bone_names:
            self.report({'WARNING'}, "Select some bones first")
            return {'CANCELLED'}

        # 1) Groups live on the rig object itself
        groups = arm_obj.bonemancer_sets

        # 2) Figure out which group to target
        if self.create_new:
            name = self.new_set_name.strip()
            if not name:
                self.report({'ERROR'}, "Bone set name cannot be empty")
                return {'CANCELLED'}
        else:
            name = self.set_enum
            if not name:
                self.report({'ERROR'}, "No bone set to add to; create a new one")
                return {'CANCELLED'}

        # 3) Find or make that group
        group = next((g for g in groups if g.name == name), None)
        if not group:
            group = groups.add()
            group.name = name

        # 4) Add the bones that are missing, in armature order
        present = {b.bone_name for b in group.bones}
        added = [name for name in bone_names if name not in present]
        for name in added:
            group.bones.add().bone_name = name

        if len(bone_names) == 1 and not added:
            self.report({'INFO'}, f"'{bone_names[0]}' already in '{group.name}'")
        elif len(bone_names) > 1:
            skipped = len(bone_names) - len(added)
            self.report({'INFO'}, f"Added {len(added)} bone{'s' if len(added) != 1 else ''} to '{group.name}'"
                                  + (f"; {skipped} already in it" if skipped else ""))

        return {'FINISHED'}

class BONEMANCER_OT_toggle_set_foldout(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_set_foldout"
    bl_label = "Expand Bone Set"
    bl_description = "Expand or collapse this bone set"

    set_name: StringProperty()

    def execute(self, context):
        # Find matching group and flip its flag
        grp = find_set(context.scene, self.set_name)
        if grp:
            grp.show_expanded = not grp.show_expanded
            return {'FINISHED'}
        return {'CANCELLED'}


class BONEMANCER_PG_ImportItem(PropertyGroup):
    """One native bone collection in the import checklist."""
    name: StringProperty(name="Name")
    use: BoolProperty(name="Import", default=True)
    bone_count: IntProperty(name="Bones")
    depth: IntProperty(name="Depth")


def native_collections(arm):
    """(collection, depth) for every bone collection of arm, parents before children."""
    def walk(colls, depth):
        for coll in colls:
            yield coll, depth
            yield from walk(coll.children, depth + 1)
    return list(walk(arm.collections, 0))


class BONEMANCER_OT_import_bone_collections(bpy.types.Operator):
    bl_idname = "bonemancer.import_bone_collections"
    bl_label = "Import Bone Collections"
    bl_description = ("Create a bone set from each ticked bone collection of the rig. "
                      "Sets with the same name gain the missing bones; nothing is removed or reordered")
    bl_options = {'REGISTER', 'UNDO'}

    items: CollectionProperty(type=BONEMANCER_PG_ImportItem, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        arm_obj = get_rig(context.scene)
        if arm_obj is None:
            return False
        if not len(arm_obj.data.collections_all):
            cls.poll_message_set("The rig has no bone collections")
            return False
        return True

    def fill_items(self, arm_obj):
        self.items.clear()
        for coll, depth in native_collections(arm_obj.data):
            item = self.items.add()
            item.name = coll.name
            item.bone_count = len(coll.bones)
            item.depth = depth
            # Empty collections (often just parents of others) start unticked
            item.use = item.bone_count > 0

    def invoke(self, context, event):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        self.fill_items(arm_obj)
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Bone collections to import as bone sets:")
        col = layout.column(align=True)
        for item in self.items:
            row = col.row(align=True)
            if item.depth:
                row.separator(factor=2.0 * item.depth)
            row.prop(item, "use", text=item.name)
            count = row.row()
            count.alignment = 'RIGHT'
            count.label(text=f"{item.bone_count} bone{'' if item.bone_count == 1 else 's'}")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        if not len(self.items):
            # Called without the dialog (scripts): import every non-empty collection
            self.fill_items(arm_obj)

        native = {coll.name: coll for coll in arm_obj.data.collections_all}
        sets_created = bones_added = 0
        for item in self.items:
            coll = native.get(item.name)
            if not item.use or coll is None:
                continue
            bone_set = next((s for s in arm_obj.bonemancer_sets if s.name == coll.name), None)
            if bone_set is None:
                bone_set = arm_obj.bonemancer_sets.add()
                bone_set.name = coll.name
                sets_created += 1
            present = {entry.bone_name for entry in bone_set.bones}
            for bone in coll.bones:
                if bone.name not in present:
                    bone_set.bones.add().bone_name = bone.name
                    bones_added += 1

        self.report({'INFO'}, f"Bone sets created: {sets_created}, bones added: {bones_added}")
        return {'FINISHED'}


# --- Sidebar helpers -----------------------------------------------------

NO_RIG_HINT = "Pick an armature in the Rig panel first."


def text_lines(context, text):
    """text split into lines that fit the sidebar; labels don't wrap on their own."""
    region = getattr(context, "region", None)
    width = region.width if region else 300
    # ui_scale is 0 when Blender runs without a window
    scale = (context.preferences.system.ui_scale if context.preferences else 0) or 1.0
    # About 5.5 px per character at scale 1, less the panel's margins
    return textwrap.wrap(text, max(24, int((width - 40 * scale) / (5.5 * scale))))


def wrapped_label(layout, context, text, icon='NONE'):
    col = layout.column(align=True)
    col.scale_y = 0.8
    for i, line in enumerate(text_lines(context, text)):
        # Indent follow-on lines under the icon
        col.label(text=line, icon=icon if i == 0 else ('BLANK1' if icon != 'NONE' else 'NONE'))
    return col


def hint(layout, context, text, icon='NONE'):
    """Greyed guidance text."""
    wrapped_label(layout, context, text, icon).active = False


def sub_panel(layout, rig, data, prop, *path):
    """A collapsible sub-panel, (header, body); body is None while closed.

    Its open state is data.prop, which saves with the rig. A rig linked without
    an override can't be changed, so there the sidebar keeps the state instead.
    """
    if rig_is_editable(rig):
        return layout.panel_prop(data, prop)
    return layout.panel("_".join(("BONEMANCER", rig.name, prop) + path), default_closed=not getattr(data, prop))


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class BONEMANCER_PT_rig(bpy.types.Panel):
    bl_label = "Rig"
    bl_idname = "BONEMANCER_PT_rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if not any(obj.type == 'ARMATURE' for obj in scene.objects):
            hint(layout, context, "This scene has no armature yet. Add one to get started.")
            layout.operator("object.armature_add", text="Add Armature", icon='ADD')
            return
        layout.prop(scene, "bonemancer_rig", text="Armature")
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, "Pick the armature you want to work on. Clicking one in the viewport picks it too.")
            return
        # Object Properties > Viewport Display > In Front: draw the rig over its meshes
        layout.prop(rig, "show_in_front", text="In Front")


class BONEMANCER_PT_bones(bpy.types.Panel):
    bl_label = "Bones"
    bl_idname = "BONEMANCER_PT_bones"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return
        settings = scene.bonemancer_settings
        layout.template_list(
            "BONEMANCER_UL_bone_picker", "",
            settings, "bone_selection",
            settings, "bone_selection_index",
            rows=6,
        )

        count = len(selected_bone_names(rig))
        row = layout.row()
        row.scale_y = 1.3
        row.enabled = count > 0
        text = f"Add {count} Selected to a Bone Set" if count else "Select Bones to Add Them to a Bone Set"
        row.operator("bonemancer.add_bone_to_set", text=text, icon='ADD').use_selected = True

        # Actions for the highlighted bone, instead of icons on every row
        idx = settings.bone_selection_index
        if 0 <= idx < len(settings.bone_selection):
            name = settings.bone_selection[idx].name
            box = layout.box()
            box.label(text=name, icon='BONE_DATA')
            row = box.row(align=True)
            row.operator("bonemancer.rename_bone", text="Rename", icon='GREASEPENCIL').bone_name = name
            row.operator("bonemancer.show_bone_relations", text="Relations", icon='ORIENTATION_PARENT').bone_name = name
            draw_bone_settings(box, rig, name)


class BONEMANCER_PT_bone_sets(bpy.types.Panel):
    bl_label = "Bone Sets"
    bl_idname = "BONEMANCER_PT_bone_sets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        layout = self.layout
        rig = get_rig(context.scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return
        if not rig.bonemancer_sets:
            hint(layout, context, "Bone Sets keep the bones you use often in one place. "
                                  "Add bones from the Bones panel, or start from the rig's bone collections.")
            layout.operator("bonemancer.import_bone_collections", icon='IMPORT')
            return
        for grp in rig.bonemancer_sets:
            draw_bone_set(context, layout, rig, grp)
        layout.operator("bonemancer.import_bone_collections", icon='IMPORT')


def draw_bone_set(context, layout, rig, grp):
    # A collapsible sub-panel per set; its open state is the set's show_expanded
    header, body = sub_panel(layout, rig, grp, "show_expanded", grp.name)
    header.label(text=grp.name, icon='OUTLINER_COLLECTION')
    count = header.row(align=True)
    count.alignment = 'RIGHT'
    count.active = False
    count.label(text=plural(len(grp.bones), "bone"))
    op = header.operator("bonemancer.toggle_set", text="", emboss=False,
                         icon='HIDE_ON' if set_is_hidden(rig, grp) else 'HIDE_OFF')
    op.set_name = grp.name
    header.operator("bonemancer.remove_set", text="", icon='TRASH', emboss=False).set_name = grp.name
    if body is None:
        return

    if not grp.bones:
        hint(body, context, "Empty. Select bones and use Add Selected in the Bones panel.")
    for entry in grp.bones:
        pb = rig.pose.bones.get(entry.bone_name)
        if not pb:
            # Bone was deleted or renamed outside of Bonemancer
            row = body.row(align=True)
            row.label(text=f"{entry.bone_name} (missing)", icon='ERROR')
            rem = row.operator("bonemancer.remove_bone_from_set", text="", icon='X', emboss=False)
            rem.set_name = grp.name
            rem.bone_name = entry.bone_name
            continue
        draw_set_bone(context, body, rig, grp, entry, pb)


def settings_bone(rig, name):
    """The bone whose Deform option the panels edit: the edit bone in Edit Mode,
    where changes to the plain bone would be lost on leaving it."""
    bones = rig.data.edit_bones if rig.mode == 'EDIT' else rig.data.bones
    return bones.get(name)


def draw_bone_settings(layout, rig, name):
    """Deform, IK Stretch and Lock IK for one bone, bound to Blender's own properties."""
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    bone = settings_bone(rig, name)
    if bone:
        col.prop(bone, "use_deform", text="Deform")
    pb = rig.pose.bones.get(name)
    if pb:
        col.prop(pb, "ik_stretch", text="IK Stretch", slider=True)
        # Property split only labels checkboxes, so lay out the label column by hand
        split = col.split(factor=0.4, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text="Lock IK")
        row = split.row(align=True)
        row.use_property_split = False
        for axis in "xyz":
            row.prop(pb, f"lock_ik_{axis}", text=axis.upper(), toggle=True)


def bone_name_button(layout, name, selected):
    """A left-aligned bone name that selects the bone; drawn pressed while the bone is selected."""
    sub = layout.row(align=True)
    sub.alignment = 'LEFT'
    op = sub.operator("bonemancer.select_bone", text=name, icon='BONE_DATA', emboss=selected, depress=selected)
    op.bone_name = name


def draw_set_bone(context, layout, rig, grp, entry, pb):
    path = (grp.name, entry.bone_name)
    header, body = sub_panel(layout, rig, entry, "show_details", *path)
    bone_name_button(header, entry.bone_name, bone_is_selected(pb))
    hidden = is_hidden(pb)
    eye = header.row(align=True)
    eye.alignment = 'RIGHT'
    op = eye.operator("bonemancer.toggle_bone", text="", icon='HIDE_ON' if hidden else 'HIDE_OFF', emboss=False)
    op.bone_name = entry.bone_name
    if body is None:
        return

    row = body.row(align=True)
    row.operator("bonemancer.rename_bone", text="Rename", icon='GREASEPENCIL').bone_name = entry.bone_name
    rem = row.operator("bonemancer.remove_bone_from_set", text="Remove from Set", icon='REMOVE')
    rem.set_name = grp.name
    rem.bone_name = entry.bone_name
    draw_bone_settings(body, rig, entry.bone_name)

    keys = [key for key in pb.keys() if key != 'constraint_active_index']
    header, props = sub_panel(body, rig, entry, "show_custom_props", *path)
    header.label(text=f"Properties ({len(keys)})")
    if props:
        draw_custom_props(props.column(), rig, pb, keys)

    broken = sum(1 for con in pb.constraints if constraint_problem(con))
    header, cons = sub_panel(body, rig, entry, "show_constraints", *path)
    header.label(text=f"Constraints ({len(pb.constraints)}" + (f", {broken} broken)" if broken else ")"),
                 icon='ERROR' if broken else 'NONE')
    if cons:
        if not pb.constraints:
            hint(cons, context, "This bone has no constraints.")
        else:
            cons.template_list(
                "BONEMANCER_UL_constraints", "",
                pb, "constraints",
                entry, "constraint_index",
                rows=3,
            )


def pose_bone_path(bone_name):
    """Path from the context to the picked rig's pose bone, for Blender's wm.properties_* operators."""
    return f"scene.bonemancer_rig.pose.bones{path_key(bone_name)}"


def draw_custom_props(col, rig, pb, keys):
    """Laid out like Blender's own Custom Properties panel: name, value, Edit (gear), Remove."""
    # Blender refuses to edit properties of linked or overridden data
    editable = rig.library is None and rig.override_library is None
    for key in keys:
        split = col.split(factor=0.4, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text=key, translate=False)
        value = split.row(align=True)
        if hasattr(pb[key], "keys"):
            # Nested groups have no single widget
            value.label(text="(property group)")
        else:
            value.prop(pb, path_key(key), text="")
        if editable:
            buttons = value.row(align=True)
            buttons.alignment = 'RIGHT'
            op = buttons.operator("bonemancer.edit_custom_prop", text="", icon='PREFERENCES', emboss=False)
            op.bone_name = pb.name
            op.prop_name = key
            op = buttons.operator("wm.properties_remove", text="", icon='X', emboss=False)
            op.data_path = pose_bone_path(pb.name)
            op.property_name = key
    col.operator("bonemancer.add_custom_prop", text="Add Property", icon='ADD').bone_name = pb.name

class BONEMANCER_UL_constraints(bpy.types.UIList):
    """Scrollable list of constraints with influence sliders + warning button"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # --- Constraint validity check ---
            problem = constraint_problem(item)
            show_warning = bool(problem)
            tooltip_text = f"Constraint {problem}"

            # Name & influence
            row.label(text=item.name, icon='CONSTRAINT')
            row.prop(item, "influence", text="", slider=True)

            # Warning button on the far right
            if show_warning:
                op = row.operator(
                    "bonemancer.show_constraint_error",
                    text="",
                    icon='ERROR'
                )
                op.constraint_name = item.name
                op.error_message = tooltip_text

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CONSTRAINT')


class BONEMANCER_OT_show_constraint_error(bpy.types.Operator):
    """Show details about an invalid constraint"""
    bl_idname = "bonemancer.show_constraint_error"
    bl_label = "Constraint Error Details"
    bl_options = {'INTERNAL'}

    constraint_name: bpy.props.StringProperty()
    error_message: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"Constraint: {self.constraint_name}", icon='CONSTRAINT_BONE')
        layout.separator()
        layout.label(text="Error:", icon='ERROR')
        layout.label(text=self.error_message, icon='INFO')

    def execute(self, context):
        return {'FINISHED'}


class BONEMANCER_UL_bone_picker(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        rig = get_rig(context.scene)
        if rig and bone_selected_in_viewport(rig, item.name):
            # Selected in the viewport: drawn pressed, like the Bone Sets names
            bone_name_button(layout, item.name, True)
        else:
            layout.label(text=item.name, icon='BONE_DATA')


# --- Rig Check -----------------------------------------------------------
# An on-demand list of problems with the picked rig. Issues hold names only:
# ID pointers would count as users and keep deleted objects in the file.

# check id -> (heading, icon, explanation lines). The ids are stored in
# saved ignores, so they must never change.
RIG_CHECKS = {
    'constraint': (
        "Broken constraints", 'CONSTRAINT_BONE',
        ("A constraint with no target, or aimed at a bone that doesn't exist,",
         "does nothing, so the bone stops following the rest of the rig.",
         "Fix: in Bone Properties > Bone Constraints, set the Target (and",
         "its Bone field), or delete the constraint if it isn't needed."),
    ),
    'driver': (
        "Broken drivers", 'DRIVER',
        ("A driver that can't evaluate leaves its property stuck, so the",
         "slider, corrective shape or switch it controls stops responding.",
         "Fix: right-click the driven property > Open Drivers Editor, then",
         "fix the variable's object and path, or the expression."),
    ),
    'unpaired': (
        "Unpaired left/right bones", 'MOD_MIRROR',
        ("This bone's name marks a side (.L, _R, Left...) but the other side",
         "has no bone of the matching name, so Symmetrize, X-Axis Mirror and",
         "pose flipping skip it.",
         "Fix: add or rename the other side's bone so the names match,",
         "or ignore this if the bone is one-sided on purpose."),
    ),
    'deform_unweighted': (
        "Deform bones without weights", 'GROUP_VERTEX',
        ("This bone has Deform on, but no skinned mesh has weights for it,",
         "so moving it doesn't move the mesh.",
         "Fix: weight paint it (or parent with Automatic Weights again), or",
         "turn off Deform in Bone Properties if it's a control or helper bone."),
    ),
    'nondeform_weighted': (
        "Weighted bones with Deform off", 'MOD_VERTEX_WEIGHT',
        ("A skinned mesh has weights for this bone, but its Deform option is",
         "off, so the weights are ignored and that part of the mesh stays put.",
         "Fix: turn on Deform in Bone Properties, or delete the bone's vertex",
         "group from the mesh if the weights are left over."),
    ),
    'rig_transform': (
        "Unapplied rig transform", 'OBJECT_DATA',
        ("The rig object is rotated or scaled. Constraints, IK and physics can",
         "act oddly, and exporters and retargeting expect a scale of 1.",
         "Fix: in Object Mode select the rig and its meshes, then",
         "Object > Apply > All Transforms. On an animated rig this changes",
         "how the existing animation plays back."),
    ),
    'mesh_no_modifier': (
        "Parented without an Armature modifier", 'MODIFIER',
        ("This mesh is parented to the rig but has no Armature modifier, so it",
         "follows the rig as a whole but doesn't bend with the bones.",
         "Fix: select the mesh, then the rig, and use Parent > With Automatic",
         "Weights, or add an Armature modifier that uses this rig."),
    ),
    'modifier_wrong_rig': (
        "Armature modifier on another rig", 'MOD_ARMATURE',
        ("This mesh is parented to this rig, but its Armature modifier has no",
         "rig set or uses a different one, so posing these bones doesn't bend it.",
         "Fix: in the mesh's Modifier Properties, set the Armature modifier's",
         "Object to this rig."),
    ),
}

# Tolerance for "the rig's rotation and scale are applied"
TRANSFORM_EPSILON = 1e-4

# Shared between the checks of one run (e.g. both weight checks read the
# same weights); emptied at the start of every run.
_check_cache = {}


def constraint_problem(con):
    """What's wrong with a constraint, as the end of a sentence, or '' if it works."""
    if getattr(con, "is_valid", True):
        return ""
    target = getattr(con, "target", None)
    if hasattr(con, "target") and not target:
        return "has no target"
    sub = getattr(con, "subtarget", "")
    bones = getattr(getattr(target, "data", None), "bones", None)
    if sub and bones is not None and sub not in bones:
        return f"targets missing bone '{sub}'"
    return "is not valid"


def find_constraint_issues(context, rig):
    for pb in rig.pose.bones:
        for con in pb.constraints:
            problem = constraint_problem(con)
            if problem:
                yield pb.name, con.name, f"{pb.name}: {con.name} {problem}", ""


def find_unpaired_bones(context, rig):
    names = {b.name for b in rig.data.bones}
    for bone in rig.data.bones:
        other = bpy.utils.flip_name(bone.name)
        if other != bone.name and other not in names:
            yield bone.name, "", f"{bone.name}: no '{other}' on the other side", ""


def skinned_meshes(scene, rig):
    """Meshes the rig deforms through an Armature modifier or armature parenting."""
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if (obj.parent == rig and obj.parent_type == 'ARMATURE') or any(
                m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers):
            yield obj


def weighted_group_names(mesh_obj):
    """Names of mesh_obj's vertex groups that have a non-zero weight on some vertex."""
    names = {g.index: g.name for g in mesh_obj.vertex_groups}
    found = set()
    for vert in mesh_obj.data.vertices:
        for elem in vert.groups:
            if elem.weight > 0.0:
                found.add(elem.group)
        if len(found) == len(names):
            break
    return {names[i] for i in found if i in names}


def rig_weights(context, rig):
    """{bone name: [meshes weighting it]} over the rig's skinned meshes, or None without any."""
    key = ("weights", rig.name)
    if key not in _check_cache:
        meshes = list(skinned_meshes(context.scene, rig))
        weights = None
        if meshes:
            weights = {}
            for mesh in meshes:
                for name in weighted_group_names(mesh):
                    weights.setdefault(name, []).append(mesh.name)
        _check_cache[key] = weights
    return _check_cache[key]


def find_unweighted_deform_bones(context, rig):
    weights = rig_weights(context, rig)
    if weights is None:
        return
    for bone in rig.data.bones:
        if bone.use_deform and bone.name not in weights:
            yield bone.name, "", f"{bone.name}: Deform is on but no skinned mesh has weights for it", ""


def find_weighted_nondeform_bones(context, rig):
    weights = rig_weights(context, rig)
    if weights is None:
        return
    for bone in rig.data.bones:
        if not bone.use_deform and bone.name in weights:
            meshes = ", ".join(weights[bone.name])
            yield bone.name, "", f"{bone.name}: weighted on {meshes} but Deform is off", ""


def driver_owners(scene, rig):
    """(ID holding drivers, object to select) for everything the driver check covers."""
    yield rig, rig
    yield rig.data, rig
    for mesh in skinned_meshes(scene, rig):
        yield mesh, mesh
        if mesh.data.shape_keys:
            yield mesh.data.shape_keys, mesh


def python_drivers_blocked():
    """True when Blender skipped Python expressions because the file's scripts aren't trusted."""
    return bpy.app.autoexec_fail


def _resolves(id_data, path):
    if id_data is None or not path:
        return False
    try:
        id_data.path_resolve(path)
        return True
    except ValueError:
        return False


def driver_problem(owner, fcurve):
    """Why an invalid driver fails, as the end of a sentence."""
    if not _resolves(owner, fcurve.data_path):
        return "drives a property that doesn't exist"
    driver = fcurve.driver
    for var in driver.variables:
        if not var.is_name_valid:
            return f"has a variable with an invalid name '{var.name}'"
        if var.type == 'CONTEXT_PROP':
            continue
        used = var.targets[:2] if var.type in {'ROTATION_DIFF', 'LOC_DIFF'} else var.targets[:1]
        for targ in used:
            if targ.id is None:
                return f"variable '{var.name}' has no object"
            if var.type == 'SINGLE_PROP':
                if not _resolves(targ.id, targ.data_path):
                    return f"variable '{var.name}' reads a missing path '{targ.data_path}'"
            elif targ.bone_target:
                bones = getattr(getattr(targ.id, "data", None), "bones", None)
                if bones is not None and targ.bone_target not in bones:
                    return f"variable '{var.name}' uses missing bone '{targ.bone_target}'"
    if driver.type == 'SCRIPTED':
        return f"expression '{driver.expression}' fails"
    return "is not valid"


_BONE_PATH = re.compile(r'^(?:pose\.)?bones\["((?:[^"\\]|\\.)*)"\]')


def driven_bone(owner, rig, data_path):
    """The rig's bone a driver drives (pose.bones["x"]... on the rig, bones["x"]... on its data), or ''."""
    if owner not in (rig, rig.data):
        return ""
    match = _BONE_PATH.match(data_path)
    if not match or match.group(0).startswith("pose.") != (owner == rig):
        return ""
    name = bpy.utils.unescape_identifier(match.group(1))
    return name if name in rig.data.bones else ""


def find_driver_issues(context, rig):
    results = context.scene.bonemancer_rig_check
    for owner, select_obj in driver_owners(context.scene, rig):
        anim = owner.animation_data
        if not anim:
            continue
        for fc in anim.drivers:
            driver = fc.driver
            if driver.is_valid:
                continue
            if driver.type == 'SCRIPTED' and not driver.is_simple_expression and python_drivers_blocked():
                results.python_drivers += 1
                continue
            bone = driven_bone(owner, rig, fc.data_path)
            label = owner.name if isinstance(owner, bpy.types.Object) else f"{select_obj.name} ({owner.id_type.title()})"
            detail = f"{owner.id_type}:{owner.name}:{fc.data_path}[{fc.array_index}]"
            message = f"{label}: driver on {fc.data_path}[{fc.array_index}] {driver_problem(owner, fc)}"
            yield bone, detail, message, select_obj.name


def find_unapplied_transform(context, rig):
    _loc, rot, scale = rig.matrix_basis.decompose()
    angle = rot.angle
    rotated = min(angle, 2 * math.pi - angle) > TRANSFORM_EPSILON
    scaled = any(abs(s - 1.0) > TRANSFORM_EPSILON for s in scale)
    if rotated or scaled:
        parts = [part for part, on in (("rotation", rotated),
                                       (f"scale ({scale.x:.3g}, {scale.y:.3g}, {scale.z:.3g})", scaled)) if on]
        yield "", "", f"{rig.name}: {' and '.join(parts)} not applied", rig.name


def meshes_parented_to(scene, rig):
    for obj in scene.objects:
        if obj.type == 'MESH' and obj.parent == rig and obj.parent_type in {'OBJECT', 'ARMATURE'}:
            yield obj


def find_meshes_without_modifier(context, rig):
    for obj in meshes_parented_to(context.scene, rig):
        if obj.parent_type == 'OBJECT' and not any(m.type == 'ARMATURE' for m in obj.modifiers):
            yield "", obj.name, f"{obj.name}: parented to the rig without an Armature modifier", obj.name


def find_modifiers_on_other_rigs(context, rig):
    for obj in meshes_parented_to(context.scene, rig):
        mods = [m for m in obj.modifiers if m.type == 'ARMATURE']
        if not mods or any(m.object == rig for m in mods):
            continue
        for m in mods:
            problem = f"uses '{m.object.name}' instead of this rig" if m.object else "has no rig set"
            yield "", f"{obj.name}:{m.name}", f"{obj.name}: Armature modifier '{m.name}' {problem}", obj.name


# --- Re-testing listed issues ---------------------------------------------
# Each drawn row asks whether its issue is fixed. These tests only read what
# is cheap and already up to date; weights are never re-read.

def _driver_owner(id_type, name):
    store = {'OBJECT': bpy.data.objects, 'ARMATURE': bpy.data.armatures, 'KEY': bpy.data.shape_keys}.get(id_type)
    return store.get(name) if store is not None else None


def _driver_fixed(issue):
    id_type, _sep, rest = issue.detail.partition(":")
    owner_name, path_and_index = rest.split(":", 1) if ":" in rest else ("", rest)
    path, _bracket, index = path_and_index.rpartition("[")
    owner = _driver_owner(id_type, owner_name)
    anim = owner.animation_data if owner else None
    try:
        fcurve = anim.drivers.find(path, index=int(index.rstrip("]"))) if anim else None
    except ValueError:
        return False
    return fcurve is None or fcurve.driver.is_valid


def _mesh_fixed(scene, rig, issue):
    obj = bpy.data.objects.get(issue.object_name)
    if obj is None or obj.parent != rig or scene.objects.get(obj.name) != obj:
        return True
    mods = [m for m in obj.modifiers if m.type == 'ARMATURE']
    if issue.check == 'mesh_no_modifier':
        return obj.parent_type != 'OBJECT' or bool(mods)
    mod_name = issue.detail[len(obj.name) + 1:]
    m = obj.modifiers.get(mod_name)
    return m is None or m.type != 'ARMATURE' or any(x.object == rig for x in mods)


def issue_fixed(context, issue):
    """True when a listed issue no longer applies (as far as a cheap re-test can tell)."""
    rig = get_rig(context.scene)
    if rig is None:
        return False
    check_id = issue.check
    if check_id in {'constraint', 'unpaired', 'deform_unweighted', 'nondeform_weighted'}:
        bone = rig.data.bones.get(issue.bone)
        if bone is None:
            return True
        if check_id == 'constraint':
            con = rig.pose.bones[issue.bone].constraints.get(issue.detail)
            return con is None or not constraint_problem(con)
        if check_id == 'unpaired':
            return bpy.utils.flip_name(bone.name) in rig.data.bones
        if check_id == 'deform_unweighted':
            return not bone.use_deform
        return bone.use_deform or not any(
            mesh.vertex_groups.get(bone.name) for mesh in skinned_meshes(context.scene, rig))
    if check_id == 'driver':
        return _driver_fixed(issue)
    if check_id == 'rig_transform':
        return not any(find_unapplied_transform(context, rig))
    if check_id in {'mesh_no_modifier', 'modifier_wrong_rig'}:
        return _mesh_fixed(context.scene, rig, issue)
    return False


def refresh_evaluation(context, rig):
    """Re-evaluate everything the checks read: validity flags only update on evaluation."""
    for owner, _obj in driver_owners(context.scene, rig):
        owner.update_tag()
    context.view_layer.update()


# Checks run in this order, which is also the order results are listed in.
# Each finder takes (context, rig) and yields (bone, detail, message, object_name).
RIG_CHECK_FINDERS = [
    ('constraint', find_constraint_issues),
    ('driver', find_driver_issues),
    ('unpaired', find_unpaired_bones),
    ('deform_unweighted', find_unweighted_deform_bones),
    ('nondeform_weighted', find_weighted_nondeform_bones),
    ('rig_transform', find_unapplied_transform),
    ('mesh_no_modifier', find_meshes_without_modifier),
    ('modifier_wrong_rig', find_modifiers_on_other_rigs),
]


class BONEMANCER_PG_Issue(PropertyGroup):
    check: StringProperty(name="Check")
    bone: StringProperty(name="Bone")
    detail: StringProperty(name="Detail")
    message: StringProperty(name="Message")
    # What Select selects when the issue isn't about a bone
    object_name: StringProperty(name="Object")


class BONEMANCER_PG_IgnoredIssue(PropertyGroup):
    # Matches an issue when all three fields are equal
    check: StringProperty(name="Check", override={'LIBRARY_OVERRIDABLE'})
    bone: StringProperty(name="Bone", override={'LIBRARY_OVERRIDABLE'})
    detail: StringProperty(name="Detail", override={'LIBRARY_OVERRIDABLE'})


class BONEMANCER_PG_RigCheck(PropertyGroup):
    issues: CollectionProperty(type=BONEMANCER_PG_Issue)
    issues_index: IntProperty(default=0)
    has_run: BoolProperty(default=False)
    show_ignored: BoolProperty(
        name="Show Ignored",
        description="Also list the issues ignored on this rig",
        default=False,
    )
    # Python expression drivers that couldn't be checked (scripts not trusted)
    python_drivers: IntProperty(default=0)


def clear_rig_check(scene):
    results = scene.bonemancer_rig_check
    results.issues.clear()
    results.issues_index = 0
    results.has_run = False
    results.python_drivers = 0


def run_rig_check(context, rig):
    """Replace the scene's results with a fresh check of rig; returns the issue count."""
    _check_cache.clear()
    refresh_evaluation(context, rig)
    # The evaluation runs the depsgraph handler, which may have picked the
    # newly active armature (and cleared the results); check that one.
    current = get_rig(context.scene)
    if current is not None and current != rig:
        rig = current
        refresh_evaluation(context, rig)
    results = context.scene.bonemancer_rig_check
    results.issues.clear()
    results.python_drivers = 0
    for check_id, finder in RIG_CHECK_FINDERS:
        for bone, detail, message, object_name in finder(context, rig):
            issue = results.issues.add()
            issue.check = check_id
            issue.bone = bone
            issue.detail = detail
            issue.message = message
            issue.object_name = object_name
    _check_cache.clear()
    results.issues_index = 0
    results.has_run = True
    return len(results.issues)


def ignore_index(rig, issue):
    """Index of the rig's ignore entry matching issue, or -1."""
    if rig is None:
        return -1
    for i, entry in enumerate(rig.bonemancer_ignored_issues):
        if entry.check == issue.check and entry.bone == issue.bone and entry.detail == issue.detail:
            return i
    return -1


def is_ignored(rig, issue):
    return ignore_index(rig, issue) >= 0


def library_ignore(arm_obj, issue):
    """True if issue is ignored in the library file an overridden rig comes from."""
    override = arm_obj.override_library if arm_obj else None
    reference = override.reference if override else None
    return reference is not None and is_ignored(reference, issue)


LINKED_IGNORE_MESSAGE = "Rig is linked from a library; make a library override to ignore issues"
LIBRARY_IGNORE_MESSAGE = "Ignored in the rig's library file; stop ignoring it there"


def visible_issues(scene):
    """The issues that aren't ignored on the picked rig."""
    rig = get_rig(scene)
    return [issue for issue in scene.bonemancer_rig_check.issues if not is_ignored(rig, issue)]


def rename_ignore_entries(arm_obj, old_name, new_name):
    """Keep the rig's ignores matching a renamed bone (its name and its data paths)."""
    old_path, new_path = f"bones{path_key(old_name)}", f"bones{path_key(new_name)}"
    for entry in arm_obj.bonemancer_ignored_issues:
        if entry.bone == old_name:
            entry.bone = new_name
        if old_path in entry.detail:
            entry.detail = entry.detail.replace(old_path, new_path)


def get_issue(scene, index):
    issues = scene.bonemancer_rig_check.issues
    return issues[index] if 0 <= index < len(issues) else None


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


class BONEMANCER_OT_check_rig(bpy.types.Operator):
    bl_idname = "bonemancer.check_rig"
    bl_label = "Check Rig"
    bl_description = ("List problems with the picked rig. Nothing in the rig is changed. "
                      "Check again after fixing things to update the list")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    def execute(self, context):
        rig = get_rig(context.scene)
        if not rig:
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        count = run_rig_check(context, rig)
        self.report({'INFO'}, f"{count} issue{'s' if count != 1 else ''} found" if count else "No issues found")
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_select_issue(bpy.types.Operator):
    bl_idname = "bonemancer.select_issue"
    bl_label = "Select"
    bl_description = "Select the bone or object this issue is about"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        issue = get_issue(context.scene, self.index)
        if not issue:
            return {'CANCELLED'}
        if issue.bone:
            error = select_bone_in_viewport(context, get_rig(context.scene), issue.bone)
        else:
            error = select_object_in_viewport(context, bpy.data.objects.get(issue.object_name))
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}


class BONEMANCER_OT_ignore_issue(bpy.types.Operator):
    bl_idname = "bonemancer.ignore_issue"
    bl_label = "Ignore"
    bl_description = "Stop listing this issue for this rig. Saved with the rig"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    @classmethod
    def description(cls, context, properties):
        rig = get_rig(context.scene)
        return LINKED_IGNORE_MESSAGE if rig and not rig_is_editable(rig) else cls.bl_description

    def execute(self, context):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, self.index)
        if not rig or not issue:
            return {'CANCELLED'}
        if not rig_is_editable(rig):
            self.report({'ERROR'}, LINKED_IGNORE_MESSAGE)
            return {'CANCELLED'}
        if not is_ignored(rig, issue):
            entry = rig.bonemancer_ignored_issues.add()
            entry.check = issue.check
            entry.bone = issue.bone
            entry.detail = issue.detail
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_unignore_issue(bpy.types.Operator):
    bl_idname = "bonemancer.unignore_issue"
    bl_label = "Stop Ignoring"
    bl_description = "List this issue again"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    @classmethod
    def description(cls, context, properties):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, properties.index)
        if rig and not rig_is_editable(rig):
            return LINKED_IGNORE_MESSAGE
        if issue and library_ignore(rig, issue):
            return LIBRARY_IGNORE_MESSAGE
        return cls.bl_description

    def execute(self, context):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, self.index)
        found = ignore_index(rig, issue) if issue else -1
        if found < 0:
            return {'CANCELLED'}
        if not rig_is_editable(rig):
            self.report({'ERROR'}, LINKED_IGNORE_MESSAGE)
            return {'CANCELLED'}
        if library_ignore(rig, issue):
            self.report({'ERROR'}, LIBRARY_IGNORE_MESSAGE)
            return {'CANCELLED'}
        try:
            rig.bonemancer_ignored_issues.remove(found)
        except TypeError:
            # Blender refuses to remove items an override inherited
            self.report({'ERROR'}, "This ignore can't be removed from an overridden rig")
            return {'CANCELLED'}
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_UL_rig_issues(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        rig = get_rig(context.scene)
        fixed = issue_fixed(context, item)
        row = layout.row(align=True)
        row.active = not (fixed or is_ignored(rig, item))
        if fixed:
            row.label(text=f"{item.message} (fixed)", icon='CHECKMARK')
        else:
            row.label(text=item.message, icon=RIG_CHECKS.get(item.check, ("", 'ERROR', ()))[1])

    def filter_items(self, context, data, propname):
        issues = getattr(data, propname)
        if self.filter_name:
            flags = bpy.types.UI_UL_list.filter_items_by_name(
                self.filter_name, self.bitflag_filter_item, issues, "message")
        else:
            flags = [self.bitflag_filter_item] * len(issues)
        if not data.show_ignored:
            rig = get_rig(context.scene)
            flags = [0 if is_ignored(rig, issue) else flag for flag, issue in zip(flags, issues)]
        return flags, []


def issue_explanation(issue):
    """(heading, icon, why, fix) for an issue; fix is "" when the check has none."""
    heading, icon, lines = RIG_CHECKS.get(issue.check, ("Issue", 'ERROR', ()))
    why, _, fix = " ".join(lines).partition(" Fix: ")
    return heading, icon, why, fix


def draw_issue_details(layout, context, rig, issue, index):
    """Why the highlighted issue matters, how to fix it, and what to do with it."""
    heading, icon, why, fix = issue_explanation(issue)
    layout.label(text=heading, icon=icon)
    # The list row is often cut short in the sidebar; show it in full here
    wrapped_label(layout, context, issue.message)
    if issue_fixed(context, issue):
        wrapped_label(layout, context, "This looks fixed now. Check again to update the list.", 'CHECKMARK')
    hint(layout, context, why)
    if fix:
        wrapped_label(layout, context, "Fix: " + fix)
    row = layout.row(align=True)
    row.operator("bonemancer.select_issue", text="Select", icon='RESTRICT_SELECT_OFF').index = index
    ignored = is_ignored(rig, issue)
    toggle = row.row(align=True)
    toggle.enabled = rig_is_editable(rig) and not (ignored and library_ignore(rig, issue))
    if ignored:
        toggle.operator("bonemancer.unignore_issue", icon='HIDE_ON').index = index
    else:
        toggle.operator("bonemancer.ignore_issue", icon='HIDE_OFF').index = index


class BONEMANCER_PT_rig_check(bpy.types.Panel):
    bl_label = "Rig Check"
    bl_idname = "BONEMANCER_PT_rig_check"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header_preset(self, context):
        results = context.scene.bonemancer_rig_check
        if results.has_run and get_rig(context.scene):
            count = len(visible_issues(context.scene))
            self.layout.label(text=str(count), icon='ERROR' if count else 'CHECKMARK')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return

        results = scene.bonemancer_rig_check
        row = layout.row()
        row.scale_y = 1.3
        row.operator("bonemancer.check_rig", text="Check Again" if results.has_run else "Check Rig", icon='VIEWZOOM')
        if not results.has_run:
            hint(layout, context, "Looks for common rigging mistakes, like broken constraints or "
                                  "bones without weights. Nothing in the rig is changed.")
            return
        if results.python_drivers:
            hint(layout, context,
                 f"{plural(results.python_drivers, 'Python driver')} can't be checked while "
                 "Auto Run Python Scripts is off.", 'SCRIPT')

        issues = visible_issues(scene)
        ignored = len(results.issues) - len(issues)
        if issues:
            layout.label(text=f"{plural(len(issues), 'issue')} found", icon='ERROR')
        else:
            layout.label(text="No issues found", icon='CHECKMARK')
        if ignored:
            layout.prop(results, "show_ignored", text=f"Show Ignored ({ignored})")
        if not issues and not (ignored and results.show_ignored):
            return
        layout.template_list(
            "BONEMANCER_UL_rig_issues", "",
            results, "issues",
            results, "issues_index",
            rows=5,
        )
        index = results.issues_index
        issue = get_issue(scene, index)
        if issue and (results.show_ignored or not is_ignored(rig, issue)):
            draw_issue_details(layout.box(), context, rig, issue, index)


classes = [
    # PropertyGroups
    BONEMANCER_PG_SetBone,
    BONEMANCER_PG_BoneSet,
    BONEMANCER_PG_ShapeKey,
    BONEMANCER_PG_ShapeKeyMesh,
    BONEMANCER_PG_PickerBone,
    BONEMANCER_PG_Settings,
    BONEMANCER_PG_ShapeKeyScanner,
    BONEMANCER_PG_ImportItem,
    BONEMANCER_PG_Issue,
    BONEMANCER_PG_IgnoredIssue,
    BONEMANCER_PG_RigCheck,

    # Operators
    BONEMANCER_OT_import_bone_collections,
    BONEMANCER_OT_select_bone,
    BONEMANCER_OT_toggle_bone,
    BONEMANCER_OT_toggle_set,
    BONEMANCER_OT_remove_bone_from_set,
    BONEMANCER_OT_remove_set,
    BONEMANCER_OT_rename_bone,
    BONEMANCER_OT_add_custom_prop,
    BONEMANCER_OT_edit_custom_prop,
    BONEMANCER_OT_add_bone_to_set,
    BONEMANCER_OT_toggle_set_foldout,
    BONEMANCER_OT_show_bone_relations,
    BONEMANCER_OT_scan_shape_keys,
    BONEMANCER_OT_toggle_shape_keyframe,
    BONEMANCER_OT_show_constraint_error,
    BONEMANCER_OT_check_rig,
    BONEMANCER_OT_select_issue,
    BONEMANCER_OT_ignore_issue,
    BONEMANCER_OT_unignore_issue,
    # UILists
    BONEMANCER_UL_constraints,
    BONEMANCER_UL_bone_picker,
    BONEMANCER_UL_shape_key_meshes,
    BONEMANCER_UL_shape_keys,
    BONEMANCER_UL_rig_issues,

    # Panels
    BONEMANCER_PT_rig,
    BONEMANCER_PT_bones,
    BONEMANCER_PT_bone_sets,
    BONEMANCER_PT_rig_check,
    BONEMANCER_PT_shape_keys
]

safe_handlers=[
    on_depsgraph_update,
]


def safely_register_handlers(handlers):
    for handle in handlers:
        if handle not in bpy.app.handlers.depsgraph_update_post:
             bpy.app.handlers.depsgraph_update_post.append(handle)

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


# --- Migration from older versions ---------------------------------------
# Up to 1.0-dev, groups lived on the Scene as rmv2_groups_<armature name> and
# the picked rig was an enum plus rmv2_rmgr_settings.last_armature. Commit
# ec08568 moved groups to the rig as Object.rmv2_groups and the pick to
# Scene.rmv2_rig. Both are copied to the bonemancer_* properties on load and
# the old data is deleted; groups whose armature can't be found are kept.

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
    global _armature_change_from_viewport

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
            _armature_change_from_viewport = True
            try:
                scene.bonemancer_rig = rig
            finally:
                _armature_change_from_viewport = False

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


@persistent
def on_load_post(dummy):
    migrate_legacy_data()


load_post_handlers = [on_load_post]


def _deferred_init():
    # bpy.data is restricted while the add-on registers; finish setup on the
    # first tick so data saved in an already-open file is picked up.
    migrate_legacy_data()
    return None


SCENE_PROPS = ["bonemancer_rig", "bonemancer_settings", "bonemancer_shape_keys", "bonemancer_selected_bone",
               "bonemancer_rig_check"]
OBJECT_PROPS = ["bonemancer_sets", "bonemancer_ignored_issues"]


def register():
    # 1) Register all UI classes
    for cls in classes:
        bpy.utils.register_class(cls)

    # 2) Scene properties: the picked rig, panel state, and the selected-bone mirror
    # A pointer (not a name-based enum) survives renames, reordering and
    # deletion of other armatures, and works with any characters in names.
    bpy.types.Scene.bonemancer_rig = PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        poll=armature_poll,
        update=on_armature_change
    )
    bpy.types.Scene.bonemancer_settings = PointerProperty(
        name="Rig Manager Settings",
        type=BONEMANCER_PG_Settings
    )
    bpy.types.Scene.bonemancer_shape_keys = PointerProperty(
        type=BONEMANCER_PG_ShapeKeyScanner
    )
    # Changes to this string tell the depsgraph handler to redraw the panels
    bpy.types.Scene.bonemancer_selected_bone = StringProperty()
    # Last Rig Check results; names only, so they keep nothing alive
    bpy.types.Scene.bonemancer_rig_check = PointerProperty(type=BONEMANCER_PG_RigCheck)

    # 3) Groups are stored on the rig object, so they follow it through
    # renames and across scenes.
    bpy.types.Object.bonemancer_sets = CollectionProperty(
        type=BONEMANCER_PG_BoneSet,
        override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'}
    )
    # Rig Check issues ignored on this rig; they travel with it like its sets
    bpy.types.Object.bonemancer_ignored_issues = CollectionProperty(
        type=BONEMANCER_PG_IgnoredIssue,
        override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'}
    )

    # 4) Handlers for depsgraph updates (only ours; never clear other add-ons')
    safely_register_handlers(safe_handlers)

    # 5) Load handlers + deferred migration for an already-open file
    for handle in load_post_handlers:
        if handle not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(handle)
    bpy.app.timers.register(_deferred_init, first_interval=0.0)

def unregister():
    # 1) Remove handlers and pending timer
    remove_handlers(safe_handlers + load_post_handlers)
    if bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.unregister(_deferred_init)

    # 2) Unregister UI classes
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"Failed to unregister class {cls.__name__}: {e}")

    # 3) Unregister properties
    unregister_properties(bpy.types.Scene, SCENE_PROPS)
    unregister_properties(bpy.types.Object, OBJECT_PROPS)
    _enum_items_cache.clear()

if __name__ == "__main__":
    register()
