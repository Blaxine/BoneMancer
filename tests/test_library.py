"""Linked rigs are read-only; library-overridden rigs keep their groups across save/reload."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir, record

mod = load_addon()
check("register()", mod.register)
sc = bpy.context.scene
work = tmp_dir()
lib_path = os.path.join(work, "lib.blend")
saved_path = os.path.join(work, "override.blend")


def pick(obj):
    mod._armature_change_from_viewport = True
    try:
        sc.bonemancer_rig = obj
    finally:
        mod._armature_change_from_viewport = False


def add(bone, group="Legs"):
    return refused(lambda: bpy.ops.bonemancer.add_bone_to_set(bone_name=bone, create_new=True, new_set_name=group))


def refusal(call):
    """Like refused(), but a Python traceback inside the operator counts as a failure."""
    try:
        return call()
    except RuntimeError as e:
        return "TRACEBACK" if "Traceback" in str(e) else {'CANCELLED'}


def write_library():
    clear_data()
    coll = bpy.data.collections.new("RigColl")
    sc.collection.children.link(coll)
    arm = make_arm("LibRig", ("hip", "knee"), collection=coll)
    arm.data.collections.new("Feet").assign(arm.data.bones["knee"])
    lib_set = arm.bonemancer_sets.add()   # a set defined in the library file
    lib_set.name = "Lib"
    lib_set.bones.add().bone_name = "hip"
    # Rig Check: two broken constraints, the knee one ignored in the library file
    for bone in ("hip", "knee"):
        arm.pose.bones[bone].constraints.new('COPY_ROTATION')
    ignored = arm.bonemancer_ignored_issues.add()
    ignored.check, ignored.bone, ignored.detail = "constraint", "knee", "Copy Rotation"
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
    # The rig dropdown only offers rigs linked into the scene itself (an
    # instanced one is unpicked by the depsgraph handler), so link it directly.
    sc.collection.objects.link(linked)
    try:
        pick(linked)
        got = (mod.rig_is_editable(linked), add("hip"), refused(lambda: bpy.ops.bonemancer.toggle_bone(bone_name="hip")),
               refused(lambda: bpy.ops.bonemancer.import_bone_collections()))
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == (False, {'CANCELLED'}, {'CANCELLED'}, {'CANCELLED'}), got)
check("linked rig: add to set, hide and import are refused", linked_readonly)


def visible(scene=None):
    return [(i.check, i.bone) for i in mod.visible_issues(scene or bpy.context.scene)]


def issue_index(bone):
    return next(i for i, it in enumerate(bpy.context.scene.bonemancer_rig_check.issues) if it.bone == bone)


def linked_rig_check():
    sc.collection.objects.link(linked)
    bpy.context.view_layer.objects.active = linked
    try:
        pick(linked)
        r = bpy.ops.bonemancer.check_rig()
        shown = visible()
        got = (r, shown,
               refusal(lambda: bpy.ops.bonemancer.ignore_issue(index=issue_index("hip"))),
               refusal(lambda: bpy.ops.bonemancer.unignore_issue(index=issue_index("knee"))),
               bpy.ops.bonemancer.select_issue(index=issue_index("hip")),
               len(linked.bonemancer_ignored_issues),
               mod.BONEMANCER_OT_ignore_issue.description(bpy.context, type("P", (), {"index": 0})()))
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == ({'FINISHED'}, [("constraint", "hip")], {'CANCELLED'}, {'CANCELLED'}, {'CANCELLED'}, 1,
                    mod.LINKED_IGNORE_MESSAGE), got)
check("linked rig: checked with library ignores; ignore, stop ignoring and select refused", linked_rig_check)

def set_panels(rig):
    """Which kind of sub-panel the Bone Sets panel uses for rig's sets: panel_prop or panel."""
    return sorted({d.kind for d in record(mod.BONEMANCER_PT_bone_sets.draw, bpy.context).drawn("panel", "panel_prop")})


def linked_sets_fold():
    sc.collection.objects.link(linked)
    try:
        pick(linked)
        got = set_panels(linked)
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == ["panel"], got)
check("linked rig: Bone Sets fold with sidebar state, since the rig can't change", linked_sets_fold)


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

check("override rig: Bone Sets fold state is saved on the sets",
      lambda: (set_panels(rig) == ["panel_prop"], set_panels(rig)))
