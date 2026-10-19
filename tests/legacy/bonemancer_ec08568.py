

bl_info = {
    "name":        "Bone Mancer: Rig Central",
    "author":      "Laurent",
    "version":     (1, 1, 0),
    "blender":     (4, 1, 0),
    "location":    "View3D > Sidebar > Bonemancer",
    "description": "Organize bones into collections with per-collection & per-bone hide/show icons",
    "category":    "Rigging"
}

import bpy
import re
from bpy.app.handlers import persistent
from bpy.props import StringProperty, IntProperty,FloatProperty,BoolProperty, CollectionProperty, EnumProperty, PointerProperty
from bpy.types import UIList, Operator, Panel, PropertyGroup

mirrored_drivers = set()
_armature_change_from_viewport = False
_suppress_shape_key_update = False
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
    obj = scene.rmv2_rig
    return obj if obj and obj.type == 'ARMATURE' else None

def rig_groups(arm_obj):
    return arm_obj.rmv2_groups if arm_obj else []

def rig_is_editable(arm_obj):
    """False for rigs linked from a library without a library override."""
    return arm_obj is not None and (arm_obj.library is None or arm_obj.override_library is not None)

def armature_poll(self, obj):
    return obj.type == 'ARMATURE' and bpy.context.scene in obj.users_scene


class RMV2_CustomPropItem(PropertyGroup):
        name: StringProperty(name="Property Name")

class BoneItem(PropertyGroup):
    name: StringProperty()
    show_constraints: BoolProperty(default=False)
    is_selected: BoolProperty(default=False)


class RMV2_Bone(PropertyGroup):

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

        constraint_index: IntProperty(default=0)
        custom_props_display: bpy.props.CollectionProperty(type=RMV2_CustomPropItem)
        custom_props_index: bpy.props.IntProperty()

        is_selected: BoolProperty(name= "Is bone selected",

        default=False,
        description="Marks if a bone is selected or not"
        )

class RMV2_RMGR_ArmatureItem(bpy.types.PropertyGroup):
    name: StringProperty()
    object_ref: PointerProperty(name="Armature", type=bpy.types.Object)

class ArmatureGroup(PropertyGroup):
    armature_name: StringProperty(
        name="Armature Name",
        description="Name of the armature this group belongs to"
    )


class RMV2_BoneSelectionItem(PropertyGroup):
        """Holds a single bone name for selection."""
        name: StringProperty(name="Bone Name")

