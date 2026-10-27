# SPDX-License-Identifier: GPL-3.0-or-later
"""Drawing of bone sets, bone settings, custom properties, constraints and Rig Check issues."""

from ..core.compat import bone_is_selected, is_hidden
from ..core.rig_check import constraint_problem, is_ignored, issue_explanation, issue_fixed, library_ignore
from ..core.utils import live_bones, path_key, pose_bone_path, rig_is_editable, set_is_hidden
from .common import bone_name_button, hint, plural, sub_panel, wrapped_label


def draw_bone_set(context, layout, rig, grp):
    # A collapsible sub-panel per set; its open state is the set's show_expanded
    header, body = sub_panel(layout, rig, grp, "show_expanded", grp.name)
    header.label(text=grp.name, icon='OUTLINER_COLLECTION')
    count = header.row(align=True)
    count.alignment = 'RIGHT'
    count.active = False
    count.label(text=plural(len(grp.bones), "bone"))
    op = header.operator("bonemancer.toggle_set", text="", emboss=False,
                         icon='HIDE_ON' if set_is_hidden(rig, grp) else 'HIDE_OFF')
    op.set_name = grp.name
    header.operator("bonemancer.remove_set", text="", icon='TRASH', emboss=False).set_name = grp.name
    if body is None:
        return

    if not grp.bones:
        hint(body, context, "Empty. Select bones and use Add Selected in the Bones panel.")
    for entry in grp.bones:
        pb = rig.pose.bones.get(entry.bone_name)
        if not pb:
            # Bone was deleted or renamed outside of Bonemancer
            row = body.row(align=True)
            row.label(text=f"{entry.bone_name} (missing)", icon='ERROR')
            rem = row.operator("bonemancer.remove_bone_from_set", text="", icon='X', emboss=False)
            rem.set_name = grp.name
            rem.bone_name = entry.bone_name
            continue
        draw_set_bone(context, body, rig, grp, entry, pb)


def settings_bone(rig, name):
    """The bone whose Deform option the panels edit: the edit bone in Edit Mode,
    where changes to the plain bone would be lost on leaving it."""
    return live_bones(rig).get(name)


def draw_bone_settings(layout, rig, name):
    """Deform, IK Stretch and Lock IK for one bone, bound to Blender's own properties."""
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    bone = settings_bone(rig, name)
    if bone:
        col.prop(bone, "use_deform", text="Deform")
    pb = rig.pose.bones.get(name)
    if pb:
        col.prop(pb, "ik_stretch", text="IK Stretch", slider=True)
        # Property split only labels checkboxes, so lay out the label column by hand
        split = col.split(factor=0.4, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text="Lock IK")
        row = split.row(align=True)
        row.use_property_split = False
        for axis in "xyz":
            row.prop(pb, f"lock_ik_{axis}", text=axis.upper(), toggle=True)


def draw_set_bone(context, layout, rig, grp, entry, pb):
    path = (grp.name, entry.bone_name)
    header, body = sub_panel(layout, rig, entry, "show_details", *path)
    bone_name_button(header, entry.bone_name, bone_is_selected(pb))
    hidden = is_hidden(pb)
    eye = header.row(align=True)
    eye.alignment = 'RIGHT'
    op = eye.operator("bonemancer.toggle_bone", text="", icon='HIDE_ON' if hidden else 'HIDE_OFF', emboss=False)
    op.bone_name = entry.bone_name
    if body is None:
        return

    row = body.row(align=True)
    row.operator("bonemancer.rename_bone", text="Rename", icon='GREASEPENCIL').bone_name = entry.bone_name
    rem = row.operator("bonemancer.remove_bone_from_set", text="Remove from Set", icon='REMOVE')
    rem.set_name = grp.name
    rem.bone_name = entry.bone_name
    draw_bone_settings(body, rig, entry.bone_name)

    keys = [key for key in pb.keys() if key != 'constraint_active_index']
    header, props = sub_panel(body, rig, entry, "show_custom_props", *path)
    header.label(text=f"Properties ({len(keys)})")
    if props:
        draw_custom_props(props.column(), rig, pb, keys)

    broken = sum(1 for con in pb.constraints if constraint_problem(con))
    header, cons = sub_panel(body, rig, entry, "show_constraints", *path)
    header.label(text=f"Constraints ({len(pb.constraints)}" + (f", {broken} broken)" if broken else ")"),
                 icon='ERROR' if broken else 'NONE')
    if cons:
        if not pb.constraints:
            hint(cons, context, "This bone has no constraints.")
        else:
            cons.template_list(
                "BONEMANCER_UL_constraints", "",
                pb, "constraints",
                entry, "constraint_index",
                rows=3,
            )
            # Target and spaces of the highlighted constraint
            if 0 <= entry.constraint_index < len(pb.constraints):
                draw_constraint_settings(cons.box(), pb.constraints[entry.constraint_index])


