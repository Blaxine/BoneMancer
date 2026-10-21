"""Shared harness for the suites in this folder. Runs inside Blender (see run.py)."""

import bpy
import importlib.util
import os
import sys
import tempfile

# Never leave __pycache__ inside the package folder: it would end up in the built zip
sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)
PACKAGE_DIR = os.path.join(REPO_DIR, "bonemancer")
LEGACY_DIR = os.path.join(TESTS_DIR, "legacy")

results = []


def check(name, fn):
    """Run fn and record PASS/FAIL. fn returns (ok, detail), or anything else to mean ok."""
    try:
        r = fn()
        ok, detail = r if isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], bool) else (True, r)
    except Exception as e:
        lines = [l for l in str(e).strip().splitlines()
                 if l.strip() and not l.startswith("Location")
                 and not l.strip().startswith(("File", "Traceback", "^", "~"))]
        ok, detail = False, f"EXC {type(e).__name__}: {' | '.join(lines[-2:])[:300]}"
    results.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f" -> {detail}"), flush=True)
    return ok


def finish():
    """Print the summary line run.py parses and exit with the suite's status."""
    passed = sum(ok for ok, _, _ in results)
    failed = len(results) - passed
    print(f"BONEMANCER_SUMMARY pass={passed} fail={failed} version={bpy.app.version_string.split()[0]}", flush=True)
    sys.exit(1 if failed else 0)


def load_addon():
    """Import the package straight from the repo (not installed) and return the module."""
    spec = importlib.util.spec_from_file_location(
        "bonemancer", os.path.join(PACKAGE_DIR, "__init__.py"),
        submodule_search_locations=[PACKAGE_DIR])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bonemancer"] = mod
    spec.loader.exec_module(mod)
    return mod


def tmp_dir():
    """Scratch folder for this suite run; run.py deletes it afterwards."""
    path = os.environ.get("BONEMANCER_TEST_TMP") or tempfile.mkdtemp(prefix="bonemancer-")
    os.makedirs(path, exist_ok=True)
    return path


def other_blenders():
    """Every Blender passed to run.py except the one running this suite."""
    me = os.path.normcase(os.path.abspath(bpy.app.binary_path))
    paths = [p for p in os.environ.get("BONEMANCER_TEST_BLENDERS", "").split(os.pathsep) if p]
    return [p for p in paths if os.path.normcase(os.path.abspath(p)) != me]


def refused(call):
    """Operator {'ERROR'} reports raise RuntimeError in background mode; treat them as CANCELLED."""
    try:
        return call()
    except RuntimeError as e:
        if "Error:" in str(e):
            return {'CANCELLED'}
        raise


def make_arm(name, bones=("a", "b"), collection=None):
    """A new armature object with one bone per name, linked to the scene (or collection)."""
    arm = bpy.data.objects.new(name, bpy.data.armatures.new(name))
    (collection or bpy.context.scene.collection).objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i, bn in enumerate(bones):
        eb = arm.data.edit_bones.new(bn)
        eb.head = (i, 0, 0)
        eb.tail = (i, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm


def clear_data():
    """Remove every object, action, collection and armature from the open file."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.actions, bpy.data.collections, bpy.data.armatures, bpy.data.meshes):
        for item in list(coll):
            coll.remove(item)
    bpy.context.scene.tool_settings.use_keyframe_insert_auto = False


class MockLayout:
    """Stands in for UILayout so panel draw() code runs headless."""
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n in ("panel", "panel_prop"):
            return lambda *a, **k: (MockLayout(), MockLayout())   # (header, body)
        return MockLayout()
    def __call__(self, *a, **k): return MockLayout()
    def __setattr__(self, n, v): pass


class FakePanel:
    layout = MockLayout()


class Drawn:
    """One thing a RecordingLayout was asked to draw."""
    def __init__(self, kind, args, kwargs, layout, result):
        self.kind, self.args, self.kwargs, self.layout, self.result = kind, args, kwargs, layout, result

    @property
    def text(self):
        return self.kwargs.get("text", "")

    @property
    def enabled(self):
        return self.layout.is_enabled()


class RecordingLayout:
    """Like MockLayout, but writes down every label, operator, prop and list it draws, in order."""
    def __init__(self, log=None, parent=None):
        self.__dict__.update(log=[] if log is None else log, parent=parent, attrs={})

    def __setattr__(self, n, v):
        self.attrs[n] = v

    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        def call(*a, **k):
            child = RecordingLayout(self.log, self)
            self.log.append(Drawn(n, a, k, self, child))
            # (header, body); the body is None while the sub-panel is closed
            if n == "panel_prop":
                return child, (RecordingLayout(self.log, self) if getattr(a[0], a[1]) else None)
            if n == "panel":
                return child, (None if k.get("default_closed") else RecordingLayout(self.log, self))
            return child
        return call

    def is_enabled(self):
        node = self
        while node is not None:
            if node.attrs.get("enabled", True) is False:
                return False
            node = node.parent
        return True

    def drawn(self, *kinds):
        return [d for d in self.log if not kinds or d.kind in kinds]

    def texts(self, *kinds):
        return [d.text for d in self.drawn(*kinds)]


def record(draw, *args):
    """Run a draw(self, context) style function and return what it drew."""
    import types
    layout = RecordingLayout()
    draw(types.SimpleNamespace(layout=layout), *args)
    return layout
