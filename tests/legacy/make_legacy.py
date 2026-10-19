"""Save a .blend in an old BoneMancer storage format (run in a separate Blender process).

    blender -b --factory-startup --python make_legacy.py -- LEGACY_MODULE OUT_BLEND FORMAT

FORMAT "scene":  groups as Scene.rmv2_groups_<armature> (commit 04883fb).
FORMAT "object": groups as Object.rmv2_groups, pick as Scene.rmv2_rig (commit ec08568).

The file always holds rig "Hero Rig.001" (bones spine, head) with group "Body"
(spine, head; expanded; head shows constraints) and rig "Prop" without groups,
with "Hero Rig.001" picked in the panel.
"""

import bpy
import importlib.util
import sys

sys.dont_write_bytecode = True
module_path, out_path, fmt = sys.argv[sys.argv.index("--") + 1:][:3]

spec = importlib.util.spec_from_file_location("BoneMancer", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.register()

sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)


def make_arm(name, bones):
    arm = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    sc.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i, bn in enumerate(bones):
        eb = arm.data.edit_bones.new(bn)
        eb.head = (i, 0, 0)
        eb.tail = (i, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm


make_arm("Hero Rig.001", ("spine", "head"))
make_arm("Prop", ("handle",))

if fmt == "scene":
    sc.rmv2_armature = "Hero Rig.001"
    bpy.ops.rmv2.add_bone_to_collection(bone_name="spine", create_new=True, new_group_name="Body")
    bpy.ops.rmv2.add_bone_to_collection(bone_name="head", group_enum="Body")
    group = getattr(sc, "rmv2_groups_Hero_Rig_001")[0]
elif fmt == "object":
    rig = bpy.data.objects["Hero Rig.001"]
    sc.rmv2_rig = rig
    bpy.ops.rmv2.add_bone_to_collection(bone_name="spine", create_new=True, new_group_name="Body")
    bpy.ops.rmv2.add_bone_to_collection(bone_name="head", group_enum="Body")
    group = rig.rmv2_groups[0]
else:
    raise SystemExit(f"unknown format {fmt!r}")

group.show_expanded = True
group.bones[1].show_constraints = True

if bpy.context.object and bpy.context.object.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.wm.save_as_mainfile(filepath=out_path)
print("LEGACY_SAVED", out_path)
