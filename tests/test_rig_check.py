"""Rig Check: each check finds its problem, results never change the rig."""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, make_arm, clear_data, FakePanel, MockLayout

mod = load_addon()
check("register()", mod.register)
sc = bpy.context.scene


def pick(obj):
    if obj and bpy.context.view_layer.objects.get(obj.name) == obj:
        bpy.context.view_layer.objects.active = obj    # the handler follows the active armature
    mod._armature_change_from_viewport = True
    try:
        sc.bonemancer_rig = obj
    finally:
        mod._armature_change_from_viewport = False


def fresh(bones=("root", "spine")):
    """A new picked rig with the given bones, in Object Mode."""
    pick(None)
    clear_data()
    rig = make_arm("Rig", bones)
    pick(rig)
    return rig


def run():
    return bpy.ops.bonemancer.check_rig()


def issues(check_id=None):
    return [(i.check, i.bone, i.detail) for i in sc.bonemancer_rig_check.issues
            if check_id is None or i.check == check_id]


def messages(check_id=None):
    return [i.message for i in sc.bonemancer_rig_check.issues if check_id is None or i.check == check_id]


def snapshot(rig):
    """Everything a check could plausibly change by mistake."""
    return (
        [(pb.name, list(pb.keys()), [(c.name, c.type, c.target, getattr(c, "subtarget", ""), c.influence)
                                    for c in pb.constraints]) for pb in rig.pose.bones],
        [(b.name, b.use_deform, b.parent.name if b.parent else "") for b in rig.data.bones],
        [tuple(v) for v in rig.matrix_basis],
        len(rig.bonemancer_sets),
    )


# --- Panel and check ------------------------------------------------------

def no_rig():
    pick(None)
    clear_data()
    mod.BONEMANCER_PT_rig_check.draw(FakePanel(), bpy.context)
    mod.BONEMANCER_PT_rig_check.draw_header_preset(FakePanel(), bpy.context)
    return (not bpy.ops.bonemancer.check_rig.poll(), None)
check("no picked rig: Check Rig is disabled and the panel draws", no_rig)


def clean_rig():
    fresh()
    before = sc.bonemancer_rig_check.has_run
    r = run()
    got = (before, r, sc.bonemancer_rig_check.has_run, issues())
    return (got == (False, {'FINISHED'}, True, []), got)
check("clean rig: no issues", clean_rig)


# --- Broken constraints ---------------------------------------------------

def constraint_no_target():
    rig = fresh()
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    run()
    got = (issues(), messages())
    return (got == ([("constraint", "spine", "Copy Rotation")], ["spine: Copy Rotation has no target"]), got)
check("constraint without a target is listed", constraint_no_target)


def constraint_missing_bone():
    rig = fresh()
    con = rig.pose.bones["spine"].constraints.new('DAMPED_TRACK')
    con.target = rig
    con.subtarget = "root"
    run()
    ok_before = issues()
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones.remove(rig.data.edit_bones["root"])
    bpy.ops.object.mode_set(mode='OBJECT')
    con.subtarget = "root"   # a bone that no longer exists
    run()
    got = (ok_before, issues(), messages())
    return (got == ([], [("constraint", "spine", "Damped Track")], ["spine: Damped Track targets missing bone 'root'"]), got)
check("constraint aimed at a missing bone is listed; a working one isn't", constraint_missing_bone)


def several_constraints():
    rig = fresh()
    pb = rig.pose.bones["spine"]
    pb.constraints.new('COPY_ROTATION')
    good = pb.constraints.new('COPY_LOCATION')
    good.target = bpy.data.objects.new("Target", None)   # aiming at its own rig would be invalid
    sc.collection.objects.link(good.target)
    pb.constraints.new('COPY_ROTATION')
    run()
    got = issues()
    return (got == [("constraint", "spine", "Copy Rotation"), ("constraint", "spine", "Copy Rotation.001")], got)
check("each broken constraint on a bone is its own issue", several_constraints)


# --- Select, explain, never change -----------------------------------------

def select_bone_issue():
    rig = fresh()
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    run()
    r = bpy.ops.bonemancer.select_issue(index=0)
    pbs = rig.pose.bones
    got = (r, rig.mode, rig.data.bones.active.name if rig.data.bones.active else None,
           [pb.name for pb in pbs if mod.bone_is_selected(pb)])
    return (got == ({'FINISHED'}, 'POSE', "spine", ["spine"]), got)
check("Select selects the issue's bone", select_bone_issue)


