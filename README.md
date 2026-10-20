# Bone Mancer: Rig Central

An animator's control hub for Blender rigs. Organize a rig's bones into **Bone
Sets** and work with them from one sidebar tab: hide and show, select, rename,
tweak custom properties and constraint influences, and key shape keys, without
digging through the Outliner or the Properties editor.

Requires Blender 4.2 or later. Free and open source under GPL-3.0-or-later.

## Features

- **Rig picker.** Choose the armature to work on, or just click one in the
  viewport: the panel follows the active armature. Picking from the list puts
  the rig in Pose Mode (only from Object, Pose or armature Edit Mode, so a
  sculpt or paint session isn't interrupted).
- **Bone Picker.** Every bone of the rig, with buttons to add it to a bone set,
  rename it, or show its parent and children. Click a bone to select it in the
  viewport; bones selected in the viewport are highlighted, and **Add Selected
  to Bone Set** puts all of them into a new or existing set in one go.
- **Bone Sets.** Named lists of bones stored on the rig, so they travel with it
  when you append or link it. For each set: expand, hide/show all its bones,
  delete. For each bone in a set:
  - select it in the viewport
  - edit its custom properties in place, or add new ones
  - see its constraints with influence sliders and a warning on broken ones
  - hide/show, rename, remove from the set
  - bones deleted or renamed outside Bone Mancer are flagged, and renames done
    elsewhere (F2, Outliner, batch rename) are followed
- **Import Bone Collections.** Turn the rig's existing bone collections into
  bone sets in one click: pick which ones in a checklist, nested like the
  Outliner. Importing again later only adds what's new; it never removes
  bones, reorders, or touches sets you made yourself.
- **Rename that keeps the rig working.** Exact, prefix (DEF_ / ORG_ / MCH_ or
  your own), suffix, or find-and-replace, with a live preview. Drivers on this
  rig and bone set entries are updated; names that already exist are refused.
- **Shape Key Scanner.** Lists the shape keys of every mesh the rig deforms
  (parented to it at any depth, or with an Armature modifier on it), with
  sliders and a keyframe toggle for the current frame.
- **Rig Check.** One click lists what's wrong with the rig: constraints with
  no target, drivers that can't evaluate, left/right bones with no partner,
  deform bones without weights (and weighted bones with Deform off), and setup
  mistakes such as an unapplied rig scale or a mesh parented without an
  Armature modifier. Each result selects its bone or object and explains why
  it matters and how to fix it; nothing is changed for you. Results you don't
  care about can be ignored per rig, and fixed ones grey out as you go.
- **Library overrides.** Bone sets can be edited on an overridden rig. Renames
  and new custom properties are refused there, because Blender doesn't keep
  them; a rig linked without an override is read-only.

Files saved with earlier versions of Bone Mancer are upgraded automatically
when opened.

## Install

**From Blender (once listed on extensions.blender.org):** Edit > Preferences >
Get Extensions, search for "Bone Mancer", click Install.

**From a zip:** download `bonemancer-<version>.zip` from the
[Releases](https://github.com/Blaxine/BoneMancer/releases) page, then in
Blender use Edit > Preferences > Get Extensions > ⌄ (top right) > Install from
Disk.

The panels are in the 3D Viewport sidebar (N), tab **Bonemancer**.

## Quick start

1. Open the **Bonemancer** tab and pick your rig in **Armature**.
2. In **Bone Sets**, click **Import Bone Collections**, untick the collections
   you don't animate with (for example ORG / DEF / MCH on a Rigify rig), and
   click OK.
3. Expand a set to select its bones, hide them, or open their custom
   properties and constraints.
4. Use the **+** button in the Bone Picker to put any bone into a new or
   existing set.
5. Open **Rig Check** and click **Check Rig** to find broken constraints,
   drivers, weights and setup mistakes; use the info button on a result to
   see how to fix it.

## Reporting bugs

Please open an [issue on GitHub](https://github.com/Blaxine/BoneMancer/issues)
with your Blender version, Bone Mancer version, the steps to reproduce, and if
possible a small .blend that shows the problem.

## Development

The add-on lives in `bonemancer/` (`__init__.py` and `blender_manifest.toml`).

Run the automated tests against one or more Blender builds:

```
blender -b --factory-startup --python tests/run.py -- PATH/TO/blender [PATH/TO/another/blender ...]
```

Each suite runs in its own background Blender with a temporary user folder,
so your own Blender configuration is never touched. Add `--only smoke` (or
`import`, `library`, `migration`, `package`, `rig_check`) to run one suite, and
`--verbose` for full output. Before a release, also go through
[tests/MANUAL_CHECKLIST.md](tests/MANUAL_CHECKLIST.md) for what headless
tests can't see.

Build the installable zip:

```
blender --command extension build --source-dir bonemancer --output-dir build
```

## License

[GPL-3.0-or-later](LICENSE)
