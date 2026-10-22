# REQ-003-PRD — Actionable Bones

| Field | Value |
| ----- | ----- |
| ID | REQ-003-PRD |
| Title | Actionable Bones |
| SOLVE | — |
| Status | Todo |
| Author | Blaxine |
| Created | 2026-10-22 |
| Last Updated | 2026-10-22 |

## Problem Statement

An animator posing a rig spends much of their time just getting to the right
control. In the viewport, controls overlap, hide inside the mesh, or sit on
hidden bone collections. In Bone Mancer's Bones panel they are one long
alphabetical list, mixed in with deform, mechanism and helper bones the
animator never touches. Maya animators work from a picker instead: a small map
of the character where each control is a button in the place it belongs on
the body. Blender has no such picker. Bone Mancer doesn't either, so selecting
a finger or lip control means searching by name or orbiting the view.

## Solution

A new **Actionable Bones** panel near the top of the Bonemancer sidebar tab
shows the rig's animation controls as a map of the character. The map is a
grid of buttons on a body silhouette, split into Body, Hands and Face tabs.
Each button is one control.
- **Picking:** clicking a button selects that control. Shift+click adds or
  removes it. Selected controls show as pressed, and controls that are
  currently hidden show greyed out and are left alone.
- **Colour tags:** a coloured tag on each button tells left (blue), right (red)
  and centre (yellow) apart.

Riggers decide what the map holds:
- **Edit Layout:** while it is on, selecting a bone in the viewport and
  clicking an empty cell places it there. Clicking a placed button moves,
  recolours or clears it. Extra tabs can be added for tails, props or anything
  the templates don't cover.
- **Rigify templates:** paint the silhouette and place a Rigify rig's body,
  hand and face controls automatically. Other rigs get the silhouette with
  empty slots to fill by hand.

The layout belongs to the rig and travels with it when it is appended or
linked. On a linked rig in a shot, animators can pick from it but cannot
rearrange it.

## User Stories

1. As an animator, I want to select a rig's controls by clicking buttons laid out like the character (body, hands and face), with Shift to add or remove, so that I can reach any control in one click without hunting in the viewport or a long bone list
2. As a rigger, I want to choose which bones are actionable and place, move, recolour or clear them on the layout, including on tabs of my own, so that the panel fits my rig, tails and props included
3. As a rigger working with a Rigify rig, I want to apply a body, hands and face template that places the controls for me, so that setting up the panel takes one click instead of placing every control by hand
4. As an animator working in a shot with a linked rig, I want the layout built in the rig file to come with the rig unchanged, so that every shot uses the same panel and nobody rearranges it by accident

## Out of Scope

- Dragging buttons around; placing them only by clicking cells.
- Fully coloured buttons; side is shown by a colour tag on each button.
- Buttons that select several bones at once; whole groups stay in Bone Sets.
- Actions from the panel other than selecting: keying, resetting the pose or
  mirroring a selection (Ctrl+click and Alt+click are reserved for later).
- Revealing hidden controls from the panel.
- Rearranging a linked rig's layout inside a shot.
- Automatic placement for rigs that aren't Rigify (Mixamo, Auto-Rig Pro and
  others), or for Rigify's legacy face rig.
- Retargeting: mapping a skeleton onto a standard human to transfer
  animation.