def select_bad_index():
    fresh()
    run()
    return (bpy.ops.bonemancer.select_issue(index=5) == {'CANCELLED'}, None)
check("Select with no such issue cancels", select_bad_index)


def explain_draws():
    rig = fresh()
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    run()
    for index in (0, 9):   # an issue, and one that no longer exists
        mod.BONEMANCER_OT_explain_issue.draw(types.SimpleNamespace(index=index, layout=MockLayout()), bpy.context)
    return (all(len(lines) >= 2 for _h, _i, lines in mod.RIG_CHECKS.values()), None)
check("Explain draws, and every check has an explanation", explain_draws)


def unchanged():
    rig = fresh(("root", "spine", "arm.L"))
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    rig.pose.bones["root"]["prop"] = 1.0
    before = snapshot(rig)
    run()
    run()
    return (snapshot(rig) == before, (before, snapshot(rig)))
check("checking twice leaves the rig unchanged", unchanged)


def cleared_on_pick_change():
    rig = fresh()
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    run()
    had = len(issues())
    other = make_arm("Other")
    pick(other)
    got = (had, issues(), sc.bonemancer_rig_check.has_run)
    return (got == (1, [], False), got)
check("results are cleared when another rig is picked", cleared_on_pick_change)


def constraint_list_warning():
    rig = fresh()
    con = rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    mod.BONEMANCER_UL_constraints.draw_item(types.SimpleNamespace(layout_type='DEFAULT'), bpy.context, MockLayout(),
                                            None, con, 0, None, "", 0)
    return (mod.constraint_problem(con) == "has no target", mod.constraint_problem(con))
check("the Bone Sets constraint list uses the same wording", constraint_list_warning)


def panel_draws():
    rig = fresh()
    fp = FakePanel()
    mod.BONEMANCER_PT_rig_check.draw(fp, bpy.context)            # before a check
    run()
    mod.BONEMANCER_PT_rig_check.draw(fp, bpy.context)            # clean
    rig.pose.bones["spine"].constraints.new('COPY_ROTATION')
    run()
    mod.BONEMANCER_PT_rig_check.draw(fp, bpy.context)            # with results
    mod.BONEMANCER_PT_rig_check.draw_header_preset(fp, bpy.context)
    for i, item in enumerate(sc.bonemancer_rig_check.issues):
        mod.BONEMANCER_UL_rig_issues.draw_item(None, bpy.context, MockLayout(), None, item, 0, None, "", i)
check("panel, header and result rows draw", panel_draws)


# --- Broken drivers -------------------------------------------------------

def skinned_mesh(rig, name="Body", shape_keys=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, me)
    sc.collection.objects.link(obj)
    obj.modifiers.new("Armature", 'ARMATURE').object = rig
    if shape_keys:
        obj.shape_key_add(name="Basis")
        obj.shape_key_add(name="Smile")
    return obj


def add_driver(owner, path, var_path, index=-1, expr="v", target=None):
    fc = owner.driver_add(path) if index < 0 else owner.driver_add(path, index)
    d = fc.driver
    d.type = 'SCRIPTED'
    d.expression = expr
    var = d.variables.new()
    var.name = "v"
    var.targets[0].id = target
    var.targets[0].data_path = var_path
    return fc


def driver_missing_prop():
    rig = fresh()
    rig["p"] = 1.0
    add_driver(rig, "location", '["p"]', 0, target=rig)          # fine
    add_driver(rig, "location", '["nope"]', 1, target=rig)       # broken
    run()
    got = (issues("driver"), messages("driver"))
    return (got == ([("driver", "", 'OBJECT:Rig:location[1]')],
                    ["Rig: driver on location[1] variable 'v' reads a missing path '[\"nope\"]'"]), got)
check("driver reading a missing property is listed; a working one isn't", driver_missing_prop)


def driver_broken_later():
    rig = fresh()
    rig["p"] = 1.0
    add_driver(rig, "location", '["p"]', 0, target=rig)
    run()
    before = issues("driver")
    del rig["p"]       # doesn't re-evaluate the driver by itself
    run()
    return ((before, len(issues("driver"))) == ([], 1), (before, issues("driver")))
check("driver broken after the last evaluation is still found", driver_broken_later)


def driver_on_shape_key():
    rig = fresh()
    body = skinned_mesh(rig, shape_keys=True)
    key = body.data.shape_keys
    add_driver(key, 'key_blocks["Smile"].value', '["missing"]', target=rig)
    run()
    got = [(i.check, i.bone, i.detail, i.object_name) for i in sc.bonemancer_rig_check.issues if i.check == "driver"]
    r = bpy.ops.bonemancer.select_issue(index=0)    # drivers are listed before weight issues
    return ((got, r, bpy.context.view_layer.objects.active == body, body.select_get())
            == ([("driver", "", f'KEY:{key.name}:key_blocks["Smile"].value[0]', "Body")], {'FINISHED'}, True, True),
            (got, r))
