"""Linked rigs are read-only; library-overridden rigs keep their groups across save/reload."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir, record, RecordingLayout

mod = load_addon()
from bonemancer.core import compat, rig_check, selection, utils
from bonemancer.operators import rig_check as rig_check_ops
from bonemancer.ui import layout as layout_ui, panels
check("register()", mod.register)
sc = bpy.context.scene
work = tmp_dir()
lib_path = os.path.join(work, "lib.blend")
saved_path = os.path.join(work, "override.blend")


def pick(obj):
    selection.follow_viewport_rig(sc, obj)


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
    arm.pose.bones["hip"]["lib_prop"] = 1.0
    # Rig Check: two broken constraints, the knee one ignored in the library file
    for bone in ("hip", "knee"):
        arm.pose.bones[bone].constraints.new('COPY_ROTATION')
    ignored = arm.bonemancer_ignored_issues.add()
    ignored.check, ignored.bone, ignored.detail = "constraint", "knee", "Copy Rotation"
    tab = arm.bonemancer_layout.add()      # Actionable Bones: a layout made in the library file
    tab.name = "Body"
    cell = tab.cells.add()
    cell.bone_name, cell.row, cell.column = "hip", 0, 0
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
        got = (utils.rig_is_editable(linked), add("hip"), refused(lambda: bpy.ops.bonemancer.toggle_bone(bone_name="hip")),
               refused(lambda: bpy.ops.bonemancer.import_bone_collections()))
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == (False, {'CANCELLED'}, {'CANCELLED'}, {'CANCELLED'}), got)
check("linked rig: add to set, hide and import are refused", linked_readonly)


def visible(scene=None):
    return [(i.check, i.bone) for i in rig_check.visible_issues(scene or bpy.context.scene)]


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
               rig_check_ops.BONEMANCER_OT_ignore_issue.description(bpy.context, type("P", (), {"index": 0})()))
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == ({'FINISHED'}, [("constraint", "hip")], {'CANCELLED'}, {'CANCELLED'}, {'CANCELLED'}, 1,
                    rig_check.LINKED_IGNORE_MESSAGE), got)
check("linked rig: checked with library ignores; ignore, stop ignoring and select refused", linked_rig_check)

def set_panels(rig):
    """Which kind of sub-panel the Bone Sets panel uses for rig's sets: panel_prop or panel."""
    return sorted({d.kind for d in record(panels.BONEMANCER_PT_bone_sets.draw, bpy.context).drawn("panel", "panel_prop")})


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


def layout_view():
    """The Actionable Bones operators drawn, and whether the Edit Layout toggle is."""
    drawn = record(panels.BONEMANCER_PT_actionable_bones.draw, bpy.context)
    return (sorted({d.args[0].split(".")[1] for d in drawn.drawn("operator")} - {"layout_blank", "show_layout_tab"}),
            [d.args[1] for d in drawn.drawn("prop")])


def layout_cells(r):
    return [(t.name, [(c.bone_name, c.row, c.column) for c in t.cells]) for t in r.bonemancer_layout]


def layout_edits():
    """Try every layout edit; returns their results."""
    cell = dict(tab="Body", row=0, column=0)
    return [refusal(lambda: bpy.ops.bonemancer.place_bone(tab="Body", row=1, column=1)),
            refusal(lambda: bpy.ops.bonemancer.new_layout_tab(name="Mine")),
            refusal(lambda: bpy.ops.bonemancer.set_cell_side(side='LEFT', **cell)),
            refusal(lambda: bpy.ops.bonemancer.start_move(**cell)),
            refusal(lambda: bpy.ops.bonemancer.clear_cell(**cell))]


def linked_layout():
    sc.collection.objects.link(linked)
    try:
        pick(linked)
        linked.data.bones.active = None
        got = (layout_view(), refusal(lambda: bpy.ops.bonemancer.pick_bone(bone_name="hip")), layout_edits(),
               layout_cells(linked))
    finally:
        pick(None)
        sc.collection.objects.unlink(linked)
    return (got == ((["layout_locked", "pick_bone"], []), {'CANCELLED'}, [{'CANCELLED'}] * 5,
                    [("Body", [("hip", 0, 0)])]), got)
check("linked rig: the library's layout shows read-only; picking and editing are refused", linked_layout)


def locked_empty_layout():
    import types
    fake = types.SimpleNamespace(library=None, override_library=object(), bonemancer_layout=[])
    drawn = RecordingLayout()
    layout_ui.draw_layout(bpy.context, drawn, fake)
    got = (" ".join(drawn.texts("label")), [d.args[0] for d in drawn.drawn("operator")])
    return (got == ("This rig has no layout. Add one in the rig's own file.", []), got)
