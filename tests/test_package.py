"""The package validates, builds, installs into an isolated extension repo, enables and uninstalls."""

import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from helpers import check, finish, tmp_dir, PACKAGE_DIR

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

work = tmp_dir()
blender = bpy.app.binary_path
manifest_path = os.path.join(PACKAGE_DIR, "blender_manifest.toml")


def command(*args):
    proc = subprocess.run([blender, "--factory-startup", "--command", "extension", *args],
                          capture_output=True, text=True, errors="replace", timeout=300)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def manifest():
    with open(manifest_path, "rb") as f:
        return tomllib.load(f)


def manifest_fields():
    m = manifest()
    got = (m["id"], m["version"], m["blender_version_min"], m["license"], len(m["tagline"]) <= 64)
    return (got == ("bonemancer", "1.0.0", "4.2.0", ["SPDX:GPL-3.0-or-later"], True), got)
check("manifest fields", manifest_fields)


def validate():
    code, out = command("validate", PACKAGE_DIR)
    return (code == 0, out[-500:])
check("extension validate", validate)

zip_path = os.path.join(work, "bonemancer-1.0.0.zip")


def build():
    code, out = command("build", "--source-dir", PACKAGE_DIR, "--output-dir", work)
    if code != 0 or not os.path.isfile(zip_path):
        return (False, out[-500:])
    names = zipfile.ZipFile(zip_path).namelist()
    unwanted = [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".zip"))]
    return ("blender_manifest.toml" in names and "__init__.py" in names and not unwanted, names)
check("extension build", build)


def user_repo():
    repo = next((r for r in bpy.context.preferences.extensions.repos if r.module == "user_default"), None)
    return repo, list(bpy.context.preferences.extensions.repos).index(repo) if repo else -1


def isolated():
    # Refuse to install into a real user configuration
    root = os.environ.get("BLENDER_USER_RESOURCES", "")
    repo, _ = user_repo()
    ok = bool(root) and repo is not None and os.path.normcase(repo.directory).startswith(os.path.normcase(root))
    return (ok, repo.directory if repo else None)


if check("user extension repo is isolated", isolated):
    module = "bl_ext.user_default.bonemancer"

    def install():
        bpy.ops.extensions.package_install_files(filepath=zip_path, repo="user_default", enable_on_install=True)
        got = (module in bpy.context.preferences.addons.keys(), hasattr(bpy.types.Scene, "bonemancer_rig"))
        return (got == (True, True), got)
    check("install and enable", install)

    def panels():
        got = [c for c in ("BONEMANCER_PT_rig", "BONEMANCER_PT_bone_sets", "BONEMANCER_PT_shape_keys")
               if not hasattr(bpy.types, c)]
        return (got == [], got)
    check("panels registered", panels)

    def uninstall():
        repo, index = user_repo()
        bpy.ops.extensions.package_uninstall(repo_index=index, pkg_id="bonemancer")
        got = (os.path.isdir(os.path.join(repo.directory, "bonemancer")), hasattr(bpy.types.Scene, "bonemancer_rig"))
        return (got == (False, False), got)
    check("uninstall", uninstall)

finish()
