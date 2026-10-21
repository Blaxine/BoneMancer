# SPDX-License-Identifier: GPL-3.0-or-later
"""Layout helpers shared by the panels."""

import textwrap

from ..core.utils import rig_is_editable


NO_RIG_HINT = "Pick an armature in the Rig panel first."


def text_lines(context, text):
    """text split into lines that fit the sidebar; labels don't wrap on their own."""
    region = getattr(context, "region", None)
    width = region.width if region else 300
    # ui_scale is 0 when Blender runs without a window
    scale = (context.preferences.system.ui_scale if context.preferences else 0) or 1.0
    # About 5.5 px per character at scale 1, less the panel's margins
    return textwrap.wrap(text, max(24, int((width - 40 * scale) / (5.5 * scale))))


def wrapped_label(layout, context, text, icon='NONE'):
    col = layout.column(align=True)
    col.scale_y = 0.8
    for i, line in enumerate(text_lines(context, text)):
        # Indent follow-on lines under the icon
        col.label(text=line, icon=icon if i == 0 else ('BLANK1' if icon != 'NONE' else 'NONE'))
    return col


def hint(layout, context, text, icon='NONE'):
    """Greyed guidance text."""
    wrapped_label(layout, context, text, icon).active = False


def sub_panel(layout, rig, data, prop, *path):
    """A collapsible sub-panel, (header, body); body is None while closed.

    Its open state is data.prop, which saves with the rig. A rig linked without
    an override can't be changed, so there the sidebar keeps the state instead.
    """
    if rig_is_editable(rig):
        return layout.panel_prop(data, prop)
    return layout.panel("_".join(("BONEMANCER", rig.name, prop) + path), default_closed=not getattr(data, prop))


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def bone_name_button(layout, name, selected):
    """A left-aligned bone name that selects the bone; drawn pressed while the bone is selected."""
    sub = layout.row(align=True)
    sub.alignment = 'LEFT'
    op = sub.operator("bonemancer.select_bone", text=name, icon='BONE_DATA', emboss=selected, depress=selected)
    op.bone_name = name