check("a library rig without a layout says where to add one, with no New Tab", locked_empty_layout)


rig = None


def make_override():
    global rig
    bpy.context.view_layer.objects.active = inst
    inst.select_set(True)
    ov = coll.override_hierarchy_create(sc, bpy.context.view_layer, do_fully_editable=False)
    rig = next(o for o in ov.all_objects if o.type == 'ARMATURE')
    bpy.context.view_layer.objects.active = rig
    pick(rig)
    return (utils.rig_is_editable(rig), rig.name)
check("override rig is editable", make_override)



def override_layout():
    bpy.context.view_layer.objects.active = rig
    pick(rig)
    shown = layout_view()
    # An API-made override is a system one, which can't enter Pose Mode
    locked = (refusal(lambda: bpy.ops.bonemancer.pick_bone(bone_name="hip")),
              refusal(lambda: bpy.ops.bonemancer.pick_bone(bone_name="hip", extend=True)), rig.mode)
    rig.override_library.is_system_override = False      # as Make Editable does
    picked = bpy.ops.bonemancer.pick_bone(bone_name="hip")
    selected = [pb.name for pb in rig.pose.bones if compat.bone_is_selected(pb)]
    sc.bonemancer_settings.edit_layout = True
    editing = layout_view()
    got = (shown, locked, picked, selected, editing, layout_edits(), layout_cells(rig))
    sc.bonemancer_settings.edit_layout = False
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == ((["layout_locked", "pick_bone"], []), ({'CANCELLED'}, {'CANCELLED'}, 'OBJECT'),
                    {'FINISHED'}, ["hip"], (["layout_locked", "pick_bone"], []),
                    [{'CANCELLED'}] * 5, [("Body", [("hip", 0, 0)])]), got)
check("override rig: the library's layout shows and picks; Edit Layout is locked and edits are refused cleanly",
      override_layout)

check("override rig: Bone Sets fold state is saved on the sets",
      lambda: (set_panels(rig) == ["panel_prop"], set_panels(rig)))
def override_prop_buttons():
    entry = rig.bonemancer_sets["Lib"].bones[0]
    rig.bonemancer_sets["Lib"].show_expanded = entry.show_details = entry.show_custom_props = True
    try:
        drawn = record(panels.BONEMANCER_PT_bone_sets.draw, bpy.context)
    finally:
        rig.bonemancer_sets["Lib"].show_expanded = entry.show_details = entry.show_custom_props = False
    got = ([d.args[0] for d in drawn.drawn("operator") if d.args[0].startswith("wm.properties_")],
           any(d.args[1] == '["lib_prop"]' for d in drawn.drawn("prop") if len(d.args) > 1))
    return (got == ([], True), got)
check("override rig: properties show their values but no Edit/Remove (Blender refuses them)", override_prop_buttons)
def override_constraints():
    pb = rig.pose.bones["hip"]
    local = pb.constraints.new('DAMPED_TRACK')          # added on the override itself
    local_name = local.name
    lib_names = [c.name for c in pb.constraints if c.name != local_name]
    try:
        got = (refusal(lambda: bpy.ops.bonemancer.remove_constraint(bone_name="hip", constraint_name=lib_names[0])),
               bpy.ops.bonemancer.remove_constraint(bone_name="hip", constraint_name=local_name),
               [c.name for c in pb.constraints] == lib_names)
    finally:
        if pb.constraints.get(local_name):
            pb.constraints.remove(pb.constraints[local_name])
    return (got == ({'CANCELLED'}, {'FINISHED'}, True), got)
check("override rig: a library constraint can't be removed; one added on the override can", override_constraints)
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
check("override rig: the layout is still the library's after reload",
      lambda: (layout_cells(next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.override_library))
               == [("Body", [("hip", 0, 0)])], None))


def ignores_after_reload():
    r = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.override_library)
    entries = [(e.bone, e.detail) for e in r.bonemancer_ignored_issues]
    bpy.context.view_layer.objects.active = r
    pick_scene = bpy.context.scene
    selection.follow_viewport_rig(pick_scene, r)
    bpy.ops.bonemancer.check_rig()
    shown = visible(pick_scene)
    r_unignore = refusal(lambda: bpy.ops.bonemancer.unignore_issue(index=issue_index("hip")))
    got = (entries, shown, r_unignore, [(e.bone, e.detail) for e in r.bonemancer_ignored_issues])
    return (got == ([("knee", "Copy Rotation"), ("hip", "Copy Rotation")], [], {'FINISHED'},
                    [("knee", "Copy Rotation")]), got)
check("override rig: ignores survive reload; one added on the override can be stopped", ignores_after_reload)

check("unregister()", mod.unregister)
finish()
