# Manual UI checklist

Run before every release, in each Blender version the release claims
(oldest supported LTS, current LTS, latest). The automated suites
(`tests/run.py`) cover data and operator behaviour; this list covers what
only a person looking at the screen can judge.

Use a fresh user folder so your own add-ons don't interfere: start Blender
from a terminal with `BLENDER_USER_RESOURCES` set to an empty temp folder.

## Install

- [ ] Edit > Preferences > Get Extensions > Install from Disk with the built
      `bonemancer-<version>.zip` installs without errors.
- [ ] The add-on appears as "Bone Mancer: Rig Central" with the right version,
      tagline and website link.
- [ ] The **Bonemancer** tab appears in the 3D Viewport sidebar with the
      Rig Central, Bone Sets, Rig Check and Shape Key Scanner panels.

## Rig picker and Bone Picker

- [ ] With no armature in the scene, the panels say so instead of erroring.
- [ ] Add > Armature > Human (Rigify) (or any rig); pick it in **Armature**:
      it becomes active and Pose Mode is entered.
- [ ] Clicking another armature in the viewport switches the picker to it.
- [ ] In Sculpt Mode on a mesh, picking a rig from the list does **not** leave
      Sculpt Mode.
- [ ] The Bone Picker lists every bone; the list scrolls and filters.
- [ ] Clicking a bone in the Bone Picker selects it (and only it) in the
      viewport and makes it active, in Object, Pose and Edit Mode.
- [ ] Clicking a bone in the viewport highlights its row in the Bone Picker,
      whether or not it is in a bone set.
- [ ] Relations (i) shows parent and children.
- [ ] Rename: each mode (Exact / Prefix / Suffix / Replace) updates the preview
      live; the driver and constraint counts look right; an existing name shows
      an error in the preview and OK does nothing.

## Bone Sets

- [ ] With no sets, the panel shows "No Bone Sets yet" and **Import Bone
      Collections**.
- [ ] Import dialog: collections are nested as in the Outliner, each shows its
      bone count, empty ones are unticked; OK creates the ticked sets.
- [ ] Running Import again changes nothing unless the rig's collections
      changed.
- [ ] **+** in the Bone Picker: adding to a new set and to an existing set
      both work; adding a bone twice shows an info message.
- [ ] Expand/collapse a set; the eye hides all its bones, and shows them all
      when every bone is hidden.
- [ ] Delete set asks for confirmation; the bones themselves stay.
- [ ] Per bone: select highlights when the bone is selected in the viewport;
      hide, rename and remove work; custom properties are editable in place
      and **Add Property** works; constraints show influence sliders and a
      warning icon (with details) on a constraint with a missing target.
- [ ] Delete a bone in Edit Mode: its row shows "(missing)" with a remove
      button.
- [ ] Rename a bone with F2: its set entry follows.
- [ ] Ctrl+Z undoes each data change above one step at a time.
- [ ] Icons read clearly in both the dark and light themes.

## Rig Check

- [ ] With no rig picked the panel says "Select an armature"; Check Rig is
      disabled.
- [ ] On a freshly generated Rigify human with a mesh parented With Automatic
      Weights, Check Rig finishes instantly and shows few or no issues.
- [ ] Break one of each and Check Rig: clear a constraint's target; make a
      driver read a property that doesn't exist; delete `hand.R`; turn off
      Deform on a weighted bone; scale the rig to 0.5; parent a mesh to the rig
      With Object (no modifier). Each appears once, grouped by check, and the
      header count matches.
- [ ] Select on a bone issue selects that bone in Pose Mode; on a mesh issue it
      selects the mesh in Object Mode and shows a message in other modes.
- [ ] Explain (info button) opens a readable why / how-to-fix dialog for every
      kind of issue.
- [ ] Fix a listed problem by hand: its row greys out with "fixed; check again
      to update"; Check Rig removes it.
- [ ] Ignore an issue: it leaves the list and the count; "Show Ignored (1)"
      brings it back greyed with Stop Ignoring; it stays ignored after F2-renaming
      its bone and after save / reopen.
- [ ] Linked rig: issues are listed, the ignore buttons are disabled and their
      tooltip says to make a library override.
- [ ] Ctrl+Z undoes Check Rig, Ignore and Stop Ignoring one step at a time.
- [ ] Rows and icons read clearly in the dark and light themes.

## Shape Key Scanner

- [ ] **Scan Rig For Shape Keys** lists meshes deformed by the rig, without
      their Basis key.
- [ ] Sliders change the shape; with auto-keying on, scanning adds no keys.
- [ ] The key button inserts a key on the current frame and removes it on a
      second click; the Dope Sheet updates.

## Files

- [ ] Save, close, reopen: sets, expanded state and the picked rig are kept.
- [ ] A file saved with an older Bone Mancer opens with its groups as bone
      sets.
- [ ] Link the rig into another file and make a library override: sets are
      editable; bone rename and Add Property are refused with a message.
      Deleting a set that came from the library file, or removing one of its
      original bones, shows an error and changes nothing.
- [ ] Delete the picked rig with X, save, reopen: the rig is gone (not kept
      by Bone Mancer) and the panel shows no rig.
- [ ] Uninstall the extension; Blender keeps working and the file still opens.
