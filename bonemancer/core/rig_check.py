# SPDX-License-Identifier: GPL-3.0-or-later
"""
Rig Check: finding problems in a rig, and remembering which ones are ignored.

An on-demand list of problems with the picked rig. Issues hold names only:
ID pointers would count as users and keep deleted objects in the file.
"""

import bpy
import math
import re

from .utils import get_rig, path_key


# check id -> (heading, icon, explanation lines). The ids are stored in
# saved ignores, so they must never change.
RIG_CHECKS = {
    'constraint': (
        "Broken constraints", 'CONSTRAINT_BONE',
        ("A constraint with no target, or aimed at a bone that doesn't exist,",
         "does nothing, so the bone stops following the rest of the rig.",
         "Fix: in Bone Properties > Bone Constraints, set the Target (and",
         "its Bone field), or delete the constraint if it isn't needed."),
    ),
    'driver': (
        "Broken drivers", 'DRIVER',
        ("A driver that can't evaluate leaves its property stuck, so the",
         "slider, corrective shape or switch it controls stops responding.",
         "Fix: right-click the driven property > Open Drivers Editor, then",
         "fix the variable's object and path, or the expression."),
    ),
    'unpaired': (
        "Unpaired left/right bones", 'MOD_MIRROR',
        ("This bone's name marks a side (.L, _R, Left...) but the other side",
         "has no bone of the matching name, so Symmetrize, X-Axis Mirror and",
         "pose flipping skip it.",
         "Fix: add or rename the other side's bone so the names match,",
         "or ignore this if the bone is one-sided on purpose."),
    ),
    'deform_unweighted': (
        "Deform bones without weights", 'GROUP_VERTEX',
        ("This bone has Deform on, but no skinned mesh has weights for it,",
         "so moving it doesn't move the mesh.",
         "Fix: weight paint it (or parent with Automatic Weights again), or",
         "turn off Deform in Bone Properties if it's a control or helper bone."),
    ),
    'nondeform_weighted': (
        "Weighted bones with Deform off", 'MOD_VERTEX_WEIGHT',
        ("A skinned mesh has weights for this bone, but its Deform option is",
         "off, so the weights are ignored and that part of the mesh stays put.",
         "Fix: turn on Deform in Bone Properties, or delete the bone's vertex",
         "group from the mesh if the weights are left over."),
    ),
    'rig_transform': (
        "Unapplied rig transform", 'OBJECT_DATA',
        ("The rig object is rotated or scaled. Constraints, IK and physics can",
         "act oddly, and exporters and retargeting expect a scale of 1.",
         "Fix: in Object Mode select the rig and its meshes, then",
         "Object > Apply > All Transforms. On an animated rig this changes",
         "how the existing animation plays back."),
    ),
    'mesh_no_modifier': (
        "Parented without an Armature modifier", 'MODIFIER',
        ("This mesh is parented to the rig but has no Armature modifier, so it",
         "follows the rig as a whole but doesn't bend with the bones.",
         "Fix: select the mesh, then the rig, and use Parent > With Automatic",
         "Weights, or add an Armature modifier that uses this rig."),
    ),
    'modifier_wrong_rig': (
        "Armature modifier on another rig", 'MOD_ARMATURE',
        ("This mesh is parented to this rig, but its Armature modifier has no",
         "rig set or uses a different one, so posing these bones doesn't bend it.",
         "Fix: in the mesh's Modifier Properties, set the Armature modifier's",
         "Object to this rig."),
    ),
}


# Tolerance for "the rig's rotation and scale are applied"
TRANSFORM_EPSILON = 1e-4


# Shared between the checks of one run (e.g. both weight checks read the
# same weights); emptied at the start of every run.
_check_cache = {}


def constraint_problem(con):
    """What's wrong with a constraint, as the end of a sentence, or '' if it works."""
    if getattr(con, "is_valid", True):
        return ""
    target = getattr(con, "target", None)
    if hasattr(con, "target") and not target:
        return "has no target"
    sub = getattr(con, "subtarget", "")
    bones = getattr(getattr(target, "data", None), "bones", None)
    if sub and bones is not None and sub not in bones:
        return f"targets missing bone '{sub}'"
    return "is not valid"


def find_constraint_issues(context, rig):
    for pb in rig.pose.bones:
        for con in pb.constraints:
            problem = constraint_problem(con)
            if problem:
                yield pb.name, con.name, f"{pb.name}: {con.name} {problem}", ""


