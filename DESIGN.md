---
name: LiteGate
description: A governed self-service door to LiteLLM, built in the macOS Settings idiom.
colors:
  blue: "#007AFF"
  blue-solid: "#0071E3"
  blue-tint: "#E6F1FF"
  blue-ink: "#005CC4"
  green: "#34C759"
  green-tint: "#E6F7EB"
  green-ink: "#1E7934"
  orange: "#FF9500"
  orange-tint: "#FFF3E0"
  orange-ink: "#A04E00"
  orange-solid: "#B25700"
  danger: "#D70015"
  danger-tint: "#FFEEED"
  danger-line: "#FFCCCC"
  danger-solid: "#D70015"
  teal: "#30B0C7"
  cyan: "#32ADE6"
  indigo: "#5856D6"
  ink: "#1D1D1F"
  ink-2: "#3A3A3C"
  ink-3: "#48484A"
  ink-4: "#6A6A70"
  ink-5: "#8E8E93"
  canvas: "#F2F2F7"
  card: "#FFFFFF"
  well: "#ECECF0"
  sidebar: "#ECECF1"
  segment: "#FFFFFF"
  line: "#D8D8DC"
  line-soft: "#E5E5EA"
  line-input: "#C7C7CC"
  paper: "#FFFFFF"
typography:
  large-title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  figure:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "38px"
    fontWeight: 600
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  metric:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    letterSpacing: "-0.01em"
    fontFeature: "tnum"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  brand:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.43
  subhead:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
  group-label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  mono:
    fontFamily: "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
rounded:
  swatch: "3px"
  control-sm: "6px"
  segment: "7px"
  control: "8px"
  segment-track: "10px"
  section: "12px"
  sheet: "16px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  page-x: "32px"
  page-top: "36px"
components:
  button-primary:
    backgroundColor: "{colors.blue-solid}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-secondary:
    backgroundColor: "rgb(29 29 31 / 0.06)"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-ghost:
    textColor: "{colors.blue-ink}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-ghost-hover:
    backgroundColor: "{colors.blue-tint}"
  button-danger:
    backgroundColor: "{colors.danger-solid}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-small:
    backgroundColor: "rgb(29 29 31 / 0.06)"
    textColor: "{colors.ink}"
    typography: "{typography.subhead}"
    rounded: "{rounded.control-sm}"
    padding: "0 12px"
    height: "32px"
  button-small-danger:
    backgroundColor: "{colors.danger-tint}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control-sm}"
    padding: "0 12px"
    height: "32px"
  field-input:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  grouped-section:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.section}"
  section-header:
    typography: "{typography.title}"
    padding: "12px 20px"
  metric-card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.section}"
    padding: "16px 18px"
  pill:
    rounded: "{rounded.full}"
    typography: "{typography.caption}"
    padding: "2px 10px"
  segmented-control:
    backgroundColor: "{colors.well}"
    rounded: "{rounded.segment-track}"
    padding: "4px"
  segmented-control-selected:
    backgroundColor: "{colors.segment}"
    textColor: "{colors.ink}"
    rounded: "{rounded.segment}"
    height: "36px"
  sidebar:
    backgroundColor: "{colors.sidebar}"
    width: "236px"
  sidebar-item:
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control-sm}"
    padding: "8px 10px"
  sidebar-item-hover:
    backgroundColor: "rgb(29 29 31 / 0.05)"
  sidebar-item-selected:
    backgroundColor: "rgb(29 29 31 / 0.09)"
    textColor: "{colors.ink}"
    rounded: "{rounded.control-sm}"
    padding: "8px 10px"
  menu-item-highlight:
    backgroundColor: "{colors.blue-solid}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control-sm}"
    height: "36px"
  sheet:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.sheet}"
    padding: "20px"
---

# Design System: LiteGate

## Overview

**Creative North Star: "The Settings Pane"**

LiteGate reads as a native macOS utility that happens to live in a browser. The ground is Apple's grouped grey, content sits in white grouped sections separated by hairlines, and a single system blue carries every action and every focus ring. Chrome is quiet so the facts LiteLLM enforces (budget left, spend, the key itself) read first. A user signs in, sees one large figure and their key, and leaves; an owner or admin moves through a light sidebar and edits in place.

