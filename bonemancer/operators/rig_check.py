# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the Rig Check panel."""

import bpy
from bpy.props import IntProperty

from ..core.rig_check import LIBRARY_IGNORE_MESSAGE, LINKED_IGNORE_MESSAGE, get_issue, ignore_index, is_ignored, library_ignore, run_rig_check
from ..core.selection import select_bone_in_viewport, select_object_in_viewport
from ..core.utils import get_rig, rig_is_editable, tag_addon_panels


class BONEMANCER_OT_check_rig(bpy.types.Operator):
    bl_idname = "bonemancer.check_rig"
    bl_label = "Check Rig"
    bl_description = ("List problems with the picked rig. Nothing in the rig is changed. "
                      "Check again after fixing things to update the list")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    def execute(self, context):
        rig = get_rig(context.scene)
        if not rig:
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        count = run_rig_check(context, rig)
        self.report({'INFO'}, f"{count} issue{'s' if count != 1 else ''} found" if count else "No issues found")
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_select_issue(bpy.types.Operator):
    bl_idname = "bonemancer.select_issue"
    bl_label = "Select"
    bl_description = "Select the bone or object this issue is about"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        issue = get_issue(context.scene, self.index)
        if not issue:
            return {'CANCELLED'}
        if issue.bone:
            error = select_bone_in_viewport(context, get_rig(context.scene), issue.bone)
        else:
            error = select_object_in_viewport(context, bpy.data.objects.get(issue.object_name))
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}


class BONEMANCER_OT_ignore_issue(bpy.types.Operator):
    bl_idname = "bonemancer.ignore_issue"
    bl_label = "Ignore"
    bl_description = "Stop listing this issue for this rig. Saved with the rig"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    @classmethod
    def description(cls, context, properties):
        rig = get_rig(context.scene)
        return LINKED_IGNORE_MESSAGE if rig and not rig_is_editable(rig) else cls.bl_description

    def execute(self, context):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, self.index)
        if not rig or not issue:
            return {'CANCELLED'}
        if not rig_is_editable(rig):
            self.report({'ERROR'}, LINKED_IGNORE_MESSAGE)
            return {'CANCELLED'}
        if not is_ignored(rig, issue):
            entry = rig.bonemancer_ignored_issues.add()
            entry.check = issue.check
            entry.bone = issue.bone
            entry.detail = issue.detail
        tag_addon_panels(context)
        return {'FINISHED'}


class BONEMANCER_OT_unignore_issue(bpy.types.Operator):
    bl_idname = "bonemancer.unignore_issue"
    bl_label = "Stop Ignoring"
    bl_description = "List this issue again"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    @classmethod
    def description(cls, context, properties):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, properties.index)
        if rig and not rig_is_editable(rig):
            return LINKED_IGNORE_MESSAGE
        if issue and library_ignore(rig, issue):
            return LIBRARY_IGNORE_MESSAGE
        return cls.bl_description

    def execute(self, context):
        rig = get_rig(context.scene)
        issue = get_issue(context.scene, self.index)
        found = ignore_index(rig, issue) if issue else -1
        if found < 0:
            return {'CANCELLED'}
        if not rig_is_editable(rig):
            self.report({'ERROR'}, LINKED_IGNORE_MESSAGE)
            return {'CANCELLED'}
        if library_ignore(rig, issue):
            self.report({'ERROR'}, LIBRARY_IGNORE_MESSAGE)
            return {'CANCELLED'}
        try:
            rig.bonemancer_ignored_issues.remove(found)
        except TypeError:
            # Blender refuses to remove items an override inherited
            self.report({'ERROR'}, "This ignore can't be removed from an overridden rig")
            return {'CANCELLED'}
        tag_addon_panels(context)
        return {'FINISHED'}