def find_unpaired_bones(context, rig):
    names = {b.name for b in rig.data.bones}
    for bone in rig.data.bones:
        other = bpy.utils.flip_name(bone.name)
        if other != bone.name and other not in names:
            yield bone.name, "", f"{bone.name}: no '{other}' on the other side", ""


def skinned_meshes(scene, rig):
    """Meshes the rig deforms through an Armature modifier or armature parenting."""
    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        if (obj.parent == rig and obj.parent_type == 'ARMATURE') or any(
                m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers):
            yield obj


def weighted_group_names(mesh_obj):
    """Names of mesh_obj's vertex groups that have a non-zero weight on some vertex."""
    names = {g.index: g.name for g in mesh_obj.vertex_groups}
    found = set()
    for vert in mesh_obj.data.vertices:
        for elem in vert.groups:
            if elem.weight > 0.0:
                found.add(elem.group)
        if len(found) == len(names):
            break
    return {names[i] for i in found if i in names}


def rig_weights(context, rig):
    """{bone name: [meshes weighting it]} over the rig's skinned meshes, or None without any."""
    key = ("weights", rig.name)
    if key not in _check_cache:
        meshes = list(skinned_meshes(context.scene, rig))
        weights = None
        if meshes:
            weights = {}
            for mesh in meshes:
                for name in weighted_group_names(mesh):
                    weights.setdefault(name, []).append(mesh.name)
        _check_cache[key] = weights
    return _check_cache[key]


def find_unweighted_deform_bones(context, rig):
    weights = rig_weights(context, rig)
    if weights is None:
        return
    for bone in rig.data.bones:
        if bone.use_deform and bone.name not in weights:
            yield bone.name, "", f"{bone.name}: Deform is on but no skinned mesh has weights for it", ""


def find_weighted_nondeform_bones(context, rig):
    weights = rig_weights(context, rig)
    if weights is None:
        return
    for bone in rig.data.bones:
        if not bone.use_deform and bone.name in weights:
            meshes = ", ".join(weights[bone.name])
            yield bone.name, "", f"{bone.name}: weighted on {meshes} but Deform is off", ""


def driver_owners(scene, rig):
    """(ID holding drivers, object to select) for everything the driver check covers."""
    yield rig, rig
    yield rig.data, rig
    for mesh in skinned_meshes(scene, rig):
        yield mesh, mesh
        if mesh.data.shape_keys:
            yield mesh.data.shape_keys, mesh


def python_drivers_blocked():
    """True when Blender skipped Python expressions because the file's scripts aren't trusted."""
    return bpy.app.autoexec_fail


def _resolves(id_data, path):
    if id_data is None or not path:
        return False
    try:
        id_data.path_resolve(path)
        return True
    except ValueError:
        return False


def driver_problem(owner, fcurve):
    """Why an invalid driver fails, as the end of a sentence."""
    if not _resolves(owner, fcurve.data_path):
        return "drives a property that doesn't exist"
    driver = fcurve.driver
    for var in driver.variables:
        if not var.is_name_valid:
            return f"has a variable with an invalid name '{var.name}'"
        if var.type == 'CONTEXT_PROP':
            continue
        used = var.targets[:2] if var.type in {'ROTATION_DIFF', 'LOC_DIFF'} else var.targets[:1]
        for targ in used:
            if targ.id is None:
                return f"variable '{var.name}' has no object"
            if var.type == 'SINGLE_PROP':
                if not _resolves(targ.id, targ.data_path):
                    return f"variable '{var.name}' reads a missing path '{targ.data_path}'"
            elif targ.bone_target:
                bones = getattr(getattr(targ.id, "data", None), "bones", None)
                if bones is not None and targ.bone_target not in bones:
                    return f"variable '{var.name}' uses missing bone '{targ.bone_target}'"
    if driver.type == 'SCRIPTED':
        return f"expression '{driver.expression}' fails"
    return "is not valid"


_BONE_PATH = re.compile(r'^(?:pose\.)?bones\["((?:[^"\\]|\\.)*)"\]')


def driven_bone(owner, rig, data_path):
    """The rig's bone a driver drives (pose.bones["x"]... on the rig, bones["x"]... on its data), or ''."""
    if owner not in (rig, rig.data):
        return ""
    match = _BONE_PATH.match(data_path)
    if not match or match.group(0).startswith("pose.") != (owner == rig):
        return ""
    name = bpy.utils.unescape_identifier(match.group(1))
    return name if name in rig.data.bones else ""