The system is deliberately un-branded beyond the blue mark: the system font stack, Apple's label greys, Apple's status hues and Apple's control shapes (segmented controls, grouped lists, sheets, filled and grey buttons). Selection in the sidebar is a quiet neutral tint, as in macOS Settings, so the only saturated colour on a resting screen is the one primary action. Density is moderate, comfortable on a desktop browser at work and still usable on a phone, where the sidebar becomes a scrolling top row.

It replaces, and refuses, the category default of a dark navy admin rail with coloured stat cards. Both light and dark themes are first-class, driven by one set of channel tokens; dark mode follows Apple's true-black grouped ground with elevated `#1C1C1E` sections.

**Key Characteristics:**
- Grouped grey canvas with white 12px-radius sections and hairline separators; true black with elevated grey sections in dark mode.
- One accent: system blue for primary buttons, focus, links, icons and every single-series chart. Everything else interactive is neutral.
- Status only in Apple's green, orange and red, always as tint ground plus ink text plus a dot.
- System font stack throughout; large titles at 28px bold with tight tracking; nothing smaller than 12px.
- Light sidebar with a neutral-tint selected row and blue icons; segmented controls for in-page switching.
- Near-flat surfaces; shadow appears only on things that float (menus, sheets, tooltips, selected segments, the brand tile).

## Colors

An Apple system palette: neutral greys stepped like iOS label colours, one blue accent, and semantic status hues that each come as a base, a tint and an ink.

All colours are stored as RGB channels on `:root` (light) and `html.dark` (dark) in `frontend/src/index.css`, mapped through `tailwind.config.ts` so one class name serves both themes. The frontmatter records the light values; dark values are listed in the sidecar.

### Primary
- **System Blue** (`blue`): the accent hue. Focus outlines (at 60%), text selection (at 25%), sidebar and menu icons, informational dots, the low-spend usage bar, and every single-series chart bar.
- **Filled Blue** (`blue-solid`): a slightly deeper blue reserved for solid fills carrying white text: primary buttons, checked checkboxes, the account-menu item highlight, the brand mark tile. Chosen so white text clears 4.5:1.
- **Blue Wash** (`blue-tint`) and **Blue Ink** (`blue-ink`): the informational pill, callout and count-badge ground and its text; ghost buttons use Blue Ink text and Blue Wash on hover; a selected org-tree row uses Blue Wash.

### Secondary (status)
- **System Green** (`green`, `green-tint`, `green-ink`): healthy, ready, OK. Dot in base green, pill in tint with ink text.
- **System Orange** (`orange`, `orange-tint`, `orange-ink`, `orange-solid`): warnings, including policy-sync failures in "Needs attention" and the 80% spend threshold. `orange-solid` is the white-text fill variant.
- **System Red** (`danger`, `danger-tint`, `danger-line`, `danger-solid`): errors, destructive buttons and the 95% spend threshold. In dark mode the base red lightens while the solid fills (`danger-solid`, `orange-solid`) keep their light-theme values so white text holds contrast.

### Tertiary (categorical series)
- **Teal, Cyan, Indigo** (`teal`, `cyan`, `indigo`, each with tint and ink): categorical palettes only, where several series must be told apart: the donut slice cycle (blue, teal, indigo, cyan, ...) and the organization group-colour cycle (blue, indigo, teal, cyan, green, orange). Never for actions, selection, status or a single-series chart.

### Neutral
- **Label** (`ink`): primary text and figures.
- **Secondary / Tertiary Label** (`ink-2`, `ink-3`): field labels, secondary copy, unselected segment text.
- **Quaternary Label** (`ink-4`): captions, descriptions, column heads, placeholders, sidebar group labels. Still meets 4.5:1 on canvas and card.
- **Placeholder Grey** (`ink-5`): avatars, neutral dots and scrollbar thumbs only; not body text.
- **Grouped Ground** (`canvas`): the page background; pure black in dark mode.
- **Section White** (`card`): grouped sections, inputs, sheets, menus; `#1C1C1E` in dark mode.
- **Well** (`well`): segmented-control track, usage-bar track, neutral pill ground.
- **Sidebar Grey** (`sidebar`): the admin sidebar surface; matches the section grey in dark mode.
- **Segment** (`segment`): the selected segment's raised face (white in light, a lifted `#636366` in dark).
- **Hairlines** (`line`, `line-soft`, `line-input`): `line-soft` separates rows and outlines sections; `line` divides chrome (sidebar footer) and inner panels; `line-input` strokes fields and checkboxes.

