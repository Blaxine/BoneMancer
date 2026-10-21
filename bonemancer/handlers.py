# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender handlers: following the viewport, and upgrading files on load."""

import bpy
from bpy.app.handlers import persistent

from .core.migration import migrate_legacy_data
from .core.selection import follow_viewport_rig, sync_selected_bone, update_bone_list
from .core.shape_keys import refresh_shape_keys
from .core.utils import tag_addon_panels


@persistent
def on_depsgraph_update(scene, depsgraph):
    """Single depsgraph handler: viewport → picker sync, bone list and selection refresh."""
    screen = bpy.context.screen
    if screen and screen.is_animation_playing:
        return

    # 1) Drop a picked rig that left the scene (deleted with X, unlinked). Our
    # pointers count as users, so keeping them would keep a deleted rig in the
    # file for good.
    rig = scene.bonemancer_rig
    if rig is not None and scene not in rig.users_scene:
        follow_viewport_rig(scene, None)

    # 2) Follow the active armature in the viewport (cheap: one lookup)
    view_layer = depsgraph.view_layer
    active = view_layer.objects.active if view_layer else None
    if active and active.type == 'ARMATURE' and scene.bonemancer_rig != active:
        follow_viewport_rig(scene, active)

    # 3) Only armature/object updates can change bone names or selection
    redraw = False
    if depsgraph.id_type_updated('ARMATURE') or depsgraph.id_type_updated('OBJECT'):
        changed = update_bone_list(scene)
        changed |= sync_selected_bone(scene, view_layer)
        redraw = changed or depsgraph.id_type_updated('ARMATURE')
    if depsgraph.id_type_updated('KEY'):
        redraw = True

    # 4) Shape Key Scanner: meshes parented/unparented, shape keys added,
    # renamed or removed. Moving a slider changes neither, so this stays a
    # comparison while posing or sculpting.
    if any(depsgraph.id_type_updated(t) for t in ('OBJECT', 'KEY', 'MESH')):
        redraw |= refresh_shape_keys(scene)

    if redraw:
        tag_addon_panels(bpy.context)


safe_handlers = [on_depsgraph_update]


def safely_register_handlers(handlers):
    for handle in handlers:
        if handle not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(handle)


@persistent
def on_load_post(dummy):
    migrate_legacy_data()


load_post_handlers = [on_load_post]


def _deferred_init():
    # bpy.data is restricted while the add-on registers; finish setup on the
    # first tick so data saved in an already-open file is picked up.
    migrate_legacy_data()
    return None


def remove_handlers(handlers):
    """
    Remove each function in `handlers` from Blender's handler lists
    (depsgraph_update_post and load_post).
    """
    for handle in handlers:
        if handle in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(handle)
        if handle in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(handle)


def register():
    # Only ours; never clear other add-ons' handlers
    safely_register_handlers(safe_handlers)
    for handle in load_post_handlers:
        if handle not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(handle)
    # Upgrade data in a file that is already open
    bpy.app.timers.register(_deferred_init, first_interval=0.0)


def unregister():
    remove_handlers(safe_handlers + load_post_handlers)
    if bpy.app.timers.is_registered(_deferred_init):
        bpy.app.timers.unregister(_deferred_init)
