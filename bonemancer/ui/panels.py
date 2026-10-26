# SPDX-License-Identifier: GPL-3.0-or-later
"""The sidebar panels, in the order they appear."""

import bpy

from ..core.rig_check import get_issue, is_ignored, visible_issues
from ..core.selection import selected_bone_names
from ..core.utils import get_rig
from .common import NO_RIG_HINT, hint, plural
from .draw import draw_bone_set, draw_bone_settings, draw_issue_details
from .layout import draw_layout


class BONEMANCER_PT_shape_keys(bpy.types.Panel):
    bl_label      = "Shape Keys"
    bl_idname     = "BONEMANCER_PT_shape_keys"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category   = 'Bonemancer'
    bl_options    = {'DEFAULT_CLOSED'}

    def draw_header_preset(self, context):
        # The list refreshes on its own; this is for when it seems out of date
        self.layout.operator("bonemancer.scan_shape_keys", text="", icon='FILE_REFRESH', emboss=False)

    def draw(self, context):
        layout   = self.layout
        settings = context.scene.bonemancer_shape_keys
        if not get_rig(context.scene):
            hint(layout, context, NO_RIG_HINT)
            return
        if not settings.object_groups:
            hint(layout, context, "No mesh that follows this rig has shape keys yet. "
                                  "They show up here as soon as one does.")
            return

        layout.template_list(
            "BONEMANCER_UL_shape_key_meshes", "",
            settings, "object_groups",
            settings, "object_groups_index",
            rows=min(max(len(settings.object_groups), 2), 4)
        )
        # The highlighted mesh's shape keys
        idx = settings.object_groups_index
        if 0 <= idx < len(settings.object_groups):
            grp = settings.object_groups[idx]
            if not grp.shape_keys:
                hint(layout, context, f"{grp.object_name} only has its Basis key.")
                return
            layout.template_list(
                "BONEMANCER_UL_shape_keys", "",
                grp, "shape_keys",
                grp, "shape_keys_index",
                rows=min(max(len(grp.shape_keys), 3), 8)
            )


class BONEMANCER_PT_rig(bpy.types.Panel):
    bl_label = "Rig"
    bl_idname = "BONEMANCER_PT_rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if not any(obj.type == 'ARMATURE' for obj in scene.objects):
            hint(layout, context, "This scene has no armature yet. Add one to get started.")
            layout.operator("object.armature_add", text="Add Armature", icon='ADD')
            return
        layout.prop(scene, "bonemancer_rig", text="Armature")
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, "Pick the armature you want to work on. Clicking one in the viewport picks it too.")
            return
        # Object Properties > Viewport Display > In Front: draw the rig over its meshes
        layout.prop(rig, "show_in_front", text="In Front")


class BONEMANCER_PT_actionable_bones(bpy.types.Panel):
    bl_label = "Actionable Bones"
    bl_idname = "BONEMANCER_PT_actionable_bones"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        rig = get_rig(context.scene)
        if not rig:
            hint(self.layout, context, NO_RIG_HINT)
            return
        draw_layout(context, self.layout, rig)


class BONEMANCER_PT_bones(bpy.types.Panel):
    bl_label = "Bones"
    bl_idname = "BONEMANCER_PT_bones"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return
        settings = scene.bonemancer_settings
        layout.template_list(
            "BONEMANCER_UL_bone_picker", "",
            settings, "bone_selection",
            settings, "bone_selection_index",
            rows=6,
        )

        count = len(selected_bone_names(rig))
        row = layout.row()
        row.scale_y = 1.3
        row.enabled = count > 0
        text = f"Add {count} Selected to a Bone Set" if count else "Select Bones to Add Them to a Bone Set"
        row.operator("bonemancer.add_bone_to_set", text=text, icon='ADD').use_selected = True

        # Actions for the highlighted bone, instead of icons on every row
        idx = settings.bone_selection_index
        if 0 <= idx < len(settings.bone_selection):
            name = settings.bone_selection[idx].name
            box = layout.box()
            box.label(text=name, icon='BONE_DATA')
            row = box.row(align=True)
            row.operator("bonemancer.rename_bone", text="Rename", icon='GREASEPENCIL').bone_name = name
            row.operator("bonemancer.show_bone_relations", text="Relations", icon='ORIENTATION_PARENT').bone_name = name
            draw_bone_settings(box, rig, name)


class BONEMANCER_PT_bone_sets(bpy.types.Panel):
    bl_label = "Bone Sets"
    bl_idname = "BONEMANCER_PT_bone_sets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'

    def draw(self, context):
        layout = self.layout
        rig = get_rig(context.scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return
        if not rig.bonemancer_sets:
            hint(layout, context, "Bone Sets keep the bones you use often in one place. "
                                  "Add bones from the Bones panel, or start from the rig's bone collections.")
            layout.operator("bonemancer.import_bone_collections", icon='IMPORT')
            return
        for grp in rig.bonemancer_sets:
            draw_bone_set(context, layout, rig, grp)
        layout.operator("bonemancer.import_bone_collections", icon='IMPORT')


class BONEMANCER_PT_rig_check(bpy.types.Panel):
    bl_label = "Rig Check"
    bl_idname = "BONEMANCER_PT_rig_check"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bonemancer'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header_preset(self, context):
        results = context.scene.bonemancer_rig_check
        if results.has_run and get_rig(context.scene):
            count = len(visible_issues(context.scene))
            self.layout.label(text=str(count), icon='ERROR' if count else 'CHECKMARK')

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rig = get_rig(scene)
        if not rig:
            hint(layout, context, NO_RIG_HINT)
            return

        results = scene.bonemancer_rig_check
        row = layout.row()
        row.scale_y = 1.3
        row.operator("bonemancer.check_rig", text="Check Again" if results.has_run else "Check Rig", icon='VIEWZOOM')
        if not results.has_run:
            hint(layout, context, "Looks for common rigging mistakes, like broken constraints or "
                                  "bones without weights. Nothing in the rig is changed.")
            return
        if results.python_drivers:
            hint(layout, context,
                 f"{plural(results.python_drivers, 'Python driver')} can't be checked while "
                 "Auto Run Python Scripts is off.", 'SCRIPT')

        issues = visible_issues(scene)
        ignored = len(results.issues) - len(issues)
        if issues:
            layout.label(text=f"{plural(len(issues), 'issue')} found", icon='ERROR')
        else:
            layout.label(text="No issues found", icon='CHECKMARK')
        if ignored:
            layout.prop(results, "show_ignored", text=f"Show Ignored ({ignored})")
        if not issues and not (ignored and results.show_ignored):
            return
        layout.template_list(
            "BONEMANCER_UL_rig_issues", "",
            results, "issues",
            results, "issues_index",
            rows=5,
        )
        index = results.issues_index
        issue = get_issue(scene, index)
        if issue and (results.show_ignored or not is_ignored(rig, issue)):
            draw_issue_details(layout.box(), context, rig, issue, index)
