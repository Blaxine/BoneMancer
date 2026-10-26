# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the Actionable Bones panel."""

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

from ..core.layout import (LAYOUT_LOCKED_MESSAGE, active_bone_name, bone_hidden_in_layout, cell_at, clear_move,
                           find_tab, layout_edit_refusal, moving_cell, place_bone)
from ..core.selection import select_bone_in_viewport, toggle_bone_in_viewport
from ..core.utils import get_rig, tag_addon_panels
from ..ui.layout import draw_cell_menu


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


class InertButton:
    """
    A button that can't be clicked, drawn greyed with its own tooltip. In the
    grid, labels or sub-layouts squeeze the real buttons out of shape; a
    never-enabled button keeps every cell the same width.
    """
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return False

    def execute(self, context):
        return {'CANCELLED'}


class BONEMANCER_OT_layout_blank(InertButton, bpy.types.Operator):
    bl_idname = "bonemancer.layout_blank"
    bl_label = "Empty Cell"
    bl_description = "Empty cell"


class BONEMANCER_OT_hidden_cell(InertButton, bpy.types.Operator):
    bl_idname = "bonemancer.hidden_cell"
    bl_label = "Hidden Bone"
    bl_description = "This bone is hidden. Show it, or its bone collection, to pick it"


class BONEMANCER_OT_missing_cell(InertButton, bpy.types.Operator):
    bl_idname = "bonemancer.missing_cell"
    bl_label = "Missing Bone"
    bl_description = "This cell's bone no longer exists. Turn on Edit Layout to clear it"


class BONEMANCER_OT_layout_locked(InertButton, bpy.types.Operator):
    """Stands in for the Edit Layout toggle on linked and overridden rigs."""
    bl_idname = "bonemancer.layout_locked"
    bl_label = "Edit Layout"
    bl_description = LAYOUT_LOCKED_MESSAGE


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
        refusal = layout_edit_refusal(rig)
        if refusal:
            self.report({'WARNING'}, refusal)
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


class CellOperator:
    """An operator on one cell of a tab of the picked rig's layout."""
    tab: StringProperty()
    row: IntProperty()
    column: IntProperty()

    def editable_tab(self, context):
        """The tab, or None after reporting why it can't be edited."""
        rig = get_rig(context.scene)
        refusal = layout_edit_refusal(rig)
        if refusal:
            self.report({'WARNING'}, refusal)
            return None
        tab = find_tab(rig, self.tab)
        if tab is None or not (0 <= self.row < tab.rows and 0 <= self.column < tab.columns):
            self.report({'WARNING'}, "That cell doesn't exist")
            return None
        return tab

    def filled_cell(self, context):
        """The cell, or None after reporting why it can't be edited."""
        tab = self.editable_tab(context)
        cell = tab and cell_at(tab, self.row, self.column)
        if tab and cell is None:
            self.report({'WARNING'}, "That cell is empty")
        return cell


class BONEMANCER_OT_cell_menu(CellOperator, bpy.types.Operator):
    bl_idname = "bonemancer.cell_menu"
    bl_label = "Edit Cell"
    bl_description = "Change this cell's side, move it or clear it"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        cell = self.filled_cell(context)
        if cell is None:
            return {'CANCELLED'}
        tab = find_tab(get_rig(context.scene), self.tab)
        context.window_manager.popup_menu(lambda menu, _ctx: draw_cell_menu(menu.layout, tab, cell),
                                          title=cell.bone_name, icon='BONE_DATA')
        return {'FINISHED'}

    def execute(self, context):
        return {'CANCELLED'}   # only meaningful as a click


class BONEMANCER_OT_set_cell_side(CellOperator, bpy.types.Operator):
    bl_idname = "bonemancer.set_cell_side"
    bl_label = "Set Side"
    bl_description = "Colour this cell as a left, right or centre control"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    side: EnumProperty(items=[('LEFT', "Left", ""), ('RIGHT', "Right", ""), ('CENTER', "Centre", "")],
                       default='CENTER')

    def execute(self, context):
        cell = self.filled_cell(context)
        if cell is None:
            return {'CANCELLED'}
        cell.side = self.side
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_clear_cell(CellOperator, bpy.types.Operator):
    bl_idname = "bonemancer.clear_cell"
    bl_label = "Clear Cell"
    bl_description = "Take the bone off this cell. The bone itself is kept"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def execute(self, context):
        cell = self.filled_cell(context)
        if cell is None:
            return {'CANCELLED'}
        tab = find_tab(get_rig(context.scene), self.tab)
        settings = context.scene.bonemancer_settings
        if moving_cell(settings, get_rig(context.scene)) == cell:
            clear_move(settings)
        tab.cells.remove(next(i for i, c in enumerate(tab.cells) if c == cell))
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_start_move(CellOperator, bpy.types.Operator):
    bl_idname = "bonemancer.start_move"
    bl_label = "Move Cell"
    bl_description = "Pick this cell up, then click an empty cell to put it there"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        if self.filled_cell(context) is None:
            return {'CANCELLED'}
        settings = context.scene.bonemancer_settings
        settings.move_tab, settings.move_row, settings.move_column = self.tab, self.row, self.column
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_cancel_move(bpy.types.Operator):
    bl_idname = "bonemancer.cancel_move"
    bl_label = "Cancel Move"
    bl_description = "Put this cell back where it was"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        clear_move(context.scene.bonemancer_settings)
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_move_cell(CellOperator, bpy.types.Operator):
    bl_idname = "bonemancer.move_cell"
    bl_label = "Move Here"
    bl_description = "Move the picked-up cell here"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def execute(self, context):
        tab = self.editable_tab(context)
        if tab is None:
            return {'CANCELLED'}
        settings = context.scene.bonemancer_settings
        cell = moving_cell(settings, get_rig(context.scene))
        if cell is None or settings.move_tab != tab.name:
            clear_move(settings)
            self.report({'WARNING'}, "Pick a cell up with Move first")
            return {'CANCELLED'}
        if cell_at(tab, self.row, self.column) is not None:
            self.report({'WARNING'}, "That cell is taken")
            return {'CANCELLED'}
        cell.row, cell.column = self.row, self.column
        clear_move(settings)
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
        refusal = layout_edit_refusal(rig)
        if refusal:
            self.report({'WARNING'}, refusal)
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
        settings = context.scene.bonemancer_settings
        settings.layout_tab = self.name
        clear_move(settings)
        tag_addon_panels(context)
        return {'FINISHED'}
