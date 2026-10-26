# SPDX-License-Identifier: GPL-3.0-or-later
"""
Actionable Bones: a rig's Layout of tabs and cells.

A Layout tab is a grid; each cell holds one bone and a side tag. A bone sits
at most once on a tab, but may sit on several tabs. Cells store names only.
"""

import bpy


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
    bone = arm_obj.data.edit_bones.active if arm_obj.mode == 'EDIT' else arm_obj.data.bones.active
    return bone.name if bone else ""


def side_from_name(name):
    """LEFT or RIGHT for names Blender can mirror (arm.L, Left_arm, eyeLeft...), else CENTER."""
    flipped = bpy.utils.flip_name(name)
    if flipped == name:
        return 'CENTER'
    # The first character that changes is the side marker's: L/l or R/r
    i = next(i for i, (a, b) in enumerate(zip(name, flipped)) if a != b)
    return 'LEFT' if name[i] in "Ll" else 'RIGHT'


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
