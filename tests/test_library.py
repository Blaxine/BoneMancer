"""Linked rigs are read-only; library-overridden rigs keep their groups across save/reload."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir

mod = load_addon()
check("register()", mod.register)
sc = bpy.context.scene
work = tmp_dir()
lib_path = os.path.join(work, "lib.blend")
saved_path = os.path.join(work, "override.blend")


def pick(obj):
    mod._armature_change_from_viewport = True
    try:
        sc.rmv2_rig = obj
    finally:
        mod._armature_change_from_viewport = False


def add(bone, group="Legs"):
    return refused(lambda: bpy.ops.rmv2.add_bone_to_collection(bone_name=bone, create_new=True, new_group_name=group))


def write_library():
    clear_data()
    coll = bpy.data.collections.new("RigColl")
    sc.collection.children.link(coll)
    make_arm("LibRig", ("hip", "knee"), collection=coll)
    bpy.data.libraries.write(lib_path, {coll})
    clear_data()
    with bpy.data.libraries.load(lib_path, link=True) as (src, dst):
        dst.collections = ["RigColl"]
    linked_coll = dst.collections[0]
    inst = bpy.data.objects.new("inst", None)
    inst.instance_type = 'COLLECTION'
    inst.instance_collection = linked_coll
    sc.collection.objects.link(inst)
    return linked_coll, inst


coll, inst = None, None


def setup():
    global coll, inst
    coll, inst = write_library()
    return (coll.library is not None, coll.library)
check("library rig links", setup)

linked = coll.objects["LibRig"] if coll else None


def linked_readonly():
    pick(linked)
    got = (mod.rig_is_editable(linked), add("hip"), refused(lambda: bpy.ops.rmv2.toggle_bone(bone_name="hip")))
    return (got == (False, {'CANCELLED'}, {'CANCELLED'}), got)
check("linked rig: add to set and hide are refused", linked_readonly)

rig = None


def make_override():
    global rig
    bpy.context.view_layer.objects.active = inst
    inst.select_set(True)
    ov = coll.override_hierarchy_create(sc, bpy.context.view_layer, do_fully_editable=False)
    rig = next(o for o in ov.all_objects if o.type == 'ARMATURE')
    bpy.context.view_layer.objects.active = rig
    pick(rig)
    return (mod.rig_is_editable(rig), rig.name)
check("override rig is editable", make_override)

check("override rig: add bones to a set", lambda: (add("hip") == add("knee") == {'FINISHED'}, None))
check("override rig: hide a bone", lambda: (bpy.ops.rmv2.toggle_bone(bone_name="hip") == {'FINISHED'}, None))
check("override rig: rename refused",
      lambda: (refused(lambda: bpy.ops.rmv2.rename_bone(bone_name="hip", mode='EXACT', new_name="hip2")) == {'CANCELLED'}
               and "hip" in rig.data.bones, None))
check("override rig: new custom property refused",
      lambda: (refused(lambda: bpy.ops.rmv2.add_custom_prop(bone_name="hip", prop_name="stretch", prop_type='FLOAT'))
               == {'CANCELLED'} and "stretch" not in rig.pose.bones["hip"].keys(), None))


def reload():
    rig.rmv2_groups[0].show_expanded = True
    bpy.ops.wm.save_as_mainfile(filepath=saved_path)
    bpy.ops.wm.open_mainfile(filepath=saved_path)
    r = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.override_library)
    got = [(g.group_name, g.show_expanded, [b.bone_name for b in g.bones]) for g in r.rmv2_groups]
    return (got == [("Legs", True, ["hip", "knee"])], got)
check("override rig: sets survive save and reload", reload)

check("unregister()", mod.unregister)
finish()
