# SPDX-License-Identifier: GPL-3.0-or-later
"""Bone Mancer: Rig Central. Animator control hub for bone sets, custom properties, constraints and shape keys."""

import bpy
import re
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
        description="Expand custom properties panel",
        override={'LIBRARY_OVERRIDABLE'}
    )
    show_constraints: BoolProperty(
        name="Show Constraints",
        default=False,
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
    # Last picked rig; also how versions up to 1.0 remembered the pick (see migration)
    last_armature: PointerProperty(name="Last Active Armature", type=bpy.types.Object)

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
    show_shape_keys:  BoolProperty(
        name="Show Shape Keys", default=False,
        description="Toggle visibility of this mesh’s shape-key list"
    )
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


def scan_shape_keys_for_armature(scene, arm_obj):
    global _suppress_shape_key_update
    settings = scene.bonemancer_shape_keys
    settings.object_groups.clear()

    # Mirroring the current values must not run BONEMANCER_PG_ShapeKey.on_value,
    # which would insert keyframes when auto-keying is on.
    _suppress_shape_key_update = True
    try:
        for obj in scene.objects:
            if obj.type != 'MESH' or not obj.data.shape_keys:
                continue
            if not is_deformed_by(obj, arm_obj):
                continue

            reference = obj.data.shape_keys.reference_key
            grp = settings.object_groups.add()
            grp.object_name = obj.name
            for kb in obj.data.shape_keys.key_blocks:
                if kb == reference:
                    continue
                item = grp.shape_keys.add()
                item.object_name = obj.name
                item.key_name    = kb.name
                item.value       = kb.value
    finally:
        _suppress_shape_key_update = False

class BONEMANCER_OT_scan_shape_keys(bpy.types.Operator):
    bl_idname      = "bonemancer.scan_shape_keys"
    bl_label       = "Scan Rig For Shape Keys"
    bl_description = "Scans and refreshes the shape key list of the selected rig to identify meshes with shape keys"
    bl_options     = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm = get_rig(context.scene)
        if not arm:
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        scan_shape_keys_for_armature(context.scene, arm)
        return {'FINISHED'}

class BONEMANCER_OT_toggle_shape_keys(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_shape_keys"
    bl_label  = "Toggle Shape Keys Visibility"

    index: IntProperty()

    def execute(self, context):
        groups = context.scene.bonemancer_shape_keys.object_groups
        if not 0 <= self.index < len(groups):
            return {'CANCELLED'}
        grp = groups[self.index]
        grp.show_shape_keys = not grp.show_shape_keys
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
        row.prop(item, "object_name", text="", emboss=False, icon='MESH_DATA')
        icon = 'TRIA_DOWN' if item.show_shape_keys else 'TRIA_RIGHT'
        op = row.operator("bonemancer.toggle_shape_keys", text="", emboss=False, icon=icon)
        op.index = index

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
    bl_label      = "Shape Key Scanner"
    bl_idname     = "BONEMANCER_PT_shape_keys"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = 'Bonemancer'
    bl_options    = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout   = self.layout
        settings = context.scene.bonemancer_shape_keys

        layout.operator("bonemancer.scan_shape_keys", icon='FILE_REFRESH')
        layout.template_list(
            "BONEMANCER_UL_shape_key_meshes", "",
            settings, "object_groups",
            settings, "object_groups_index",
            rows=5
        )

        idx = settings.object_groups_index
        if 0 <= idx < len(settings.object_groups):
            grp = settings.object_groups[idx]
            if grp.show_shape_keys:
                layout.separator()
                layout.template_list(
                    "BONEMANCER_UL_shape_keys", "",
                    grp, "shape_keys",
                    grp, "shape_keys_index",
                    rows=5
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

    # 1) Follow the active armature in the viewport (cheap: one lookup)
    view_layer = depsgraph.view_layer
    active = view_layer.objects.active if view_layer else None
    if active and active.type == 'ARMATURE' and scene.bonemancer_rig != active:
        _armature_change_from_viewport = True  # mark source of change
        try:
            scene.bonemancer_rig = active
        finally:
            _armature_change_from_viewport = False

    # 2) Only armature/object updates can change bone names or selection
    if depsgraph.id_type_updated('ARMATURE') or depsgraph.id_type_updated('OBJECT'):
        changed = update_bone_list(scene)
        changed |= sync_selected_bone(scene, view_layer)
        if changed or depsgraph.id_type_updated('ARMATURE'):
            tag_addon_panels(bpy.context)
    elif depsgraph.id_type_updated('KEY'):
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


class BONEMANCER_OT_remove_bone_from_set(bpy.types.Operator):
    bl_idname = "bonemancer.remove_bone_from_set"
    bl_label = "Remove Bone from Set"
    bl_description = "Remove this bone from the bone set (the bone itself is kept)"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        group = find_set(context.scene, self.set_name)
        if not group or not rig_is_editable(get_rig(context.scene)):
            self.report({'WARNING'}, f"Bone set '{self.set_name}' not found")
            return {'CANCELLED'}
        for i, b in enumerate(group.bones):
            if b.bone_name == self.bone_name:
                group.bones.remove(i)
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
        groups = arm.bonemancer_sets
        for i, g in enumerate(groups):
            if g.name == self.set_name:
                groups.remove(i)
                return {'FINISHED'}
        return {'CANCELLED'}

class BONEMANCER_OT_toggle_bone_constraints(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_bone_constraints"
    bl_label = "Toggle Constraints Foldout"
    bl_description = "Expand or collapse the constraints list for this bone"

    bone_name: StringProperty()

    def execute(self, context):
        # Find the bone in any group
        for g in rig_sets(get_rig(context.scene)):
            for b in g.bones:
                if b.bone_name == self.bone_name:
                    b.show_constraints = not b.show_constraints
                    return {"FINISHED"}
        return {"CANCELLED"}


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


class BONEMANCER_OT_add_bone_to_set(bpy.types.Operator):
    bl_idname = "bonemancer.add_bone_to_set"
    bl_label = "Add Bone to Bone Set"
    bl_description = "Add this bone to a new or existing bone set"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty(options={'HIDDEN'})
    set_enum: EnumProperty(name="Bone Set", items=get_set_items)
    create_new: BoolProperty(name="New Bone Set", default=False)
    new_set_name: StringProperty(name="Bone Set Name", default="")

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


    def draw(self, context):
        layout = self.layout
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

        # 4) Add our bone if it's missing
        if self.bone_name not in [b.bone_name for b in group.bones]:
            entry = group.bones.add()
            entry.bone_name = self.bone_name
        else:
            self.report(
                {'INFO'},
                f"'{self.bone_name}' already in '{group.name}'"
            )

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


class BONEMANCER_PT_rig(bpy.types.Panel):
    bl_label = "Bonemancer Rig Central"
    bl_idname = "BONEMANCER_PT_rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene  = context.scene
        armatures = [obj for obj in context.scene.objects if obj.type =='ARMATURE']
        if not armatures:
            #Show warning if no armatures
            layout.label(text="Add an armature", icon='ERROR')
            return  # Skip drawing the bone picker
        else:
            # Armature selector
            layout.prop(scene, "bonemancer_rig", text="Armature")

            # Bone Picker box
            box = layout.box()
            box.label(text="Bone Picker")
            box.template_list(
                    "BONEMANCER_UL_bone_picker",
                    "",
                    scene.bonemancer_settings,
                    "bone_selection",
                    scene.bonemancer_settings,
                    "bone_selection_index",
                    rows=6,
                )

class BONEMANCER_PT_bone_sets(bpy.types.Panel):
    bl_label = "Bone Sets"
    bl_idname = "BONEMANCER_PT_bone_sets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}


    def _draw_bone_buttons(self, row, set_name, bone_name, pbone):

            # Hide/Unhide (state of the armature picked in the panel)
            hidden = is_hidden(pbone)
            icon = 'HIDE_ON' if hidden else 'HIDE_OFF'
            tog = row.operator("bonemancer.toggle_bone", text="", icon=icon, depress=hidden)
            tog.bone_name = bone_name

            # Rename
            edit = row.operator("bonemancer.rename_bone", text="", icon='FILE_TEXT')
            edit.bone_name  = bone_name

            # Remove
            rem = row.operator("bonemancer.remove_bone_from_set", text="", icon='X')
            rem.set_name = set_name
            rem.bone_name  = bone_name

    def draw(self, context):
        armatures = [obj for obj in bpy.context.scene.objects if obj.type =='ARMATURE']
        if not armatures:
             self.layout.label(text="Add or select an armature", icon='ERROR')
        else:
            layout   = self.layout
            scene    = context.scene
            obj      = get_rig(scene)

            # Early exit if no valid armature
            if not obj:
                layout.label(text="Select an armature", icon='ERROR')
                return

            # Fetch groups
            groups = obj.bonemancer_sets

            if not groups:
                layout.label(text="No Bone Sets yet", icon='INFO')
            layout.operator("bonemancer.import_bone_collections", icon='IMPORT')

            # Draw each collection group
            for grp in groups:
                box    = layout.box()
                header = box.row(align=True)

                # Foldout toggle
                icon = 'TRIA_DOWN' if grp.show_expanded else 'TRIA_RIGHT'
                op   = header.operator(
                    "bonemancer.toggle_set_foldout",
                    text="",
                    icon=icon,
                    emboss=False
                )
                op.set_name = grp.name

                # Title + Remove button
                header.label(text=grp.name, icon='OUTLINER_COLLECTION')

                group_icon = 'HIDE_ON' if set_is_hidden(obj, grp) else 'HIDE_OFF'
                hide_show_group = header.operator("bonemancer.toggle_set", text="", icon=group_icon)
                hide_show_group.set_name = grp.name

                remg = header.operator("bonemancer.remove_set", text="", icon='TRASH')
                remg.set_name = grp.name

                # Bones inside group
                if grp.show_expanded:
                    for b in grp.bones:
                        row = box.row(align=True)
                        pb  = obj.pose.bones.get(b.bone_name)
                        if not pb:
                            # Bone was deleted or renamed outside of Bonemancer
                            row.label(text=f"{b.bone_name} (missing)", icon='ERROR')
                            rem = row.operator("bonemancer.remove_bone_from_set", text="", icon='X')
                            rem.set_name = grp.name
                            rem.bone_name  = b.bone_name
                            continue
                        row.label(text=b.bone_name, icon='BONE_DATA')
                        # Highlight if selected in viewport
                        op = row.operator(
                            "bonemancer.select_bone",
                            text="",
                            icon='RESTRICT_SELECT_OFF',
                            depress=bone_is_selected(pb)
                        )
                        op.bone_name = b.bone_name

                        row.prop(
                        b, "show_custom_props",
                        icon = 'RNA',text="")
                        icon_c = 'CONSTRAINT_BONE'
                        togc   = row.operator(
                            "bonemancer.toggle_bone_constraints",
                            text="",
                        icon=icon_c,
                            depress=b.show_constraints)
                        togc.bone_name = b.bone_name
                        self._draw_bone_buttons(row, grp.name, b.bone_name, pb)
                         # CUSTOM PROPLS FOLDOUT
                        if b.show_custom_props:
                            cbox = box.box().column()
                            cbox.label(text="Custom Props:", icon='RNA')
                            # Live‐draw every custom property in its native widget
                            for key in pb.keys():
                                if key != 'constraint_active_index':
                                    val = pb[key]
                                    # Nested groups have no single widget
                                    if hasattr(val, "keys"):
                                        cbox.label(text=f"{key} (property group)")
                                        continue
                                    # 1) Arrays → grouped fields
                                    if isinstance(val, (list, tuple)):
                                        cbox.label(text=key)
                                        row = cbox.row(align=True)
                                        for i in range(len(val)):
                                            row.prop(pb, f'{path_key(key)}[{i}]', text=str(i))
                                        continue

                                    # 2–4) All other types → let Blender pick the widget
                                    row = cbox.row()
                                    row.prop(pb, path_key(key), text=key)

                            # “Add Property” button stays the same
                            op = cbox.operator("bonemancer.add_custom_prop", text="Add Property", icon='ADD')
                            op.bone_name = b.bone_name


                        # Expanded Constraints
                        if b.show_constraints:
                            cbox = box.box().column()
                            cbox.label(
                                text=f"Constraints on {b.bone_name}",
                                icon='CONSTRAINT_BONE'
                                )

                            if not pb.constraints:
                                cbox.label(text="(no constraints)", icon='INFO')
                            else:
                                 cbox.template_list(
                                    "BONEMANCER_UL_constraints",
                                    "",                        # custom list_id
                                    pb,                        # data: PoseBone
                                    "constraints",             # its CollectionProperty
                                    b,                         # active_data: BONEMANCER_PG_SetBone PG
                                    "constraint_index",        # its index IntProperty
                                    rows=4
                                )

class BONEMANCER_UL_constraints(bpy.types.UIList):
    """Scrollable list of constraints with influence sliders + warning button"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # --- Constraint validity check ---
            show_warning = False
            tooltip_text = ""

            if hasattr(item, "is_valid") and not item.is_valid:
                show_warning = True
                tooltip_text = "Constraint is not valid"
            else:
                if hasattr(item, "target") and not item.target:
                    show_warning = True
                    tooltip_text = "Missing target object"
                if (
                    hasattr(item, "subtarget")
                    and getattr(item, "target", None)
                    and item.subtarget
                ):
                    arm = getattr(item.target, "data", None)
                    if getattr(arm, "bones", None) and item.subtarget not in arm.bones:
                        show_warning = True
                        tooltip_text = f"Bone '{item.subtarget}' not found on target"

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
        row = layout.row(align=True)
        row.label(text=item.name, icon='BONE_DATA')
        row.separator(factor=1.0)

        # Add to Collection
        op = row.operator(
            "bonemancer.add_bone_to_set",
            text="",
            icon='ADD'
        )
        op.bone_name = item.name

        op = row.operator(
            "bonemancer.rename_bone",                 #     Operator to execute
            text="",                                  #     No text—just an icon
            icon='FILE_TEXT'                               #     Info icon for “relations”
        )
        op.bone_name = item.name
        op = row.operator(
            "bonemancer.show_bone_relations",                 #     Operator to execute
            text="",                                  #     No text—just an icon
            icon='INFO'                               #     Info icon for “relations”
        )
        op.bone_name = item.name


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

    # Operators
    BONEMANCER_OT_import_bone_collections,
    BONEMANCER_OT_select_bone,
    BONEMANCER_OT_toggle_bone,
    BONEMANCER_OT_toggle_set,
    BONEMANCER_OT_remove_bone_from_set,
    BONEMANCER_OT_remove_set,
    BONEMANCER_OT_rename_bone,
    BONEMANCER_OT_toggle_bone_constraints,
    BONEMANCER_OT_add_custom_prop,
    BONEMANCER_OT_add_bone_to_set,
    BONEMANCER_OT_toggle_set_foldout,
    BONEMANCER_OT_show_bone_relations,
    BONEMANCER_OT_scan_shape_keys,
    BONEMANCER_OT_toggle_shape_keys,
    BONEMANCER_OT_toggle_shape_keyframe,
    BONEMANCER_OT_show_constraint_error,
    # UILists
    BONEMANCER_UL_constraints,
    BONEMANCER_UL_bone_picker,
    BONEMANCER_UL_shape_key_meshes,
    BONEMANCER_UL_shape_keys,

    # Panels
    BONEMANCER_PT_rig,
    BONEMANCER_PT_bone_sets,
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

    # Bail if invalid
    if not arm_obj:
        update_bone_list(scene)
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

    scene.bonemancer_settings.last_armature = arm_obj


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


SCENE_PROPS = ["bonemancer_rig", "bonemancer_settings", "bonemancer_shape_keys", "bonemancer_selected_bone"]
OBJECT_PROPS = ["bonemancer_sets"]


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

    # 3) Groups are stored on the rig object, so they follow it through
    # renames and across scenes.
    bpy.types.Object.bonemancer_sets = CollectionProperty(
        type=BONEMANCER_PG_BoneSet,
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
