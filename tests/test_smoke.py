"""Smoke checks, pitfall regressions and register/unregister lifecycle."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir, FakePanel, MockLayout, record


def foreign_handler(scene, depsgraph=None):
    pass


bpy.app.handlers.depsgraph_update_post.append(foreign_handler)

mod = load_addon()
check("register()", mod.register)
sc = bpy.context.scene


def reset():
    sc.bonemancer_rig = None
    clear_data()


def pick(obj, from_viewport=True):
    if from_viewport and obj and bpy.context.view_layer.objects.get(obj.name) == obj:
        bpy.context.view_layer.objects.active = obj   # what clicking it in the viewport does
    mod._armature_change_from_viewport = from_viewport
    try:
        sc.bonemancer_rig = obj
    finally:
        mod._armature_change_from_viewport = False


def add(bone, group="G"):
    return bpy.ops.bonemancer.add_bone_to_set(bone_name=bone, create_new=True, new_set_name=group)


def names(arm):
    return [b.name for b in arm.data.bones]


def entries(arm, i=0):
    return [b.bone_name for b in arm.bonemancer_sets[i].bones]


def handler_run():
    mod.on_depsgraph_update(sc, bpy.context.evaluated_depsgraph_get())


def add_mesh(arm=None, keys=("Basis", "Smile")):
    bpy.ops.mesh.primitive_cube_add()
    m = bpy.context.active_object
    for k in keys:
        m.shape_key_add(name=k)
    if arm:
        m.parent = arm
    return m


def key_count(m, path=None):
    fcurves = mod.get_anim_fcurves(m.data.shape_keys.animation_data)
    return sum(len(fc.keyframe_points) for fc in fcurves if path is None or fc.data_path == path)


# ---------------------------------------------------------------- smoke

def smoke():
    reset()
    arm = make_arm("Rig", ("root", "arm.L"))
    cube = add_mesh(arm)
    pick(arm, from_viewport=False)

    def keytest():
        r = []
        for _ in range(3):
            bpy.ops.bonemancer.toggle_shape_keyframe(object_name=cube.name, shape_key_name="Smile")
            r.append(key_count(cube, 'key_blocks["Smile"].value'))
        return (r == [1, 0, 1], r)

    def scan():
        bpy.ops.bonemancer.scan_shape_keys()
        got = [k.key_name for k in sc.bonemancer_shape_keys.object_groups[0].shape_keys]
        return (got == ["Smile"], got)

    steps = [
        ("dropdown pick enters pose mode", lambda: (bpy.context.mode == 'POSE', bpy.context.mode)),
        ("bone list", lambda: ([i.name for i in sc.bonemancer_settings.bone_selection] == ["root", "arm.L"], None)),
        ("add_bone_to_collection", lambda: add("arm.L", "Arms")),
        ("toggle_bone", lambda: bpy.ops.bonemancer.toggle_bone(bone_name="arm.L")),
        ("toggle_group", lambda: bpy.ops.bonemancer.toggle_set(set_name="Arms")),
        ("toggle_group missing -> cancelled", lambda: (bpy.ops.bonemancer.toggle_set(set_name="Nope") == {'CANCELLED'}, None)),
        ("toggle_group_foldout", lambda: bpy.ops.bonemancer.toggle_set_foldout(set_name="Arms")),
        ("select_bone", lambda: bpy.ops.bonemancer.select_bone(bone_name="arm.L")),
        ("add_custom_prop", lambda: bpy.ops.bonemancer.add_custom_prop(bone_name="arm.L", prop_name="ik_fk", prop_type='FLOAT', default_float=0.5)),
        ("rename_bone", lambda: (bpy.ops.bonemancer.rename_bone(bone_name="arm.L", mode='EXACT', new_name="arm_renamed.L") == {'FINISHED'}
                                 and entries(arm) == ["arm_renamed.L"], entries(arm))),
        ("remove_bone", lambda: bpy.ops.bonemancer.remove_bone_from_set(set_name="Arms", bone_name="arm_renamed.L")),
        ("remove_bone missing group -> cancelled", lambda: (bpy.ops.bonemancer.remove_bone_from_set(set_name="Nope", bone_name="x") == {'CANCELLED'}, None)),
        ("remove_group", lambda: bpy.ops.bonemancer.remove_set(set_name="Arms")),
        ("scan_shape_keys", scan),
        ("key_shape_value insert/remove/insert", keytest),
        ("handler run", handler_run),
        ("draw panels with mock layout", draw_all),
        ("foreign handler kept", lambda: (foreign_handler in bpy.app.handlers.depsgraph_update_post, None)),
    ]
    for n, f in steps:
        check("smoke: " + n, f)


def draw_all():
    arm = mod.get_rig(sc)
    add("root", "Core")
    arm.bonemancer_sets[-1].bones.add().bone_name = "ghost"   # missing-bone row
    arm.pose.bones["root"]['we"ird'] = 1.0
    for grp in arm.bonemancer_sets:
        grp.show_expanded = True
        for b in grp.bones:
            b.show_details = True
            b.show_custom_props = True
            b.show_constraints = True
    for panel in (mod.BONEMANCER_PT_rig, mod.BONEMANCER_PT_bones, mod.BONEMANCER_PT_bone_sets, mod.BONEMANCER_PT_shape_keys):
        panel.draw(FakePanel(), bpy.context)
    mod.BONEMANCER_PT_shape_keys.draw_header_preset(FakePanel(), bpy.context)
    grp = sc.bonemancer_shape_keys.object_groups[0]
    mod.BONEMANCER_UL_shape_key_meshes.draw_item(None, bpy.context, MockLayout(), None, grp, 0, None, "", 0)
    for i, it in enumerate(grp.shape_keys):
        mod.BONEMANCER_UL_shape_keys.draw_item(None, bpy.context, MockLayout(), grp, it, 0, grp, "shape_keys_index", i)


check("smoke suite", smoke)


# ---------------------------------------------------------------- pitfall regressions
# Each check states the expected behaviour.

def p1():
    reset(); arm = make_arm("Rig"); pick(arm); add("a")
    r = refused(lambda: bpy.ops.bonemancer.rename_bone(bone_name="a", mode='EXACT', new_name="b"))
    return (r == {'CANCELLED'} and names(arm) == ["a", "b"] and entries(arm) == ["a"], (r, names(arm), entries(arm)))
check("P1 rename onto existing name is refused, nothing changes", p1)


def p2():
    reset(); arm = make_arm("Rig"); pick(arm)
    r = refused(lambda: bpy.ops.bonemancer.rename_bone(bone_name="a", mode='EXACT', new_name=""))
    return (r == {'CANCELLED'} and names(arm) == ["a", "b"], (r, names(arm)))
check("P2 empty name is refused cleanly", p2)


def p3():
    reset(); arm = make_arm("Rig", ("arm",)); pick(arm)
    r = refused(lambda: bpy.ops.bonemancer.rename_bone(bone_name="arm", mode='REPLACE', find_text="", replace_text="_"))
    return (r == {'CANCELLED'} and names(arm) == ["arm"], (r, names(arm)))
check("P3 REPLACE with empty Find is refused", p3)


def p4():
    reset(); a = make_arm("RigA", ("hand",)); b = make_arm("RigB", ("hand",))
    bpy.ops.mesh.primitive_cube_add(); m = bpy.context.active_object
    d = m.driver_add("location", 0).driver
    vb = d.variables.new(); vb.type = 'SINGLE_PROP'
    vb.targets[0].id = b; vb.targets[0].data_path = 'pose.bones["hand"].location[0]'
    vt = d.variables.new(); vt.type = 'TRANSFORMS'
    vt.targets[0].id = b; vt.targets[0].bone_target = "hand"
    d2 = m.driver_add("location", 1).driver
    va = d2.variables.new(); va.type = 'SINGLE_PROP'
    va.targets[0].id = a; va.targets[0].data_path = 'pose.bones["hand"].location[0]'
    pick(a); bpy.ops.bonemancer.rename_bone(bone_name="hand", mode='EXACT', new_name="hand_renamed")
    got = (vb.targets[0].data_path, vt.targets[0].bone_target, va.targets[0].data_path)
    return (got == ('pose.bones["hand"].location[0]', "hand", 'pose.bones["hand_renamed"].location[0]'), got)
check("P4 rename only retargets drivers of this rig", p4)


def p5():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm)
    sc.tool_settings.use_keyframe_insert_auto = True
    pick(arm, from_viewport=False); bpy.ops.bonemancer.scan_shape_keys()
    ad = m.data.shape_keys.animation_data
    keyed = [fc.data_path for fc in mod.get_anim_fcurves(ad)] if ad else []
    return (keyed == [], keyed)
check("P5 picking/scanning with auto-key inserts no keys", p5)


def p6():
    reset(); arm = make_arm("Rig"); add_mesh(arm, ("Rest", "Smile"))
    pick(arm); bpy.ops.bonemancer.scan_shape_keys()
    got = [k.key_name for k in sc.bonemancer_shape_keys.object_groups[0].shape_keys]
    return (got == ["Smile"], got)
check("P6 reference key skipped whatever its name", p6)


def p6b():
    reset(); arm = make_arm("Rig"); m = add_mesh()
    bpy.ops.mesh.primitive_cube_add(); holder = bpy.context.active_object
    holder.parent = arm; m.parent = holder
    pick(arm); bpy.ops.bonemancer.scan_shape_keys()
    got = [g.object_name for g in sc.bonemancer_shape_keys.object_groups]
    return (got == [m.name], got)
check("P6b mesh parented through another object is found", p6b)


def p7():
    reset(); make_arm("A"); b = make_arm("B"); make_arm("C"); pick(b)
    bpy.data.objects.remove(bpy.data.objects["A"])
    return (sc.bonemancer_rig == b, sc.bonemancer_rig.name if sc.bonemancer_rig else None)
check("P7 pick survives deleting another armature", p7)


def p7b():
    reset(); make_arm("A"); c = make_arm("C"); pick(c)
    bpy.data.objects.remove(c)
    return (sc.bonemancer_rig is None, sc.bonemancer_rig)
check("P7b deleting the picked armature clears the pick", p7b)


def p8():
    reset(); arm = make_arm("R" * 63); pick(arm)
    r = add("a")
    return (r == {'FINISHED'} and entries(arm) == ["a"], (r, len(arm.name)))
check("P8 63-char armature name works", p8)


def p8b():
    reset(); make_arm("A"); arm = make_arm("Rüstung"); pick(arm)
    r = add("a")
    return (sc.bonemancer_rig == arm and r == {'FINISHED'}, (sc.bonemancer_rig.name, r))
check("P8b non-ASCII armature name works", p8b)


def p8c():
    reset(); arm = make_arm("Rig"); pick(arm); add("a", "Gruppe_ä")
    r = bpy.ops.bonemancer.add_bone_to_set(bone_name="b", set_enum="Gruppe_ä")
    return (r == {'FINISHED'} and entries(arm) == ["a", "b"], (r, entries(arm)))
check("P8c non-ASCII group name in dynamic enum", p8c)


def p9():
    reset(); r1 = make_arm("Rig.001"); r2 = make_arm("Rig_001")
    pick(r1); add("a", "OnlyOnDot001"); pick(r2)
    return (len(r2.bonemancer_sets) == 0, [g.name for g in r2.bonemancer_sets])
check("P9 similar names don't share groups", p9)


def p10():
    reset(); arm = make_arm("Rig"); pick(arm); add("a")
    arm.name = "Rig_v2"
    return (len(arm.bonemancer_sets) == 1, len(arm.bonemancer_sets))
check("P10 groups survive renaming the armature", p10)


def p10b():
    reset(); arm = make_arm("Rig"); pick(arm); add("a")
    arm.data.bones["a"].name = "a_renamed_elsewhere"
    handler_run()
    return (entries(arm) == ["a_renamed_elsewhere"], entries(arm))
check("P10b bone renamed outside the add-on is followed", p10b)


def p10c():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm); add("a"); add("c")
    for bn, nn in (("a", "x"), ("c", "z")):
        arm.data.bones[bn].name = nn
    handler_run()
    return (entries(arm) == ["x", "z"], entries(arm))
check("P10c batch rename outside the add-on is followed", p10c)


def p10d():
    reset(); arm = make_arm("Rig", ("a", "b")); pick(arm); add("a")
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT'); handler_run()
    bpy.ops.object.mode_set(mode='POSE'); handler_run()
    return (entries(arm) == ["a"], entries(arm))
check("P10d mode switches don't fake renames", p10d)


def p11():
    reset(); make_arm("A"); b = make_arm("B")
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='SCULPT')
    pick(b, from_viewport=False)
    return (bpy.context.mode == 'SCULPT' and sc.bonemancer_rig == b, bpy.context.mode)
check("P11 dropdown pick doesn't kick you out of Sculpt", p11)


def exclude_from_view_layer(arm):
    coll = bpy.data.collections.new("Excl"); sc.collection.children.link(coll)
    coll.objects.link(arm); sc.collection.objects.unlink(arm)
    bpy.context.view_layer.layer_collection.children["Excl"].exclude = True


def p11b():
    reset(); arm = make_arm("Rig"); pick(arm)
    exclude_from_view_layer(arm)
    r = bpy.ops.bonemancer.select_bone(bone_name="a")
    return (r == {'CANCELLED'}, r)
check("P11b select_bone on excluded rig cancels cleanly", p11b)


def p11c():
    reset(); arm = make_arm("Rig")
    exclude_from_view_layer(arm)
    pick(arm, from_viewport=False)
    return (sc.bonemancer_rig == arm, bpy.context.mode)
check("P11c dropdown pick of rig outside view layer doesn't raise", p11c)


def p14():
    reset(); arm = make_arm("Rig"); pick(arm); add("a")
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode='EDIT')
    r = bpy.ops.bonemancer.rename_bone(bone_name="a", mode='EXACT', new_name="renamed_in_edit")
    bpy.ops.object.mode_set(mode='OBJECT')
    return (r == {'FINISHED'} and "renamed_in_edit" in names(arm) and entries(arm) == ["renamed_in_edit"],
            (r, names(arm), entries(arm)))
check("P14 rename in Edit Mode sticks", p14)


def p17():
    reset(); arm = make_arm("Rig"); pb = arm.pose.bones["a"]; pb['ik "soft"'] = 1.0
    return (pb.path_resolve(mod.path_key('ik "soft"')) == 1.0, None)
check("P17 custom prop with quote resolves via escaped path", p17)


def p18():
    reset(); arm = make_arm("Rig"); pick(arm)
    bpy.ops.mesh.primitive_cube_add()
    return (bpy.ops.bonemancer.add_bone_to_set.poll() is True, None)
check("P18 add-to-set enabled while a mesh is active", p18)


def p19():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm, ("Basis", 'Sm"ile'))
    r1 = bpy.ops.bonemancer.toggle_shape_keyframe(object_name=m.name, shape_key_name='Sm"ile')
    r2 = bpy.ops.bonemancer.toggle_shape_keyframe(object_name=m.name, shape_key_name='Sm"ile')
    n = key_count(m)
    return (r1 == r2 == {'FINISHED'} and n == 0, (r1, r2, n))
check("P19 keyframe toggle on shape key with quote", p19)


def p21():
    reset(); arm = make_arm("Rig"); pick(arm); add("a"); add("b")
    bpy.ops.bonemancer.toggle_bone(bone_name="a")
    bpy.ops.bonemancer.toggle_set(set_name="G"); s1 = {n: mod.is_hidden(arm.pose.bones[n]) for n in "ab"}
    bpy.ops.bonemancer.toggle_set(set_name="G"); s2 = {n: mod.is_hidden(arm.pose.bones[n]) for n in "ab"}
    return (s1 == {"a": True, "b": True} and s2 == {"a": False, "b": False}, (s1, s2))
check("P21 group toggle unifies visibility", p21)


def p22():
    must = {"bonemancer.remove_bone_from_set", "bonemancer.remove_set", "bonemancer.toggle_bone", "bonemancer.toggle_set", "bonemancer.select_bone",
            "bonemancer.toggle_shape_keyframe", "bonemancer.rename_bone", "bonemancer.add_custom_prop", "bonemancer.add_bone_to_set"}
    missing = sorted(c.bl_idname for c in mod.classes
                     if getattr(c, "bl_idname", "") in must and 'UNDO' not in getattr(c, "bl_options", set()))
    return (missing == [] and hasattr(mod.BONEMANCER_OT_remove_set, "invoke"), missing)
check("P22 data-changing operators are undoable; remove group confirms", p22)


def p23():
    reset(); arm = make_arm("Rig"); pick(arm)
    pb = arm.pose.bones["a"]; pb["rig_id"] = "keep-me"
    r = refused(lambda: bpy.ops.bonemancer.add_custom_prop(bone_name="a", prop_name="rig_id", prop_type='FLOAT'))
    return (r == {'CANCELLED'} and pb["rig_id"] == "keep-me", (r, pb["rig_id"]))
check("P23 existing custom prop is not overwritten", p23)


def p24():
    reset(); arm = make_arm("Rig"); pick(arm); add("a")
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode='POSE')
    mod.set_bone_selected(arm.pose.bones["a"], True)
    bpy.ops.object.mode_set(mode='OBJECT')
    return (mod.bone_is_selected(arm.pose.bones["a"]), None)
check("P24 selection highlight reads live selection", p24)


def p25():
    reset(); a = make_arm("A"); b = make_arm("B"); pick(a)
    bpy.context.view_layer.objects.active = b
    handler_run()
    return (sc.bonemancer_rig == b, sc.bonemancer_rig.name)
check("P25 viewport active armature follows into picker", p25)


def p26():
    reset(); a = make_arm("A"); pick(a); m = add_mesh(a)
    kb = m.data.shape_keys.key_blocks["Smile"]
    kb.value = 0.3; kb.keyframe_insert("value", frame=10.5)
    sc.frame_set(10)
    bpy.ops.bonemancer.toggle_shape_keyframe(object_name=m.name, shape_key_name="Smile")
    frames = sorted(round(kp.co.x, 2) for fc in mod.get_anim_fcurves(m.data.shape_keys.animation_data)
                    for kp in fc.keyframe_points)
    return (frames == [10.0, 10.5], frames)
check("P26 subframe key isn't treated as a key on the whole frame", p26)


# ---------------------------------------------------------------- lifecycle

def leftover_handlers():
    hs = list(bpy.app.handlers.depsgraph_update_post) + list(bpy.app.handlers.load_post)
    return [h.__name__ for h in hs if h.__module__ == mod.__name__]


def pose_selected(arm):
    return [pb.name for pb in arm.pose.bones if mod.bone_is_selected(pb)]


def edit_selected(arm):
    return [eb.name for eb in arm.data.edit_bones if eb.select]


def picker():
    return sc.bonemancer_settings


def p27():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    mod.set_bone_selected(arm.pose.bones["a"], True)
    picker().bone_selection_index = 1
    got = (bpy.context.mode, pose_selected(arm), arm.data.bones.active.name)
    return (got == ('POSE', ["b"], "b"), got)
check("P27 Bone Picker click selects that bone in Pose Mode", p27)


def p27b():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm)
    picker().bone_selection_index = 2
    got = (bpy.context.mode, pose_selected(arm), arm.data.bones.active.name)
    return (got == ('POSE', ["c"], "c"), got)
check("P27b Bone Picker click from Object Mode enters Pose Mode", p27b)


def p27c():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm)
    bpy.context.view_layer.objects.active = arm; bpy.ops.object.mode_set(mode='EDIT')
    picker().bone_selection_index = 1
    got = (bpy.context.mode, edit_selected(arm), arm.data.edit_bones.active.name)
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == ('EDIT_ARMATURE', ["b"], "b"), got)
check("P27c Bone Picker click in Edit Mode selects the edit bone", p27c)


def p27d():
    reset(); arm = make_arm("Rig", ("a", "b")); pick(arm)
    bpy.ops.mesh.primitive_cube_add(); bpy.ops.object.mode_set(mode='SCULPT')
    picker().bone_selection_index = 1
    got = (bpy.context.mode, pose_selected(arm))
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == ('SCULPT', []), got)
check("P27d Bone Picker click doesn't leave Sculpt Mode", p27d)


def p28():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    for name in ("b", "c"):
        mod.set_bone_selected(arm.pose.bones[name], True)
    arm.data.bones.active = arm.data.bones["c"]
    handler_run()
    got = (picker().bone_selection_index, pose_selected(arm))
    return (got == (2, ["b", "c"]), got)
check("P28 viewport selection highlights the active bone in the Bone Picker", p28)


def p28b():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    picker().bone_selection_index = 2
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in arm.data.edit_bones:
        eb.select = eb.select_head = eb.select_tail = False
    eb = arm.data.edit_bones["a"]; eb.select = True; arm.data.edit_bones.active = eb
    handler_run()
    got = (picker().bone_selection_index, edit_selected(arm))
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == (0, ["a"]), got)
check("P28b Edit Mode selection highlights the bone in the Bone Picker", p28b)


def p28c():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    picker().bone_selection_index = 2
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in arm.data.edit_bones:
        eb.select = eb.select_head = eb.select_tail = False
    arm.data.edit_bones.remove(arm.data.edit_bones["c"])
    handler_run()
    got = (picker().bone_selection_index, edit_selected(arm))
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == (1, []), got)
check("P28c shrinking the bone list moves the highlight without selecting", p28c)


def select_in_pose(arm, names):
    bpy.context.view_layer.objects.active = arm
    if arm.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    for pb in arm.pose.bones:
        mod.set_bone_selected(pb, pb.name in names)


def p28d():
    reset(); arm = make_arm("Rig", ("a", "b", "c", "d")); pick(arm, from_viewport=False)
    select_in_pose(arm, ("b", "d"))
    arm.data.bones.active = arm.data.bones["d"]                # the active bone won't change below
    handler_run()
    first = mod._picker_selection
    mod.set_bone_selected(arm.pose.bones["b"], False)          # ctrl-click off a non-active bone
    redraw = mod.sync_selected_bone(sc, bpy.context.view_layer)
    for i, item in enumerate(picker().bone_selection):
        mod.BONEMANCER_UL_bone_picker.draw_item(None, bpy.context, MockLayout(), None, item, 0, None, "", i)
    mod.BONEMANCER_PT_bones.draw(FakePanel(), bpy.context)
    got = (first, redraw, mod._picker_selection,
           [it.name for it in picker().bone_selection if mod.bone_selected_in_viewport(arm, it.name)])
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == (("b", "d"), True, ("d",), ["d"]), got)
check("P28d every selected bone is highlighted, and any selection change redraws", p28d)


def p28e():
    reset(); arm = make_arm("Rig", ("a", "b", "c", "d")); pick(arm, from_viewport=False)
    select_in_pose(arm, ("d", "b"))
    mod.set_hidden(arm.pose.bones["c"], True)
    mod.set_bone_selected(arm.pose.bones["c"], True)            # hidden bones don't count
    r1 = bpy.ops.bonemancer.add_bone_to_set(use_selected=True, create_new=True, new_set_name="Picked")
    select_in_pose(arm, ("a", "b"))
    r2 = bpy.ops.bonemancer.add_bone_to_set(use_selected=True, set_enum="Picked")
    bpy.ops.object.mode_set(mode='OBJECT')
    got = (r1, r2, [b.bone_name for b in arm.bonemancer_sets["Picked"].bones])
    return (got == ({'FINISHED'}, {'FINISHED'}, ["b", "d", "a"]), got)
check("P28e Add Selected adds every selected visible bone once, in armature order", p28e)


def p28f():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in arm.data.edit_bones:
        eb.select = eb.name in ("a", "c")
    r = bpy.ops.bonemancer.add_bone_to_set(use_selected=True, create_new=True, new_set_name="Edit")
    bpy.ops.object.mode_set(mode='OBJECT')
    got = (r, [b.bone_name for b in arm.bonemancer_sets["Edit"].bones])
    return (got == ({'FINISHED'}, ["a", "c"]), got)
check("P28f Add Selected uses the edit-bone selection in Edit Mode", p28f)


def p28g():
    reset(); arm = make_arm("Rig", ("a", "b")); pick(arm, from_viewport=False)
    select_in_pose(arm, ())
    r = bpy.ops.bonemancer.add_bone_to_set(use_selected=True, create_new=True, new_set_name="None")
    bpy.ops.object.mode_set(mode='OBJECT')
    valid = {i.identifier for i in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items}
    got = (r, len(arm.bonemancer_sets), 'GROUP_BONE' in valid)
    return (got == ({'CANCELLED'}, 0, True), got)
check("P28g Add Selected with nothing selected changes nothing", p28g)


def p29():
    global sc
    reset(); arm = make_arm("Rig"); pick(arm, from_viewport=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.ops.object.delete()   # what X does in the viewport
    handler_run()
    picked = sc.bonemancer_rig
    path = os.path.join(tmp_dir(), "deleted_rig.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    bpy.app.handlers.depsgraph_update_post.append(foreign_handler)   # loading a file drops non-persistent handlers
    got = (picked, sc.bonemancer_settings.bone_list_owner, "Rig" in bpy.data.objects)
    return (got == (None, None, False), got)
check("P29 a rig deleted with X is unpicked and not kept in the saved file", p29)


def p29b():
    reset(); arm = make_arm("Rig"); pick(arm)
    sc.collection.objects.unlink(arm)
    handler_run()
    return (sc.bonemancer_rig is None, sc.bonemancer_rig)
check("P29b a rig unlinked from the scene is unpicked", p29b)


def p30():
    reset(); arm = make_arm("Rig"); pick(arm)
    settings = sc.bonemancer_settings
    settings["last_armature"] = arm      # what 1.0 development builds saved
    before = arm.users
    mod.migrate_legacy_data()
    got = (hasattr(settings, "last_armature"), settings.get("last_armature"), before - arm.users)
    return (got == (False, None, 1), got)
check("P30 last_armature is gone, and stale values from dev builds are removed on load", p30)


def scanner():
    return [(g.object_name, [k.key_name for k in g.shape_keys]) for g in sc.bonemancer_shape_keys.object_groups]


def p31():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm); pick(arm)
    first = scanner()
    m.shape_key_add(name="Frown")
    added = mod.refresh_shape_keys(sc)
    after_add = scanner()
    m.data.shape_keys.key_blocks["Smile"].name = "Grin"
    mod.refresh_shape_keys(sc)
    after_rename = scanner()
    m.shape_key_remove(m.data.shape_keys.key_blocks["Frown"])
    mod.refresh_shape_keys(sc)
    got = (first, added, after_add, after_rename, scanner())
    return (got == ([(m.name, ["Smile"])], True, [(m.name, ["Smile", "Frown"])], [(m.name, ["Grin", "Frown"])],
                    [(m.name, ["Grin"])]), got)
check("P31 the scanner follows shape keys added, renamed and removed", p31)


def p31b():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm); pick(arm)
    other = add_mesh()                                      # not deformed yet
    before = scanner()
    other.modifiers.new("Armature", 'ARMATURE').object = arm
    mod.refresh_shape_keys(sc)
    added = [name for name, _keys in scanner()]
    m.parent = None
    mod.refresh_shape_keys(sc)
    got = (before, added, [name for name, _keys in scanner()])
    return (got == ([(m.name, ["Smile"])], sorted([m.name, other.name]), [other.name]), got)
check("P31b meshes appear and disappear as they gain or lose the rig", p31b)


def p31c():
    reset(); arm = make_arm("Rig"); a = add_mesh(arm, ("Basis", "One", "Two")); b = add_mesh(arm); pick(arm)
    settings = sc.bonemancer_shape_keys
    names = [g.object_name for g in settings.object_groups]
    settings.object_groups_index = names.index(a.name)
    grp = settings.object_groups[names.index(a.name)]
    grp.shape_keys_index = 1                                # "Two"
    a.shape_key_add(name="Three")
    mod.refresh_shape_keys(sc)
    names = [g.object_name for g in settings.object_groups]
    grp = settings.object_groups[names.index(a.name)]
    got = (settings.object_groups[settings.object_groups_index].object_name == a.name,
           grp.shape_keys[grp.shape_keys_index].key_name)
    return (got == (True, "Two"), got)
check("P31c a rebuild keeps the highlighted mesh and shape key", p31c)


def p31d():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm); pick(arm)
    sc.tool_settings.use_keyframe_insert_auto = True
    m.data.shape_keys.key_blocks["Smile"].value = 0.7       # dragging a slider
    rebuilt = mod.refresh_shape_keys(sc)
    m.shape_key_add(name="Frown")
    mod.refresh_shape_keys(sc)                              # a rebuild with auto-key on
    ad = m.data.shape_keys.animation_data
    keyed = [fc.data_path for fc in mod.get_anim_fcurves(ad)] if ad else []
    sc.tool_settings.use_keyframe_insert_auto = False
    return ((rebuilt, keyed) == (False, []), (rebuilt, keyed))
check("P31d moving a slider doesn't rebuild, and rebuilding never keys", p31d)


def p31e():
    reset(); arm = make_arm("Rig"); m = add_mesh(arm); pick(arm)
    m.shape_key_add(name="Frown")
    m.data.update()
    handler_run()
    via_handler = scanner()
    pick(None)
    got = (via_handler, scanner())
    return (got == ([(m.name, ["Smile", "Frown"])], []), got)
check("P31e the depsgraph handler refreshes the scanner; unpicking empties it", p31e)


# ---------------------------------------------------------------- sidebar layout

def ui1():
    reset(); arm = make_arm("Rig", ("a", "b", "c")); pick(arm, from_viewport=False)
    select_in_pose(arm, ("a", "c"))
    arm.data.bones.active = arm.data.bones["c"]
    handler_run()
    drawn = record(mod.BONEMANCER_PT_bones.draw, bpy.context)
    add = [d for d in drawn.drawn("operator") if d.args == ("bonemancer.add_bone_to_set",)]
    actions = [(d.args[0], d.text, d.result.attrs.get("bone_name")) for d in drawn.drawn("operator")
               if d.args[0] in ("bonemancer.rename_bone", "bonemancer.show_bone_relations")]
    select_in_pose(arm, ())
    empty = [d for d in record(mod.BONEMANCER_PT_bones.draw, bpy.context).drawn("operator")
             if d.args == ("bonemancer.add_bone_to_set",)]
    bpy.ops.object.mode_set(mode='OBJECT')
    got = ([(d.text, d.enabled, d.result.attrs.get("use_selected")) for d in add],
           actions, [(d.text, d.enabled) for d in empty])
    return (got == ([("Add 2 Selected to a Bone Set", True, True)],
                    [("bonemancer.rename_bone", "Rename", "c"), ("bonemancer.show_bone_relations", "Relations", "c")],
                    [("Select Bones to Add Them to a Bone Set", False)]), got)
check("UI1 Bones panel: one Add Selected button, and Rename/Relations for the highlighted bone", ui1)


def ui2():
    reset(); arm = make_arm("Rig", ("a", "b")); pick(arm, from_viewport=False)
    select_in_pose(arm, ("b",))
    rows = []
    for i, item in enumerate(picker().bone_selection):
        layout = record(lambda self, ctx: mod.BONEMANCER_UL_bone_picker.draw_item(
            None, ctx, self.layout, None, item, 0, None, "", i), bpy.context)
        rows.append([(d.kind, d.text, d.args[:1]) for d in layout.drawn("label", "operator")])
    bpy.ops.object.mode_set(mode='OBJECT')
    return (rows == [[("label", "a", ())], [("operator", "b", ("bonemancer.select_bone",))]], rows)
check("UI2 Bone Picker rows are just the bone name; no icon buttons per row", ui2)


def ui3():
    reset(); arm = make_arm("Rig", ("a", "b")); pick(arm, from_viewport=False)
    arm.pose.bones["a"]["ik_fk"] = 1.0
    arm.pose.bones["a"].constraints.new('COPY_ROTATION')            # no target: broken
    add("a", "Arms")
    grp = arm.bonemancer_sets["Arms"]
    grp.show_expanded = True
    collapsed = record(mod.BONEMANCER_PT_bone_sets.draw, bpy.context)
    grp.bones[0].show_details = True
    expanded = record(mod.BONEMANCER_PT_bone_sets.draw, bpy.context)

    def bone_row(drawn):
        ops = [d.args[0] for d in drawn.drawn("operator")]
        start = ops.index("bonemancer.select_bone")
        return ops[start:start + 2] + [d.args[1] for d in drawn.drawn("panel_prop") if d.args[1] == "show_details"]
    texts = [t for t in expanded.texts("operator", "prop", "label") if t]
    got = (bone_row(collapsed), "Rename" in collapsed.texts("operator"),
           [t for t in ("Rename", "Remove from Set", "Properties (1)", "Constraints (1, 1 broken)", "1 bone")
            if t not in texts])
    return (got == (["bonemancer.select_bone", "bonemancer.toggle_bone", "show_details"], False, []), got)
check("UI3 Bone Set rows show select, hide and details; details hold labelled actions", ui3)


def ui4():
    valid = {i.identifier for i in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items}
    source = open(mod.__file__, encoding="utf-8").read()
    used = set(re.findall(r"icon\s*=\s*'([A-Z0-9_]+)'", source))
    used |= {icon for _h, icon, _l in mod.RIG_CHECKS.values()}
    return (len(used) > 20 and used <= valid, sorted(used - valid))
check("UI4 every icon the add-on names exists in this Blender", ui4)


def ui5():
    import types
    text = "Bone Sets keep the bones you use often in one place. Add bones from the Bones panel."
    ctx = types.SimpleNamespace(region=types.SimpleNamespace(width=300), preferences=bpy.context.preferences)
    lines = mod.text_lines(ctx, text)
    return (len(lines) > 1 and " ".join(lines) == text and max(map(len, lines)) <= 47, lines)
check("UI5 hints wrap to the sidebar's width", ui5)


def ui6():
    panels = [c for c in mod.classes if issubclass(c, bpy.types.Panel)]
    got = [(c.bl_label, 'DEFAULT_CLOSED' in getattr(c, "bl_options", set())) for c in panels]
    return (got == [("Rig", False), ("Bones", False), ("Bone Sets", False), ("Rig Check", True),
                    ("Shape Keys", True)], got)
check("UI6 panels are Rig, Bones, Bone Sets, Rig Check, Shape Keys; the first three start open", ui6)


def ui7():
    reset(); arm = make_arm("Rig"); add_mesh(arm, ("Basis", "Smile", "Blink")); pick(arm)
    drawn = record(mod.BONEMANCER_PT_shape_keys.draw, bpy.context)
    lists = [d.args[0] for d in drawn.drawn("template_list")]
    no_rig = (sc.__setattr__("bonemancer_rig", None), record(mod.BONEMANCER_PT_shape_keys.draw, bpy.context))[1]
    got = (lists, no_rig.drawn("template_list"), any("Rig panel" in t for t in no_rig.texts("label")))
    return (got == (["BONEMANCER_UL_shape_key_meshes", "BONEMANCER_UL_shape_keys"], [], True), got)
check("UI7 Shape Keys shows the highlighted mesh's keys without expanding it", ui7)


def ui8():
    reset()
    empty = record(mod.BONEMANCER_PT_rig.draw, bpy.context)
    arm = make_arm("Rig")
    pick(None, from_viewport=False)
    unpicked = record(mod.BONEMANCER_PT_rig.draw, bpy.context)
    pick(arm, from_viewport=False)
    picked = record(mod.BONEMANCER_PT_rig.draw, bpy.context)
    got = ([d.args[0] for d in empty.drawn("operator")], len(unpicked.texts("label")) > 0, picked.texts("label"))
    return (got == (["object.armature_add"], True, []), got)
check("UI8 Rig panel guides you until a rig is picked, then stays quiet", ui8)


def registered_props():
    return sorted(p for p in dir(bpy.types.Scene) + dir(bpy.types.Object) if p.startswith(("rmv2_", "bonemancer_")))


def ui_strings():
    """Every label, description and property name BoneMancer registers."""
    for cls in mod.classes:
        idname = getattr(cls, "bl_idname", "")
        if issubclass(cls, bpy.types.Operator):
            rna = getattr(bpy.ops, idname.split(".")[0]).__getattr__(idname.split(".")[1]).get_rna_type()
            yield idname, rna.name
            yield idname, rna.description
            props = rna.properties
        elif issubclass(cls, bpy.types.Panel):
            yield idname, cls.bl_label
            continue
        elif issubclass(cls, bpy.types.PropertyGroup):
            props = cls.bl_rna.properties
        else:
            continue
        for p in props:
            if p.identifier != "rna_type":
                yield f"{cls.__name__}.{p.identifier}", p.name
                yield f"{cls.__name__}.{p.identifier}", p.description


def wrong_set_terms():
    # BoneMancer's own sets are "Bone Sets"; "Bone Collection" only means Blender's native ones
    pattern = re.compile(r"(?<!Bone )\bcollections?\b|\bgroups?\b", re.I)
    return sorted({f"{where}: {text}" for where, text in ui_strings() if text and pattern.search(text)})


check("UI says Bone Set, never collection/group", lambda: (wrong_set_terms() == [], wrong_set_terms()))


EXPECTED_PROPS = sorted(["bonemancer_rig", "bonemancer_settings", "bonemancer_shape_keys", "bonemancer_selected_bone",
                         "bonemancer_rig_check", "bonemancer_sets", "bonemancer_ignored_issues"])
check("registered properties match the allow-list", lambda: (registered_props() == EXPECTED_PROPS, registered_props()))

reset()
check("unregister()", mod.unregister)
check("no leftover add-on props", lambda: (registered_props() == [], registered_props()))
check("no leftover handlers", lambda: (leftover_handlers() == [], leftover_handlers()))
check("foreign handler still present", lambda: (foreign_handler in bpy.app.handlers.depsgraph_update_post, None))
check("re-register()", mod.register)
check("unregister() again", mod.unregister)

finish()
