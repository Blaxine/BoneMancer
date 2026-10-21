# SPDX-License-Identifier: GPL-3.0-or-later
"""Data the add-on stores in .blend files."""

import bpy
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty, CollectionProperty, PointerProperty
from bpy.types import PropertyGroup

from .core.selection import on_armature_change, on_picker_index
from .core.shape_keys import set_shape_key_value
from .core.utils import armature_poll


class BONEMANCER_PG_SetBone(PropertyGroup):
    bone_name: StringProperty(name="Bone Name", override={'LIBRARY_OVERRIDABLE'})
    show_custom_props: BoolProperty(
        name="Show Custom Props",
        default=False,
        description="Expand the custom properties of this bone",
        override={'LIBRARY_OVERRIDABLE'}
    )
    show_constraints: BoolProperty(
        name="Show Constraints",
        default=False,
        description="Expand the constraints of this bone",
        override={'LIBRARY_OVERRIDABLE'}
    )
    show_details: BoolProperty(
        name="Show Details",
        default=False,
        description="Show this bone's actions, properties and constraints",
        override={'LIBRARY_OVERRIDABLE'}
    )
    # Active row of the constraint list drawn for this bone
    constraint_index: IntProperty(default=0)


class BONEMANCER_PG_PickerBone(PropertyGroup):
    """Holds a single bone name for selection."""
    name: StringProperty(name="Bone Name")


class BONEMANCER_PG_BoneSet(PropertyGroup):
    # Overridable so groups can be edited on library-overridden rigs
    name: StringProperty(name="Name", override={'LIBRARY_OVERRIDABLE'})
    bones: CollectionProperty(type=BONEMANCER_PG_SetBone, override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'})
    show_expanded: BoolProperty(
        name="Expand Bone Set",
        description="Toggle bone list visibility",
        default=False,
        override={'LIBRARY_OVERRIDABLE'}
    )


class BONEMANCER_PG_Settings(PropertyGroup):
    # The bone picker list
    bone_selection: CollectionProperty(type=BONEMANCER_PG_PickerBone)
    # Clicking a row selects that bone in the viewport
    bone_selection_index: IntProperty(
        name="Index", default=0,
        update=lambda self, ctx: on_picker_index(self, ctx),
    )
    # Armature the bone_selection list was built from (for rename tracking)
    bone_list_owner: PointerProperty(type=bpy.types.Object)


class BONEMANCER_PG_ShapeKey(bpy.types.PropertyGroup):
    object_name: StringProperty(name="Mesh Object Name")
    key_name:    StringProperty(name="Shape Key Name")
    value: FloatProperty(
        name="Value", default=0.0, min=0.0, max=1.0, subtype='FACTOR',
        update=set_shape_key_value,
    )


class BONEMANCER_PG_ShapeKeyMesh(bpy.types.PropertyGroup):
    object_name:      StringProperty(name="Mesh Object Name")
    shape_keys:       CollectionProperty(type=BONEMANCER_PG_ShapeKey)
    shape_keys_index: IntProperty(default=0)


class BONEMANCER_PG_ShapeKeyScanner(bpy.types.PropertyGroup):
    object_groups:       CollectionProperty(type=BONEMANCER_PG_ShapeKeyMesh)
    object_groups_index: IntProperty(default=0)


class BONEMANCER_PG_ImportItem(PropertyGroup):
    """One native bone collection in the import checklist."""
    name: StringProperty(name="Name")
    use: BoolProperty(name="Import", default=True)
    bone_count: IntProperty(name="Bones")
    depth: IntProperty(name="Depth")


class BONEMANCER_PG_Issue(PropertyGroup):
    check: StringProperty(name="Check")
    bone: StringProperty(name="Bone")
    detail: StringProperty(name="Detail")
    message: StringProperty(name="Message")
    # What Select selects when the issue isn't about a bone
    object_name: StringProperty(name="Object")


class BONEMANCER_PG_IgnoredIssue(PropertyGroup):
    # Matches an issue when all three fields are equal
    check: StringProperty(name="Check", override={'LIBRARY_OVERRIDABLE'})
    bone: StringProperty(name="Bone", override={'LIBRARY_OVERRIDABLE'})
    detail: StringProperty(name="Detail", override={'LIBRARY_OVERRIDABLE'})


class BONEMANCER_PG_RigCheck(PropertyGroup):
    issues: CollectionProperty(type=BONEMANCER_PG_Issue)
    issues_index: IntProperty(default=0)
    has_run: BoolProperty(default=False)
    show_ignored: BoolProperty(
        name="Show Ignored",
        description="Also list the issues ignored on this rig",
        default=False,
    )
    # Python expression drivers that couldn't be checked (scripts not trusted)
    python_drivers: IntProperty(default=0)


classes = (
    BONEMANCER_PG_SetBone,
    BONEMANCER_PG_BoneSet,
    BONEMANCER_PG_ShapeKey,
    BONEMANCER_PG_ShapeKeyMesh,
    BONEMANCER_PG_PickerBone,
    BONEMANCER_PG_Settings,
    BONEMANCER_PG_ShapeKeyScanner,
    BONEMANCER_PG_ImportItem,
    BONEMANCER_PG_Issue,
    BONEMANCER_PG_IgnoredIssue,
    BONEMANCER_PG_RigCheck,
)

SCENE_PROPS = ["bonemancer_rig", "bonemancer_settings", "bonemancer_shape_keys", "bonemancer_selected_bone",
               "bonemancer_rig_check"]
OBJECT_PROPS = ["bonemancer_sets", "bonemancer_ignored_issues"]


def register():
    """Add the add-on's properties to Scene and Object. The classes must be registered first."""
    # The picked rig, panel state, and the selected-bone mirror.
    # A pointer (not a name-based enum) survives renames, reordering and
    # deletion of other armatures, and works with any characters in names.
    bpy.types.Scene.bonemancer_rig = PointerProperty(
        name="Armature",
        type=bpy.types.Object,
        poll=armature_poll,
        update=on_armature_change
    )
    bpy.types.Scene.bonemancer_settings = PointerProperty(
        name="Rig Manager Settings",
        type=BONEMANCER_PG_Settings
    )
    bpy.types.Scene.bonemancer_shape_keys = PointerProperty(
        type=BONEMANCER_PG_ShapeKeyScanner
    )
    # Changes to this string tell the depsgraph handler to redraw the panels
    bpy.types.Scene.bonemancer_selected_bone = StringProperty()
    # Last Rig Check results; names only, so they keep nothing alive
    bpy.types.Scene.bonemancer_rig_check = PointerProperty(type=BONEMANCER_PG_RigCheck)

    # Sets are stored on the rig object, so they follow it through
    # renames and across scenes.
    bpy.types.Object.bonemancer_sets = CollectionProperty(
        type=BONEMANCER_PG_BoneSet,
        override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'}
    )
    # Rig Check issues ignored on this rig; they travel with it like its sets
    bpy.types.Object.bonemancer_ignored_issues = CollectionProperty(
        type=BONEMANCER_PG_IgnoredIssue,
        override={'LIBRARY_OVERRIDABLE', 'USE_INSERTION'}
    )


def unregister_properties(base_type, props):
    for p in props:
        if hasattr(base_type, p):
            delattr(base_type, p)


def unregister():
    unregister_properties(bpy.types.Scene, SCENE_PROPS)
    unregister_properties(bpy.types.Object, OBJECT_PROPS)
