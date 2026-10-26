# SPDX-License-Identifier: GPL-3.0-or-later
"""The Bonemancer tab in the 3D Viewport sidebar."""

from . import layout, lists, panels

classes = (
    lists.BONEMANCER_UL_constraints,
    lists.BONEMANCER_UL_bone_picker,
    lists.BONEMANCER_UL_shape_key_meshes,
    lists.BONEMANCER_UL_shape_keys,
    lists.BONEMANCER_UL_rig_issues,
    layout.BONEMANCER_MT_layout_tab,
    # Panels show in the order they are registered
    panels.BONEMANCER_PT_rig,
    panels.BONEMANCER_PT_actionable_bones,
    panels.BONEMANCER_PT_bones,
    panels.BONEMANCER_PT_bone_sets,
    panels.BONEMANCER_PT_rig_check,
    panels.BONEMANCER_PT_shape_keys,
)
