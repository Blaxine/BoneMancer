"""Actionable Bones: layout tabs, placing bones in cells, and picking them."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir, record

mod = load_addon()
from bonemancer import handlers
from bonemancer.core import compat, layout, selection
from bonemancer.ui import panels
check("register()", mod.register)
sc = bpy.context.scene
BONES = ("root", "spine", "arm.L", "hand.R")


def pick(obj):
    selection.follow_viewport_rig(sc, obj)


def fresh():
    """A rig with BONES, picked, in Object Mode, with an empty layout."""
    pick(None)
    clear_data()
    sc.bonemancer_settings.layout_tab = ""
    sc.bonemancer_settings.edit_layout = False
    rig = make_arm("Rig", BONES)
    pick(rig)
    return rig


def op(idname, /, **kw):
    return refused(lambda: getattr(bpy.ops.bonemancer, idname)(**kw))


def new_tab(name="Body", columns=16, rows=24):
    return op("new_layout_tab", name=name, columns=columns, rows=rows)


def place(bone, row, column, tab="Body"):
    rig = sc.bonemancer_rig
    rig.data.bones.active = rig.data.bones[bone] if bone else None
    return op("place_bone", tab=tab, row=row, column=column)


def cells(rig, tab="Body"):
    return sorted((c.bone_name, c.row, c.column, c.side) for c in layout.find_tab(rig, tab).cells)


def draw():
    return record(panels.BONEMANCER_PT_actionable_bones.draw, bpy.context)


def selected(rig):
    return sorted(pb.name for pb in rig.pose.bones if compat.bone_is_selected(pb))


# ---------------------------------------------------------------- tabs

def empty_states():
    pick(None)
    no_rig = draw()
    fresh()
    empty = draw()
    got = (any("Pick an armature" in t or "armature" in t.lower() for t in no_rig.texts("label")),
           [d.args[0] for d in empty.drawn("operator")],
           any("Lay out" in t for t in empty.texts("label")))
    return (got == (True, ["bonemancer.new_layout_tab"], True), got)
check("no rig and empty layout show their hints; the empty layout offers New Tab", empty_states)


def tab_creation():
    rig = fresh()
    got = (new_tab(), [(t.name, t.columns, t.rows) for t in rig.bonemancer_layout],
           sc.bonemancer_settings.layout_tab,
           new_tab(), new_tab(name="  "), new_tab(name="Hands", columns=20, rows=12),
           sc.bonemancer_settings.layout_tab)
    return (got == ({'FINISHED'}, [("Body", 16, 24)], "Body", {'CANCELLED'}, {'CANCELLED'}, {'FINISHED'}, "Hands"),
            got)
check("New Tab adds a named tab of the given size and shows it; duplicates and blank names are refused",
      tab_creation)


def no_rig_refused():
    fresh()
    bpy.context.view_layer.objects.active = None   # or the handler picks it again
    pick(None)
    return (new_tab() == {'CANCELLED'}, None)
check("New Tab is refused without a picked rig", no_rig_refused)


def show_tab():
    rig = fresh()
    new_tab()
    new_tab(name="Hands")
    op("show_layout_tab", name="Body")
    shown = layout.active_tab(sc, rig).name
    sc.bonemancer_settings.layout_tab = "Gone"
    fallback = layout.active_tab(sc, rig).name
    return ((shown, fallback) == ("Body", "Body"), (shown, fallback))
check("the tab bar switches tabs; an unknown tab falls back to the first", show_tab)


# ---------------------------------------------------------------- placing

def placing():
    rig = fresh()
    new_tab()
    got = (place("arm.L", 3, 2), place("spine", 2, 7), place("hand.R", 4, 12), cells(rig))
    return (got == ({'FINISHED'}, {'FINISHED'}, {'FINISHED'},
                    [("arm.L", 3, 2, 'LEFT'), ("hand.R", 4, 12, 'RIGHT'), ("spine", 2, 7, 'CENTER')]), got)
check("placing stores the active bone with a side from its name", placing)


def placing_refused():
    rig = fresh()
    new_tab()
    got = (place(None, 0, 0), place("root", 24, 0), place("root", 0, 16), place("root", 0, 0, tab="Nope"),
           cells(rig))
    return (got == ({'CANCELLED'},) * 4 + ([],), got)
check("placing is refused without an active bone, outside the grid or on an unknown tab", placing_refused)


def placing_in_edit_mode():
    rig = fresh()
    new_tab()
    bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones.active = rig.data.edit_bones["spine"]
    got = op("place_bone", tab="Body", row=1, column=1)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ((got, cells(rig)) == ({'FINISHED'}, [("spine", 1, 1, 'CENTER')]), (got, cells(rig)))
check("in armature Edit Mode the active edit bone is placed", placing_in_edit_mode)


# ---------------------------------------------------------------- picking

def picking():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    for pb in rig.pose.bones:
        compat.set_bone_selected(pb, pb.name == "root")
    rig.data.bones.active = rig.data.bones["root"]
    got = (op("pick_bone", bone_name="arm.L"), rig.mode, selected(rig), rig.data.bones.active.name)
    return (got == ({'FINISHED'}, 'POSE', ["arm.L"], "arm.L"), got)
check("clicking a cell selects only its bone, makes it active and enters Pose Mode", picking)


def pick_missing():
    fresh()
    return (op("pick_bone", bone_name="nope") == {'CANCELLED'}, None)
check("picking a bone that doesn't exist is refused", pick_missing)


def active_named():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    op("pick_bone", bone_name="arm.L")
    return ("arm.L" in draw().texts("label"), draw().texts("label"))
check("the panel names the active bone under the grid", active_named)


def shift_toggles():
    rig = fresh()
    new_tab()
    op("pick_bone", bone_name="arm.L")
    added = (op("pick_bone", bone_name="spine", extend=True), selected(rig), rig.data.bones.active.name)
    removed = (op("pick_bone", bone_name="arm.L", extend=True), selected(rig))
    plain = (op("pick_bone", bone_name="hand.R"), selected(rig))
    got = (added, removed, plain)
    return (got == (({'FINISHED'}, ["arm.L", "spine"], "spine"), ({'FINISHED'}, ["spine"]),
                    ({'FINISHED'}, ["hand.R"])), got)
check("Shift+click adds a bone to the selection or removes it; a plain click replaces it", shift_toggles)


def shift_in_edit_mode():
    rig = fresh()
    bpy.ops.object.mode_set(mode='EDIT')
    for eb in rig.data.edit_bones:
        eb.select = eb.select_head = eb.select_tail = eb.name == "root"
    got = (op("pick_bone", bone_name="spine", extend=True), rig.mode,
           sorted(eb.name for eb in rig.data.edit_bones if eb.select), rig.data.edit_bones.active.name)
    bpy.ops.object.mode_set(mode='OBJECT')
    return (got == ({'FINISHED'}, 'EDIT', ["root", "spine"], "spine"), got)
check("Shift+click in armature Edit Mode toggles edit bones and stays in Edit Mode", shift_in_edit_mode)


def pick_is_undoable():
    return ('UNDO' in bpy.types.BONEMANCER_OT_pick_bone.bl_options, None)
check("picking from a cell is one undo step", pick_is_undoable)


def hidden_rig(how):
    """A rig with arm.L placed and hidden the given way; returns the rig."""
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    coll = rig.data.collections.new("Arms")
    coll.assign(rig.data.bones["arm.L"])
    if how == "flag":
        compat.set_hidden(rig.pose.bones["arm.L"], True)
    elif how == "collection":
        coll.is_visible = False
    elif how == "parent":
        parent = rig.data.collections.new("Limbs")
        coll.parent = parent
        parent.is_visible = False
    elif how == "solo":
        other = rig.data.collections.new("Torso")
        other.assign(rig.data.bones["spine"])
        other.is_solo = True
    return rig


def hidden_cells():
    got = {}
    for how in ("flag", "collection", "parent", "solo"):
        rig = hidden_rig(how)
        bpy.ops.object.mode_set(mode='POSE')
        for pb in rig.pose.bones:
            compat.set_bone_selected(pb, False)
        drawn = [d.args[0] for d in draw().drawn("operator") if d.args[0].endswith(("pick_bone", "hidden_cell"))]
        got[how] = (op("pick_bone", bone_name="arm.L"), op("pick_bone", bone_name="arm.L", extend=True),
                    selected(rig), drawn)
        bpy.ops.object.mode_set(mode='OBJECT')
    want = ({'CANCELLED'}, {'CANCELLED'}, [], ["bonemancer.hidden_cell"])
    return (all(g == want for g in got.values()), got)
check("a bone hidden by its flag, its collection, a parent collection or another collection's solo draws "
      "greyed and can't be picked", hidden_cells)


def visible_in_one_collection():
    rig = hidden_rig("collection")
    rig.data.collections.new("Shown").assign(rig.data.bones["arm.L"])
    return (op("pick_bone", bone_name="arm.L") == {'FINISHED'}, None)
check("a bone in a hidden and a visible collection can still be picked", visible_in_one_collection)


def missing_cell():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones.remove(rig.data.edit_bones["arm.L"])
    bpy.ops.object.mode_set(mode='OBJECT')
    ops = [d for d in draw().drawn("operator") if d.args[0] == "bonemancer.missing_cell"]
    got = (len(ops), ops[0].kwargs.get("icon") if ops else None, cells(rig))
    return (got == (1, 'ERROR', [("arm.L", 3, 2, 'LEFT')]), got)
check("a cell whose bone was deleted draws a warning and keeps its name", missing_cell)


def follows_rename_operator():
    rig = fresh()
    new_tab()
    new_tab(name="Hands")
    place("arm.L", 3, 2)
    place("arm.L", 0, 0, tab="Hands")
    bpy.ops.bonemancer.rename_bone(bone_name="arm.L", mode='EXACT', new_name="upper_arm.L")
    got = (cells(rig), cells(rig, "Hands"))
    return (got == ([("upper_arm.L", 3, 2, 'LEFT')], [("upper_arm.L", 0, 0, 'LEFT')]), got)
check("cells on every tab follow a bone renamed with Rename", follows_rename_operator)


def follows_outside_rename():
    rig = fresh()
    new_tab()
    place("spine", 1, 1)
    selection.update_bone_list(sc)                   # the Bone Picker knows the current names
    rig.data.bones["spine"].name = "chest"           # F2 / Outliner rename
    handlers.on_depsgraph_update(sc, bpy.context.evaluated_depsgraph_get())
    return (cells(rig) == [("chest", 1, 1, 'CENTER')], cells(rig))
check("cells follow an outside rename", follows_outside_rename)


# ---------------------------------------------------------------- drawing

def grid_drawing():
    rig = fresh()
    new_tab(columns=16, rows=24)
    place("arm.L", 3, 2)
    op("pick_bone", bone_name="arm.L")
    picking_view = draw()
    sc.bonemancer_settings.edit_layout = True
    editing_view = draw()
    picks = [(d.result, d.kwargs) for d in picking_view.drawn("operator") if d.args[0] == "bonemancer.pick_bone"]
    grid = [d for d in picking_view.drawn("grid_flow")]
    blanks = [d for d in picking_view.drawn("operator") if d.args[0] == "bonemancer.layout_blank"]
    places = [d for d in editing_view.drawn("operator") if d.args[0] == "bonemancer.place_bone"]
    tabs = [d.kwargs for d in picking_view.drawn("operator") if d.args[0] == "bonemancer.show_layout_tab"]
    got = (len(grid), grid[0].kwargs.get("columns") if grid else None, len(picks),
           picks[0][1].get("icon") if picks else None, picks[0][1].get("depress") if picks else None,
           len(blanks), len(places), [t.get("text") for t in tabs],
           [d.args[1] for d in picking_view.drawn("prop")])
    return (got == (1, 16, 1, 'COLLECTION_COLOR_05', True, 16 * 24 - 1, 16 * 24 - 1, ["Body"], ["edit_layout"]),
            got)
check("the grid draws one button per placed bone, pressed while selected; Edit Layout turns blanks into "
      "place buttons", grid_drawing)


# ---------------------------------------------------------------- saving

def survives_reload():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    sc.bonemancer_settings.edit_layout = True
    path = os.path.join(tmp_dir(), "layout.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    rig = bpy.data.objects["Rig"]
    got = ([(t.name, t.columns, t.rows) for t in rig.bonemancer_layout], cells(rig))
    return (got == ([("Body", 16, 24)], [("arm.L", 3, 2, 'LEFT')]), got)
check("the layout survives save and reopen", survives_reload)

sc = bpy.context.scene
finish()
