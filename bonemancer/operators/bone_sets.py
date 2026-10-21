# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators on bone sets."""

import bpy
from bpy.props import StringProperty, BoolProperty, CollectionProperty, EnumProperty

from ..core.compat import set_hidden
from ..core.selection import selected_bone_names
from ..core.utils import find_set, get_rig, keep_enum_items, library_set, rig_is_editable, rig_sets, set_is_hidden
from ..properties import BONEMANCER_PG_ImportItem


def get_set_items(self, context):
    groups = rig_sets(get_rig(context.scene))
    return keep_enum_items("groups", [(g.name, g.name, "") for g in groups])


class BONEMANCER_OT_toggle_set(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_set"
    bl_label = "Toggle Bone Set Visibility"
    bl_description = "Hide every bone in this bone set, or show them all if all are hidden"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()

    def execute(self, context):
        sc = context.scene
        obj = get_rig(sc)
        group = find_set(sc, self.set_name)
        if not rig_is_editable(obj) or not group:
            self.report({'WARNING'}, f"Bone set '{self.set_name}' not found")
            return {'CANCELLED'}
        # Mixed visibility hides all; only a fully hidden group is shown again
        hide = not set_is_hidden(obj, group)
        for b in group.bones:
            set_hidden(obj.pose.bones.get(b.bone_name), hide)
        return {'FINISHED'}


class BONEMANCER_OT_remove_bone_from_set(bpy.types.Operator):
    bl_idname = "bonemancer.remove_bone_from_set"
    bl_label = "Remove Bone from Set"
    bl_description = "Remove this bone from the bone set (the bone itself is kept)"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()
    bone_name: bpy.props.StringProperty()

    def execute(self, context):
        arm = get_rig(context.scene)
        group = find_set(context.scene, self.set_name)
        if not group or not rig_is_editable(arm):
            self.report({'WARNING'}, f"Bone set '{self.set_name}' not found")
            return {'CANCELLED'}
        lib = library_set(arm, self.set_name)
        if lib and any(b.bone_name == self.bone_name for b in lib.bones):
            self.report({'ERROR'}, f"'{self.bone_name}' is in '{self.set_name}' in the rig's library file; remove it there")
            return {'CANCELLED'}
        for i, b in enumerate(group.bones):
            if b.bone_name == self.bone_name:
                try:
                    group.bones.remove(i)
                except TypeError:
                    self.report({'ERROR'}, "This bone can't be removed from an overridden rig")
                    return {'CANCELLED'}
                break
        return {'FINISHED'}


class BONEMANCER_OT_remove_set(bpy.types.Operator):
    bl_idname = "bonemancer.remove_set"
    bl_label = "Remove Bone Set"
    bl_description = "Delete this bone set (the bones themselves are kept)"
    bl_options = {'REGISTER', 'UNDO'}
    set_name: StringProperty()

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        arm = get_rig(context.scene)
        if not rig_is_editable(arm):
            return {'CANCELLED'}
        if library_set(arm, self.set_name):
            self.report({'ERROR'}, f"Bone set '{self.set_name}' comes from the rig's library file; remove it there")
            return {'CANCELLED'}
        groups = arm.bonemancer_sets
        for i, g in enumerate(groups):
            if g.name == self.set_name:
                try:
                    groups.remove(i)
                except TypeError:
                    self.report({'ERROR'}, "This bone set can't be removed from an overridden rig")
                    return {'CANCELLED'}
                return {'FINISHED'}
        return {'CANCELLED'}


class BONEMANCER_OT_add_bone_to_set(bpy.types.Operator):
    bl_idname = "bonemancer.add_bone_to_set"
    bl_label = "Add Bone to Bone Set"
    bl_description = "Add this bone to a new or existing bone set"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: StringProperty(options={'HIDDEN'})
    # Add every selected bone of the picked rig instead of bone_name
    use_selected: BoolProperty(name="Selected Bones", default=False, options={'HIDDEN', 'SKIP_SAVE'})
    set_enum: EnumProperty(name="Bone Set", items=get_set_items)
    create_new: BoolProperty(name="New Bone Set", default=False)
    new_set_name: StringProperty(name="Bone Set Name", default="")

    @classmethod
    def poll(cls, context):
        return get_rig(context.scene) is not None

    @classmethod
    def description(cls, context, properties):
        if properties.use_selected:
            return "Add every selected bone to a new or existing bone set"
        return cls.bl_description

    def bone_names(self, context):
        if self.use_selected:
            return selected_bone_names(get_rig(context.scene))
        return [self.bone_name]

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


    def draw(self, context):
        layout = self.layout
        if self.use_selected:
            names = self.bone_names(context)
            layout.label(text=f"{len(names)} selected bone{'s' if len(names) != 1 else ''}", icon='GROUP_BONE')
        else:
            layout.label(text=self.bone_name, icon='BONE_DATA')
        layout.prop(self, "create_new")
        if self.create_new:
            layout.prop(self, "new_set_name", text="Name")
        else:
            layout.prop(self, "set_enum", text="Bone Set")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        bone_names = self.bone_names(context)
        if not bone_names:
            self.report({'WARNING'}, "Select some bones first")
            return {'CANCELLED'}

        # 1) Groups live on the rig object itself
        groups = arm_obj.bonemancer_sets

        # 2) Figure out which group to target
        if self.create_new:
            name = self.new_set_name.strip()
            if not name:
                self.report({'ERROR'}, "Bone set name cannot be empty")
                return {'CANCELLED'}
        else:
            name = self.set_enum
            if not name:
                self.report({'ERROR'}, "No bone set to add to; create a new one")
                return {'CANCELLED'}

        # 3) Find or make that group
        group = next((g for g in groups if g.name == name), None)
        if not group:
            group = groups.add()
            group.name = name

        # 4) Add the bones that are missing, in armature order
        present = {b.bone_name for b in group.bones}
        added = [name for name in bone_names if name not in present]
        for name in added:
            group.bones.add().bone_name = name

        if len(bone_names) == 1 and not added:
            self.report({'INFO'}, f"'{bone_names[0]}' already in '{group.name}'")
        elif len(bone_names) > 1:
            skipped = len(bone_names) - len(added)
            self.report({'INFO'}, f"Added {len(added)} bone{'s' if len(added) != 1 else ''} to '{group.name}'"
                                  + (f"; {skipped} already in it" if skipped else ""))

        return {'FINISHED'}


class BONEMANCER_OT_toggle_set_foldout(bpy.types.Operator):
    bl_idname = "bonemancer.toggle_set_foldout"
    bl_label = "Expand Bone Set"
    bl_description = "Expand or collapse this bone set"

    set_name: StringProperty()

    def execute(self, context):
        # Find matching group and flip its flag
        grp = find_set(context.scene, self.set_name)
        if grp:
            grp.show_expanded = not grp.show_expanded
            return {'FINISHED'}
        return {'CANCELLED'}


def native_collections(arm):
    """(collection, depth) for every bone collection of arm, parents before children."""
    def walk(colls, depth):
        for coll in colls:
            yield coll, depth
            yield from walk(coll.children, depth + 1)
    return list(walk(arm.collections, 0))


class BONEMANCER_OT_import_bone_collections(bpy.types.Operator):
    bl_idname = "bonemancer.import_bone_collections"
    bl_label = "Import Bone Collections"
    bl_description = ("Create a bone set from each ticked bone collection of the rig. "
                      "Sets with the same name gain the missing bones; nothing is removed or reordered")
    bl_options = {'REGISTER', 'UNDO'}

    items: CollectionProperty(type=BONEMANCER_PG_ImportItem, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        arm_obj = get_rig(context.scene)
        if arm_obj is None:
            return False
        if not len(arm_obj.data.collections_all):
            cls.poll_message_set("The rig has no bone collections")
            return False
        return True

    def fill_items(self, arm_obj):
        self.items.clear()
        for coll, depth in native_collections(arm_obj.data):
            item = self.items.add()
            item.name = coll.name
            item.bone_count = len(coll.bones)
            item.depth = depth
            # Empty collections (often just parents of others) start unticked
            item.use = item.bone_count > 0

    def invoke(self, context, event):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        self.fill_items(arm_obj)
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Bone collections to import as bone sets:")
        col = layout.column(align=True)
        for item in self.items:
            row = col.row(align=True)
            if item.depth:
                row.separator(factor=2.0 * item.depth)
            row.prop(item, "use", text=item.name)
            count = row.row()
            count.alignment = 'RIGHT'
            count.label(text=f"{item.bone_count} bone{'' if item.bone_count == 1 else 's'}")

    def execute(self, context):
        arm_obj = get_rig(context.scene)
        if not rig_is_editable(arm_obj):
            self.report({'ERROR'}, "Rig is linked from a library; make a library override first")
            return {'CANCELLED'}
        if not len(self.items):
            # Called without the dialog (scripts): import every non-empty collection
            self.fill_items(arm_obj)

        native = {coll.name: coll for coll in arm_obj.data.collections_all}
        sets_created = bones_added = 0
        for item in self.items:
            coll = native.get(item.name)
            if not item.use or coll is None:
                continue
            bone_set = next((s for s in arm_obj.bonemancer_sets if s.name == coll.name), None)
            if bone_set is None:
                bone_set = arm_obj.bonemancer_sets.add()
                bone_set.name = coll.name
                sets_created += 1
            present = {entry.bone_name for entry in bone_set.bones}
            for bone in coll.bones:
                if bone.name not in present:
                    bone_set.bones.add().bone_name = bone.name
                    bones_added += 1

        self.report({'INFO'}, f"Bone sets created: {sets_created}, bones added: {bones_added}")
        return {'FINISHED'}
