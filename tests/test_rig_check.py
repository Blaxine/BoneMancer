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


check("unregister()", mod.unregister)
finish()
