# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeping bone sets and drivers working when a bone is renamed."""

import bpy

from .utils import path_key, rig_sets


def rename_set_entries(arm_obj, old_name, new_name):
    for grp in rig_sets(arm_obj):
        for entry in grp.bones:
            if entry.bone_name == old_name:
                entry.bone_name = new_name


def bone_data_path(bone_name):
    return f'pose.bones{path_key(bone_name)}'


def update_driver_variable_paths(arm_obj, old_name, new_name):
    """
    Replace references to pose.bones["old_name"] in driver variables that
    target arm_obj, and update their bone_target fields. Drivers targeting
    other rigs (which may have a bone with the same name) are left alone.
    """
    bone_ref_old = bone_data_path(old_name)
    bone_ref_new = bone_data_path(new_name)
    count = 0

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if not ad or not ad.drivers:
            continue

        for fc in ad.drivers:
            for var in fc.driver.variables:
                for targ in var.targets:
                    if targ.id != arm_obj:
                        continue
                    # 1) Update data_path string
                    if targ.data_path and bone_ref_old in targ.data_path:
                        targ.data_path = targ.data_path.replace(bone_ref_old, bone_ref_new)
                        count += 1

                    # 2) Update bone_target property
                    if targ.bone_target == old_name:
                        targ.bone_target = new_name
                        count += 1

    return count


def count_bone_references(arm_obj, bone_name):
    """(drivers, constraints) in the file that point at this bone of arm_obj."""
    bone_ref = bone_data_path(bone_name)
    drivers = 0
    constraints = 0

    for obj in bpy.data.objects:
        ad = obj.animation_data
        if ad:
            for fc in ad.drivers:
                if any(
                    targ.id == arm_obj and
                    ((targ.data_path and bone_ref in targ.data_path) or targ.bone_target == bone_name)
                    for var in fc.driver.variables for targ in var.targets
                ):
                    drivers += 1

        owners = [obj] + (list(obj.pose.bones) if obj.pose else [])
        for owner in owners:
            for con in owner.constraints:
                if getattr(con, "target", None) == arm_obj and getattr(con, "subtarget", "") == bone_name:
                    constraints += 1

    return drivers, constraints