def draw_custom_props(col, rig, pb, keys):
    """Laid out like Blender's own Custom Properties panel: name, value, Edit (gear), Remove."""
    # Blender refuses to edit properties of linked or overridden data
    editable = rig.library is None and rig.override_library is None
    for key in keys:
        split = col.split(factor=0.4, align=True)
        label = split.row()
        label.alignment = 'RIGHT'
        label.label(text=key, translate=False)
        value = split.row(align=True)
        if hasattr(pb[key], "keys"):
            # Nested groups have no single widget
            value.label(text="(property group)")
        else:
            value.prop(pb, path_key(key), text="")
        if editable:
            buttons = value.row(align=True)
            buttons.alignment = 'RIGHT'
            op = buttons.operator("bonemancer.edit_custom_prop", text="", icon='PREFERENCES', emboss=False)
            op.bone_name = pb.name
            op.prop_name = key
            op = buttons.operator("wm.properties_remove", text="", icon='X', emboss=False)
            op.data_path = pose_bone_path(pb.name)
            op.property_name = key
    col.operator("bonemancer.add_custom_prop", text="Add Property", icon='ADD').bone_name = pb.name


# Which space dropdowns Blender's own constraint panels show, as (target, owner)
CONSTRAINT_SPACES = {
    'COPY_LOCATION': (True, True), 'COPY_ROTATION': (True, True), 'COPY_SCALE': (True, True),
    'COPY_TRANSFORMS': (True, True), 'TRACK_TO': (True, True), 'LIMIT_DISTANCE': (True, True),
    'FLOOR': (True, True), 'TRANSFORM': (True, True), 'ACTION': (True, False),
    'LIMIT_LOCATION': (False, True), 'LIMIT_ROTATION': (False, True), 'LIMIT_SCALE': (False, True),
    'MAINTAIN_VOLUME': (False, True),
}


# Constraints whose target takes no bone or vertex group
NO_SUBTARGET = {'SHRINKWRAP', 'GEOMETRY_ATTRIBUTE'}


def subtarget_search(layout, owner, prop, target, text_prefix=""):
    """A Bone or Vertex Group field for target, as Blender's constraint panels draw it."""
    if not target:
        return
    if target.type == 'ARMATURE':
        layout.prop_search(owner, prop, target.data, "bones", text=text_prefix + "Bone")
    elif target.type in {'MESH', 'LATTICE'}:
        layout.prop_search(owner, prop, target, "vertex_groups", text=text_prefix + "Vertex Group")


def draw_constraint_settings(layout, con):
    """Target, pole target and target/owner spaces of one constraint, where it has them."""
    col = layout.column()
    col.use_property_split = True
    col.use_property_decorate = False
    col.label(text=con.name, icon='CONSTRAINT')
    shown = False
    if hasattr(con, "target"):
        col.prop(con, "target")
        if con.type not in NO_SUBTARGET:
            subtarget_search(col, con, "subtarget", con.target)
        shown = True
    if hasattr(con, "pole_target"):
        col.prop(con, "pole_target")
        subtarget_search(col, con, "pole_subtarget", con.pole_target, "Pole ")
        shown = True
    # The Armature constraint has a list of weighted targets instead
    for i, tgt in enumerate(getattr(con, "targets", ())):
        box = col.box()
        box.prop(tgt, "target", text=f"Target {i + 1}")
        subtarget_search(box, tgt, "subtarget", tgt.target)
        box.prop(tgt, "weight", slider=True)
        shown = True
    target_space, owner_space = CONSTRAINT_SPACES.get(con.type, (False, False))
    if target_space:
        col.prop(con, "target_space", text="Target Space")
    if owner_space:
        col.prop(con, "owner_space", text="Owner Space")
    if (target_space or owner_space) and 'CUSTOM' in (con.target_space, con.owner_space):
        col.prop(con, "space_object")
        subtarget_search(col, con, "space_subtarget", con.space_object, "Space ")
    if not (shown or target_space or owner_space):
        hint_col = col.column()
        hint_col.active = False
        hint_col.label(text="No target or spaces to set")


def draw_issue_details(layout, context, rig, issue, index):
    """Why the highlighted issue matters, how to fix it, and what to do with it."""
    heading, icon, why, fix = issue_explanation(issue)
    layout.label(text=heading, icon=icon)
    # The list row is often cut short in the sidebar; show it in full here
    wrapped_label(layout, context, issue.message)
    if issue_fixed(context, issue):
        wrapped_label(layout, context, "This looks fixed now. Check again to update the list.", 'CHECKMARK')
    hint(layout, context, why)
    if fix:
        wrapped_label(layout, context, "Fix: " + fix)
    row = layout.row(align=True)
    row.operator("bonemancer.select_issue", text="Select", icon='RESTRICT_SELECT_OFF').index = index
    ignored = is_ignored(rig, issue)
    toggle = row.row(align=True)
    toggle.enabled = rig_is_editable(rig) and not (ignored and library_ignore(rig, issue))
    if ignored:
        toggle.operator("bonemancer.unignore_issue", icon='HIDE_ON').index = index
    else:
        toggle.operator("bonemancer.ignore_issue", icon='HIDE_OFF').index = index
