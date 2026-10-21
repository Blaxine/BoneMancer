# SPDX-License-Identifier: GPL-3.0-or-later
"""
Differences between Blender 4.x and 5.x.

Blender 5.0 moved pose-mode selection/visibility from Bone to PoseBone
and removed Action.fcurves in favour of slotted actions (channelbags).
"""


def bone_is_selected(pb):
    return pb.select if hasattr(pb, "select") else pb.bone.select


def set_bone_selected(pb, value):
    if hasattr(pb, "select"):
        pb.select = value
    else:
        pb.bone.select = value


def get_anim_fcurves(anim_data):
    """Return the F-curves of the action assigned to anim_data (any Blender version)."""
    action = anim_data.action if anim_data else None
    if not action:
        return []
    slot = getattr(anim_data, "action_slot", None)
    if slot is not None:
        from bpy_extras import anim_utils
        channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
        return channelbag.fcurves if channelbag else []
    # Pre-5.0 legacy API; on 5.x an action without an assigned slot has no curves yet
    return getattr(action, "fcurves", [])


def is_hidden(pb):
    if not pb:
        return False
    # Blender 5.0+ stores pose-mode visibility on the PoseBone
    return pb.hide if hasattr(pb, "hide") else pb.bone.hide


def set_hidden(pb, value):
    if not pb:
        return
    if hasattr(pb, "hide"):
        pb.hide = value
    else:
        pb.bone.hide = value


def toggle_hidden(pb):
    if pb:
        set_hidden(pb, not is_hidden(pb))
