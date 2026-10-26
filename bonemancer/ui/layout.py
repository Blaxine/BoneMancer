# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing of the Actionable Bones layout: tab bar and cell grid."""

from ..core.layout import (active_bone_name, active_tab, bone_exists, bone_hidden_in_layout, cells_by_position,
                           layout_tabs)
from ..core.selection import bone_selected_in_viewport
from .common import hint

SIDE_ICONS = {'LEFT': 'COLLECTION_COLOR_05', 'RIGHT': 'COLLECTION_COLOR_01', 'CENTER': 'COLLECTION_COLOR_03'}
EMPTY_LAYOUT_HINT = "Lay out this rig's controls to pick them in one click."


def draw_layout(context, layout, rig):
    scene = context.scene
    settings = scene.bonemancer_settings
    tab = active_tab(scene, rig)
    if tab is None:
        hint(layout, context, EMPTY_LAYOUT_HINT)
        layout.operator("bonemancer.new_layout_tab", icon='ADD')
        return

    row = layout.row(align=True)
    tabs = row.row(align=True)
    for other in layout_tabs(rig):
        tabs.operator("bonemancer.show_layout_tab", text=other.name, depress=other == tab).name = other.name
    row.prop(settings, "edit_layout", text="", icon='GREASEPENCIL', toggle=True)

    draw_grid(layout, rig, tab, settings.edit_layout)
    # Cells have no text; name the bone the last click made active
    name = active_bone_name(rig)
    sub = layout.row()
    sub.active = False
    sub.label(text=name or "No active bone", icon='BONE_DATA')


def draw_grid(layout, rig, tab, editing):
    cells = cells_by_position(tab)
    grid = layout.grid_flow(row_major=True, columns=tab.columns, even_columns=True, even_rows=True, align=True)
    for row in range(tab.rows):
        for column in range(tab.columns):
            cell = cells.get((row, column))
            if cell:
                draw_cell(grid, rig, cell)
            elif editing:
                op = grid.operator("bonemancer.place_bone", text="", icon='BLANK1')
                op.tab, op.row, op.column = tab.name, row, column
            else:
                grid.operator("bonemancer.layout_blank", text="", icon='BLANK1', emboss=False)


def draw_cell(grid, rig, cell):
    name = cell.bone_name
    if not bone_exists(rig, name):
        grid.operator("bonemancer.missing_cell", text="", icon='ERROR')
    elif bone_hidden_in_layout(rig, name):
        grid.operator("bonemancer.hidden_cell", text="", icon=SIDE_ICONS[cell.side])
    else:
        op = grid.operator("bonemancer.pick_bone", text="", icon=SIDE_ICONS[cell.side],
                           depress=bone_selected_in_viewport(rig, name))
        op.bone_name = name