class RMV2_Group(PropertyGroup):
        # Overridable so groups can be edited on library-overridden rigs
        group_name: bpy.props.StringProperty(name="Group Name", override={'LIBRARY_OVERRIDABLE'})
        bones: bpy.props.CollectionProperty(type=RMV2_Bone, override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'})
        bone_index: bpy.props.IntProperty(default=0)
        show_bones: bpy.props.BoolProperty(default=True)
        show_expanded: bpy.props.BoolProperty(
        name="Expand Group",
        description="Toggle bone list visibility",
        default=False,
        override={'LIBRARY_OVERRIDABLE'})


class RMV2_RmgrSettings(PropertyGroup):
        auto_load: BoolProperty(
        name="Auto Load",
        description="Automatically load last rig on file open",
        default=False
        )
        # The new bone-pick list
        bone_selection: CollectionProperty(type=RMV2_BoneSelectionItem)
        bone_selection_index: IntProperty(name="Index", default=0)
        # Armature the bone_selection list was built from (for rename tracking)
        bone_list_owner: PointerProperty(type=bpy.types.Object)
        groups: CollectionProperty(type=RMV2_Group)
        groups_index: IntProperty(name="Group Index", default=0)

        #armature list properties
        armature_items: CollectionProperty(type=RMV2_RMGR_ArmatureItem)
        armature_index: IntProperty(default=0)
        last_armature: PointerProperty(name="Last Active Armature", type=bpy.types.Object)

class ShapeKeyItem(bpy.types.PropertyGroup):
    object_name: StringProperty(name="Mesh Object Name")
    key_name:    StringProperty(name="Shape Key Name")
    value: FloatProperty(
        name="Value", default=0.0, min=0.0, max=1.0, subtype='FACTOR',
        update=lambda self, ctx: ShapeKeyItem.on_value(self, ctx),
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

class ObjectShapeKeyGroup(bpy.types.PropertyGroup):
    object_name:      StringProperty(name="Mesh Object Name")
    show_shape_keys:  BoolProperty(
        name="Show Shape Keys", default=False,
        description="Toggle visibility of this mesh’s shape-key list"
    )
    shape_keys:       CollectionProperty(type=ShapeKeyItem)
    shape_keys_index: IntProperty(default=0)

class RMV2_ShapeKeyScannerSettings(bpy.types.PropertyGroup):
    object_groups:       CollectionProperty(type=ObjectShapeKeyGroup)
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
    settings = scene.rmv2_shape_key_scanner
    settings.object_groups.clear()

    # Mirroring the current values must not run ShapeKeyItem.on_value,
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

class RMV2_OT_ScanShapeKeys(bpy.types.Operator):
    bl_idname      = "rmv2.scan_shape_keys"
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

class RMV2_OT_ToggleShapeKeys(bpy.types.Operator):
    bl_idname = "rmv2.toggle_shape_keys"
    bl_label  = "Toggle Shape Keys Visibility"

    index: IntProperty()

    def execute(self, context):
        groups = context.scene.rmv2_shape_key_scanner.object_groups
        if not 0 <= self.index < len(groups):
            return {'CANCELLED'}
        grp = groups[self.index]
        grp.show_shape_keys = not grp.show_shape_keys
        return {'FINISHED'}

def keyframes_at(fcurve, frame):
    # Same tolerance Blender uses when looking up a keyframe on a frame
    return [kp for kp in fcurve.keyframe_points if abs(kp.co.x - frame) < 0.01]

class RMV2_OT_KeyShapeValue(bpy.types.Operator):
    bl_idname = "rmv2.key_shape_value"
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
class RMV2_UL_ObjectGroupList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "object_name", text="", emboss=False, icon='MESH_DATA')
        icon = 'TRIA_DOWN' if item.show_shape_keys else 'TRIA_RIGHT'
        op = row.operator("rmv2.toggle_shape_keys", text="", emboss=False, icon=icon)
        op.index = index

class RMV2_UL_ShapeKeyList(bpy.types.UIList):
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

        op = row.operator("rmv2.key_shape_value", text="", icon=icon)
        op.object_name    = item.object_name
        op.shape_key_name = item.key_name

def tag_addon_panels(context):
    # Ensure our 3D View sidebar panels redraw
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class RMV2_PT_ShapeKeyScanner(bpy.types.Panel):
    bl_label      = "Shape Key Scanner"
    bl_idname     = "RMV2_PT_ShapeKeyScanner"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = 'Bonemancer'
    bl_options    = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout   = self.layout
        settings = context.scene.rmv2_shape_key_scanner

        layout.operator("rmv2.scan_shape_keys", icon='FILE_REFRESH')
        layout.template_list(
            "RMV2_UL_ObjectGroupList", "",
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
                    "RMV2_UL_ShapeKeyList", "",
                    grp, "shape_keys",
                    grp, "shape_keys_index",
                    rows=5
                )

class RMV2_OT_ShowBoneRelations(bpy.types.Operator):
    bl_idname = "bi.show_bone_relations"
    bl_label = "Show Bone Relations"
    bl_description = "Display the selected bone’s parent and children in a dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    bone_name: StringProperty(name="Bone Name")  # Passed from UIList row

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return (
            get_rig(scene) is not None and
            len(scene.rmv2_rmgr_settings.bone_selection) > 0
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

class SINGLE_BONES_ACTIONS():
    ADD_BONE=1
    DELETE=2
    RENAME=3
    HIDE=4
    SHOW=5
    SELECT=6


def sanitize_name(name):
    safe = re.sub(r'\W', '_', name)
    return '_' + safe if re.match(r'^\d', safe) else safe

def safe_register_prop(base_type, prop_name, prop_def):
    if not hasattr(base_type, prop_name):
        setattr(base_type, prop_name, prop_def)

def safe_unregister_prop(base_type, prop_name):
    if hasattr(base_type, prop_name):
        delattr(base_type, prop_name)

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


def find_group(scene, group_name):
    return next((g for g in rig_groups(get_rig(scene)) if g.group_name == group_name), None)


def rename_group_entries(arm_obj, old_name, new_name):
    for grp in rig_groups(arm_obj):
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


def duplicate_driver(fcurve, target_id, target_path):
    """Copy one driver F-curve onto another data block."""
    # Create new fcurve on the target ID/data_path
    new_fcu = target_id.driver_add(target_path).driver
    src_drv = fcurve.driver

    # Copy driver type and expression
    new_fcu.type = src_drv.type
    new_fcu.expression = src_drv.expression

    # Copy each variable
    for src_var in src_drv.variables:
        dst_var = new_fcu.variables.new()
        dst_var.name = src_var.name
        dst_var.type = src_var.type
        # Copy targets
        dst_var.targets.clear()
        for t in src_var.targets:
            new_t = dst_var.targets.new()
            new_t.id = t.id
            new_t.data_path = t.data_path
            new_t.transform_type = t.transform_type
            new_t.bone_target = t.bone_target

    # Copy modifiers (if any)
    for mod in src_drv.modifiers:
        new_mod = new_fcu.modifiers.new(type=mod.type)
        # If it’s a generator or scripted expr, copy relevant settings
        for prop in mod.bl_rna.properties:
            if prop.identifier in {"mode", "use_additive"}:
                setattr(new_mod, prop.identifier, getattr(mod, prop.identifier))

def _armature_bone_names(arm_obj):
    bones = arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones
    return [b.name for b in bones]

def update_bone_list(scene):
    """Rebuild the bone picker for the picked rig; returns True if it changed."""
    settings = scene.rmv2_rmgr_settings

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
                rename_group_entries(arm_obj, old_name, new_name)

    settings.bone_selection.clear()
    for name in names:
        item = settings.bone_selection.add()
        item.name = name

    settings.bone_list_owner = arm_obj
    settings.bone_selection_index = min(settings.bone_selection_index, max(len(names) - 1, 0))
    return True


def sync_selected_bone(scene, view_layer):
    """Mirror the first selected pose bone into scene.rmv2_selected_bone; True if it changed."""
    ob = view_layer.objects.active if view_layer else None
    if not (ob and ob.type == 'ARMATURE' and ob.mode == 'POSE'):
        return False
    selected = next((pb.name for pb in ob.pose.bones if bone_is_selected(pb)), "")
    if scene.rmv2_selected_bone == selected:
        return False
    scene.rmv2_selected_bone = selected
    return True


@persistent
def rmv2_depsgraph_handler(scene, depsgraph):
    """Single depsgraph handler: viewport → picker sync, bone list and selection refresh."""
    global _armature_change_from_viewport

    screen = bpy.context.screen
    if screen and screen.is_animation_playing:
        return

    # 1) Follow the active armature in the viewport (cheap: one lookup)
    view_layer = depsgraph.view_layer
    active = view_layer.objects.active if view_layer else None
    if active and active.type == 'ARMATURE' and scene.rmv2_rig != active:
        _armature_change_from_viewport = True  # mark source of change
        try:
            scene.rmv2_rig = active
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


def get_bones(self, context):
    obj = get_rig(context.scene)
    return keep_enum_items("bones", [(b.name, b.name, "") for b in obj.data.bones] if obj else [])


def get_group_items(self, context):
    groups = rig_groups(get_rig(context.scene))
    return keep_enum_items("groups", [(g.group_name, g.group_name, "") for g in groups])


def get_constraint_bone_items(self, context):
    items = []
    obj = context.object
    if not obj or obj.type != 'ARMATURE' or not obj.pose:
        return items

    for pb in obj.pose.bones:
        if pb.constraints:
            items.append((pb.name, pb.name, "Bone with constraints"))

    return keep_enum_items("constraint_bone_items", items)
def get_all_driver_sources():
    """
    Returns a list of (name, type) tuples for every datablock
    that has drivers in the current blend file.
    """
    sources = []

    # Check objects
    for obj in bpy.data.objects:
        ad = obj.animation_data
        if ad and ad.drivers:
            sources.append((obj.name, "Object"))

    # Check materials
    for mat in bpy.data.materials:
        ad = mat.animation_data
        if ad and ad.drivers:
            sources.append((mat.name, "Material"))

    # Check node trees (shaders, compositing, geometry)
    for nt in (*bpy.data.node_groups, *bpy.data.worlds):
        ad = nt.animation_data
        if ad and ad.drivers:
            sources.append((nt.name, "NodeTree"))

    return sources

def get_all_driver_sources_two():
    """
    Returns a list of dicts for every datablock with drivers.
    Each dict contains:
      - name: datablock name
      - type: datablock type (Object, Material, etc.)
      - drivers: list of drivers, each with data_path and variables
    """
    sources = []

    collections = [
        (bpy.data.objects,  "Object"),
        (bpy.data.materials, "Material"),
        (bpy.data.worlds,    "World"),
        (bpy.data.node_groups, "NodeTree"),
    ]

    for data_coll, label in collections:
        for db in data_coll:
            ad = db.animation_data
            if not (ad and ad.drivers):
                continue

            drivers = []
            for fcurve in ad.drivers:
                drv = {
                    "data_path": fcurve.data_path,
                    "variables": []
                }

                for var in fcurve.driver.variables:
                    v = {
                        "name": var.name,
                        "type": var.type,
                        "targets": []
                    }
                    for targ in var.targets:
                        id_name = targ.id.name if targ.id else "None"
                        v["targets"].append({
                            "id_name": id_name,
                            "data_path": targ.data_path
                        })
                    drv["variables"].append(v)

                drivers.append(drv)

            sources.append({
                "name": db.name,
                "type": label,
                "drivers": drivers
            })

    return sources

def get_object_driver_info():
    """
    Returns a list of (object_name, data_path) for every driver
    found on objects in the current blend file.
    """
    info = []

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if not (ad and ad.drivers):
            continue

        for fcurve in ad.drivers:
            info.append((obj.name, fcurve.data_path))

    return info

def get_object_driver_variable_paths():
    """
    Returns a list of (object_name, variable_target_path) for every
    driver variable target found on objects in the current blend file.
    """
    info = []

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if not (ad and ad.drivers):
            continue

        for fcurve in ad.drivers:
            drv = fcurve.driver
            for var in drv.variables:
                for targ in var.targets:
                    # targ.data_path is the path inside the variable context
                    info.append((obj.name, targ.data_path))

    return info

def get_constraint_bones(self, context):
    obj = get_rig(context.scene)
    return keep_enum_items("constraint_bones", [(pb.name, pb.name, "") for pb in obj.pose.bones if pb.constraints] if obj else [])

class RMV2_OT_AddToGroup(bpy.types.Operator):
    """Add the bone highlighted in the Bone Picker to a collection"""
    bl_idname = "rmv2.add_to_group"
    bl_label = "Add to Collection"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[('NEW', "New Group", ""), ('EXIST', "Existing Group", "")],
        default='NEW'
    )
    new_name: bpy.props.StringProperty(name="Group Name", default="Group")
    existing: bpy.props.EnumProperty(name="Group", items=get_group_items)

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)
        if self.mode == 'NEW':
            layout.prop(self, "new_name")
        else:
            layout.prop(self, "existing")

    def execute(self, context):
        sc = context.scene
        arm = get_rig(sc)
        settings = sc.rmv2_rmgr_settings
        idx = settings.bone_selection_index
        bone = settings.bone_selection[idx].name if 0 <= idx < len(settings.bone_selection) else ""
        if not bone:
            self.report({'ERROR'}, "No bone selected in the Bone Picker")
            return {'CANCELLED'}
        if not rig_is_editable(arm):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}

        groups = arm.rmv2_groups
        name = (self.new_name if self.mode == 'NEW' else self.existing).strip()
        if not name:
            self.report({'ERROR'}, "Group name cannot be empty")
            return {'CANCELLED'}
        group = next((g for g in groups if g.group_name == name), None)
        if not group:
            group = groups.add()
            group.group_name = name
        if bone not in [b.bone_name for b in group.bones]:
            entry = group.bones.add()
            entry.bone_name = bone
        return {'FINISHED'}


