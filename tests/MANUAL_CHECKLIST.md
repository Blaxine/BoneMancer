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
- [ ] The **Bonemancer** tab appears in the 3D Viewport sidebar with the Rig,
      Bones, Bone Sets, Rig Check and Shape Keys panels, in that order. On a
      first run Rig, Bones and Bone Sets are open; Rig Check and Shape Keys are
      closed.

## Sidebar layout

- [ ] In an empty scene, Rig says there's no armature and offers **Add
      Armature**; every other panel says to pick an armature in the Rig panel.
- [ ] Hint and explanation text wraps to the sidebar and is never cut off with
      "...": at the default width, dragged wide, dragged narrow, and with
      Preferences > Interface > Resolution Scale at 1.5.
- [ ] No list row carries a row of icon buttons: Bones rows are names only,
      Bone Set bone rows are a name and an eye, Rig Check rows are a message.

## Rig picker and Bone Picker

- [ ] With no armature in the scene, the panels say so instead of erroring.
- [ ] Add > Armature > Human (Rigify) (or any rig); pick it in **Armature**:
      it becomes active and Pose Mode is entered.
- [ ] Clicking another armature in the viewport switches the picker to it.
- [ ] **In Front** under Armature matches Object Properties > Viewport Display >
      In Front for the picked rig; ticking it draws the bones over the mesh,
      and it follows when another rig is picked. Ctrl+Z undoes it.
- [ ] In Sculpt Mode on a mesh, picking a rig from the list does **not** leave
      Sculpt Mode.
- [ ] The Bone Picker lists every bone; the list scrolls and filters.
- [ ] Clicking a bone in the Bone Picker selects it (and only it) in the
      viewport and makes it active, in Object, Pose and Edit Mode.
- [ ] Clicking a bone in the viewport highlights its row in the Bone Picker,
      whether or not it is in a bone set.
- [ ] Shift-click several bones in the viewport (Pose and Edit Mode): every
      selected bone's row is highlighted; Ctrl-click one off and its highlight
      goes. Hidden bones are never highlighted.
- [ ] **Add n Selected to a Bone Set** shows the selected count and adds all of
      them to a new or existing set in one click, skipping ones already in it.
      With nothing selected it reads "Select Bones to Add Them to a Bone Set"
      and is disabled.
- [ ] Under the list, the highlighted bone's name is shown with **Rename** and
      **Relations**; Relations shows parent and children.
- [ ] **Deform**, **IK Stretch** and **Lock IK** X / Y / Z under the list match
      the Bone Properties editor for the highlighted bone, and changing them
      here changes them there (and the other way round). In Edit Mode, untick
      Deform, go back to Pose Mode: it stays off. Ctrl+Z undoes each change.
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
- [ ] **Add Selected to a Bone Set**: adding to a new set and to an existing
      set both work; adding one bone that's already in the set shows an info
      message.
- [ ] Click a set's header to fold it open and closed; it shows the bone
      count. The eye hides all its bones, and shows them all when every bone is
      hidden.
- [ ] Delete set asks for confirmation; the bones themselves stay.
- [ ] Per bone: clicking the name selects the bone, and the name is drawn
      pressed while the bone is selected in the viewport; the eye hides it.
      Opening the bone shows **Rename** and **Remove from Set** (both work),
      the same Deform / IK Stretch / Lock IK controls,
      **Properties (n)** (editable in place; **Add Property** works; the gear
      opens Blender's Edit Property dialog for that bone's property, and
      renaming, changing min/max or type there shows up in the panel; on a
      Float made with Add Property, switching Type to Integer and back raises
      no Python error; X removes it, and Ctrl+Z brings it back) and
      **Constraints (n)** with influence sliders. A constraint with a missing
      target adds ", 1 broken" and a warning icon to the heading, and a warning
      button (with details) in its row.
- [ ] Sets, bones, Properties and Constraints stay open or closed after save /
      reopen.
- [ ] Delete a bone in Edit Mode: its row shows "(missing)" with a remove
      button.
- [ ] Rename a bone with F2: its set entry follows.
- [ ] Ctrl+Z undoes each data change above one step at a time.
- [ ] Icons read clearly in both the dark and light themes.

## Rig Check

- [ ] With no rig picked the panel says to pick an armature in the Rig panel.
      Before the first check it explains what Check Rig does.
- [ ] On a freshly generated Rigify human with a mesh parented With Automatic
      Weights, Check Rig finishes instantly and shows few or no issues.
- [ ] Break one of each and Check Rig: clear a constraint's target; make a
      driver read a property that doesn't exist; delete `hand.R`; turn off
      Deform on a weighted bone; scale the rig to 0.5; parent a mesh to the rig
      With Object (no modifier). Each appears once, grouped by check, and "n
      issues found" and the header count match. The button now reads **Check
      Again**.
- [ ] Clicking a result shows, under the list, its heading, the full message,
      why it matters and how to fix it, readable for every kind of issue.
- [ ] **Select** on a bone issue selects that bone in Pose Mode; on a mesh
      issue it selects the mesh in Object Mode and shows a message in other
      modes.
- [ ] Fix a listed problem by hand: its row greys out with "(fixed)" and the
      details say to check again; Check Again removes it.
- [ ] **Ignore** an issue: it leaves the list and the count; "Show Ignored (1)"
      brings it back greyed, and its details offer **Stop Ignoring**; it stays
      ignored after F2-renaming its bone and after save / reopen.
- [ ] Linked rig: issues are listed, Ignore is disabled and its tooltip says to
      make a library override. Its Bone Sets still fold open and closed.
- [ ] Ctrl+Z undoes Check Rig, Ignore and Stop Ignoring one step at a time.
- [ ] Rows and icons read clearly in the dark and light themes.

## Shape Key Scanner

- [ ] **Shape Keys** lists the meshes deformed by the rig with their key
      counts; clicking one shows its shape keys below, without the Basis key.
      A mesh with only a Basis key says so.
- [ ] Without clicking the refresh icon: adding, renaming or removing a shape
      key, and parenting a new mesh to the rig (or removing its Armature
      modifier), update the list right away; the highlighted mesh stays
      highlighted. Dragging a slider or sculpting doesn't make the panel flicker
      or lag. The refresh icon in the panel header rebuilds the list on demand.
- [ ] Sliders change the shape; with auto-keying on, scanning adds no keys.
- [ ] The key button inserts a key on the current frame and removes it on a
      second click; the Dope Sheet updates.

## Files

- [ ] Save, close, reopen: sets, expanded state and the picked rig are kept.
- [ ] A file saved with an older Bone Mancer opens with its groups as bone
      sets.
- [ ] Link the rig into another file and make a library override: sets are
      editable; bone rename and Add Property are refused with a message, and
      bone properties show no gear or X.
      Deleting a set that came from the library file, or removing one of its
      original bones, shows an error and changes nothing.
- [ ] Delete the picked rig with X, save, reopen: the rig is gone (not kept
      by Bone Mancer) and the panel shows no rig.
- [ ] Uninstall the extension; Blender keeps working and the file still opens.
