# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators for the Shape Keys panel."""

import bpy
from bpy.props import StringProperty

from ..core.compat import get_anim_fcurves
from ..core.shape_keys import ensure_shape_keys_action, keyframes_at, scan_shape_keys_for_armature, tag_shape_key_editors
from ..core.utils import get_rig, path_key, tag_addon_panels


class BONEMANCER_OT_scan_shape_keys(bpy.types.Operator):
    bl_idname      = "bonemancer.scan_shape_keys"
    bl_label       = "Refresh Shape Keys"
    bl_description = ("Rebuild the list of meshes the rig deforms and their shape keys now. "
                      "It also refreshes on its own when meshes or shape keys change")
    bl_options     = {'REGISTER', 'UNDO'}

    def execute(self, context):
        arm = get_rig(context.scene)
        if not arm:
            self.report({'WARNING'}, "Select an armature first")
            return {'CANCELLED'}
        scan_shape_keys_for_armature(context.scene, arm)
        return {'FINISHED'}


class BONEMANCER_OT_toggle_shape_keyframe(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_shape_keyframe"
    bl_label  = "Toggle Shape Key Keyframe"
    bl_options = {'REGISTER', 'UNDO'}

    object_name:    StringProperty()
    shape_key_name: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if not obj or obj.type != 'MESH' or not obj.data.shape_keys:
            return {'CANCELLED'}

        frame   = context.scene.frame_current
        sk_data = obj.data.shape_keys
        if not sk_data.key_blocks.get(self.shape_key_name):
            self.report({'WARNING'}, f"Shape key '{self.shape_key_name}' not found; rescan the rig")
            return {'CANCELLED'}
        path    = f'key_blocks{path_key(self.shape_key_name)}.value'
        ensure_shape_keys_action(sk_data, obj.name)

        fcurves = get_anim_fcurves(sk_data.animation_data)
        fcu = next((fc for fc in fcurves if fc.data_path == path), None)
        if fcu and keyframes_at(fcu, frame):
            sk_data.keyframe_delete(data_path=path, frame=frame)
            tag_shape_key_editors(context)
            tag_addon_panels(context)
            return {'FINISHED'}

        sk_data.keyframe_insert(data_path=path, frame=frame)
        tag_shape_key_editors(context)
        return {'FINISHED'}
