"""Run every BoneMancer test suite against one or more Blender builds.

    blender -b --factory-startup --python tests/run.py -- [options] BLENDER [BLENDER ...]

BLENDER is the path to a blender executable. The orchestrator needs no bpy, so
any Python 3 works too:  python tests/run.py [options] BLENDER [BLENDER ...]

Options:
    --only NAME    run only tests/test_NAME.py (repeatable)
    --verbose      print each suite's full output

Each suite runs in its own background Blender process with --factory-startup
and BLENDER_USER_RESOURCES pointing at a fresh temp folder, so nothing is read
from or written to your own Blender configuration. Exits non-zero if any check
fails or a suite crashes.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SUITE_TIMEOUT = 900
SUMMARY_RE = re.compile(r"^BONEMANCER_SUMMARY pass=(\d+) fail=(\d+) version=(\S+)", re.M)


def parse_args(argv):
    only, verbose, blenders = [], False, []
    it = iter(argv)
    for arg in it:
        if arg == "--only":
            only.append(next(it, ""))
        elif arg == "--verbose":
            verbose = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            blenders.append(arg)
    return only, verbose, blenders


def run_suite(blender, suite, blenders):
    root = tempfile.mkdtemp(prefix="bonemancer-test-")
    env = dict(os.environ)
    env["BLENDER_USER_RESOURCES"] = os.path.join(root, "user")
    env["BONEMANCER_TEST_TMP"] = os.path.join(root, "work")
    env["BONEMANCER_TEST_BLENDERS"] = os.pathsep.join(blenders)
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python", suite]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=SUITE_TIMEOUT)
        output, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        output, code = (e.stdout or "") if isinstance(e.stdout, str) else "", None
        output += f"\nTIMEOUT after {SUITE_TIMEOUT}s"
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return output, code


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    only, verbose, blenders = parse_args(argv)
    if not blenders:
        print(__doc__)
        return 2
    missing = [b for b in blenders if not os.path.isfile(b)]
    if missing:
        print("Not found:", *missing, sep="\n  ")
        return 2

    suites = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    if only:
        suites = [s for s in suites if os.path.basename(s)[5:-3] in only]
        if not suites:
            print("No suite matches", only)
            return 2

    rows = []   # (suite, version, status)
    failed = False
    for blender in blenders:
        for suite in suites:
            name = os.path.basename(suite)[5:-3]
            print(f"--- {name} on {blender}", flush=True)
            output, code = run_suite(blender, suite, blenders)
            m = SUMMARY_RE.search(output)
            if m:
                passed, fails, version = int(m.group(1)), int(m.group(2)), m.group(3)
                ok = fails == 0 and code == 0
                status = f"{passed} pass" if ok else f"{fails} FAIL / {passed} pass"
            else:
                version, ok, status = os.path.basename(os.path.dirname(blender)), False, f"CRASH (exit {code})"
            failed |= not ok
            if verbose:
                print(output)
            elif not ok:
                lines = [l for l in output.splitlines() if l.startswith("[FAIL]")]
                print("\n".join(lines) if lines and m else "\n".join(output.splitlines()[-40:]))
            rows.append((name, version, status))

    versions = list(dict.fromkeys(v for _, v, _ in rows))
    names = list(dict.fromkeys(n for n, _, _ in rows))
    table = {(n, v): s for n, v, s in rows}
    widths = [max(len("suite"), *map(len, names))] + [max(len(v), *(len(table.get((n, v), "")) for n in names)) for v in versions]
    print()
    print("  ".join(h.ljust(w) for h, w in zip(["suite", *versions], widths)))
    print("  ".join("-" * w for w in widths))
    for n in names:
        print("  ".join(c.ljust(w) for c, w in zip([n, *(table.get((n, v), "-") for v in versions)], widths)))
    print("\nRESULT:", "FAILED" if failed else "ALL PASSED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