### Named Rules
**The One Accent Rule.** UI accents are blue or neutral, nothing else. Primary action, focus, links and icons are blue; selection is a neutral tint; a chart with one series is blue. Teal, cyan and indigo exist only to separate categories.

**The Solid Variant Rule.** White text sits only on a `-solid` fill (`blue-solid`, `orange-solid`, `danger-solid`), never on the base hue. The base hue is for dots, bars, outlines and icons.

**The Tint-Ink-Dot Rule.** Status is always tint ground, matching ink text and a base-hue dot. Never colour a whole card or a large figure by status.

**The Spend Threshold Rule.** Usage bars are blue below 80%, orange from 80%, red from 95%.

## Typography

**Display Font:** System stack (SF Pro where available; Segoe UI, Roboto, Helvetica Neue, Arial fallback)
**Body Font:** Same system stack
**Label/Mono Font:** `ui-monospace` / SF Mono / Menlo / Consolas for key prefixes, IDs, audit actions and URLs

**Character:** The platform's own type, so the page feels like part of the operating system. Hierarchy comes from size and weight steps, never from a second family, uppercase or letter-spaced labels.

### Hierarchy
- **Large Title** (700, 28px, 1.25, -0.02em): one per page, in the page header and on sign-in.
- **Figure** (600, 38px, -0.02em, tabular): the budget-left or spent-so-far number on My key; the page's one dominant fact.
- **Metric** (600, 26px, -0.01em, tabular): metric tiles; 24px in personal analytics summaries.
- **Headline** (600, 22px, -0.01em): sub-sections and the team name on the user page.
- **Brand** (600, 17px, -0.01em): the product name beside the mark; also the large user-page action label and the sign-in card title.
- **Title** (600, 15px): grouped-section titles. Page descriptions use 15px regular in Quaternary Label, capped at 48rem.
- **Body** (400, 14px): default UI text, buttons, nav items, inputs.
- **Subhead** (500, 13px): field labels, metric captions, small buttons, secondary detail lines, table cells for secondary data.
- **Caption** (500, 12px): column heads, pills, segment labels in the compact control, chart-centre labels.
- **Group Label** (600, 12px, sentence case): sidebar group headings.

### Named Rules
**The 12px Floor Rule.** No text is set below 12px. Caption and group labels are the smallest steps; anything that wants to be smaller is cut or moved into a tooltip.

**The Sentence Case Rule.** Every label, heading and group title is sentence case at normal tracking. Hierarchy is size and weight.

**The Tabular Figures Rule.** Money, counts and percentages that sit in tiles or figures use tabular numerals so they align and do not jitter on refresh.

## Layout

Two frames share one content language.

- **User frame** (ordinary users): a sticky translucent top bar (card at 80% with backdrop blur and saturation, hairline bottom) holding the brand and a few text links; content in a centred column capped at 1080px, 16px side gutters growing to 32px from the small breakpoint, 36px top and 56px bottom padding.
- **Admin frame** (owners and admins): a 236px light sidebar, full height with its own scroll, beside a scrolling content column capped at 1152px, 28px top padding. Below the medium breakpoint (768px) the sidebar collapses into a top block whose nav becomes a horizontally scrolling row that keeps the current item in view.
- **Sign-in**: a single centred 360px column with a 28px gap rhythm.

Every page opens with the large-title header (title, one-line description, actions right-aligned and wrapping, 14px gap), then its primary grouped section. Lists live flush inside their section: rows run edge to edge under the section header, separated by `line-soft` hairlines, with no box nested inside the box. Related facts (a person's details, a key's properties) are one grouped section of hairline rows, not a grid of separate cards. Wide tables keep a fixed-width trailing actions track (the Teams table reserves 17rem) so buttons align down the column and the table scrolls horizontally on narrow screens rather than wrapping actions. Spacing follows a 4px grid; the working steps are 8px and 12px inside controls and rows, 16px to 20px for section padding.

## Elevation & Depth

Near-flat. Sections sit on the grouped ground by tonal contrast and a hairline border, not shadow. In dark mode depth is tonal: black ground, `#1C1C1E` sections, `#2C2C2E` wells. Shadow is reserved for things that physically float above the page or are pressed out of a track.

