# SPDX-License-Identifier: GPL-3.0-or-later
"""Bone Mancer: Rig Central. Animator control hub for bone sets, custom properties, constraints and shape keys."""

import bpy

from . import handlers, operators, properties, ui
from .core.utils import clear_enum_items

classes = (*properties.classes, *operators.classes, *ui.classes)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    properties.register()
    handlers.register()


def unregister():
    handlers.unregister()
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            print(f"Failed to unregister class {cls.__name__}: {e}")
    properties.unregister()
    clear_enum_items()
