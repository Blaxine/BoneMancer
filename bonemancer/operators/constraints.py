# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators on a bone's constraints."""

import bpy
from bpy.props import StringProperty

from ..core.utils import get_rig, rig_is_editable, tag_addon_panels


class BONEMANCER_OT_remove_constraint(bpy.types.Operator):
    """Delete this constraint from the bone"""
    bl_idname = "bonemancer.remove_constraint"
    bl_label = "Remove Constraint"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty()
    constraint_name: StringProperty()

    def execute(self, context):
        rig = get_rig(context.scene)
        pb = rig.pose.bones.get(self.bone_name) if rig else None
        con = pb.constraints.get(self.constraint_name) if pb else None
        if not con:
            return {'CANCELLED'}
        if not rig_is_editable(rig):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        if con.is_override_data:   # it came with the linked rig, not added on the override
            self.report({'ERROR'}, "This constraint comes from the rig's library file; remove it there")
            return {'CANCELLED'}
        pb.constraints.remove(con)
        tag_addon_panels(context)
        return {'FINISHED'}


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