### Shadow Vocabulary
- **Segment lift** (`box-shadow: 0 1px 2px rgb(0 0 0 / 0.12), 0 0 0 0.5px rgb(0 0 0 / 0.04)`): the selected segment in a segmented control.
- **Mark lift** (`box-shadow: 0 1px 2px rgb(0 0 0 / 0.15)`): the small blue brand tile.
- **Popover** (`box-shadow: 0 10px 30px rgb(0 0 0 / 0.16), 0 1px 3px rgb(0 0 0 / 0.08)`): the account menu, with card at 95% and a strong backdrop blur.
- **Sheet** (`box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25)`): modal sheets over a 30% black scrim with a 2px backdrop blur.
- **Tooltip** (`box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`): chart tooltips.

### Named Rules
**The Floats-Only Rule.** Only menus, sheets, tooltips, selected segments and the brand tile cast shadows. Grouped sections, metric tiles, inputs and sidebar rows are flat.

## Shapes

Continuous, gently rounded corners scaled to the size of the object: 3px for legend swatches and thin report bars, 6px for small buttons, sidebar and menu rows, 7px for segments and the brand tile, 8px for buttons and inputs, 10px for the segmented-control track and inner panels, 12px for grouped sections, metric tiles, callouts and menus, 16px for sheets. Pills, avatars, status dots and usage bars are fully round. Borders are single hairlines (`line-soft` on surfaces, `line-input` on fields); no double strokes, no heavy outlines. Legend and colour keys are drawn shapes (a 9px square at 3px radius, or a 10px round dot), never text glyphs.

## Components

### Buttons
Apple's three button weights: filled for the one main action, grey for the rest, plain accent text for low emphasis.
- **Shape:** gently rounded (8px), 40px minimum height, 16px side padding, 14px medium label, 8px icon gap.
- **Primary:** Filled Blue with white text. Hover brightens to 110%; press dims to 95%.
- **Secondary:** Label colour at 6% as the ground, Label text; hover deepens to 10%.
- **Ghost:** Blue Ink text on nothing; Blue Wash on hover.
- **Danger:** `danger-solid` with white text, same behaviour as primary.
- **Small:** 32px tall, 6px radius, 12px padding, 13px label; grey or red-tint variants for row actions.
- **Large (user page only):** the regenerate / create-key action on My key is 52px tall, 12px radius, 17px semibold, full width in its section.
- **Disabled:** 40% opacity, not-allowed cursor. Transitions are 150ms on background, filter and opacity.

### Chips / Pills
- **Style:** fully round, 12px medium text, 10px side padding, transparent border, with a 6px leading dot in the base hue.
- **State:** five tones (ok, warn, bad, info, neutral) drawn from the Tint-Ink-Dot Rule; neutral uses Well and Tertiary Label.

### Cards / Containers (grouped sections)
- **Corner Style:** 12px.
- **Background:** Section White on the Grouped Ground.
- **Shadow Strategy:** none (Floats-Only Rule).
- **Border:** `line-soft` hairline.
- **Internal Padding:** header row 12px by 20px with a hairline underneath and a 15px semibold title; rows separated by hairlines, the last row without one. Lists and tables sit flush inside, clipped to the radius.
- **Metric tile:** same container, 16px by 18px padding, 13px caption, 26px tabular figure, 13px detail line. Only the Organization summary uses tiles, and only from the `sm` breakpoint; on phones the same figures are one grouped list (label and detail left, 17px figure right). Status checks, My key details and usage-report figures are always label/value rows, never tiles.
- **Filter chips:** a row of fully round 32px chips above a list (Keys status: All, Active, Blocked). Selected chip is blue tint with blue ink and shows the list's total; others are grey (`ink` at 6%) with no count, so no extra requests are made just to count.
- **Breadcrumb:** a 13px path above the large title when a group is open (Organization › Engineering › Infrastructure). Earlier steps are plain buttons that open that level; the current step is medium weight `ink` with `aria-current`. Separators are 13px chevrons in `ink-5`.
- **Row actions:** small buttons at the end of each row, destructive action last in the small danger style (Teams Delete, People Disable).
- **Callout:** same 12px radius, tone tint ground, 12px by 16px padding, 14px text, optional semibold title.