check("driver on a skinned mesh's shape key is listed and Select picks the mesh", driver_on_shape_key)


def driver_on_armature_data():
    rig = fresh()
    rig.data["q"] = 1.0
    add_driver(rig.data, '["q"]', '["missing"]', target=rig)
    run()
    got = issues("driver")
    return (got == [("driver", "", 'ARMATURE:Rig:["q"][0]')], got)
check("driver on the armature data is listed", driver_on_armature_data)


def driver_on_pose_bone():
    rig = fresh()
    add_driver(rig, 'pose.bones["spine"].location', '["missing"]', 0, target=rig)
    run()
    got = [(i.bone, i.object_name) for i in sc.bonemancer_rig_check.issues]
    return (got == [("spine", "Rig")], got)
check("driver on a pose bone property is tied to that bone", driver_on_pose_bone)


def driver_missing_bone():
    rig = fresh()
    fc = rig.driver_add("location", 2)
    d = fc.driver
    d.type = 'AVERAGE'
    var = d.variables.new()
    var.type = 'TRANSFORMS'
    var.targets[0].id = rig
    var.targets[0].bone_target = "nobone"
    run()
    got = messages("driver")
    return (got == ["Rig: driver on location[2] variable 'var' uses missing bone 'nobone'"], got)
check("driver using a missing bone is listed with the variable", driver_missing_bone)


def driver_bad_expression():
    rig = fresh()
    rig["p"] = 1.0
    add_driver(rig, "location", '["p"]', 0, expr="v +", target=rig)
    run()
    got = messages("driver")
    return (got == ["Rig: driver on location[0] expression 'v +' fails"], got)
check("driver with a broken expression is listed", driver_bad_expression)


def drivers_out_of_scope():
    rig = fresh()
    other = bpy.data.objects.new("Prop", None)
    sc.collection.objects.link(other)
    add_driver(other, "location", '["missing"]', 0, target=rig)        # reads the rig, not part of it
    unskinned = skinned_mesh(rig, "Loose")
    unskinned.modifiers.clear()
    unskinned.parent = rig                                              # object parenting only
    add_driver(unskinned, "location", '["missing"]', 0, target=rig)
    run()
    return (issues("driver") == [], issues("driver"))
check("drivers outside the rig and its skinned meshes are not checked", drivers_out_of_scope)


def python_drivers_when_blocked():
    rig = fresh()
    rig["p"] = 1.0
    add_driver(rig, "location", '["p"]', 0, expr="v +", target=rig)
    original = mod.python_drivers_blocked
    mod.python_drivers_blocked = lambda: True
    try:
        run()
        fp = FakePanel()
        mod.BONEMANCER_PT_rig_check.draw(fp, bpy.context)
        got = (issues("driver"), sc.bonemancer_rig_check.python_drivers)
    finally:
        mod.python_drivers_blocked = original
    run()
    got += (sc.bonemancer_rig_check.python_drivers,)
    return (got == ([], 1, 0), got)
check("Python drivers are counted, not listed, while scripts are blocked", python_drivers_when_blocked)


# --- Unpaired left/right bones --------------------------------------------

def unpaired(bones):
    fresh(bones)
    run()
    return [bone for _c, bone, _d in issues("unpaired")]


check("a side bone without its partner is listed",
      lambda: (unpaired(("root", "arm.L")) == ["arm.L"], unpaired(("root", "arm.L"))))
check("a matched pair is not listed",
      lambda: (unpaired(("arm.L", "arm.R", "hand_l", "hand_r")) == [], unpaired(("arm.L", "arm.R", "hand_l", "hand_r"))))
check("prefix and word sides are paired too (L_hand, LeftFoot)",
      lambda: (unpaired(("L_hand", "LeftFoot", "RightFoot")) == ["L_hand"], unpaired(("L_hand", "LeftFoot", "RightFoot"))))
check("names without a side are never listed (spine, Lid)",
      lambda: (unpaired(("spine", "Lid", "root")) == [], unpaired(("spine", "Lid", "root"))))
check("numbered copies need a numbered partner",
      lambda: (unpaired(("arm.L", "arm.R", "arm.L.001")) == ["arm.L.001"], unpaired(("arm.L", "arm.R", "arm.L.001"))))


