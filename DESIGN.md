---
name: ConfEdit
description: Precise, low-distraction configuration object management for internal teams.
colors:
  brand-cinema-red: "oklch(0.52 0.16 5)"
  brand-cinema-red-hover: "oklch(0.46 0.15 5)"
  action-blue: "oklch(0.50 0.16 255)"
  action-blue-hover: "oklch(0.44 0.15 255)"
  canvas: "oklch(1 0 0)"
  surface: "oklch(0.985 0.004 255)"
  sidebar: "oklch(0.965 0.008 255)"
  ink: "oklch(0.23 0.025 255)"
  muted-ink: "oklch(0.47 0.025 255)"
  border: "oklch(0.88 0.012 255)"
  selected: "oklch(0.92 0.045 255)"
  success: "oklch(0.55 0.12 145)"
  warning: "oklch(0.68 0.14 78)"
  danger-soft: "oklch(0.95 0.035 5)"
typography:
  headline:
    fontFamily: '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
    fontSize: "1rem"
    fontWeight: 650
    lineHeight: 1.35
  body:
    fontFamily: '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"Segoe UI Variable", "Segoe UI", system-ui, sans-serif'
    fontSize: "0.8125rem"
    fontWeight: 600
    lineHeight: 1.35
  code:
    fontFamily: '"Cascadia Code", "SFMono-Regular", Consolas, monospace'
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "9px 14px"
  button-danger:
    backgroundColor: "{colors.brand-cinema-red}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.sm}"
    padding: "9px 14px"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
  file-navigation:
    backgroundColor: "{colors.sidebar}"
    textColor: "{colors.ink}"
    width: "240px"
  editor-drawer:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    width: "min(620px, 100vw)"
---

# Design System: ConfEdit

## Overview

**Creative North Star: "The Review Bench"**

ConfEdit feels like an office code-review bench in clear daylight: every file, object and diagnostic has a known place, and nothing competes with the work. The system uses a restrained light product register because colleagues read dense JSON and SQL for sustained periods on ordinary Windows displays.

The approved structure is a persistent file sidebar, a dominant object list and a right-side editor drawer. Familiar controls, crisp tonal separation and exact status copy create trust. The interface explicitly rejects terminal cosplay, generic SaaS card grids, purple gradients, glassmorphism and decorative motion.

**Key Characteristics:**

- Dense but calm file and object navigation.
- Strong hierarchy without oversized typography.
- Familiar controls with complete hover, focus, disabled, loading and error states.
- Motion limited to 180–220 ms state transitions.
- Red is rare; blue carries ordinary primary actions.

## Colors

The palette is cool-neutral and restrained. Pure white keeps long code sessions clear; blue marks current work and primary action; the cinema-red seed appears only as a small brand signature, destructive action or explicit error.

### Primary

- **Cinema Red:** the brand anchor and destructive-action fill. It never decorates inactive surfaces.

### Secondary

- **Review Blue:** primary buttons, links, selected rows and focus affordances.

### Neutral

- **Clear Canvas:** the main reading and editor surface.
- **Cool Sidebar:** file navigation and quiet secondary regions.
- **Deep Review Ink:** all primary text and data.
- **Steel Muted Ink:** secondary copy that still meets product contrast requirements.
- **Quiet Border:** separators and field outlines; never used as a thick accent stripe.

### Named Rules

**The Rare Red Rule.** Red occupies less than five percent of a normal screen and always communicates brand, danger or error.

**The One Action Rule.** Blue is the only ordinary action color. Inactive controls stay neutral.

## Typography

**Display Font:** Segoe UI Variable with system-ui fallbacks

**Body Font:** Segoe UI Variable with system-ui fallbacks

**Label/Mono Font:** Cascadia Code with Consolas fallback for source editors

**Character:** One familiar Windows-native sans keeps the tool invisible and dependable. Monospace is reserved for JSON, SQL, hashes and diffs.

### Hierarchy

- **Headline** (700, 1.375rem, 1.25): current file title and dialog titles.
- **Title** (650, 1rem, 1.35): object names, navigation groups and section headings.
- **Body** (400, 0.9375rem, 1.5): descriptions, diagnostics and controls.
- **Label** (600, 0.8125rem, 1.35): field labels, status metadata and compact actions.
- **Code** (400, 0.875rem, 1.55): JSON, SQL and unified diffs.

### Named Rules

**The Fixed Scale Rule.** Product typography uses fixed rem sizes; no fluid clamp headings and no display font in labels or buttons.

## Elevation

The system is flat by default. Sidebar, toolbar and content separate through tonal layers and one-pixel borders. Shadows appear only when an element leaves the document flow: the editor drawer, confirmation dialog, toast or raised hover state.

### Shadow Vocabulary

- **Drawer Lift:** 0 18px 60px color-mix(in oklch, black 18%, transparent), used only on the editor and history drawer.
- **Control Lift:** 0 4px 14px color-mix(in oklch, black 10%, transparent), used for menus and toasts.

### Named Rules

**The Flat-at-Rest Rule.** Lists, toolbars and panels never carry decorative shadows.

## Components

### Buttons

- **Shape:** compact, gently rounded rectangles (6px).
- **Primary:** Review Blue with white text and 9px 14px padding.
- **Hover / Focus:** darker blue on hover; a two-pixel blue focus ring with a white offset.
- **Secondary:** white or transparent surface with a quiet border.
- **Danger:** Cinema Red with white text, used only after the target is named.

### Chips

- **Style:** pale semantic background, dark semantic text, no all-caps tracking.
- **State:** always paired with readable status text such as “有效”, “只读” or “存在冲突”.

### Cards / Containers

- **Corner Style:** medium rounding (10px) only for dialogs, diagnostic panels and true grouped containers.
- **Background:** Clear Canvas or Cool Sidebar.
- **Shadow Strategy:** flat at rest; drawer lift only when floating.
- **Border:** one-pixel Quiet Border.
- **Internal Padding:** 12–16px.

### Inputs / Fields

- **Style:** white background, one-pixel quiet border, 6px radius.
- **Focus:** Review Blue border plus visible focus ring.
- **Error / Disabled:** errors use soft red background plus text and icon; disabled fields retain readable text.

### Navigation

The 240px file sidebar groups JSON and SQL without card tiles. Rows are full-width buttons with a clear selected fill, type badge and status. Below 900px it collapses behind a standard menu button; typography does not scale fluidly.

### Editor Drawer

The drawer uses native dialog semantics, occupies min(620px, 100vw), and becomes full-screen below 900px. JSON shows one code editor; SQL uses standard tabs for CREATE and INSERT. Validation and dirty state remain visible near the save action.

## Do's and Don'ts

### Do:

- **Do** keep the current file, current object and validation result visible.
- **Do** use Review Blue for ordinary primary actions and selection.
- **Do** name the target in delete and rollback confirmations.
- **Do** use status text and icons in addition to semantic color.
- **Do** preserve a visible keyboard focus ring on every control.

### Don't:

- **Don't** build a “terminal role-playing” all-black developer interface.
- **Don't** turn the object list into a grid of identical SaaS cards.
- **Don't** use purple gradients, glassmorphism, neon glow or decorative motion.
- **Don't** use Cinema Red for normal navigation or save actions.
- **Don't** use border-left or border-right greater than 1px as a colored accent stripe.
- **Don't** invent custom form, modal or navigation behavior where a standard control exists.