### Inputs / Fields
- **Style:** 40px tall, 8px radius, `line-input` stroke, Section White ground, 14px text, Quaternary Label placeholder. Labels sit above in 13px medium Secondary Label with a 6px gap.
- **Focus:** stroke turns System Blue plus a 3px blue ring at 25%.
- **Disabled:** 60% opacity.
- **Checkbox:** custom 16px box with a 5px radius and `line-input` stroke; checked fills Filled Blue with a white check; 2px blue focus outline offset 2px; falls back to native rendering under forced colours.

### Navigation
- **Admin sidebar:** Sidebar Grey, 236px, right hairline. Brand at top; 12px semibold sentence-case group labels in Quaternary Label; rows 14px Label text with a 16px System Blue icon, 6px radius, hover at 5% Label. The selected row is a neutral tint (Label at 9%) with medium-weight Label text; the icon stays blue. Status dots (green or red) may trail a row. Theme toggle and account sit at the bottom above a `line` hairline.
- **User top bar:** translucent, sticky, text links in Tertiary Label with a 6% hover ground.
- **Account menu:** avatar trigger; popover with 12px radius, Popover shadow and blur; 36px items highlight in Filled Blue with white text on hover and keyboard focus, the macOS menu idiom. Full arrow-key, Home/End and Escape handling.
- **Mobile:** sidebar nav becomes a horizontal scrolling row; the account menu and theme toggle move to the top-right.

### Segmented Control (signature)
- A Well track (10px radius, 4px inset) holding equal-weight segments (7px radius, 36px tall, 14px medium). The selected segment is the raised `segment` face with Segment lift and Label text; unselected segments are Tertiary Label, turning Label on hover. Uses `aria-pressed`. The compact demo variant uses a 6% Label track, 2px inset and 12px labels.

### Sheet
- Centred modal: 16px radius, Section White, `line-soft` border, 20px to 24px padding, Sheet shadow over a 30% black scrim with a light blur, capped at 90vh with its own scroll.

### Usage Bar and Charts
- **Usage bar:** a 6px fully round Well track with a fill coloured by the Spend Threshold Rule, width animating over 300ms.
- **Single-series bars:** spend, requests and tokens bars are System Blue on a rounded track.
- **Donut:** 14px stroke rings (18px on the hovered slice, others fade to 35%) in the categorical cycle; centre shows the hovered slice or the total; legend rows use drawn round swatches, 13px labels and a share in Quaternary Label.

## Do's and Don'ts

### Do:
- **Do** use the large-title header (28px bold, -0.02em) at the top of every page with the primary grouped section directly beneath.
- **Do** give each screen at most one Filled Blue primary button; everything else is grey or ghost.
- **Do** put content in white 12px-radius grouped sections with `line-soft` hairlines on the Grouped Ground, with lists flush inside.
- **Do** mark the current sidebar row with the neutral 9% Label tint and keep its icon blue.
- **Do** use the segmented control for switching views or scopes within a page.
- **Do** express status as tint ground, ink text and a base-hue dot, in green, orange or red only; sync problems are orange.
- **Do** colour single-series charts blue and reserve teal, cyan and indigo for categorical series.
- **Do** define every new colour as an RGB channel pair in both `:root` and `html.dark` and map it through the Tailwind config.
- **Do** use tabular numerals for money, counts and percentages in tiles and figures.
- **Do** keep 4.5:1 text contrast in both themes and a visible blue focus treatment on every control.

### Don't:
- **Don't** bring back the dark navy admin rail or coloured stat cards; the sidebar is light and tiles are white.
- **Don't** fill the selected sidebar row with solid blue; selection is neutral.
- **Don't** put white text on a base hue; use the `-solid` variant.
- **Don't** use teal, cyan or indigo for actions, selection, status or a single-series chart.
- **Don't** set any text below 12px.
- **Don't** nest a bordered box inside a grouped section, or split related facts into a grid of separate cards.
- **Don't** draw legend swatches with text glyphs; draw the shape.
- **Don't** use uppercase or letter-spaced labels, eyebrows or kickers above titles.
- **Don't** add shadows to grouped sections, tiles, inputs or sidebar rows.
- **Don't** introduce a web font; the system stack is the brand.