check("override rig: add bones to a set", lambda: (add("hip") == add("knee") == {'FINISHED'}, None))
check("override rig: import bone collections",
      lambda: (bpy.ops.bonemancer.import_bone_collections() == {'FINISHED'}
               and [s.name for s in rig.bonemancer_sets] == ["Lib", "Legs", "Feet"], [s.name for s in rig.bonemancer_sets]))
check("override rig: hide a bone", lambda: (bpy.ops.bonemancer.toggle_bone(bone_name="hip") == {'FINISHED'}, None))
check("override rig: rename refused",
      lambda: (refused(lambda: bpy.ops.bonemancer.rename_bone(bone_name="hip", mode='EXACT', new_name="hip2")) == {'CANCELLED'}
               and "hip" in rig.data.bones, None))
check("override rig: new custom property refused",
      lambda: (refused(lambda: bpy.ops.bonemancer.add_custom_prop(bone_name="hip", prop_name="stretch", prop_type='FLOAT'))
               == {'CANCELLED'} and "stretch" not in rig.pose.bones["hip"].keys(), None))



def lib_bones():
    return [b.bone_name for b in rig.bonemancer_sets["Lib"].bones]


check("override rig: removing a library-defined set is refused cleanly",
      lambda: (refusal(lambda: bpy.ops.bonemancer.remove_set(set_name="Lib")) == {'CANCELLED'}
               and "Lib" in rig.bonemancer_sets, [s.name for s in rig.bonemancer_sets]))
check("override rig: removing a library-defined bone from its set is refused cleanly",
      lambda: (refusal(lambda: bpy.ops.bonemancer.remove_bone_from_set(set_name="Lib", bone_name="hip")) == {'CANCELLED'}
               and lib_bones() == ["hip"], lib_bones()))


def local_bone_in_library_set():
    bpy.ops.bonemancer.add_bone_to_set(bone_name="knee", set_enum="Lib")
    added = lib_bones()
    r = refusal(lambda: bpy.ops.bonemancer.remove_bone_from_set(set_name="Lib", bone_name="knee"))
    return (added == ["hip", "knee"] and r == {'FINISHED'} and lib_bones() == ["hip"], (added, r, lib_bones()))
check("override rig: a bone added on the override to a library set can be removed", local_bone_in_library_set)


def override_rig_check():
    bpy.context.view_layer.objects.active = rig
    pick(rig)
    bpy.ops.bonemancer.check_rig()
    shown = visible()
    r_ignore = refusal(lambda: bpy.ops.bonemancer.ignore_issue(index=issue_index("hip")))
    r_unignore = refusal(lambda: bpy.ops.bonemancer.unignore_issue(index=issue_index("knee")))
    got = (shown, r_ignore, r_unignore, visible(), [(e.bone, e.detail) for e in rig.bonemancer_ignored_issues])
    return (got == ([("constraint", "hip")], {'FINISHED'}, {'CANCELLED'}, [],
                    [("knee", "Copy Rotation"), ("hip", "Copy Rotation")]), got)
check("override rig: ignore works; a library-file ignore can't be stopped (no traceback)", override_rig_check)


def reload():
    rig.bonemancer_sets["Legs"].show_expanded = True
    bpy.ops.wm.save_as_mainfile(filepath=saved_path)
    bpy.ops.wm.open_mainfile(filepath=saved_path)
    r = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.override_library)
    got = [(g.name, g.show_expanded, [b.bone_name for b in g.bones]) for g in r.bonemancer_sets]
    return (got == [("Lib", False, ["hip"]), ("Legs", True, ["hip", "knee"]), ("Feet", False, ["knee"])], got)
check("override rig: sets survive save and reload", reload)


def ignores_after_reload():
    r = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.override_library)
    entries = [(e.bone, e.detail) for e in r.bonemancer_ignored_issues]
    bpy.context.view_layer.objects.active = r
    pick_scene = bpy.context.scene
    mod._armature_change_from_viewport = True
    try:
        pick_scene.bonemancer_rig = r
    finally:
        mod._armature_change_from_viewport = False
    bpy.ops.bonemancer.check_rig()
    shown = visible(pick_scene)
    r_unignore = refusal(lambda: bpy.ops.bonemancer.unignore_issue(index=issue_index("hip")))
    got = (entries, shown, r_unignore, [(e.bone, e.detail) for e in r.bonemancer_ignored_issues])
    return (got == ([("knee", "Copy Rotation"), ("hip", "Copy Rotation")], [], {'FINISHED'},
                    [("knee", "Copy Rotation")]), got)
check("override rig: ignores survive reload; one added on the override can be stopped", ignores_after_reload)

check("unregister()", mod.unregister)
finish()