class RMV2_OT_SelectBone(bpy.types.Operator):
    bl_idname = "rmv2.select_bone"
    bl_label  = "Select Bone"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = get_rig(context.scene)
        if not obj:
            self.report({'WARNING'}, "No valid armature")
            return {'CANCELLED'}
        if context.view_layer.objects.get(obj.name) != obj:
            self.report({'WARNING'}, f"'{obj.name}' is not in the current view layer")
            return {'CANCELLED'}
        if not rig_is_editable(obj):
            self.report({'WARNING'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}

        # pick our bone
        pb = obj.pose.bones.get(self.bone_name)
        if not pb:
            self.report({'WARNING'}, f"Bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        # ensure armature visible
        obj.hide_set(False)
        obj.hide_viewport = False

        # Object mode → Pose mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')

        # deselect all bones
        for p in obj.pose.bones:
            set_bone_selected(p, False)

        # unhide & select target
        set_hidden(pb, False)
        set_bone_selected(pb, True)
        obj.data.bones.active = pb.bone
        return {'FINISHED'}

class RMV2_OT_ToggleBone(bpy.types.Operator):
    bl_idname = "rmv2.toggle_bone"
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


def group_is_hidden(arm_obj, group):
    pbs = [arm_obj.pose.bones.get(b.bone_name) for b in group.bones]
    pbs = [pb for pb in pbs if pb]
    return bool(pbs) and all(is_hidden(pb) for pb in pbs)


class RMV2_OT_ToggleGroup(bpy.types.Operator):
    bl_idname = "rmv2.toggle_group"
    bl_label = "Toggle Group"
    bl_description = "Hide every bone in this collection, or show them all if all are hidden"
    bl_options = {'REGISTER', 'UNDO'}
    group_name: bpy.props.StringProperty()

    def execute(self, context):
        sc = context.scene
        obj = get_rig(sc)
        group = find_group(sc, self.group_name)
        if not rig_is_editable(obj) or not group:
            self.report({'WARNING'}, f"Group '{self.group_name}' not found")
            return {'CANCELLED'}
        # Mixed visibility hides all; only a fully hidden group is shown again
        hide = not group_is_hidden(obj, group)
        for b in group.bones:
            set_hidden(obj.pose.bones.get(b.bone_name), hide)
        return {'FINISHED'}


class RMV2_OT_RemoveBoneFromGroup(bpy.types.Operator):
    bl_idname = "rmv2.remove_bone"
    bl_label = "Remove Bone"
    bl_options = {'REGISTER', 'UNDO'}
    group_name: bpy.props.StringProperty()
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        group = find_group(context.scene, self.group_name)
        if not group or not rig_is_editable(get_rig(context.scene)):
            self.report({'WARNING'}, f"Group '{self.group_name}' not found")
            return {'CANCELLED'}
        for i, b in enumerate(group.bones):
            if b.bone_name == self.bone_name:
                group.bones.remove(i)
                break
        return {'FINISHED'}


class RMV2_OT_RemoveGroup(bpy.types.Operator):
    bl_idname = "rmv2.remove_group"
    bl_label = "Remove Group"
    bl_description = "Delete this collection (the bones themselves are kept)"
    bl_options = {'REGISTER', 'UNDO'}
    group_name: bpy.props.StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        arm = get_rig(context.scene)
        if not rig_is_editable(arm):
            return {'CANCELLED'}
        groups = arm.rmv2_groups
        for i, g in enumerate(groups):
            if g.group_name == self.group_name:
                groups.remove(i)
                return {'FINISHED'}
        return {'CANCELLED'}

class RMV2_OT_ToggleBoneConstraints(bpy.types.Operator):
    bl_idname = "rmv2.toggle_constraints_bone"
    bl_label = "Toggle Constraints Foldout"
    bl_description = "Expand or collapse the constraints list for this bone"

    bone_name: StringProperty()

    def execute(self, context):
        # Find the bone in any group
        for g in rig_groups(get_rig(context.scene)):
            for b in g.bones:
                if b.bone_name == self.bone_name:
                    b.show_constraints = not b.show_constraints
                    return {"FINISHED"}
        return {"CANCELLED"}


class RMV2_OT_RenameBone(bpy.types.Operator):
    bl_idname = "rmv2.rename_bone"
    bl_label = "Rename Bone"
    bl_options = {'REGISTER', 'UNDO'}

    group_name: StringProperty()
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
        rename_group_entries(arm_obj, self.bone_name, new_name)
        update_driver_variable_paths(arm_obj, self.bone_name, new_name)
        update_bone_list(context.scene)
        arm_obj.update_tag()

        return {'FINISHED'}

    def check(self, context):
        # Live-preview on any property change
        self.update_preview()
        return True


class RMV2_OT_AddCustomProperty(bpy.types.Operator):
    bl_idname = "rmv2.add_custom_prop"
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


class RMV2_OT_add_bone_to_collection(bpy.types.Operator):
    bl_idname = "rmv2.add_bone_to_collection"
    bl_label = "Add Bone to Collection"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty(options={'HIDDEN'})
    group_enum: EnumProperty(name="Collection", items=get_group_items)
    create_new: BoolProperty(name="Create New?", default=False)
    new_group_name: StringProperty(name="New Collection Name", default="")

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
            layout.prop(self, "new_group_name", text="Name")
        else:
            layout.prop(self, "group_enum", text="Collection")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}

        # 1) Groups live on the rig object itself
        groups = arm_obj.rmv2_groups

        # 2) Figure out which group to target
        if self.create_new:
            name = self.new_group_name.strip()
            if not name:
                self.report({'ERROR'}, "New collection name cannot be empty")
                return {'CANCELLED'}
        else:
            name = self.group_enum
            if not name:
                self.report({'ERROR'}, "No collection to add to; create a new one")
                return {'CANCELLED'}

        # 3) Find or make that group
        group = next((g for g in groups if g.group_name == name), None)
        if not group:
            group = groups.add()
            group.group_name = name

        # 4) Add our bone if it's missing
        if self.bone_name not in [b.bone_name for b in group.bones]:
            entry = group.bones.add()
            entry.bone_name = self.bone_name
        else:
            self.report(
                {'INFO'},
                f"'{self.bone_name}' already in '{group.group_name}'"
            )

        return {'FINISHED'}

class RMV2_OT_ToggleGroupFoldout(bpy.types.Operator):
    bl_idname = "rmv2.toggle_group_foldout"
    bl_label = "Toggle Group Foldout"
    bl_description = "Expand or collapse this bone group in the UI"

    group_name: bpy.props.StringProperty()

    def execute(self, context):
        # Find matching group and flip its flag
        grp = find_group(context.scene, self.group_name)
        if grp:
            grp.show_expanded = not grp.show_expanded
            return {'FINISHED'}
        return {'CANCELLED'}

class RMV2_PT_ArmaturePicker(bpy.types.Panel):
    bl_label = "Bonemancer Rig Central"
    bl_idname = "RMV2_PT_ArmaturePicker"
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
            layout.prop(scene, "rmv2_rig", text="Armature")

            # Bone Picker box
            box = layout.box()
            box.label(text="Bone Picker")
            box.template_list(
                    "RMV_2_BONE_UL_selection_list",
                    "",
                    scene.rmv2_rmgr_settings,
                    "bone_selection",
                    scene.rmv2_rmgr_settings,
                    "bone_selection_index",
                    rows=6,
                )

class RMV2_PT_Collections(bpy.types.Panel):
    bl_label = "Collections"
    bl_idname = "RMV2_PT_Collections"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}


    def _draw_bone_buttons(self, row, group_name, bone_name, pbone):

            # Hide/Unhide (state of the armature picked in the panel)
            hidden = is_hidden(pbone)
            icon = 'HIDE_ON' if hidden else 'HIDE_OFF'
            tog = row.operator("rmv2.toggle_bone", text="", icon=icon, depress=hidden)
            tog.bone_name = bone_name

            # Rename
            edit = row.operator("rmv2.rename_bone", text="", icon='FILE_TEXT')
            edit.group_name = group_name
            edit.bone_name  = bone_name

            # Remove
            rem = row.operator("rmv2.remove_bone", text="", icon='X')
            rem.group_name = group_name
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
            groups = obj.rmv2_groups

            if not groups:
                layout.label(text="(no collections)", icon='INFO')
                return

            # Draw each collection group
            for grp in groups:
                box    = layout.box()
                header = box.row(align=True)

                # Foldout toggle
                icon = 'TRIA_DOWN' if grp.show_expanded else 'TRIA_RIGHT'
                op   = header.operator(
                    "rmv2.toggle_group_foldout",
                    text="",
                    icon=icon,
                    emboss=False
                )
                op.group_name = grp.group_name

                # Title + Remove button
                header.label(text=grp.group_name, icon='OUTLINER_COLLECTION')

                group_icon = 'HIDE_ON' if group_is_hidden(obj, grp) else 'HIDE_OFF'
                hide_show_group = header.operator("rmv2.toggle_group", text="", icon=group_icon)
                hide_show_group.group_name = grp.group_name

                remg = header.operator("rmv2.remove_group", text="", icon='TRASH')
                remg.group_name = grp.group_name

                # Bones inside group
                if grp.show_expanded:
                    for b in grp.bones:
                        row = box.row(align=True)
                        pb  = obj.pose.bones.get(b.bone_name)
                        if not pb:
                            # Bone was deleted or renamed outside of Bonemancer
                            row.label(text=f"{b.bone_name} (missing)", icon='ERROR')
                            rem = row.operator("rmv2.remove_bone", text="", icon='X')
                            rem.group_name = grp.group_name
                            rem.bone_name  = b.bone_name
                            continue
                        row.label(text=b.bone_name, icon='BONE_DATA')
                        # Highlight if selected in viewport
                        op = row.operator(
                            "rmv2.select_bone",
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
                            "rmv2.toggle_constraints_bone",
                            text="",
                        icon=icon_c,
                            depress=b.show_constraints)
                        togc.bone_name = b.bone_name
                        self._draw_bone_buttons(row, grp.group_name, b.bone_name, pb)
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
                                        cbox.label(text=f"{key} (group)")
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
                            op = cbox.operator("rmv2.add_custom_prop", text="Add Property", icon='ADD')
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
                                    "RMV2_UL_ConstraintList",
                                    "",                        # custom list_id
                                    pb,                        # data: PoseBone
                                    "constraints",             # its CollectionProperty
                                    b,                         # active_data: RMV2_Bone PG
                                    "constraint_index",        # its index IntProperty
                                    rows=4
                                )

