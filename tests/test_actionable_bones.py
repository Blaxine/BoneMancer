"""Actionable Bones: layout tabs, placing bones in cells, and picking them."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import addon_utils
import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, tmp_dir, record

mod = load_addon()
from bonemancer import handlers
from bonemancer.core import compat, layout, selection, templates
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
    return (got == (True, ["bonemancer.apply_layout_template", "bonemancer.new_layout_tab"], True), got)
check("no rig and empty layout show their hints; the empty layout offers Apply Rigify Template and New Tab",
      empty_states)


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


# ---------------------------------------------------------------- editing

def cell_op(idname, row, column, tab="Body", **kw):
    return op(idname, tab=tab, row=row, column=column, **kw)


def side_defaults():
    rig = fresh()
    for name in ("thigh_R", "Left_toe", "neck"):
        bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones.new(name).tail = (0, 0, 1)
        bpy.ops.object.mode_set(mode='OBJECT')
    new_tab()
    for i, name in enumerate(("arm.L", "hand.R", "thigh_R", "Left_toe", "neck")):
        place(name, 0, i)
    return (cells(rig) == [("Left_toe", 0, 3, 'LEFT'), ("arm.L", 0, 0, 'LEFT'), ("hand.R", 0, 1, 'RIGHT'),
                           ("neck", 0, 4, 'CENTER'), ("thigh_R", 0, 2, 'RIGHT')], cells(rig))
check("a placed bone's side comes from its name: .L, _R, Left_ and unmirrored names", side_defaults)


def once_per_tab():
    rig = fresh()
    new_tab()
    new_tab(name="Hands")
    place("arm.L", 3, 2)
    place("arm.L", 5, 5)
    place("arm.L", 1, 1, tab="Hands")
    got = (cells(rig), cells(rig, "Hands"))
    return (got == ([("arm.L", 5, 5, 'LEFT')], [("arm.L", 1, 1, 'LEFT')]), got)
check("placing a bone already on the tab moves it; another tab can hold it too", once_per_tab)


def recolour_and_clear():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    place("spine", 2, 7)
    got = (cell_op("set_cell_side", 3, 2, side='RIGHT'), cell_op("clear_cell", 2, 7),
           cell_op("clear_cell", 9, 9), cell_op("set_cell_side", 9, 9, side='LEFT'), cells(rig),
           sorted(b.name for b in rig.data.bones))
    return (got == ({'FINISHED'}, {'FINISHED'}, {'CANCELLED'}, {'CANCELLED'}, [("arm.L", 3, 2, 'RIGHT')],
                    sorted(BONES)), got)
check("a cell can be recoloured and cleared, keeping the bone; empty cells are refused", recolour_and_clear)


def moving():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    place("spine", 2, 7)
    cell_op("set_cell_side", 3, 2, side='CENTER')
    settings = sc.bonemancer_settings
    got = (cell_op("start_move", 3, 2), layout.moving_cell(settings, rig).bone_name,
           cell_op("move_cell", 2, 7),                       # taken
           cell_op("move_cell", 6, 6), cells(rig), settings.move_tab,
           cell_op("move_cell", 0, 0))                       # nothing picked up
    return (got == ({'FINISHED'}, "arm.L", {'CANCELLED'}, {'FINISHED'},
                    [("arm.L", 6, 6, 'CENTER'), ("spine", 2, 7, 'CENTER')], "", {'CANCELLED'}), got)
check("Move picks a cell up and the next empty cell takes it, side kept; taken cells are refused", moving)


def cancel_move():
    rig = fresh()
    new_tab()
    new_tab(name="Hands")
    op("show_layout_tab", name="Body")
    place("arm.L", 3, 2)
    settings = sc.bonemancer_settings
    got = []
    for undo in (lambda: op("cancel_move"), lambda: op("show_layout_tab", name="Hands"),
                 lambda: setattr(settings, "edit_layout", False), lambda: cell_op("clear_cell", 3, 2)):
        op("show_layout_tab", name="Body")
        settings.edit_layout = True
        if not cells(rig):
            place("arm.L", 3, 2)
        cell_op("start_move", 3, 2)
        undo()
        got.append(settings.move_tab)
    return (got == [""] * 4, got)
check("a move is dropped by clicking its cell again, switching tab, leaving Edit Layout or clearing the cell",
      cancel_move)


def session_reset():
    global sc
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    settings = sc.bonemancer_settings
    settings.edit_layout = True
    cell_op("start_move", 3, 2)
    other = make_arm("Other", ("a",))
    pick(other)
    after_pick = (settings.edit_layout, settings.move_tab)
    bpy.context.view_layer.objects.active = rig    # or the handler picks Other again
    pick(rig)
    settings.edit_layout = True
    cell_op("start_move", 3, 2)
    before_save = (settings.edit_layout, settings.move_tab)
    path = os.path.join(tmp_dir(), "session.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    settings = sc.bonemancer_settings
    got = (after_pick, before_save, (settings.edit_layout, settings.move_tab))
    return (got == ((False, ""), (True, "Body"), (False, "")), got)
check("Edit Layout and a pending move are off after picking another rig and after reopening", session_reset)


def edit_drawing():
    rig = fresh()
    new_tab(columns=4, rows=4)
    place("arm.L", 0, 0)
    place("spine", 1, 1)
    bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones.remove(rig.data.edit_bones["spine"])
    bpy.ops.object.mode_set(mode='OBJECT')
    settings = sc.bonemancer_settings
    settings.edit_layout = True

    def ops(view):
        return [(d.args[0].split(".")[1], d.kwargs.get("icon")) for d in view.drawn("operator")
                if d.args[0] not in ("bonemancer.show_layout_tab",)]
    editing = ops(draw())
    cell_op("start_move", 0, 0)
    view = draw()
    moving = ops(view)
    line = [t for t in view.texts("label") if "move" in t]
    got = (editing[:2], editing.count(("place_bone", 'BLANK1')), editing[5],
           moving[0], moving.count(("move_cell", 'BLANK1')), line)
    return (got == ([("cell_menu", 'COLLECTION_COLOR_05'), ("place_bone", 'BLANK1')], 14, ("cell_menu", 'ERROR'),
                    ("cancel_move", 'COLLECTION_COLOR_05'), 14, ["Click an empty cell to move arm.L"]), got)
check("in Edit Layout filled cells open their menu, missing ones too; a move shows its line and turns blanks "
      "into move targets", edit_drawing)


def cell_menu_drawing():
    rig = fresh()
    new_tab()
    place("arm.L", 3, 2)
    from bonemancer.ui.layout import draw_cell_menu
    tab = layout.find_tab(rig, "Body")
    view = record(lambda panel, _ctx: draw_cell_menu(panel.layout, tab, tab.cells[0]), bpy.context)
    got = [(d.args[0].split(".")[1], d.text) for d in view.drawn("operator")]
    return (got == [("set_cell_side", "Left"), ("set_cell_side", "Right"), ("set_cell_side", "Centre"),
                    ("start_move", "Move"), ("clear_cell", "Clear")], got)
check("a filled cell's menu offers Left, Right, Centre, Move and Clear", cell_menu_drawing)


# ---------------------------------------------------------------- templates

# Columns each template mirrors across: Body around column 7, Hands down the middle
MIRRORED = {"RIGIFY_BODY": 15, "RIGIFY_HANDS": 16}


def template_shapes():
    bad = []
    for t in templates.TEMPLATES:
        positions = list(t.cells.values())
        width = MIRRORED[t.id]
        if len(t.silhouette) != t.rows or any(len(line) != t.columns for line in t.silhouette):
            bad.append((t.id, "silhouette size"))
        if any(line[:width] != line[:width][::-1] for line in t.silhouette):
            bad.append((t.id, "silhouette not mirrored"))
        if any(t.cells[n.replace(".R", ".L", 1)] != (r, width - 1 - c) for n, (r, c) in t.cells.items() if ".R" in n):
            bad.append((t.id, "controls not mirrored"))
        if len(set(positions)) != len(positions):
            bad.append((t.id, "two controls share a cell"))
        if any(not (0 <= r < t.rows and 0 <= c < t.columns) for r, c in positions):
            bad.append((t.id, "control outside the grid"))
        if any("tweak" in name for name in t.cells):
            bad.append((t.id, "tweak control"))
    got = (bad, [(t.id, len(t.cells)) for t in templates.TEMPLATES])
    return (got == ([], [("RIGIFY_BODY", 50), ("RIGIFY_HANDS", 52)]), got)
check("templates: silhouettes fit and mirror, every control has its own cell, no tweak controls", template_shapes)


def rigify_human():
    """Generate a Rigify human; returns the generated rig, picked, with an empty layout."""
    pick(None)
    clear_data()
    sc.bonemancer_settings.layout_tab = ""
    addon_utils.enable("rigify", default_set=True)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.active_object
    bpy.ops.pose.rigify_generate()
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o != meta)
    bpy.context.view_layer.objects.active = rig
    pick(rig)
    return rig


human = None


def template_bones_exist():
    global human
    human = rigify_human()
    missing = sorted(name for t in templates.TEMPLATES for name in t.cells if name not in human.data.bones)
    return (missing == [], missing)
check("templates: every control is on a generated Rigify human (guards Rigify renames)", template_bones_exist)


def template_cells(tab):
    return sorted((c.bone_name, c.row, c.column) for c in layout.find_tab(human, tab).cells)


def apply_on_rigify():
    result = op("apply_layout_template")
    tabs = [(t.name, t.columns, t.rows, t.template) for t in human.bonemancer_layout]
    sides = {c.bone_name: c.side for t in human.bonemancer_layout for c in t.cells}
    got = (result, tabs, len(template_cells("Body")), len(template_cells("Hands")),
           [sides[n] for n in ("hand_ik.L", "thumb.01.R.001", "head")], sc.bonemancer_settings.layout_tab,
           template_cells("Body") == sorted((n, r, c) for n, (r, c) in templates.BODY.cells.items()))
    return (got == ({'FINISHED'}, [("Body", 16, 23, "RIGIFY_BODY"), ("Hands", 16, 9, "RIGIFY_HANDS")], 50, 52,
                    ['LEFT', 'RIGHT', 'CENTER'], "Body", True), got)
check("Apply Rigify Template adds Body and Hands tabs and places every control in its cell", apply_on_rigify)


def reapply_changes_nothing():
    before = (template_cells("Body"), template_cells("Hands"))
    placed = templates.apply_templates(human)
    return ((placed, (template_cells("Body"), template_cells("Hands"))) == (0, before), placed)
check("applying again places nothing and changes nothing", reapply_changes_nothing)


def hand_edits_survive():
    settings = sc.bonemancer_settings
    settings.edit_layout = True
    hand = templates.BODY.cells["hand_ik.R"]
    cell_op("start_move", *hand)
    cell_op("move_cell", 21, 0)                         # hand_ik.R moved
    cell_op("set_cell_side", *templates.BODY.cells["hips"], side='LEFT')
    cell_op("clear_cell", *templates.BODY.cells["head"])     # cleared, its cell stays empty
    neck = templates.BODY.cells["neck"]
    cell_op("clear_cell", *neck)                        # cleared, and its cell taken by root
    cell_op("start_move", *templates.BODY.cells["root"])
    cell_op("move_cell", *neck)
    placed = templates.apply_templates(human)
    body = {c.bone_name: (c.row, c.column, c.side) for c in layout.find_tab(human, "Body").cells}
    got = (placed, body["hand_ik.R"][:2], body["hips"][2], body.get("head", ())[:2], "neck" in body,
           body["root"][:2], hand in [v[:2] for v in body.values()])
    return (got == (1, (21, 0), 'LEFT', templates.BODY.cells["head"], False, neck, False), got)
check("re-applying keeps moved and recoloured cells, and places a cleared control only if its cell is free",
      hand_edits_survive)


def apply_on_plain_rig():
    pick(None)
    clear_data()
    rig = make_arm("Plain", ("Bone", "Bone.001"))
    pick(rig)
    placed = templates.apply_templates(rig)
    rig.bonemancer_layout.clear()
    result = op("apply_layout_template")
    view = draw()
    boxes = [d for d in view.drawn("operator") if d.args[0] == "bonemancer.layout_blank" and d.kwargs.get("emboss")]
    got = (placed, result, [(t.name, len(t.cells)) for t in rig.bonemancer_layout], len(boxes))
    return (got == (0, {'FINISHED'}, [("Body", 0), ("Hands", 0)], len(templates.silhouette_cells(templates.BODY))),
            got)
check("on a rig that isn't Rigify the tabs appear with their silhouettes and nothing placed", apply_on_plain_rig)


def user_tab_kept():
    rig = fresh()
    new_tab(name="Body", columns=4, rows=4)
    place("root", 0, 0)
    op("apply_layout_template")
    body = layout.find_tab(rig, "Body")
    view = draw()
    boxes = [d for d in view.drawn("operator") if d.args[0] == "bonemancer.layout_blank" and d.kwargs.get("emboss")]
    got = ((body.columns, body.rows, body.template), cells(rig), len(boxes))
    return (got == ((4, 4, ""), [("root", 0, 0, 'CENTER')], 0), got)
check("a tab of the same name made by hand is kept as it is, without a silhouette", user_tab_kept)


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
