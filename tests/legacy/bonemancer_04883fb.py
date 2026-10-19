

bl_info = {
    "name":        "Bone Mancer: Rig Central",
    "author":      "Laurent",
    "version":     (1, 0, 0),
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

previous_armatures = set()
mirrored_drivers = set()
_last_selected_armature = None
_armature_change_from_viewport = False


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


class RMV2_CustomPropItem(PropertyGroup):
        name: StringProperty(name="Property Name")  
        
class BoneItem(PropertyGroup):
    name: StringProperty()
    show_constraints: BoolProperty(default=False)
    is_selected: BoolProperty(default=False)

      
class RMV2_Bone(PropertyGroup):
    
        bone_name: StringProperty(name="Bone Name")
        
        show_custom_props: BoolProperty(
            name="Show Custom Props",
            default=False,
            description="Expand custom properties panel"
        )

        show_constraints: BoolProperty(
            name="Show Constraints",
            default=False
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
        group_name: bpy.props.StringProperty(name="Group Name")
        bones: bpy.props.CollectionProperty(type=RMV2_Bone)
        bone_index: bpy.props.IntProperty(default=0)
        show_bones: bpy.props.BoolProperty(default=True)
        show_expanded: bpy.props.BoolProperty(
        name="Expand Group",
        description="Toggle bone list visibility",
        default=False)


class RMV2_RmgrSettings(PropertyGroup):
        auto_load: BoolProperty(
        name="Auto Load",
        description="Automatically load last rig on file open",
        default=False
        )
        # The new bone-pick list
        bone_selection: CollectionProperty(type=RMV2_BoneSelectionItem)
        bone_selection_index: IntProperty(name="Index", default=0)
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
                data_path=f'key_blocks["{self.key_name}"].value',
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


def update_active_armature(self, context):
    arm = self.armature
    if not arm or arm.type != 'ARMATURE':
        return

    # 1. Exit any non-object mode (so selection works reliably)
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # 2. Deselect everything, select the new armature, make it active
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    context.view_layer.objects.active = arm

    # 3. Enter Pose Mode on the newly active armature
    bpy.ops.object.mode_set(mode='POSE')


def scan_shape_keys_for_armature(context, arm_obj):
    settings = context.scene.rmv2_shape_key_scanner
    settings.object_groups.clear()

    for obj in context.scene.objects:
        if obj.type != 'MESH' or not obj.data.shape_keys:
            continue
        attached = (
            obj.parent == arm_obj or
            any(mod.type=='ARMATURE' and mod.object==arm_obj
                for mod in obj.modifiers)
        )
        if not attached:
            continue

        grp = settings.object_groups.add()
        grp.object_name = obj.name
        for kb in obj.data.shape_keys.key_blocks:
            if kb.name == "Basis":
                continue
            item = grp.shape_keys.add()
            item.object_name = obj.name
            item.key_name    = kb.name
            item.value       = kb.value

class RMV2_OT_ScanShapeKeys(bpy.types.Operator):
    bl_idname      = "rmv2.scan_shape_keys"
    bl_label       = "Scan Rig For Shape Keys"
    bl_description = "Scans and refreshes the shape key list of the selected rig to identify meshes with shape keys"

    def execute(self, context):
        arm = bpy.data.objects.get(context.scene.rmv2_armature)
        if not arm or arm.type != 'ARMATURE':
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        scan_shape_keys_for_armature(context, arm)
        return {'FINISHED'}

class RMV2_OT_ToggleShapeKeys(bpy.types.Operator):
    bl_idname = "rmv2.toggle_shape_keys"
    bl_label  = "Toggle Shape Keys Visibility"

    index: IntProperty()

    def execute(self, context):
        grp = context.scene.rmv2_shape_key_scanner.object_groups[self.index]
        grp.show_shape_keys = not grp.show_shape_keys
        return {'FINISHED'}

class RMV2_OT_KeyShapeValue(bpy.types.Operator):
    bl_idname = "rmv2.key_shape_value"
    bl_label  = "Toggle Shape Key Keyframe"

    object_name:    StringProperty()
    shape_key_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not obj or obj.type != 'MESH' or not obj.data.shape_keys:
            return {'CANCELLED'}

        frame   = context.scene.frame_current
        sk_data = obj.data.shape_keys
        path    = f'key_blocks["{self.shape_key_name}"].value'
        ensure_shape_keys_action(sk_data, obj.name)

        fcurves = get_anim_fcurves(sk_data.animation_data)
        fcu = next((fc for fc in fcurves if fc.data_path == path), None)
        if fcu:
            removed = False
            for kp in list(fcu.keyframe_points):
                if int(kp.co.x) == frame:
                    sk_data.keyframe_delete(data_path=path, frame=frame)
                    removed = True
            if removed:
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
            path = f'key_blocks["{item.key_name}"].value'
            if any(
                int(kp.co.x) == context.scene.frame_current
                for fc in fcurves if fc.data_path == path
                for kp in fc.keyframe_points
            ):
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
        settings = scene.rmv2_rmgr_settings
        armature_name = scene.rmv2_armature
        return (
            armature_name in bpy.data.objects and
            len(settings.bone_selection) > 0
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        armature_obj = bpy.data.objects.get(scene.rmv2_armature)

        if not armature_obj or armature_obj.type != 'ARMATURE':
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


def toggle_hidden(pb):
    if not pb:
        return
    if hasattr(pb, "hide"):
        pb.hide = not pb.hide
    else:
        pb.bone.hide = not pb.bone.hide
            
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



def unregister_properties(static_props):
    for p in static_props:
        if hasattr(bpy.types.Scene, p):
            delattr(bpy.types.Scene, p)

def cleanup_dynamic_props():
    for key in dynamic_props:
        if hasattr(bpy.types.Scene, key):
            delattr(bpy.types.Scene, key)
    dynamic_props.clear()


def ensure_group_prop(arm_name):
    """Register Scene.rmv2_groups_<armature> if needed and return its name."""
    key = f"rmv2_groups_{sanitize_name(arm_name)}"
    if not hasattr(bpy.types.Scene, key):
        setattr(bpy.types.Scene, key, CollectionProperty(type=RMV2_Group))
    if key not in dynamic_props:
        dynamic_props.append(key)
    return key


def find_group(scene, group_name):
    groups = getattr(scene, f"rmv2_groups_{sanitize_name(scene.rmv2_armature)}", [])
    return next((g for g in groups if g.group_name == group_name), None)


def update_driver_variable_paths(old_name, new_name):
    """
    Replace any reference to pose.bones["old_name"] in driver variable
    targets across all objects, and update bone_target fields.
    """
    bone_ref_old = f'pose.bones["{old_name}"]'
    bone_ref_new = f'pose.bones["{new_name}"]'
    count = 0

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if not ad or not ad.drivers:
            continue

        for fc in ad.drivers:
            for var in fc.driver.variables:
                for targ in var.targets:
                    # 1) Update data_path string
                    if targ.data_path and bone_ref_old in targ.data_path:
                        targ.data_path = targ.data_path.replace(bone_ref_old, bone_ref_new)
                        count += 1

                    # 2) Update bone_target property
                    if hasattr(targ, "bone_target") and targ.bone_target == old_name:
                        targ.bone_target = new_name
                        count += 1

    return count


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

def update_bone_list(self, context):
    scene    = context.scene
    settings = scene.rmv2_rmgr_settings

    arm_obj = bpy.data.objects.get(scene.rmv2_armature)
    names = _armature_bone_names(arm_obj) if arm_obj and arm_obj.type == 'ARMATURE' else []

    # Skip the rebuild when nothing changed (this runs from depsgraph handlers)
    if names == [item.name for item in settings.bone_selection]:
        return

    settings.bone_selection.clear()
    for name in names:
        item = settings.bone_selection.add()
        item.name = name

    settings.bone_selection_index = min(settings.bone_selection_index, max(len(names) - 1, 0))

def refresh_bones(context):
    update_bone_list(None, context)

@persistent
def armature_monitor(scene):
    # Grab the active object from the current context
    arm = bpy.context.active_object

    # Early out if it's not an armature
    if not arm or arm.type != 'ARMATURE':
        return

    settings = scene.rmv2_rmgr_settings
    if settings.last_armature != arm:
        refresh_bone_list(bpy.context)
        settings.last_armature = arm


def refresh_bone_list(context):
    update_bone_list(None, bpy.context)



@persistent
def sync_selected_bone(scene, depsgraph=None):
    ctx = bpy.context
    ob = ctx.active_object
    if not (ob and ob.type == 'ARMATURE' and ctx.mode == 'POSE'):
        return
    selected = next((pb.name for pb in ob.pose.bones if bone_is_selected(pb)), "")
    if scene.rmv2_selected_bone != selected:
        scene.rmv2_selected_bone = selected


@persistent
def depsgraph_update_handler(scene, depsgraph):
    ctx = bpy.context
    needs_bone_refresh = False
    needs_redraw = False

    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Armature):
            needs_bone_refresh = True
            needs_redraw = True
            break
        # Shape Key datablocks are bpy.types.Key
        if isinstance(update.id, bpy.types.Key):
            needs_redraw = True

    if needs_bone_refresh:
        refresh_bones(ctx)
    if needs_redraw:
        tag_addon_panels(ctx)


@persistent
def armature_list_update_handler(scene):
    global previous_armatures

    current_armatures = {obj.name for obj in bpy.data.objects if obj.type == 'ARMATURE'}
    if current_armatures != previous_armatures:
        previous_armatures = current_armatures
        # Refresh lists only; re-assigning rmv2_armature here would run
        # on_armature_change and switch modes from inside a depsgraph handler.
        refresh_bone_list(bpy.context)


def get_armatures(self, context):
      return [
        (obj.name, obj.name, "")
        for obj in context.scene.objects
        if obj.type == 'ARMATURE'
    ]



def get_bones(self, context):
    arm = context.scene.rmv2_armature
    obj = bpy.data.objects.get(arm)
    return [(b.name, b.name, "") for b in obj.data.bones] if obj else []


def get_group_items(self, context):
    safe = sanitize_name(context.scene.rmv2_armature)
    groups = getattr(context.scene, f"rmv2_groups_{safe}", [])
    return [(g.group_name, g.group_name, "") for g in groups]


def get_constraint_bone_items(self, context):
    items = []
    obj = context.object
    if not obj or obj.type != 'ARMATURE' or not obj.pose:
        return items

    for pb in obj.pose.bones:
        if pb.constraints:
            items.append((pb.name, pb.name, "Bone with constraints"))

    return items
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
    arm = context.scene.rmv2_armature
    obj = bpy.data.objects.get(arm)
    return [(pb.name, pb.name, "") for pb in obj.pose.bones if pb.constraints] if obj else []
                               
class RMV2_OT_AddToGroup(bpy.types.Operator):
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
        arm = sc.rmv2_armature
        bone = sc.rmv2_bone
        if not bone:
            self.report({'ERROR'}, "No bone selected")
            return {'CANCELLED'}

        groups = getattr(sc, ensure_group_prop(arm))
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
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        arm_name = context.scene.rmv2_armature
        obj = bpy.data.objects.get(arm_name)
        if not obj or obj.type != 'ARMATURE':
            self.report({'WARNING'}, "No valid armature")
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

        # pick our bone
        pb = obj.pose.bones.get(self.bone_name)
        if not pb:
            self.report({'WARNING'}, f"Bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        # deselect all bones
        for p in obj.pose.bones:
            set_bone_selected(p, False)

        # unhide & select target
        if is_hidden(pb):
            toggle_hidden(pb)
        set_bone_selected(pb, True)
        obj.data.bones.active = pb.bone
        return {'FINISHED'}

class RMV2_OT_ToggleBone(bpy.types.Operator):
    bl_idname = "rmv2.toggle_bone"
    bl_label = "Toggle Bone"
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(context.scene.rmv2_armature)
        if not obj or obj.type != 'ARMATURE':
            self.report({'WARNING'}, "No valid armature")
            return {'CANCELLED'}
        toggle_hidden(obj.pose.bones.get(self.bone_name))
        return {'FINISHED'}


class RMV2_OT_ToggleGroup(bpy.types.Operator):
    bl_idname = "rmv2.toggle_group"
    bl_label = "Toggle Group"
    group_name: bpy.props.StringProperty()

    def execute(self, context):
        sc = context.scene
        obj = bpy.data.objects.get(sc.rmv2_armature)
        group = find_group(sc, self.group_name)
        if not obj or obj.type != 'ARMATURE' or not group:
            self.report({'WARNING'}, f"Group '{self.group_name}' not found")
            return {'CANCELLED'}
        for b in group.bones:
            toggle_hidden(obj.pose.bones.get(b.bone_name))
        return {'FINISHED'}


class RMV2_OT_RemoveBoneFromGroup(bpy.types.Operator):
    bl_idname = "rmv2.remove_bone"
    bl_label = "Remove Bone"
    group_name: bpy.props.StringProperty()
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        group = find_group(context.scene, self.group_name)
        if not group:
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
    group_name: bpy.props.StringProperty()

    def execute(self, context):
        sc = context.scene
        groups = getattr(sc, f"rmv2_groups_{sanitize_name(sc.rmv2_armature)}", [])
        for i, g in enumerate(groups):
            if g.group_name == self.group_name:
                groups.remove(i)
                break
        return {'FINISHED'}

class RMV2_OT_ToggleBoneConstraints(bpy.types.Operator):
    bl_idname = "rmv2.toggle_constraints_bone"
    bl_label = "Toggle Constraints Foldout"
    bl_description = "Expand or collapse the constraints list for this bone"

    bone_name: StringProperty()

    def execute(self, context):
        scene = context.scene
        arm = scene.rmv2_armature
        safe = sanitize_name(arm)
        groups = getattr(scene, f"rmv2_groups_{safe}", [])

        # Find the bone in any group
        for g in groups:
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

        # Count drivers referencing this bone
        self.drivers_count = 0
        for obj in bpy.data.objects:
            ad = obj.animation_data
            if ad and ad.drivers:
                for drv in ad.drivers:
                    for var in drv.driver.variables:
                        for tgt in var.targets:
                            if f'pose.bones["{self.bone_name}"]' in (tgt.data_path or ""):
                                self.drivers_count += 1
                                break

        # Count constraints on the pose bone
        arm = context.scene.rmv2_armature
        arm_obj = bpy.data.objects.get(arm)
        pb = arm_obj.pose.bones.get(self.bone_name) if arm_obj else None
        self.constraints_count = len(pb.constraints) if pb else 0

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
        layout.box().label(text=self.preview, icon='BONE_DATA')

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
            out = name.replace(self.find_text, self.replace_text)

        self.preview = out

    def execute(self, context):
        # 1) Compute the final name from your preview logic
        self.update_preview()
        new_name = self.preview

        # 2) Grab the selected armature object
        arm_name = context.scene.rmv2_armature
        arm_obj  = bpy.data.objects.get(arm_name)
        if not arm_obj or arm_obj.type != 'ARMATURE':
            self.report({'ERROR'}, "No valid armature selected")
            return {'CANCELLED'}

        # 3) Rename in both the EditBone (data) and PoseBone layers
        bone_dat  = arm_obj.data.bones.get(self.bone_name)
        bone_pose = arm_obj.pose.bones.get(self.bone_name)
        if not bone_dat or not bone_pose:
            self.report({'ERROR'}, f"Bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        bone_dat.name  = new_name
        bone_pose.name = new_name

        # 4) Update every RMV2_Group on this armature that references the old name
        safe_key = sanitize_name(arm_name)
        groups   = getattr(context.scene, f"rmv2_groups_{safe_key}", [])
        for grp in groups:
            for entry in grp.bones:
                if entry.bone_name == self.bone_name:
                    entry.bone_name = new_name

        # 5) Sync the bone‐picker and update any driver references
        context.scene.rmv2_bone = new_name
        update_driver_variable_paths(self.bone_name, new_name)
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
        arm_obj = bpy.data.objects.get(context.scene.rmv2_armature)
        pb = arm_obj and arm_obj.pose.bones.get(self.bone_name)
        if not pb:
            self.report({'ERROR'}, "Bone not found")
            return {'CANCELLED'}
        if not self.prop_name.strip():
            self.report({'ERROR'}, "Property name cannot be empty")
            return {'CANCELLED'}

        if self.prop_type == 'FLOAT':
            pb[self.prop_name] = self.default_float
        elif self.prop_type == 'INT':
            pb[self.prop_name] = self.default_int
        elif self.prop_type == 'BOOLEAN':
            pb[self.prop_name] = self.default_bool
        else:
            pb[self.prop_name] = self.default_string

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
        obj = context.object
        return obj and obj.type == 'ARMATURE'

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
        scene     = context.scene

        # 1) Ensure the Scene has that dynamic group-list
        groups = getattr(scene, ensure_group_prop(scene.rmv2_armature))

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
    
class RMV2_OT_SyncViewportSelection(bpy.types.Operator):
    """Continuously sync viewport bone selection with panel"""
    bl_idname = "rm.sync_viewport_selection"
    bl_label = "Sync Viewport Selection"
    bl_options = {'INTERNAL'}

    _timer = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            self.sync_bone_selection(context)
        return {'PASS_THROUGH'}

    def sync_bone_selection(self, context):
        arm = context.object
        if not arm or arm.type != 'ARMATURE':
            return

        selected = {pb.name for pb in arm.pose.bones if bone_is_selected(pb)}

        groups = getattr(context.scene, f"rmv2_groups_{sanitize_name(arm.name)}", [])
        for group in groups:
            for bone in group.bones:
                bone.is_selected = bone.bone_name in selected

        tag_addon_panels(context)

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
            
class RMV2_OT_ToggleGroupFoldout(bpy.types.Operator):
    bl_idname = "rmv2.toggle_group_foldout"
    bl_label = "Toggle Group Foldout"
    bl_description = "Expand or collapse this bone group in the UI"

    group_name: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        arm = scene.rmv2_armature
        safe = sanitize_name(arm)
        groups = getattr(scene, f"rmv2_groups_{safe}", [])

        # Find matching group and flip its flag
        grp = next((g for g in groups if g.group_name == self.group_name), None)
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
            layout.prop(scene, "rmv2_armature", text="Armature")
        
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

     
    def _draw_bone_buttons(self, row, group_name, bone_name):

            # Hide/Unhide (state of the armature picked in the panel)
            obj = bpy.data.objects.get(bpy.context.scene.rmv2_armature)
            pbone = obj.pose.bones.get(bone_name) if obj and obj.type == 'ARMATURE' else None
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
            arm_name = scene.rmv2_armature
            obj      = bpy.data.objects.get(arm_name)

            # Early exit if no valid armature
            if not obj or obj.type != 'ARMATURE':
                layout.label(text="Select an armature", icon='ERROR')
                return

            # Fetch groups
            safe_name = sanitize_name(arm_name)
            groups    = getattr(scene, f"rmv2_groups_{safe_name}", [])

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

                hide_show_group = header.operator("rmv2.toggle_group", text="", icon='HIDE_OFF')
                hide_show_group.group_name = grp.group_name
                            
                remg = header.operator("rmv2.remove_group", text="", icon='TRASH')
                remg.group_name = grp.group_name

                # Bones inside group
                if grp.show_expanded:
                    for b in grp.bones:
                        row = box.row(align=True)
                        row.label(text=b.bone_name, icon='BONE_DATA')
                        pb  = obj.pose.bones.get(b.bone_name)
                        # Highlight if selected in viewport
    # single operator invocation, always assign bone_name and reflect selection
                        op = row.operator(
                            "rmv2.select_bone",
                            text="",
                            icon='RESTRICT_SELECT_OFF',
                            depress=b.is_selected
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
                        self._draw_bone_buttons(row, grp.group_name, b.bone_name)
                         # CUSTOM PROPLS FOLDOUT
                        if b.show_custom_props and pb:
                            cbox = box.box().column()
                            cbox.label(text="Custom Props:", icon='RNA')
                            # Live‐draw every custom property in its native widget
                            for key in pb.keys():
                                if key != 'constraint_active_index':
                                    # 1) Arrays → grouped fields
                                    val = pb[key]
                                    if isinstance(val, (list, tuple)):
                                        cbox.label(text=key)
                                        row = cbox.row(align=True)
                                        for i in range(len(val)):
                                            row.prop(pb, f'["{key}"][{i}]', text=str(i))
                                        continue

                                    # 2–4) All other types → let Blender pick the widget
                                    row = cbox.row()
                                    row.prop(pb, f'["{key}"]', text=key)

                            # “Add Property” button stays the same
                            op = cbox.operator("rmv2.add_custom_prop", text="Add Property", icon='ADD')
                            op.bone_name = b.bone_name


                        # Expanded Constraints
                        if b.show_constraints and pb:
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
        arm = context.object
        pb  = arm.pose.bones.get(bone_item.bone_name) if arm and arm.type == 'ARMATURE' else None
        if not pb:
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon='RNA')
        # live slider on pb["<prop_name>"]
        row.prop(pb, f'["{item.name}"]', text="", slider=True)
        

@persistent
def viewport_armature_sync(scene, depsgraph=None):
    """
    Called after every depsgraph update. If the active object
    is an armature and it's different than last time, push it
    into scene.rmv2_armature so on_armature_change() runs.
    Viewport-triggered changes should NOT force Pose Mode.
    """
    global _last_selected_armature, _armature_change_from_viewport

    ctx = bpy.context
    obj = ctx.view_layer.objects.active

    # only care about Armatures
    if not obj or obj.type != 'ARMATURE':
        return

    # if truly changed, update the Scene prop (fires update callback)
    if obj.name != _last_selected_armature:
        _last_selected_armature = obj.name
        _armature_change_from_viewport = True  # mark source of change
        ctx.scene.rmv2_armature = obj.name



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
    RMV2_OT_SyncViewportSelection,
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
    depsgraph_update_handler,
    sync_selected_bone, 
    armature_monitor, 
    armature_list_update_handler, 
    viewport_armature_sync
]


dynamic_props = []

@persistent
def init_armature_groups(dummy):
    """
    After Blender fully loads data, scan for all ARMATURE objects
    and create a Scene.rmv2_groups_<armature> CollectionProperty.
    """
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            ensure_group_prop(obj.name)

def safely_register_handlers(handlers):
    for handle in handlers:
        if handle not in bpy.app.handlers.depsgraph_update_post:
             bpy.app.handlers.depsgraph_update_post.append(handle)
             
def on_armature_change(self, context):
    """
    Handler called when the user picks a new armature in the UI
    or when the active armature changes in the viewport.

    - From viewport: refresh lists only (no mode/selection changes).
    - From dropdown: also switch to Pose Mode and activate the armature.
    """
    global _armature_change_from_viewport, _last_selected_armature

    scene = context.scene
    arm_name = scene.rmv2_armature
    arm_obj = bpy.data.objects.get(arm_name)

    # Bail if invalid
    if not arm_obj or arm_obj.type != 'ARMATURE':
        _armature_change_from_viewport = False
        return

    _last_selected_armature = arm_name
    ensure_group_prop(arm_name)

    if _armature_change_from_viewport:
        # Viewport selection: do NOT alter modes; just refresh addon state.
        update_bone_list(self, context)
        scan_shape_keys_for_armature(context, arm_obj)
        scene.rmv2_rmgr_settings.last_armature = arm_obj
        sync_armature_entry(scene, arm_name)
        _armature_change_from_viewport = False
        return

    # Dropdown selection: proceed with activation and Pose Mode
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    arm_obj.select_set(True)
    context.view_layer.objects.active = arm_obj

    bpy.ops.object.mode_set(mode='POSE')

    update_bone_list(self, context)
    scan_shape_keys_for_armature(context, arm_obj)

    scene.rmv2_rmgr_settings.last_armature = arm_obj
    sync_armature_entry(scene, arm_name)



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



@persistent
def on_load_post(dummy):
    global previous_armatures, _last_selected_armature
    previous_armatures = {obj.name for obj in bpy.data.objects if obj.type == 'ARMATURE'}
    _last_selected_armature = None


load_post_handlers = [on_load_post, init_armature_groups]


def _deferred_init():
    # bpy.data is restricted while the add-on registers; finish setup on the
    # first tick so groups saved in an already-open file show up immediately.
    init_armature_groups(None)
    on_load_post(None)
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

    # 3) PointerProperty for settings & Armature enum + update
    bpy.types.Scene.rmv2_rmgr_settings = PointerProperty(
        name="Rig Manager Settings",
        type=RMV2_RmgrSettings
    )

    bpy.types.Scene.rmv2_armature = EnumProperty(
        name="Armature",
        items=get_armatures,
        update=on_armature_change
    )

    bpy.types.Scene.rmv2_bone_list = CollectionProperty(
        type=RMV2_BoneSelectionItem
    )

    bpy.types.Scene.rmv2_shape_key_scanner = PointerProperty(
        type=RMV2_ShapeKeyScannerSettings
    )
    bpy.types.Scene.rmv2_armature_groups = CollectionProperty(type=ArmatureGroup)
    bpy.types.Scene.rmv2_active_armature = StringProperty(update=on_armature_change)

    # 4) Handlers for depsgraph updates (only ours; never clear other add-ons')
    safely_register_handlers(safe_handlers)

    # 5) Load handlers + deferred init of dynamic armature-group props
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

    # 3) Unregister static properties
    static_props = [
        "rmv2_armature",
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
    ]
    unregister_properties(static_props)

    # 4) Clean up dynamic per-armature group props
    cleanup_dynamic_props()

if __name__ == "__main__":
    register()
