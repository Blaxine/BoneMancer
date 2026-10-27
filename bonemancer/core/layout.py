# SPDX-License-Identifier: GPL-3.0-or-later
"""
Actionable Bones: a rig's Layout of tabs and cells.

A Layout tab is a grid; each cell holds one bone and a side tag. A bone sits
at most once on a tab, but may sit on several tabs. Cells store names only.
"""

import bpy

from .compat import is_hidden
from .utils import live_bones

SIDE_ITEMS = [('LEFT', "Left", ""), ('RIGHT', "Right", ""), ('CENTER', "Centre", "")]


def layout_tabs(arm_obj):
    return arm_obj.bonemancer_layout if arm_obj else ()


def find_tab(arm_obj, name):
    return next((tab for tab in layout_tabs(arm_obj) if tab.name == name), None)


def active_tab(scene, arm_obj):
    """The tab the panel shows: the one named in the scene settings, else the first."""
    tabs = layout_tabs(arm_obj)
    if not len(tabs):
        return None
    return find_tab(arm_obj, scene.bonemancer_settings.layout_tab) or tabs[0]


def cell_at(tab, row, column):
    return next((c for c in tab.cells if c.row == row and c.column == column), None)


def cells_by_position(tab):
    return {(c.row, c.column): c for c in tab.cells}


def active_bone_name(arm_obj):
    """The armature's active bone (edit bone in Edit Mode), or ''."""
    if not arm_obj or arm_obj.type != 'ARMATURE':
        return ""
    bone = live_bones(arm_obj).active
    return bone.name if bone else ""


def side_from_name(name):
    """LEFT or RIGHT for names Blender can mirror (arm.L, Left_arm, eyeLeft...), else CENTER."""
    flipped = bpy.utils.flip_name(name)
    if flipped == name:
        return 'CENTER'
    # The first character that changes is the side marker's: L/l or R/r
    i = next(i for i, (a, b) in enumerate(zip(name, flipped)) if a != b)
    return 'LEFT' if name[i] in "Ll" else 'RIGHT'


LAYOUT_LOCKED_MESSAGE = "The layout belongs to the rig's file; open it there to edit"


def layout_is_editable(arm_obj):
    """Only a rig in its own file: on an override the layout comes from the library file."""
    return arm_obj is not None and arm_obj.library is None and arm_obj.override_library is None


def layout_edit_refusal(arm_obj):
    """Why arm_obj's layout can't be edited, or '' if it can."""
    if arm_obj is None:
        return "Pick an armature first"
    return "" if layout_is_editable(arm_obj) else LAYOUT_LOCKED_MESSAGE


def bone_hidden_in_layout(arm_obj, bone_name):
    """
    True if the bone is hidden in the viewport: its own Hide flag, or it is in
    bone collections and none of them is visible (their parents included).
    """
    bone = live_bones(arm_obj).get(bone_name)
    if bone is None:
        return False
    hidden = bone.hide if arm_obj.mode == 'EDIT' else is_hidden(arm_obj.pose.bones.get(bone_name))
    collections = bone.collections
    return hidden or (len(collections) > 0 and not any(c.is_visible_effectively for c in collections))


def bone_exists(arm_obj, bone_name):
    return live_bones(arm_obj).get(bone_name) is not None


def rename_layout_cells(arm_obj, old_name, new_name):
    """Follow a bone rename on every tab of the rig's own layout."""
    if not layout_is_editable(arm_obj):
        return
    for tab in arm_obj.bonemancer_layout:
        for cell in tab.cells:
            if cell.bone_name == old_name:
                cell.bone_name = new_name


def tab_name_refusal(arm_obj, name, current=None):
    """Why name can't be given to a tab (current is the tab being renamed), or ''."""
    if not name:
        return "Give the tab a name"
    if (current is None or name != current.name) and find_tab(arm_obj, name):
        return f"A tab named '{name}' already exists"
    return ""


def add_tab(arm_obj, name, columns, rows, template=""):
    tab = arm_obj.bonemancer_layout.add()
    tab.name, tab.columns, tab.rows, tab.template = name, columns, rows, template
    return tab


def moving_cell(settings, arm_obj):
    """The cell a pending Move picked up, or None."""
    tab = find_tab(arm_obj, settings.move_tab) if settings.move_tab else None
    return cell_at(tab, settings.move_row, settings.move_column) if tab else None


def clear_move(settings):
    settings.move_tab = ""


def reset_layout_session(settings):
    """Edit Layout and a pending Move don't outlive the file or the picked rig."""
    settings.edit_layout = False
    clear_move(settings)


def place_bone(tab, row, column, bone_name):
    """Put bone_name in the cell, moving it if it's elsewhere on the tab; returns the cell."""
    for i, cell in enumerate(tab.cells):
        if cell.bone_name == bone_name and (cell.row, cell.column) != (row, column):
            tab.cells.remove(i)
            break
    cell = cell_at(tab, row, column)
    if cell is None:
        cell = tab.cells.add()
        cell.row, cell.column = row, column
    if cell.bone_name != bone_name:
        cell.bone_name = bone_name
        cell.side = side_from_name(bone_name)
    return cell
