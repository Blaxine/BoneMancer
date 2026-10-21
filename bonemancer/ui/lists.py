# SPDX-License-Identifier: GPL-3.0-or-later
"""The sidebar's lists."""

import bpy

from ..core.compat import get_anim_fcurves
from ..core.rig_check import RIG_CHECKS, constraint_problem, is_ignored, issue_fixed
from ..core.selection import bone_selected_in_viewport
from ..core.shape_keys import keyframes_at
from ..core.utils import get_rig, path_key
from .common import bone_name_button, plural


class BONEMANCER_UL_shape_key_meshes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.object_name, icon='MESH_DATA')
        count = row.row(align=True)
        count.alignment = 'RIGHT'
        count.active = False
        count.label(text=plural(len(item.shape_keys), "key"))


class BONEMANCER_UL_shape_keys(bpy.types.UIList):
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
            path = f'key_blocks{path_key(item.key_name)}.value'
            if any(keyframes_at(fc, context.scene.frame_current)
                   for fc in fcurves if fc.data_path == path):
                icon = 'KEY_DEHLT'

        op = row.operator("bonemancer.toggle_shape_keyframe", text="", icon=icon)
        op.object_name    = item.object_name
        op.shape_key_name = item.key_name


class BONEMANCER_UL_constraints(bpy.types.UIList):
    """Scrollable list of constraints with influence sliders, a warning button and Remove"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # --- Constraint validity check ---
            problem = constraint_problem(item)
            show_warning = bool(problem)
            tooltip_text = f"Constraint {problem}"

            # Name & influence
            row.label(text=item.name, icon='CONSTRAINT')
            row.prop(item, "influence", text="", slider=True)

            # Warning button on the far right
            if show_warning:
                op = row.operator(
                    "bonemancer.show_constraint_error",
                    text="",
                    icon='ERROR'
                )
                op.constraint_name = item.name
                op.error_message = tooltip_text

            # data is the pose bone whose constraints this list shows
            op = row.operator("bonemancer.remove_constraint", text="", icon='X', emboss=False)
            op.bone_name = data.name
            op.constraint_name = item.name

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='CONSTRAINT')


class BONEMANCER_UL_bone_picker(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon,
                  active_data, active_propname, index):
        rig = get_rig(context.scene)
        if rig and bone_selected_in_viewport(rig, item.name):
            # Selected in the viewport: drawn pressed, like the Bone Sets names
            bone_name_button(layout, item.name, True)
        else:
            layout.label(text=item.name, icon='BONE_DATA')


class BONEMANCER_UL_rig_issues(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        rig = get_rig(context.scene)
        fixed = issue_fixed(context, item)
        row = layout.row(align=True)
        row.active = not (fixed or is_ignored(rig, item))
        if fixed:
            row.label(text=f"{item.message} (fixed)", icon='CHECKMARK')
        else:
            row.label(text=item.message, icon=RIG_CHECKS.get(item.check, ("", 'ERROR', ()))[1])

    def filter_items(self, context, data, propname):
        issues = getattr(data, propname)
        if self.filter_name:
            flags = bpy.types.UI_UL_list.filter_items_by_name(
                self.filter_name, self.bitflag_filter_item, issues, "message")
        else:
            flags = [self.bitflag_filter_item] * len(issues)
        if not data.show_ignored:
            rig = get_rig(context.scene)
            flags = [0 if is_ignored(rig, issue) else flag for flag, issue in zip(flags, issues)]
        return flags, []
