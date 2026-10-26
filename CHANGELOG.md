# Changelog

Notable changes to Bone Mancer. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version numbers
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.1]

### Added

- **Apply Rigify Template** also adds a Face tab with the eye, brow, lid,
  nose, lip, jaw, teeth and tongue controls of a generated Rigify human. On a
  rig laid out with 1.2.0, applying again adds it without touching Body and
  Hands.

## [1.2.0]

### Added

- **Actionable Bones** panel: select a rig's controls by clicking buttons laid
  out like the character, with Shift+click to add or remove. Cells show
  pressed for selected bones, greyed for hidden ones, and blue / red / yellow
  for left, right and centre controls.
- **Apply Rigify Template** lays out a generated Rigify human's body and hand
  controls on Body and Hands tabs over a grey silhouette. Applying again only
  fills empty cells.
- **Edit Layout**: place the viewport's active bone in a cell, recolour, move
  and clear cells, and add, rename and remove tabs of your own. The layout is
  saved on the rig and follows bone renames; overridden rigs show the layout
  from their own file.

- **Bones** highlights every bone selected in the viewport, and **Add Selected
  to a Bone Set** adds all of them at once.
- **Deform**, **IK Stretch** and **Lock IK** X / Y / Z can be set under the
  highlighted bone and inside an opened bone of a set.
- **In Front** checkbox under the picked rig.
- Custom properties: the gear opens Blender's Edit Property dialog (name, type,
  range, default, description) and the X removes the property.
- Constraints: the X removes a constraint; clicking one shows its target
  (object and bone or vertex group), pole target, the targets of an Armature
  constraint, and its target and owner spaces.

### Changed

- Redesigned sidebar: six panels (Rig, Actionable Bones, Bones, Bone Sets,
  Rig Check, Shape Keys), names instead of rows of icons, labelled actions, and empty panels
  that say what to do next. Rig Check explanations show in the panel instead
  of a dialog.
- The Shape Keys list keeps itself up to date as shape keys and skinned meshes
  change.
- The add-on's code is organised into modules (`core/`, `operators/`, `ui/`)
  instead of one file. Behaviour and saved data are unchanged.

- **Bones** starts closed; Actionable Bones takes its place as the way to pick
  bones.

### Fixed

- Picking a bone on a library override that isn't editable reports why
  instead of failing.
- Switching a property to Integer in Edit Property no longer fails with
  "max_int value not in 'int' range".

## [1.1.0]

### Added

- **Rig Check** panel: one click lists constraints with no target, drivers
  that can't evaluate, left/right bones with no partner, deform bones without
  weights and weighted bones with Deform off, and setup mistakes such as an
  unapplied rig scale or a mesh parented without an Armature modifier. Each
  result explains why it matters and selects its bone or object; results can
  be ignored per rig, and fixed ones grey out. Works on linked and overridden
  rigs.
- The Bone Picker follows bone selection in the viewport.

### Fixed

- A deleted rig is no longer kept in the file by the add-on.
- Removing a bone set that comes from the library is refused on an overridden
  rig.

## [1.0.0]

First release as a Blender extension (Blender 4.2 or later).

### Added

- **Import Bone Collections** turns the rig's bone collections into bone sets.
- Automated test suites for Blender 4.5 and 5.x, and a manual checklist.

### Changed

- Groups are called **Bone Sets** and are stored on the rig, so they travel
  with it when it is appended or linked.
- Every operator and property is named `bonemancer`. Files saved with earlier
  versions are upgraded when opened.

### Removed

- Half-built features and unused properties.

[Unreleased]: https://github.com/Blaxine/BoneMancer/commits/main