class RMV2_UL_ConstraintList(bpy.types.UIList):
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
                    "rmv2.show_constraint_error",
                    text="",
                    icon='ERROR'
                )
                op.constraint_name = item.name
                op.error_message = tooltip_text

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CONSTRAINT')


class RMV2_OT_ShowConstraintError(bpy.types.Operator):
    """Show details about an invalid constraint"""
    bl_idname = "rmv2.show_constraint_error"
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


class RMV_2_BONE_UL_selection_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.name, icon='BONE_DATA')
        row.separator(factor=1.0)

        # Add to Collection
        op = row.operator(
            "rmv2.add_bone_to_collection",
            text="",
            icon='ADD'
        )
        op.bone_name = item.name

        op = row.operator(
            "rmv2.rename_bone",                 #     Operator to execute
            text="",                                  #     No text—just an icon
            icon='FILE_TEXT'                               #     Info icon for “relations”
        )
        op.bone_name = item.name
        op = row.operator(
            "bi.show_bone_relations",                 #     Operator to execute
            text="",                                  #     No text—just an icon
            icon='INFO'                               #     Info icon for “relations”
        )
        op.bone_name = item.name


class RMV2_UL_CustomPropsList(bpy.types.UIList):
    bl_idname = "RMV2_UL_CustomPropsList"
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # data is your RMV2_Bone PropertyGroup, item.name is the custom-prop key
        bone_item = data
        arm = get_rig(context.scene)
        pb  = arm.pose.bones.get(bone_item.bone_name) if arm else None
        if not pb:
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon='RNA')
        # live slider on pb["<prop_name>"]
        row.prop(pb, path_key(item.name), text="", slider=True)



