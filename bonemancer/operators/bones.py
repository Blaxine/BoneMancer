# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators on single bones."""

import bpy
from bpy.props import StringProperty, IntProperty, EnumProperty

from ..core.compat import toggle_hidden
from ..core.layout import rename_layout_cells
from ..core.renaming import count_bone_references, rename_set_entries, update_driver_variable_paths
from ..core.rig_check import rename_ignore_entries
from ..core.selection import armature_bone_names, select_bone_in_viewport, update_bone_list
from ..core.utils import get_rig, rig_is_editable


class BONEMANCER_OT_show_bone_relations(bpy.types.Operator):
    bl_idname = "bonemancer.show_bone_relations"
    bl_label = "Show Bone Relations"
    bl_description = "Display the selected bone’s parent and children in a dialog"
    bl_options = {'REGISTER', 'INTERNAL'}

    bone_name: StringProperty(name="Bone Name")  # Passed from UIList row

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return (
            get_rig(scene) is not None and
            len(scene.bonemancer_settings.bone_selection) > 0
        )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        armature_obj = get_rig(context.scene)

        if not armature_obj:
            layout.label(text="Armature not found")
            return

        bone = armature_obj.data.bones.get(self.bone_name)
        if not bone:
            layout.label(text=f"Bone '{self.bone_name}' not found")
            return

        layout.label(text=f"Bone: {bone.name}", icon='BONE_DATA')

        # Parent
        if bone.parent:
            layout.label(text=f"Parent: {bone.parent.name}")
        else:
            layout.label(text="Parent: None")

        # Children
        if bone.children:
            layout.label(text="Children:")
            for child in bone.children:
                layout.label(text=f"  • {child.name}")
        else:
            layout.label(text="Children: None")

    def execute(self, context):
        return {'FINISHED'}


class BONEMANCER_OT_select_bone(bpy.types.Operator):
    bl_idname = "bonemancer.select_bone"
    bl_label  = "Select Bone"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        error = select_bone_in_viewport(context, get_rig(context.scene), self.bone_name)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}
        return {'FINISHED'}


