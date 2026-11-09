---
name: Cart Recovery
description: A restrained operations work surface for recovery decisions and conversion evidence.
colors:
  paper: "#fff"
  surface: "#f5f6f2"
  ink: "#182b24"
  muted: "#54645c"
  line: "#d7dfd8"
  accent: "#176344"
  hover: "#104b33"
  soft: "#e8f2eb"
  warn: "#87521b"
  danger: "#a22a2a"
  warning-surface: "#fbefdc"
  danger-surface: "#fbe9e7"
  field-border: "#a6b7ac"
typography:
  headline:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "-0.015em"
  body:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  supporting:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 600
  metric:
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "30px"
    fontWeight: 650
    letterSpacing: "-0.03em"
rounded:
  tag: "4px"
  field: "6px"
  navigation: "7px"
  control: "8px"
  table: "10px"
  panel: "12px"
spacing:
  compact: "8px"
  small: "12px"
  regular: "16px"
  panel: "24px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.hover}"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "9px 11px"
  status:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.tag}"
    padding: "4px 8px"
  panel:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.panel}"
    padding: "24px"
  navigation-active:
    backgroundColor: "{colors.soft}"
    textColor: "{colors.accent}"
    rounded: "{rounded.navigation}"
    padding: "12px 14px"
---

# Design System: Cart Recovery

## Overview

**Creative North Star: "The Recovery Workbench"**

A restrained off-white and pine operations surface makes decisions and their evidence easy to read. Familiar system typography, compact rows, and steady alignment support repeated inspection rather than visual spectacle.

White containers separate tasks from the warm work surface. Text labels accompany semantic color, and visible focus states keep contextual actions accessible. This system is extracted from the delivered CSS; the earlier provisional notes are reconciled here with its actual values.

**Key Characteristics:**
- Warm work surface with white task containers and pine actions.
- Compact operational typography with tabular numbers.
- Flat bordered surfaces and shallow rounded controls.
- Responsive navigation and locally scrolling data tables.

## Colors

Pine supplies action and selection; warm near-whites and muted green-grays carry the working environment. The frontmatter is the normative palette.

### Primary
- **Pine** (`accent`): primary actions, links, progress bars, and focus outlines.
- **Deep Pine** (`hover`): primary-action and link hover.
- **Pale Pine** (`soft`): selected navigation, ordinary status chips, notes, and secondary-button hover.

### Secondary
- **Amber** (`warn`, `warning-surface`): warning text and its pale backing.
- **Brick** (`danger`, `danger-surface`): errors, adverse statuses, and their pale backing.

### Neutral
- **Paper** (`paper`): navigation, top bar, fields, and task containers.
- **Warm Surface** (`surface`): page background, quiet hover, and evidence-code backgrounds.
- **Pine Ink** (`ink`): primary text and toast background.
- **Sage Gray** (`muted`): supporting copy, dates, labels, and inactive navigation.
- **Divider** (`line`): structural borders and row separators.
- **Field Stroke** (`field-border`): stronger field boundaries.

**The Labeled State Rule.** Status meaning is carried by visible text alongside semantic color.

## Typography

**UI and Body Font:** the system sans stack recorded in the frontmatter. There is no downloaded font or distinct display family.

The typography is familiar and operational. Tabular numerals are applied to times, table cells, and description-list values; numeric columns align right.

### Hierarchy
- **Headline:** page titles; reduces to 24px below 560px.
- **Title:** section headings; compact subheadings use 15px.
- **Body:** the 14px UI base; paragraph copy uses a 1.6 line height, with heading descriptions limited to 68ch.
- **Supporting:** helper copy, table cells, pagination, and footer; table headers and status labels use 11px.
- **Label:** semibold form labels and controls, in sentence case.
- **Metric:** overview values; reduces to 25px below 1100px.

**The Numeric Alignment Rule.** Use tabular numerals for operational values and right-align comparable numeric columns.

## Layout

A fixed white side navigation occupies 232px on desktop; the workspace follows its width. The top bar is 78px tall. Main content has 32px vertical and 36px horizontal padding, a 1600px maximum width, and centered content within the workspace. Sections use a 32px separation; panels and paired-detail grids use 24px padding or gaps.

At 1100px and below, navigation narrows to 205px, main padding becomes 28px 24px, and the asymmetric content columns stack. At 900px and below, navigation becomes an in-flow horizontal scrolling row, the workspace margin disappears, the top bar becomes 58px tall, and detail/quality grids stack. At 560px and below, main padding becomes 24px 16px, headings stack with their actions, metrics use two columns, filters wrap, and panel padding becomes 18px.

Tables scroll within their own rounded containers; their no-wrap cells preserve scanning. Filters and contextual action groups use wrapping flex layouts. Ordered evidence uses timestamp/content rows with separators rather than nested cards.

## Elevation & Depth

The workspace is flat. White surfaces, soft selection fills, and thin dividers convey grouping. Only the floating toast carries a shadow (`0 8px 30px #182b2426`); task panels and tables do not.

**The Work-Surface Rule.** Keep data containers flat and use the floating-toast shadow only for transient feedback.

## Shapes

Controls have gently rounded corners, with the radius roles recorded in the frontmatter. Fields are tighter than buttons, status chips are compact rounded rectangles, and larger containers receive broader corners. Structural boundaries are 1px strokes. Progress tracks are shallow rounded bars, not decorative graphics.

## Components

### Buttons

Compact, semibold controls keep actions close to the decision. Primary buttons use pine and paper; secondary buttons use paper with a divider border; quiet buttons are transparent. Standard buttons are at least 40px high. Inline table actions use a denser 32px minimum height and 12px type. Hover changes the fill over 150ms. Disabled buttons use half opacity and a waiting cursor.

### Inputs / Fields

White fields have a stronger sage stroke, a 42px minimum height, and compact padding. Labels sit above them. Textareas and evidence content wrap within available space. All interactive controls share a 3px pine focus outline with a 3px offset.

### Chips

Text-bearing chips use 11px semibold type, compact padding, and no wrapping. Normal, warning, and adverse states pair the corresponding text and background colors. These are status indicators rather than primary actions.

### Cards / Containers

White panels use a thin divider border, panel radius, and panel padding. Table containers use their own slightly tighter radius and overflow region. Metric summaries use open columns bounded by horizontal rules rather than individual cards.

### Navigation

Muted semibold links sit on white; active links use pale pine with pine text. Hover uses the warm surface. Desktop navigation is vertical; the mobile row preserves labels and scrolls horizontally as needed.

### Data Tables and Evidence

Tables use 14px by 16px cell padding, small muted headers, fine row dividers, and a subtle near-white hover. Timelines and journals separate events with rules and reserve a stable timestamp column. Evidence disclosures use native expand/collapse controls and wrapped, scrollable code content.

### Feedback

Inline errors use brick text and a pale brick background. Toasts float at the lower right with inverse text. Loading feedback pulses a neutral bar over 1.3 seconds. The reduced-motion media query disables animations and transitions.

## Do's and Don'ts

### Do:
- **Do** use text with semantic status colors.
- **Do** preserve tabular numeric alignment in operational data.
- **Do** keep tables inside their own scrolling regions on narrow screens.
- **Do** retain the shared visible focus outline and reduced-motion behavior.
- **Do** use the existing system font stack without external font requests.

### Don't:
- **Don't** add shadows to task panels or data tables.
- **Don't** substitute decorative cards for compact rows of comparable data.
- **Don't** use color alone to distinguish errors, warnings, or selection.