def find_driver_issues(context, rig):
    results = context.scene.bonemancer_rig_check
    for owner, select_obj in driver_owners(context.scene, rig):
        anim = owner.animation_data
        if not anim:
            continue
        for fc in anim.drivers:
            driver = fc.driver
            if driver.is_valid:
                continue
            if driver.type == 'SCRIPTED' and not driver.is_simple_expression and python_drivers_blocked():
                results.python_drivers += 1
                continue
            bone = driven_bone(owner, rig, fc.data_path)
            label = owner.name if isinstance(owner, bpy.types.Object) else f"{select_obj.name} ({owner.id_type.title()})"
            detail = f"{owner.id_type}:{owner.name}:{fc.data_path}[{fc.array_index}]"
            message = f"{label}: driver on {fc.data_path}[{fc.array_index}] {driver_problem(owner, fc)}"
            yield bone, detail, message, select_obj.name


def find_unapplied_transform(context, rig):
    _loc, rot, scale = rig.matrix_basis.decompose()
    angle = rot.angle
    rotated = min(angle, 2 * math.pi - angle) > TRANSFORM_EPSILON
    scaled = any(abs(s - 1.0) > TRANSFORM_EPSILON for s in scale)
    if rotated or scaled:
        parts = [part for part, on in (("rotation", rotated),
                                       (f"scale ({scale.x:.3g}, {scale.y:.3g}, {scale.z:.3g})", scaled)) if on]
        yield "", "", f"{rig.name}: {' and '.join(parts)} not applied", rig.name


def meshes_parented_to(scene, rig):
    for obj in scene.objects:
        if obj.type == 'MESH' and obj.parent == rig and obj.parent_type in {'OBJECT', 'ARMATURE'}:
            yield obj


def find_meshes_without_modifier(context, rig):
    for obj in meshes_parented_to(context.scene, rig):
        if obj.parent_type == 'OBJECT' and not any(m.type == 'ARMATURE' for m in obj.modifiers):
            yield "", obj.name, f"{obj.name}: parented to the rig without an Armature modifier", obj.name


def find_modifiers_on_other_rigs(context, rig):
    for obj in meshes_parented_to(context.scene, rig):
        mods = [m for m in obj.modifiers if m.type == 'ARMATURE']
        if not mods or any(m.object == rig for m in mods):
            continue
        for m in mods:
            problem = f"uses '{m.object.name}' instead of this rig" if m.object else "has no rig set"
            yield "", f"{obj.name}:{m.name}", f"{obj.name}: Armature modifier '{m.name}' {problem}", obj.name


# --- Re-testing listed issues ---------------------------------------------
# Each drawn row asks whether its issue is fixed. These tests only read what
# is cheap and already up to date; weights are never re-read.

def _driver_owner(id_type, name):
    store = {'OBJECT': bpy.data.objects, 'ARMATURE': bpy.data.armatures, 'KEY': bpy.data.shape_keys}.get(id_type)
    return store.get(name) if store is not None else None


def _driver_fixed(issue):
    id_type, _sep, rest = issue.detail.partition(":")
    owner_name, path_and_index = rest.split(":", 1) if ":" in rest else ("", rest)
    path, _bracket, index = path_and_index.rpartition("[")
    owner = _driver_owner(id_type, owner_name)
    anim = owner.animation_data if owner else None
    try:
        fcurve = anim.drivers.find(path, index=int(index.rstrip("]"))) if anim else None
    except ValueError:
        return False
    return fcurve is None or fcurve.driver.is_valid


def _mesh_fixed(scene, rig, issue):
    obj = bpy.data.objects.get(issue.object_name)
    if obj is None or obj.parent != rig or scene.objects.get(obj.name) != obj:
        return True
    mods = [m for m in obj.modifiers if m.type == 'ARMATURE']
    if issue.check == 'mesh_no_modifier':
        return obj.parent_type != 'OBJECT' or bool(mods)
    mod_name = issue.detail[len(obj.name) + 1:]
    m = obj.modifiers.get(mod_name)
    return m is None or m.type != 'ARMATURE' or any(x.object == rig for x in mods)


