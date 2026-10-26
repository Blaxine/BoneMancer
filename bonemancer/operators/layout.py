# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the Actionable Bones panel."""

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty

from ..core.layout import active_bone_name, bone_hidden_in_layout, find_tab, place_bone
from ..core.selection import select_bone_in_viewport, toggle_bone_in_viewport
from ..core.utils import get_rig, rig_is_editable, tag_addon_panels


class BONEMANCER_OT_pick_bone(bpy.types.Operator):
    bl_idname = "bonemancer.pick_bone"
    bl_label = "Pick Bone"
    # No per-bone description(): with one, Blender stops drawing the button
    # pressed while its bone is selected. The panel names the active bone instead.
    bl_description = "Select this bone. Shift+click adds it to the selection or removes it"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: StringProperty()
    extend: BoolProperty(name="Extend", options={'SKIP_SAVE'})

    def invoke(self, context, event):
        # Ctrl and Alt are reserved; they act like a plain click for now
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        rig = get_rig(context.scene)
        if rig and bone_hidden_in_layout(rig, self.bone_name):
            self.report({'INFO'}, f"'{self.bone_name}' is hidden")
            return {'CANCELLED'}
        select = toggle_bone_in_viewport if self.extend else select_bone_in_viewport
        error = select(context, rig, self.bone_name)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}


class InertCell:
    """
    A cell button that can't be clicked. Labels or sub-layouts in the grid
    squeeze the real buttons out of shape; a never-enabled button keeps every
    cell the same width, and draws greyed.
    """
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return False

    def execute(self, context):
        return {'CANCELLED'}


class BONEMANCER_OT_layout_blank(InertCell, bpy.types.Operator):
    bl_idname = "bonemancer.layout_blank"
    bl_label = "Empty Cell"
    bl_description = "Empty cell"


class BONEMANCER_OT_hidden_cell(InertCell, bpy.types.Operator):
    bl_idname = "bonemancer.hidden_cell"
    bl_label = "Hidden Bone"
    bl_description = "This bone is hidden. Show it, or its bone collection, to pick it"


class BONEMANCER_OT_missing_cell(InertCell, bpy.types.Operator):
    bl_idname = "bonemancer.missing_cell"
    bl_label = "Missing Bone"
    bl_description = "This cell's bone no longer exists. Turn on Edit Layout to clear it"


class BONEMANCER_OT_place_bone(bpy.types.Operator):
    bl_idname = "bonemancer.place_bone"
    bl_label = "Place Bone"
    bl_description = "Place the bone that's active in the viewport in this cell"
    bl_options = {'REGISTER', 'UNDO'}
    tab: StringProperty()
    row: IntProperty()
    column: IntProperty()

    def execute(self, context):
        rig = get_rig(context.scene)
        if not rig_is_editable(rig):
            self.report({'WARNING'}, "Pick an editable armature first")
            return {'CANCELLED'}
        tab = find_tab(rig, self.tab)
        if tab is None or not (0 <= self.row < tab.rows and 0 <= self.column < tab.columns):
            self.report({'WARNING'}, "That cell doesn't exist")
            return {'CANCELLED'}
        bone_name = active_bone_name(rig)
        if not bone_name:
            self.report({'WARNING'}, "Select a bone in the viewport first")
            return {'CANCELLED'}
        place_bone(tab, self.row, self.column, bone_name)
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_new_layout_tab(bpy.types.Operator):
    bl_idname = "bonemancer.new_layout_tab"
    bl_label = "New Tab"
    bl_description = "Add an empty tab to this rig's layout"
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty(name="Name", default="Body")
    columns: IntProperty(name="Columns", default=16, min=4, max=32)
    rows: IntProperty(name="Rows", default=24, min=4, max=48)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        rig = get_rig(context.scene)
        if not rig_is_editable(rig):
            self.report({'WARNING'}, "Pick an editable armature first")
            return {'CANCELLED'}
        name = self.name.strip()
        if not name:
            self.report({'WARNING'}, "Give the tab a name")
            return {'CANCELLED'}
        if find_tab(rig, name):
            self.report({'WARNING'}, f"A tab named '{name}' already exists")
            return {'CANCELLED'}
        tab = rig.bonemancer_layout.add()
        tab.name, tab.columns, tab.rows = name, self.columns, self.rows
        context.scene.bonemancer_settings.layout_tab = name
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_show_layout_tab(bpy.types.Operator):
    bl_idname = "bonemancer.show_layout_tab"
    bl_label = "Show Tab"
    bl_description = "Show this tab of the layout"
    name: StringProperty()

    def execute(self, context):
        context.scene.bonemancer_settings.layout_tab = self.name
        tag_addon_panels(context)
        return {'FINISHED'}
