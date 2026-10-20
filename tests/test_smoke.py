"""Smoke checks, pitfall regressions and register/unregister lifecycle."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, FakePanel, MockLayout


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
        ("toggle_constraints_bone", lambda: bpy.ops.bonemancer.toggle_bone_constraints(bone_name="arm.L")),
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
            b.show_custom_props = True
            b.show_constraints = True
    fp = FakePanel()
    fp._draw_bone_buttons = lambda *a: mod.BONEMANCER_PT_bone_sets._draw_bone_buttons(fp, *a)
    mod.BONEMANCER_PT_bone_sets.draw(fp, bpy.context)
    mod.BONEMANCER_PT_rig.draw(FakePanel(), bpy.context)
    grp = sc.bonemancer_shape_keys.object_groups[0]
    grp.show_shape_keys = True
    mod.BONEMANCER_PT_shape_keys.draw(FakePanel(), bpy.context)
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


EXPECTED_PROPS = sorted(["bonemancer_rig", "bonemancer_settings", "bonemancer_shape_keys", "bonemancer_selected_bone", "bonemancer_sets"])
check("registered properties match the allow-list", lambda: (registered_props() == EXPECTED_PROPS, registered_props()))

reset()
check("unregister()", mod.unregister)
check("no leftover add-on props", lambda: (registered_props() == [], registered_props()))
check("no leftover handlers", lambda: (leftover_handlers() == [], leftover_handlers()))
check("foreign handler still present", lambda: (foreign_handler in bpy.app.handlers.depsgraph_update_post, None))
check("re-register()", mod.register)
check("unregister() again", mod.unregister)

finish()
