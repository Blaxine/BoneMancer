# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators on a bone's custom properties."""

import bpy
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty, EnumProperty

from ..core.utils import get_rig, path_key, pose_bone_path


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