def unpaired_message():
    fresh(("root", "arm.R"))
    run()
    return (messages("unpaired") == ["arm.R: no 'arm.L' on the other side"], messages("unpaired"))
check("the message names the missing partner", unpaired_message)


# --- Weight mismatch ------------------------------------------------------

def weigh(mesh_obj, group, weight):
    """A vertex group on mesh_obj for group, with weight on every vertex (0 = empty group)."""
    vg = mesh_obj.vertex_groups.new(name=group)
    if weight:
        vg.add(list(range(len(mesh_obj.data.vertices))), weight, 'REPLACE')
    return vg


def weight_rig():
    """root: weighted, deform · spine: deform, empty group · tail: deform, no group ·
    ctrl: not deform, weighted · mch: not deform, empty group."""
    rig = fresh(("root", "spine", "tail", "ctrl", "mch"))
    for name in ("ctrl", "mch"):
        rig.data.bones[name].use_deform = False
    body = skinned_mesh(rig)
    weigh(body, "root", 1.0)
    weigh(body, "spine", 0.0)
    weigh(body, "ctrl", 0.5)
    weigh(body, "mch", 0.0)
    return rig, body


def unweighted_deform():
    weight_rig()
    run()
    got = [bone for _c, bone, _d in issues("deform_unweighted")]
    return (got == ["spine", "tail"], got)
check("deform bones with an empty group or no group are listed", unweighted_deform)


def weighted_nondeform():
    weight_rig()
    run()
    got = (issues("nondeform_weighted"), messages("nondeform_weighted"))
    return (got == ([("nondeform_weighted", "ctrl", "")], ["ctrl: weighted on Body but Deform is off"]), got)
check("non-deform bones with weights are listed; an empty group isn't", weighted_nondeform)


def weights_across_meshes():
    rig, body = weight_rig()
    other = skinned_mesh(rig, "Head")
    weigh(other, "spine", 1.0)
    weigh(other, "tail", 1.0)
    run()
    return (issues("deform_unweighted") == [], issues("deform_unweighted"))
check("weights on any skinned mesh count", weights_across_meshes)


def armature_parented_mesh():
    rig = fresh(("root",))
    body = skinned_mesh(rig)
    body.modifiers.clear()
    body.parent = rig
    body.parent_type = 'ARMATURE'
    run()
    return (issues("deform_unweighted") == [("deform_unweighted", "root", "")], issues())
check("a mesh with armature parenting counts as skinned", armature_parented_mesh)


def bone_parented_prop():
    rig = fresh(("root", "hand"))
    rig.data.bones["hand"].use_deform = False
    body = skinned_mesh(rig)
    weigh(body, "root", 1.0)
    prop = skinned_mesh(rig, "Sword")
    prop.modifiers.clear()
    prop.parent = rig
    prop.parent_type = 'BONE'
    prop.parent_bone = "hand"
    weigh(prop, "hand", 1.0)      # leftover weights on a rigid prop
    run()
    return (issues("nondeform_weighted") == [], issues())
check("a bone-parented prop is not skinned, so its groups don't count", bone_parented_prop)


def no_skinned_mesh():
    fresh(("root", "spine"))
    run()
    return (issues("deform_unweighted") + issues("nondeform_weighted") == [], issues())
check("a rig with no skinned mesh gets no weight issues", no_skinned_mesh)


# --- Setup mistakes -------------------------------------------------------

def transform(scale=(1, 1, 1), rotation=(0, 0, 0)):
    rig = fresh(("root",))
    rig.scale = scale
    rig.rotation_euler = rotation
    run()
    return [(i.check, i.object_name, i.message) for i in sc.bonemancer_rig_check.issues if i.check == "rig_transform"]


check("unapplied scale is listed",
      lambda: (transform(scale=(0.5, 0.5, 0.5)) == [("rig_transform", "Rig", "Rig: scale (0.5, 0.5, 0.5) not applied")],
               transform(scale=(0.5, 0.5, 0.5))))
check("unapplied rotation is listed",
      lambda: (transform(rotation=(1.5708, 0, 0)) == [("rig_transform", "Rig", "Rig: rotation not applied")],
               transform(rotation=(1.5708, 0, 0))))
check("rotation and scale together are one issue",
      lambda: ([m for _c, _o, m in transform(scale=(2, 2, 2), rotation=(0, 0, 3.0))]
               == ["Rig: rotation and scale (2, 2, 2) not applied"], transform(scale=(2, 2, 2), rotation=(0, 0, 3.0))))
