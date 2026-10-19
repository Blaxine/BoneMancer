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
      Rig Central, Bone Sets and Shape Key Scanner panels.

## Rig picker and Bone Picker

- [ ] With no armature in the scene, the panels say so instead of erroring.
- [ ] Add > Armature > Human (Rigify) (or any rig); pick it in **Armature**:
      it becomes active and Pose Mode is entered.
- [ ] Clicking another armature in the viewport switches the picker to it.
- [ ] In Sculpt Mode on a mesh, picking a rig from the list does **not** leave
      Sculpt Mode.
- [ ] The Bone Picker lists every bone; the list scrolls and filters.
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
- [ ] Uninstall the extension; Blender keeps working and the file still opens.
