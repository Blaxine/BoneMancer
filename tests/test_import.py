"""Import Bone Collections: one bone set per native collection, merged by name on re-import."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, load_addon, refused, make_arm, clear_data, FakePanel, MockLayout

mod = load_addon()
from bonemancer.core import selection
from bonemancer.operators import bone_sets
from bonemancer.ui import panels
check("register()", mod.register)
sc = bpy.context.scene


def pick(obj):
    selection.follow_viewport_rig(sc, obj)


def make_rig():
    """
    Body   (root, spine)
    Arms   (no direct bones)
      Arm.L  (arm.L, hand.L)
      Arm.R  (arm.R)
    Empty  (no bones)
    """
    sc.bonemancer_rig = None
    clear_data()
    arm = make_arm("Rig", ("root", "spine", "arm.L", "hand.L", "arm.R"))
    data = arm.data
    for coll in list(data.collections_all):
        data.collections.remove(coll)
    body = data.collections.new("Body")
    arms = data.collections.new("Arms")
    arm_l = data.collections.new("Arm.L", parent=arms)
    arm_r = data.collections.new("Arm.R", parent=arms)
    data.collections.new("Empty")
    for coll, bones in ((body, ("root", "spine")), (arm_l, ("arm.L", "hand.L")), (arm_r, ("arm.R",))):
        for name in bones:
            coll.assign(data.bones[name])
    pick(arm)
    return arm


def sets(arm):
    return [(s.name, [b.bone_name for b in s.bones]) for s in arm.bonemancer_sets]


def import_(**kw):
    return refused(lambda: bpy.ops.bonemancer.import_bone_collections(**kw))


def tree():
    arm = make_rig()
    got = [(c.name, d) for c, d in bone_sets.native_collections(arm.data)]
    return (got == [("Body", 0), ("Arms", 0), ("Arm.L", 1), ("Arm.R", 1), ("Empty", 0)], got)
check("collections listed parents first with nesting depth", tree)


def default_import():
    arm = make_rig()
    r = import_()
    got = sets(arm)
    return (r == {'FINISHED'} and got == [("Body", ["root", "spine"]), ("Arm.L", ["arm.L", "hand.L"]), ("Arm.R", ["arm.R"])],
            (r, got))
check("default import: one set per non-empty collection, direct bones only", default_import)


def ticked_only():
    arm = make_rig()
    import_(items=[{"name": name, "use": use, "bone_count": 0, "depth": 0}
                   for name, use in (("Arm.L", True), ("Body", False), ("Arms", True))])
    got = sets(arm)
    return (got == [("Arm.L", ["arm.L", "hand.L"]), ("Arms", [])], got)
check("only ticked collections are imported (an empty one too, if ticked)", ticked_only)


def reimport_merges():
    arm = make_rig()
    import_()
    # User edits: reorder and extend Arm.L, add a bone to Body, make their own set
    arm_l = arm.bonemancer_sets["Arm.L"]
    arm_l.bones.move(1, 0)
    arm_l.bones.add().bone_name = "spine"
    arm.bonemancer_sets["Body"].bones.add().bone_name = "arm.R"
    fav = arm.bonemancer_sets.add(); fav.name = "Favorites"; fav.bones.add().bone_name = "root"
    arm.bonemancer_sets.move(3, 0)   # Favorites first
    # Rig changes: a bone joins Arm.L, a new collection appears
    arm.data.collections_all["Arm.L"].assign(arm.data.bones["root"])
    arm.data.collections.new("Spine").assign(arm.data.bones["spine"])
    import_()
    got = sets(arm)
    expected = [
        ("Favorites", ["root"]),
        ("Body", ["root", "spine", "arm.R"]),
        ("Arm.L", ["hand.L", "arm.L", "spine", "root"]),
        ("Arm.R", ["arm.R"]),
        ("Spine", ["spine"]),
    ]
    return (got == expected, got)
check("re-import adds missing bones and sets, keeps user edits and order", reimport_merges)


def reimport_idempotent():
    arm = make_rig()
    import_(); first = sets(arm)
    import_()
    return (sets(arm) == first, sets(arm))
check("importing twice changes nothing the second time", reimport_idempotent)


def no_collections():
    sc.bonemancer_rig = None
    clear_data()
    arm = make_arm("Bare")
    for coll in list(arm.data.collections_all):
        arm.data.collections.remove(coll)
    pick(arm)
    return (bpy.ops.bonemancer.import_bone_collections.poll() is False, None)
check("disabled when the rig has no bone collections", no_collections)


def undoable():
    opts = bone_sets.BONEMANCER_OT_import_bone_collections.bl_options
    return ('UNDO' in opts and 'REGISTER' in opts, opts)
check("import is undoable", undoable)


class FakeItem:
    def __init__(self, name, count, depth, use):
        self.name, self.bone_count, self.depth, self.use = name, count, depth, use


class FakeOperator:
    layout = MockLayout()
    items = [FakeItem("Arms", 0, 0, False), FakeItem("Arm.L", 2, 1, True), FakeItem("Arm.R", 1, 1, True)]


check("dialog draws", lambda: bone_sets.BONEMANCER_OT_import_bone_collections.draw(FakeOperator(), bpy.context))


def panel_empty_state():
    make_rig()
    fp = FakePanel()
    fp._draw_bone_buttons = lambda *a: None
    panels.BONEMANCER_PT_bone_sets.draw(fp, bpy.context)
check("Bone Sets panel draws its empty state", panel_empty_state)

check("unregister()", mod.unregister)
finish()