check("an applied rig is not listed (a full turn counts as applied)",
      lambda: (transform(rotation=(0, 0, 2 * 3.141592653589793)) == [], transform(rotation=(0, 0, 6.283185307179586))))


def parented_mesh(rig, name, parent_type='OBJECT', modifier_object="none"):
    """A mesh parented to rig; modifier_object: 'none' = no modifier, None = modifier without object."""
    obj = skinned_mesh(rig, name)
    obj.modifiers.clear()
    obj.parent = rig
    obj.parent_type = parent_type
    if modifier_object != "none":
        obj.modifiers.new("Armature", 'ARMATURE').object = modifier_object
    return obj


def setup_issues():
    return [(i.check, i.detail, i.message) for i in sc.bonemancer_rig_check.issues
            if i.check in ("mesh_no_modifier", "modifier_wrong_rig")]


def mesh_without_modifier():
    rig = fresh(("root",))
    parented_mesh(rig, "Bare")
    parented_mesh(rig, "Fine", modifier_object=rig)
    run()
    got = setup_issues()
    return (got == [("mesh_no_modifier", "Bare", "Bare: parented to the rig without an Armature modifier")], got)
check("a mesh parented without an Armature modifier is listed", mesh_without_modifier)


def modifier_problems():
    rig = fresh(("root",))
    other = make_arm("Other")
    pick(rig)
    parented_mesh(rig, "Empty", modifier_object=None)
    parented_mesh(rig, "Elsewhere", modifier_object=other)
    layered = parented_mesh(rig, "Layered", modifier_object=other)
    layered.modifiers.new("Armature.001", 'ARMATURE').object = rig      # one of them is this rig: fine
    parented_mesh(rig, "ArmParent", parent_type='ARMATURE', modifier_object=other)
    run()
    got = setup_issues()
    return (got == [
        ("modifier_wrong_rig", "Empty:Armature", "Empty: Armature modifier 'Armature' has no rig set"),
        ("modifier_wrong_rig", "Elsewhere:Armature", "Elsewhere: Armature modifier 'Armature' uses 'Other' instead of this rig"),
        ("modifier_wrong_rig", "ArmParent:Armature", "ArmParent: Armature modifier 'Armature' uses 'Other' instead of this rig"),
    ], got)
check("Armature modifiers with no rig or another rig are listed", modifier_problems)


def bone_parented_mesh():
    rig = fresh(("root",))
    prop = parented_mesh(rig, "Sword", parent_type='BONE')
    prop.parent_bone = "root"
    run()
    return (setup_issues() == [], setup_issues())
check("a bone-parented mesh is never a setup mistake", bone_parented_mesh)


def select_object_issue():
    rig = fresh(("root",))
    bare = parented_mesh(rig, "Bare")
    run()
    index = next(i for i, it in enumerate(sc.bonemancer_rig_check.issues) if it.check == "mesh_no_modifier")
    r_obj = bpy.ops.bonemancer.select_issue(index=index)
    selected = (bpy.context.view_layer.objects.active == bare, bare.select_get())
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    r_pose = bpy.ops.bonemancer.select_issue(index=index)
    bpy.ops.object.mode_set(mode='OBJECT')
    got = (r_obj, selected, r_pose)
    return (got == ({'FINISHED'}, (True, True), {'CANCELLED'}), got)
check("Select picks an object issue's mesh in Object Mode and refuses elsewhere", select_object_issue)


def pick_switch_during_check():
    broken = fresh(("root",))
    broken.pose.bones["root"].constraints.new('COPY_ROTATION')
    clean = make_arm("Clean", ("root",))
    bpy.context.view_layer.objects.active = clean      # the viewport's armature...
    mod._armature_change_from_viewport = True
    sc.bonemancer_rig = broken                         # ...differs from the pick
    mod._armature_change_from_viewport = False
    run()
    got = (sc.bonemancer_rig.name, issues(), sc.bonemancer_rig_check.has_run)
    return (got == ("Clean", [], True), got)
check("results always describe the rig that ends up picked", pick_switch_during_check)


def icons_exist():
    valid = {i.identifier for i in bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items}
    used = {icon for _h, icon, _l in mod.RIG_CHECKS.values()} | {'VIEWZOOM', 'CHECKMARK', 'SCRIPT', 'INFO',
                                                                  'RESTRICT_SELECT_OFF', 'ERROR'}
    return (used <= valid, sorted(used - valid))
check("every Rig Check icon exists in this Blender", icons_exist)


check("unregister()", mod.unregister)
finish()