classes = [
    # PropertyGroups
    RMV2_CustomPropItem,
    RMV2_Bone,
    RMV2_Group,
    ShapeKeyItem,
    ObjectShapeKeyGroup,
    RMV2_BoneSelectionItem,
    RMV2_RMGR_ArmatureItem,
    RMV2_RmgrSettings,
    RMV2_ShapeKeyScannerSettings,
    ArmatureGroup,

    # Operators
    RMV2_OT_AddToGroup,
    RMV2_OT_SelectBone,
    RMV2_OT_ToggleBone,
    RMV2_OT_ToggleGroup,
    RMV2_OT_RemoveBoneFromGroup,
    RMV2_OT_RemoveGroup,
    RMV2_OT_RenameBone,
    RMV2_OT_ToggleBoneConstraints,
    RMV2_OT_AddCustomProperty,
    RMV2_OT_add_bone_to_collection,
    RMV2_OT_ToggleGroupFoldout,
    RMV2_OT_ShowBoneRelations,
    RMV2_OT_ScanShapeKeys,
    RMV2_OT_ToggleShapeKeys,
    RMV2_OT_KeyShapeValue,
    RMV2_OT_ShowConstraintError,
    # UILists
    RMV2_UL_ConstraintList,
    RMV_2_BONE_UL_selection_list,
    RMV2_UL_CustomPropsList,
    RMV2_UL_ObjectGroupList,
    RMV2_UL_ShapeKeyList,

    # Panels
    RMV2_PT_ArmaturePicker,
    RMV2_PT_Collections,
    RMV2_PT_ShapeKeyScanner
]