def issue_fixed(context, issue):
    """True when a listed issue no longer applies (as far as a cheap re-test can tell)."""
    rig = get_rig(context.scene)
    if rig is None:
        return False
    check_id = issue.check
    if check_id in {'constraint', 'unpaired', 'deform_unweighted', 'nondeform_weighted'}:
        bone = rig.data.bones.get(issue.bone)
        if bone is None:
            return True
        if check_id == 'constraint':
            con = rig.pose.bones[issue.bone].constraints.get(issue.detail)
            return con is None or not constraint_problem(con)
        if check_id == 'unpaired':
            return bpy.utils.flip_name(bone.name) in rig.data.bones
        if check_id == 'deform_unweighted':
            return not bone.use_deform
        return bone.use_deform or not any(
            mesh.vertex_groups.get(bone.name) for mesh in skinned_meshes(context.scene, rig))
    if check_id == 'driver':
        return _driver_fixed(issue)
    if check_id == 'rig_transform':
        return not any(find_unapplied_transform(context, rig))
    if check_id in {'mesh_no_modifier', 'modifier_wrong_rig'}:
        return _mesh_fixed(context.scene, rig, issue)
    return False


def refresh_evaluation(context, rig):
    """Re-evaluate everything the checks read: validity flags only update on evaluation."""
    for owner, _obj in driver_owners(context.scene, rig):
        owner.update_tag()
    context.view_layer.update()


# Checks run in this order, which is also the order results are listed in.
# Each finder takes (context, rig) and yields (bone, detail, message, object_name).
RIG_CHECK_FINDERS = [
    ('constraint', find_constraint_issues),
    ('driver', find_driver_issues),
    ('unpaired', find_unpaired_bones),
    ('deform_unweighted', find_unweighted_deform_bones),
    ('nondeform_weighted', find_weighted_nondeform_bones),
    ('rig_transform', find_unapplied_transform),
    ('mesh_no_modifier', find_meshes_without_modifier),
    ('modifier_wrong_rig', find_modifiers_on_other_rigs),
]


def clear_rig_check(scene):
    results = scene.bonemancer_rig_check
    results.issues.clear()
    results.issues_index = 0
    results.has_run = False
    results.python_drivers = 0


def run_rig_check(context, rig):
    """Replace the scene's results with a fresh check of rig; returns the issue count."""
    _check_cache.clear()
    refresh_evaluation(context, rig)
    # The evaluation runs the depsgraph handler, which may have picked the
    # newly active armature (and cleared the results); check that one.
    current = get_rig(context.scene)
    if current is not None and current != rig:
        rig = current
        refresh_evaluation(context, rig)
    results = context.scene.bonemancer_rig_check
    results.issues.clear()
    results.python_drivers = 0
    for check_id, finder in RIG_CHECK_FINDERS:
        for bone, detail, message, object_name in finder(context, rig):
            issue = results.issues.add()
            issue.check = check_id
            issue.bone = bone
            issue.detail = detail
            issue.message = message
            issue.object_name = object_name
    _check_cache.clear()
    results.issues_index = 0
    results.has_run = True
    return len(results.issues)


def ignore_index(rig, issue):
    """Index of the rig's ignore entry matching issue, or -1."""
    if rig is None:
        return -1
    for i, entry in enumerate(rig.bonemancer_ignored_issues):
        if entry.check == issue.check and entry.bone == issue.bone and entry.detail == issue.detail:
            return i
    return -1


def is_ignored(rig, issue):
    return ignore_index(rig, issue) >= 0


def library_ignore(arm_obj, issue):
    """True if issue is ignored in the library file an overridden rig comes from."""
    override = arm_obj.override_library if arm_obj else None
    reference = override.reference if override else None
    return reference is not None and is_ignored(reference, issue)


LINKED_IGNORE_MESSAGE = "Rig is linked from a library; make a library override to ignore issues"


LIBRARY_IGNORE_MESSAGE = "Ignored in the rig's library file; stop ignoring it there"


def visible_issues(scene):
    """The issues that aren't ignored on the picked rig."""
    rig = get_rig(scene)
    return [issue for issue in scene.bonemancer_rig_check.issues if not is_ignored(rig, issue)]


def rename_ignore_entries(arm_obj, old_name, new_name):
    """Keep the rig's ignores matching a renamed bone (its name and its data paths)."""
    old_path, new_path = f"bones{path_key(old_name)}", f"bones{path_key(new_name)}"
    for entry in arm_obj.bonemancer_ignored_issues:
        if entry.bone == old_name:
            entry.bone = new_name
        if old_path in entry.detail:
            entry.detail = entry.detail.replace(old_path, new_path)


def get_issue(scene, index):
    issues = scene.bonemancer_rig_check.issues
    return issues[index] if 0 <= index < len(issues) else None


def issue_explanation(issue):
    """(heading, icon, why, fix) for an issue; fix is "" when the check has none."""
    heading, icon, lines = RIG_CHECKS.get(issue.check, ("Issue", 'ERROR', ()))
    why, _, fix = " ".join(lines).partition(" Fix: ")
    return heading, icon, why, fix
