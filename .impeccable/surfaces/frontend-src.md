---
version: 1
slug: "frontend-src"
primary_target: "frontend/src"
related_targets: []
---

## Scope

Whole LiteGate frontend (`frontend/src`), every screen and both layouts. Mode: Operate.

## Direction contract

THESIS: LiteGate should feel like a native macOS utility in the browser: quiet chrome, content first, one accent. It refuses the category default of a dark navy admin rail with coloured stat cards.

OWN-WORLD: Apple system palette. Light: grouped grey ground (#F2F2F7), white grouped sections, hairline separators, labels at Apple's primary/secondary/tertiary opacities, systemBlue accent; status in systemGreen, systemOrange, systemRed. Dark: true dark grouped ground, elevated #1C1C1E sections. System font stack (SF Pro where available). Inset grouped lists, segmented controls, sheets, 10px section radius, 8px control radius.

STORY: A user sees how much budget is left and their key, copies or regenerates it, and leaves. An owner or admin moves between sections in a sidebar and edits in place.

FIRST VIEWPORT: Translucent light sidebar (236px) with tinted selected row; content column with a large-title header (28px bold) and the page's primary grouped section directly under it; the primary action is a filled blue button in the header or section.

FORM: Apple HIG (macOS Settings / System app idiom), pinned by the user. seed: none (pinned) "follow Apple's Human Interface Guidelines for layout, typography, spacing, controls and feedback"; "macOS-style, light sidebar".

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