safe_handlers=[
    rmv2_depsgraph_handler,
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
    scene = self  # the Scene that owns rmv2_rig (may differ from context.scene)
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

    scene.rmv2_rmgr_settings.last_armature = arm_obj
    sync_armature_entry(scene, arm_obj.name)



def sync_armature_entry(scene, arm_name):
    """
    Ensures there’s an entry in scene.rmv2_rmgr_settings.armature_items
    for the named armature, using RMV2_RMGR_ArmatureItem fields.
    """
    settings = scene.rmv2_rmgr_settings
    exists = next(
        (item for item in settings.armature_items
         if item.name == arm_name or (item.object_ref and item.object_ref.name == arm_name)),
        None
    )
    if not exists:
        new = settings.armature_items.add()
        new.name = arm_name
        new.object_ref = bpy.data.objects.get(arm_name)


LEGACY_GROUPS_PREFIX = "rmv2_groups_"

def _read_legacy_groups(scene, key):
    """
    Old group data for `key` as plain dicts, plus a function that deletes it.
    Blender 4.x keeps Python-defined properties as custom properties; 5.x keeps
    them as system properties, reachable only through a registered RNA property.
    """
    def as_dicts(groups, get):
        return [{
            "group_name":    get(g, "group_name", ""),
            "show_expanded": bool(get(g, "show_expanded", False)),
            "bones": [{
                "bone_name":         get(b, "bone_name", ""),
                "show_custom_props": bool(get(b, "show_custom_props", False)),
                "show_constraints":  bool(get(b, "show_constraints", False)),
            } for b in get(g, "bones", [])],
        } for g in groups]

    if hasattr(bpy.types.Scene, key):
        return [], lambda: None
    try:
        setattr(bpy.types.Scene, key, CollectionProperty(type=RMV2_Group))
    except (ValueError, TypeError):
        return [], lambda: None  # name too long to ever have been registered
    try:
        data = as_dicts(getattr(scene, key), getattr)
    finally:
        delattr(bpy.types.Scene, key)

    raw = scene.get(key)
    if raw is not None and not data:
        data = as_dicts(raw, lambda d, k, default: d.get(k, default))

    def remove():
        # A 4.x file opened in 5.x can hold the data in both places
        scene.pop(key, None)
        setattr(bpy.types.Scene, key, CollectionProperty(type=RMV2_Group))
        try:
            scene.property_unset(key)
        finally:
            delattr(bpy.types.Scene, key)
    return data, remove


def migrate_legacy_groups():
    """
    Versions up to 1.0 stored groups on the Scene as rmv2_groups_<armature name>.
    Copy them onto the matching rig objects and drop the old Scene data.
    Data whose armature can't be found is left untouched.
    """
    global _armature_change_from_viewport
    for scene in bpy.data.scenes:
        rigs_by_key = {}
        for obj in scene.objects:
            if obj.type == 'ARMATURE' and rig_is_editable(obj):
                rigs_by_key.setdefault(LEGACY_GROUPS_PREFIX + sanitize_name(obj.name), []).append(obj)

        for key, rigs in rigs_by_key.items():
            targets = [obj for obj in rigs if not len(obj.rmv2_groups)]
            if not targets:
                continue
            data, remove = _read_legacy_groups(scene, key)
            if not data:
                continue
            for obj in targets:
                for old_grp in data:
                    grp = obj.rmv2_groups.add()
                    grp.group_name    = old_grp["group_name"]
                    grp.show_expanded = old_grp["show_expanded"]
                    for old_bone in old_grp["bones"]:
                        entry = grp.bones.add()
                        entry.bone_name         = old_bone["bone_name"]
                        entry.show_custom_props = old_bone["show_custom_props"]
                        entry.show_constraints  = old_bone["show_constraints"]
            remove()

        # The old armature picker was an index-based enum; restore the pick
        # from the last-armature pointer it also kept.
        last = scene.rmv2_rmgr_settings.last_armature
        if scene.rmv2_rig is None and last and last.type == 'ARMATURE':
            _armature_change_from_viewport = True
            try:
                scene.rmv2_rig = last
            finally:
                _armature_change_from_viewport = False


@persistent
def on_load_post(dummy):
    migrate_legacy_groups()


load_post_handlers = [on_load_post]


def _deferred_init():
    # bpy.data is restricted while the add-on registers; finish setup on the
    # first tick so data saved in an already-open file is picked up.
    migrate_legacy_groups()
    return None


def register():
    # 1) Register all UI classes
    for cls in classes:
        bpy.utils.register_class(cls)

    # 2) Static Scene properties via safe_register_prop
    safe_register_prop(
        bpy.types.Scene, "rmv2_bone",
        EnumProperty(name="Bone", items=get_bones)
    )
    safe_register_prop(
        bpy.types.Scene, "rmv2_constr_bone",
        EnumProperty(name="Bone", items=get_constraint_bones)
    )
    safe_register_prop(
        bpy.types.Scene, "rmv2_selected_bone",
        StringProperty()
    )
    safe_register_prop(
        bpy.types.Scene, "rmv2_groups",
        CollectionProperty(type=RMV2_Group)
    )
    safe_register_prop(
        bpy.types.Scene, "rmv2_index",
        IntProperty(default=0)
    )
    safe_register_prop(
        bpy.types.Scene, "rmv2_active_bone_name",
        StringProperty()
    )

    # 3) PointerProperty for settings & the picked rig + update
    bpy.types.Scene.rmv2_rmgr_settings = PointerProperty(
        name="Rig Manager Settings",
        type=RMV2_RmgrSettings
    )

    # A pointer (not a name-based enum) survives renames, reordering and
    # deletion of other armatures, and works with any characters in names.
    bpy.types.Scene.rmv2_rig = PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        poll=armature_poll,
        update=on_armature_change
    )

    # Bone collections are stored on the rig object, so they follow it
    # through renames and across scenes.
    bpy.types.Object.rmv2_groups = CollectionProperty(
        type=RMV2_Group,
        override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'}
    )

    bpy.types.Scene.rmv2_bone_list = CollectionProperty(
        type=RMV2_BoneSelectionItem
    )

    bpy.types.Scene.rmv2_shape_key_scanner = PointerProperty(
        type=RMV2_ShapeKeyScannerSettings
    )
    bpy.types.Scene.rmv2_armature_groups = CollectionProperty(type=ArmatureGroup)
    bpy.types.Scene.rmv2_active_armature = StringProperty()

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
    unregister_properties(bpy.types.Scene, [
        "rmv2_rig",
        "rmv2_bone",
        "rmv2_constr_bone",
        "rmv2_selected_bone",
        "rmv2_groups",
        "rmv2_index",
        "rmv2_active_bone_name",
        "rmv2_rmgr_settings",
        "rmv2_bone_list",
        "rmv2_shape_key_scanner",
        "rmv2_armature_groups",
        "rmv2_active_armature",
    ])
    unregister_properties(bpy.types.Object, ["rmv2_groups"])
    _enum_items_cache.clear()

if __name__ == "__main__":
    register()
