# SPDX-License-Identifier: GPL-3.0-or-later
"""
Layout templates: ready-made Layout tabs for a generated Rigify human.

A template gives a tab's size, a body silhouette drawn under its empty cells,
and the cell of each control. Characters face the viewer, so right-side
controls sit on the left of the grid. Silhouettes ship with the add-on and are
never saved; a tab made from a template only stores the template's id.
"""

from typing import NamedTuple

from .layout import bone_exists, find_tab, side_from_name


class LayoutTemplate(NamedTuple):
    id: str
    tab: str
    columns: int
    rows: int
    silhouette: tuple   # one string per row; '#' is body
    cells: dict         # bone name -> (row, column)


def sided(cells, mirror):
    """
    Expand {name with '{side}': (row, column)} given for the right side into
    both sides; a left-side control sits in column mirror - column.
    """
    out = {}
    for name, (row, column) in cells.items():
        out[name.format(side="R")] = (row, column)
        out[name.format(side="L")] = (row, mirror - column)
    return out


# Body: 16 wide, mirrored around column 7 (left side column = 14 - right side column)
BODY = LayoutTemplate(
    id="RIGIFY_BODY", tab="Body", columns=16, rows=23,
    silhouette=(
        "......###.......",
        "......###.......",
        "......###.......",
        ".......#........",
        "...#########....",
        "..###########...",
        "..##.#####.##...",
        ".###.#####.###..",
        ".##..#####..##..",
        ".##..#####..##..",
        ".##..#####..##..",
        ".....#####......",
        "....#######.....",
        ".....##.##......",
        ".....##.##......",
        "....###.###.....",
        ".....##.##......",
        ".....##.##......",
        "....###.###.....",
        ".....##.##......",
        ".....##.##......",
        "................",
        ".......#........",
    ),
    cells={
        "head": (1, 7), "neck": (3, 7), "chest": (5, 7),
        "spine_fk.003": (6, 7), "spine_fk.002": (7, 7), "spine_fk.001": (8, 7), "spine_fk": (9, 7),
        "torso": (10, 7), "hips": (11, 7), "root": (22, 7),
        **sided({
            "shoulder.{side}": (4, 5), "breast.{side}": (6, 5),
            # Arm: FK on the inside, IK one column out
            "upper_arm_parent.{side}": (4, 3), "upper_arm_fk.{side}": (5, 4), "upper_arm_ik.{side}": (5, 3),
            "forearm_fk.{side}": (7, 3), "upper_arm_ik_target.{side}": (7, 1),
            "hand_fk.{side}": (9, 2), "hand_ik.{side}": (10, 1),
            # Leg: FK on the inside, IK one column out, extras beyond
            "thigh_parent.{side}": (12, 4), "thigh_ik.{side}": (12, 5), "thigh_fk.{side}": (12, 6),
            "thigh_ik_target.{side}": (15, 4), "shin_fk.{side}": (15, 6),
            "foot_spin_ik.{side}": (18, 4), "foot_ik.{side}": (18, 5), "foot_fk.{side}": (18, 6),
            "foot_heel_ik.{side}": (19, 5),
            "toe_ik.{side}": (20, 5), "toe_fk.{side}": (20, 6),
        }, 14),
    },
)


def finger(name, column):
    """A finger's controls in one column, tip at the top, master at the knuckle."""
    return {f"{name}.01.{{side}}.001": (0, column), f"{name}.03.{{side}}": (1, column),
            f"{name}.02.{{side}}": (2, column), f"{name}.01.{{side}}": (3, column),
            f"{name}.01_master.{{side}}": (4, column)}


# Hands: 16 wide, palms facing the viewer, thumbs out (left side column = 15 - right side column).
# 20 columns made cells too narrow to click in a default-width sidebar.
HANDS = LayoutTemplate(
    id="RIGIFY_HANDS", tab="Hands", columns=16, rows=9,
    silhouette=(
        "..####....####..",
        "..####....####..",
        "..####....####..",
        "######....######",
        "######....######",
        "######....######",
        ".#####....#####.",
        ".#####....#####.",
        "..###......###..",
    ),
    cells=sided({
        **finger("f_index", 2), **finger("f_middle", 3), **finger("f_ring", 4), **finger("f_pinky", 5),
        "thumb.01.{side}.001": (3, 0), "thumb.03.{side}": (4, 0), "thumb.02.{side}": (5, 0),
        "thumb.01.{side}": (6, 1), "thumb.01_master.{side}": (7, 1),
        "palm.{side}": (6, 3),
    }, 15),
)

# Face: 16 wide, front view, mirrored around column 7 like Body. Rigify's Face and
# Face (Primary) controls; the eye aim target sits between the eyes.
FACE = LayoutTemplate(
    id="RIGIFY_FACE", tab="Face", columns=16, rows=14,
    silhouette=(
        "..###########...",
        ".#############..",
        ".#############..",
        ".#############..",
        ".#############..",
        "###############.",
        ".#############..",
        ".#############..",
        "..###########...",
        "..###########...",
        "...#########....",
        "....#######.....",
        ".....#####......",
        "......###.......",
    ),
    cells={
        "eyes": (3, 7), "nose_master": (5, 7), "nose.002": (6, 7), "teeth.T": (7, 7), "lip.T": (8, 7),
        "tongue_master": (9, 7), "lip.B": (10, 7), "teeth.B": (11, 7), "chin": (12, 7), "jaw_master": (13, 7),
        **sided({
            "brow.T.{side}.002": (0, 3), "brow.T.{side}.001": (1, 1), "brow.T.{side}.003": (1, 5),
            "lid.T.{side}.002": (2, 3), "master_eye.{side}": (3, 1), "eye.{side}": (3, 3),
            "lid.B.{side}.002": (4, 3), "ear.{side}": (5, 0), "nose.{side}.001": (6, 6),
            "cheek.B.{side}.001": (7, 2), "lip.T.{side}.001": (8, 6), "lips.{side}": (9, 5),
            "lip.B.{side}.001": (10, 6),
        }, 14),
    },
)

TEMPLATES = (BODY, HANDS, FACE)


def find_template(template_id):
    return next((t for t in TEMPLATES if t.id == template_id), None)


def silhouette_cells(template):
    """The (row, column) cells the silhouette covers, the template's own cells included."""
    body = {(r, c) for r, line in enumerate(template.silhouette) for c, ch in enumerate(line) if ch == "#"}
    return body | set(template.cells.values())


def apply_templates(arm_obj, templates=TEMPLATES):
    """
    Add each template's tab if the rig has none of that name, then place every
    template control the rig has and the tab lacks, if its cell is empty.
    Existing cells are never moved, cleared or recoloured. Returns the number
    of controls placed.
    """
    placed = 0
    for template in templates:
        tab = find_tab(arm_obj, template.tab)
        if tab is None:
            tab = arm_obj.bonemancer_layout.add()
            tab.name, tab.columns, tab.rows, tab.template = (template.tab, template.columns, template.rows,
                                                            template.id)
        on_tab = {c.bone_name for c in tab.cells}
        taken = {(c.row, c.column) for c in tab.cells}
        for bone_name, (row, column) in template.cells.items():
            if (bone_name in on_tab or (row, column) in taken or not bone_exists(arm_obj, bone_name)
                    or row >= tab.rows or column >= tab.columns):
                continue
            cell = tab.cells.add()
            cell.bone_name, cell.row, cell.column, cell.side = bone_name, row, column, side_from_name(bone_name)
            taken.add((row, column))
            placed += 1
    return placed