class BONEMANCER_OT_toggle_bone(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_bone"
    bl_label = "Toggle Bone"
    bl_options = {'REGISTER', 'UNDO'}
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = get_rig(context.scene)
        if not rig_is_editable(obj):
            self.report({'WARNING'}, "No editable armature")
            return {'CANCELLED'}
        toggle_hidden(obj.pose.bones.get(self.bone_name))
        return {'FINISHED'}


class BONEMANCER_OT_rename_bone(bpy.types.Operator):
    bl_idname = "bonemancer.rename_bone"
    bl_label = "Rename Bone"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name:  StringProperty()

    mode: EnumProperty(
        name="Mode",
        items=[
            ('EXACT',   "Exact",   "Type the full new name"),
            ('PREFIX',  "Prefix",  "Add text before the old name"),
            ('SUFFIX',  "Suffix",  "Add text after the old name"),
            ('REPLACE', "Replace", "Find & replace in the old name"),
        ],
        default='EXACT'
    )

    # Exact
    new_name: StringProperty(name="New Bone Name", default="")

    # Prefix presets + custom
    preset_prefix: EnumProperty(
        name="Preset",
        items=[
            ('NONE',   "None",   "No preset prefix"),
            ('DEF',    "DEF_",   "Default prefix"),
            ('ORG',    "ORG_",   "Original prefix"),
            ('MCH',    "MCH_",   "Match prefix"),
            ('CUSTOM', "Custom", "Type your own prefix"),
        ],
        default='NONE'
    )
    affix_text: StringProperty(name="Custom Prefix", default="")

    # Suffix
    suffix_text: StringProperty(name="Text", default="")

    # Replace
    find_text:    StringProperty(name="Find",    default="")
    replace_text: StringProperty(name="Replace", default="")

    # Preview + counts
    preview:            StringProperty(name="Preview", default="")
    drivers_count:      IntProperty(default=0)
    constraints_count:  IntProperty(default=0)

    def invoke(self, context, event):
        # Initialize fields
        self.new_name       = self.bone_name
        self.preset_prefix  = 'NONE'
        self.affix_text     = ""
        self.suffix_text    = ""
        self.find_text      = ""
        self.replace_text   = ""
        self.preview        = ""
        self.mode           = 'EXACT'

        # Count drivers / constraints pointing at this bone (Blender retargets them)
        arm_obj = get_rig(context.scene)
        if arm_obj:
            self.drivers_count, self.constraints_count = count_bone_references(arm_obj, self.bone_name)
        else:
            self.drivers_count = self.constraints_count = 0

        # Compute initial preview
        self.update_preview()
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)

        if self.mode == 'EXACT':
            layout.prop(self, "new_name")

        elif self.mode == 'PREFIX':
            layout.prop(self, "preset_prefix", text="Preset")
            if self.preset_prefix == 'CUSTOM':
                layout.prop(self, "affix_text", text="Custom Prefix")

        elif self.mode == 'SUFFIX':
            layout.prop(self, "suffix_text", text="Text")

        else:  # REPLACE
            layout.prop(self, "find_text")
            layout.prop(self, "replace_text")

        layout.separator()
        layout.label(text=f"{self.drivers_count} driver(s) will update")
        layout.label(text=f"{self.constraints_count} constraint(s) will update")
        layout.separator()
        layout.label(text="Result Preview:")
        error = self.validate(context)
        layout.box().label(text=error or self.preview, icon='ERROR' if error else 'BONE_DATA')

    def update_preview(self):
        name = self.bone_name

        if self.mode == 'EXACT':
            out = self.new_name

        elif self.mode == 'PREFIX':
            # decide which prefix to use
            if self.preset_prefix == 'DEF':
                prefix = "DEF_"
            elif self.preset_prefix == 'ORG':
                prefix = "ORG_"
            elif self.preset_prefix == 'MCH':
                prefix = "MCH_"
            elif self.preset_prefix == 'CUSTOM':
                prefix = self.affix_text
            else:
                prefix = ""
            out = prefix + name

        elif self.mode == 'SUFFIX':
            out = name + self.suffix_text

        else:  # REPLACE
            # An empty Find would insert the replacement between every character
            out = name.replace(self.find_text, self.replace_text) if self.find_text else name

        self.preview = out

    def validate(self, context):
        """Return an error message for the current preview, or ''."""
        arm_obj = get_rig(context.scene)
        if not arm_obj:
            return "No valid armature selected"
        if arm_obj.data.library or arm_obj.data.override_library:
            return "Bones of a linked/overridden rig can't be renamed"
        if self.mode == 'REPLACE' and not self.find_text:
            return "Find text is empty"
        if not self.preview.strip():
            return "New name is empty"
        if self.preview != self.bone_name and self.preview in armature_bone_names(arm_obj):
            return f"A bone named '{self.preview}' already exists"
        return ""

    def execute(self, context):
        # 1) Compute the final name from your preview logic
        self.update_preview()
        error = self.validate(context)
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        new_name = self.preview
        if new_name == self.bone_name:
            return {'FINISHED'}

        # 2) Rename the bone in the layer that is live in the current mode
        arm_obj = get_rig(context.scene)
        bones = arm_obj.data.edit_bones if arm_obj.mode == 'EDIT' else arm_obj.data.bones
        bone = bones.get(self.bone_name)
        if not bone:
            self.report({'ERROR'}, f"Bone '{self.bone_name}' not found")
            return {'CANCELLED'}

        bone.name = new_name
        new_name = bone.name  # Blender may still adjust it (e.g. length limit)

        # 3) Update group entries, driver variables on this rig, and the picker
        rename_set_entries(arm_obj, self.bone_name, new_name)
        rename_ignore_entries(arm_obj, self.bone_name, new_name)
        rename_layout_cells(arm_obj, self.bone_name, new_name)
        update_driver_variable_paths(arm_obj, self.bone_name, new_name)
        update_bone_list(context.scene)
        arm_obj.update_tag()

        return {'FINISHED'}

    def check(self, context):
        # Live-preview on any property change
        self.update_preview()
        return True
