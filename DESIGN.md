---
name: ALTA Operator Console
description: A quiet instrument-grade workspace for live opportunity flow and durable research decisions.
colors:
  accent-blue: "#3067e8"
  accent-blue-soft: "#e9eefc"
  accent-blue-ink: "#244fbb"
  canvas: "#f3f4f2"
  surface: "#ffffff"
  surface-muted: "#eceeeb"
  ink: "#171918"
  muted-ink: "#626862"
  line: "#dfe3e1"
  evidence-plane: "#171a19"
  success: "#277456"
  destructive: "#bd3a50"
typography:
  display:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
    fontSize: "clamp(25px, 2.25vw, 38px)"
    fontWeight: 580
    lineHeight: 1
    letterSpacing: "-0.045em"
  headline:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
    fontSize: "19px"
    fontWeight: 590
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
    fontSize: "13px"
    fontWeight: 620
    lineHeight: 1.35
  body:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
    fontSize: "11px"
    fontWeight: 450
    lineHeight: 1.45
  label:
    fontFamily: "Geist Variable, -apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
    fontSize: "10px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "0.08em"
  mono:
    fontFamily: "SFMono-Regular, Consolas, monospace"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: "8px"
  md: "11px"
  lg: "14px"
  xl: "17px"
  panel: "22px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  2xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.surface}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "32px"
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 10px"
    height: "32px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
    height: "32px"
  status-pill:
    backgroundColor: "rgba(255, 255, 255, 0.75)"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0 8px"
    height: "24px"
  operating-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "20px"
  navigation-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "0 12px"
    height: "42px"
---

## Design System: ALTA Operator Console

## Overview

### Creative North Star: “The Quiet Instrument Desk”

ALTA is a calm, evidence-first operating environment rather than a decorative market terminal. Its pale neutral workspace behaves like a precise physical instrument: hierarchy comes from position, scale, and material contrast, while saturated color is reserved for selection, motion, and operator action.

The visual system joins two complementary modes. The live opportunity field uses matte white surfaces, thin cool-gray boundaries, and ordered horizontal handoffs to make the research lifecycle legible. The evidence inspector forms a persistent dark plane where decision packets, assessments, provenance, and normalized records can be read as durable institutional memory.

**Key Characteristics:**

- Restrained neutral canvas with matte white working surfaces.
- One blue interaction voice used for selection, progress, and operator action.
- Dense but readable information, built from compact labels and generous panel-level spacing.
- A fixed dark evidence plane that visually separates durable records from live operations.
- Responsive re-composition that preserves the lifecycle order rather than shrinking the desktop topology.

## Colors

The palette is intentionally narrow: warm-neutral operational surfaces, near-black evidence, and a single clear blue punctuation color.

### Primary

- **Signal Blue:** The sole saturated interaction color. Use it for primary controls, active icons, selected tabs, focus outlines, timeline progress, and live handoff motion.
- **Signal Blue Wash:** A quiet selection and icon background that supports Signal Blue without competing with content.
- **Signal Blue Ink:** The darker blue used when blue must carry text on a pale surface.

### Secondary

- **Verified Green:** Communicates ready, live, validated, and research-safety states, always paired with a text label, icon, or both.
- **Controlled Rose:** Reserved for destructive controls, stopped or failed states, and recoverable action errors.

### Neutral

- **Instrument Canvas:** The application ground. It keeps the workspace distinct from white panels without looking tinted or decorative.
- **Matte Surface:** The default card, toolbar, selected-navigation, input, and dialog surface.
- **Soft Equipment Gray:** Used for recessed controls, rail backgrounds, grouped metrics, and subdued interactive regions.
- **Primary Ink:** The main text and brand-mark color.
- **Muted Ink:** Secondary metadata and quiet contextual text; operational facts must remain above the implemented readability floor.
- **Hairline:** The shared border, divider, and input-stroke color.
- **Evidence Plane:** The inspector background and the strongest material contrast in the interface.

### Named Rules

**The One Signal Rule.** Blue is the only general-purpose accent; green and rose remain semantic state colors and never become decorative alternatives.

**The Evidence Plane Rule.** Durable record detail belongs on the dark plane, while live topology and controls remain on pale operating surfaces.

**The State Has Words Rule.** Health, safety, failure, and selection are never communicated by color alone.

## Typography

**Display Font:** Geist Variable (with Apple system sans-serif fallbacks)

**Body Font:** Geist Variable (with Apple system sans-serif fallbacks)
**Label/Mono Font:** Geist Variable for labels; SFMono-Regular or Consolas for normalized records

**Character:** The single sans-serif family is compact, lucid, and slightly technical without becoming mechanical. Tight display tracking gives high-level views authority; tabular numerals and small, disciplined labels keep operational data aligned.

### Hierarchy

- **Display:** Used for the current workspace statement. It is fluid on desktop and resolves to a fixed 27px on mobile.
- **Headline:** Used for major panel and inspector titles; it stays concise and close to its supporting metadata.
- **Title:** Used for opportunity names and other high-value record labels inside cards.
- **Body:** Used for facts, summaries, and control labels. Dense regions use the compact end of the scale, but saved facts and explanatory copy retain comfortable line spacing.
- **Label:** Used for status pills, stage labels, categories, and metadata. Uppercase and tracked treatment is limited to short state or structural labels.
- **Mono:** Used only for normalized JSON and machine-shaped records, never as a general “trading terminal” texture.

### Named Rules

**The Operational Readability Rule.** Compact type may organize metadata, but decision facts, status, and explanatory copy must meet the established 10–11px readability floor.

**The Sentence Before Symbol Rule.** Important opportunities and decisions are named in plain language; identifiers, timestamps, and status labels support that title rather than replacing it.

## Layout

Desktop uses a three-plane shell: a 174px navigation rail, a flexible central workspace, and a fixed 344px evidence inspector beneath a 72px top bar. The rail can collapse to 74px, while the central field remains the visual priority. Major workspace panels use 20–24px internal rhythm and 14–26px separation from surrounding content.

The live field is a directed four-stage topology—Discovery, Foundry, Committee, and Expression & Audit—with narrow connector columns between stages. Cards stack vertically inside stages and maintain clear handoff order. The replay ribbon sits below the current field, reinforcing that live state and durable history are two views of the same event ledger.

At 1350px the rail collapses and the inspector narrows. At 1050px the evidence inspector moves below the workspace and the field becomes a two-column matrix. At 760px the shell becomes a continuous vertical page: the top bar fixes at 62px, navigation becomes a horizontally scrollable strip, and a four-option stage selector shows one lifecycle stage at a time. This is a structural re-composition, not a scaled-down desktop canvas.

**The Lifecycle Order Rule.** Responsive layouts may change the number of visible stages, but the discover → foundry → committee → audit sequence stays explicit and navigable.

**The Persistent Context Rule.** Runtime control and primary navigation remain reachable while the operator moves through live and historical content.

## Elevation & Depth

The system uses a hybrid of tonal layering, hairline boundaries, and soft ambient lift. Large white work surfaces float gently above the canvas; nested information cards use shallower shadows or borders. The dark evidence plane is separated by material contrast rather than by a cast shadow.

### Shadow Vocabulary

- **Panel Ambient:** `0 20px 60px rgba(33, 40, 36, 0.08), 0 2px 10px rgba(33, 40, 36, 0.04)` for the primary opportunity field and stopped-state panels.
- **Card Ambient:** `0 8px 22px rgba(35, 41, 37, 0.055)` for selectable opportunity cards.
- **Selected Blue Lift:** `0 10px 26px rgba(48, 103, 232, 0.10)` for a hovered or selected opportunity.
- **Navigation Lift:** `0 4px 16px rgba(39, 45, 41, 0.07)` for the active item on the recessed rail.

### Named Rules

**The Ambient Not Dramatic Rule.** Shadows describe surface separation and selection; they stay diffuse, low-opacity, and vertically restrained.

**The Selection Earns Lift Rule.** Stronger blue-tinted elevation appears only when an interactive record is hovered or selected.

## Shapes

The form language is softly machined: small controls use 8–11px corners, record cards use 12–14px corners, supporting panels use 17px corners, and major work surfaces use 22px corners. Pills are fully rounded. Borders are thin and cool; dashed boundaries are reserved for audit limits, preview posture, or empty capacity.

Circular geometry is functional rather than ornamental: six-pixel dots indicate live or waiting state, the brand mark maps an asterism with three points, and timeline nodes mark durable events.

**The Nested Radius Rule.** Corner radius increases with structural scale: controls < records < panels. Nested surfaces must not match or exceed the radius of their parent.

**The Dashed Boundary Rule.** Dashed strokes mean provisional, bounded, or unfilled—not ordinary grouping.

## Components

### Buttons

- **Shape:** Compact controls use gently curved 8–11px corners; icon-only controls retain the same family.
- **Primary:** Signal Blue with white text, used for the affirmative runtime action and other singular high-priority commands.
- **Hover / Focus:** Hover changes tone rather than shape. Keyboard focus uses a 2px Signal Blue outline with 2px offset; active buttons move by one pixel when appropriate.
- **Secondary / Ghost / Destructive:** Outline controls sit on white; ghost controls reveal a muted surface on hover; destructive controls use a pale rose treatment and remain visually subordinate until needed.

### Chips

- **Style:** Status pills use a translucent white surface, subtle neutral border, compact uppercase label, and a leading state dot.
- **State:** Healthy states use Verified Green, failed states use Controlled Rose, and neutral workflow states use Primary Ink. Live animation may pulse, but the label always carries the meaning.

### Cards / Containers

- **Corner Style:** Record cards use medium corners; major work surfaces use the large panel radius.
- **Background:** Matte white is the default. Recessed summaries use Soft Equipment Gray; evidence cards use translucent white over the Evidence Plane.
- **Shadow Strategy:** Primary panels receive ambient lift; nested cards are border-led until hover or selection.
- **Border:** One-pixel Hairline strokes define containment. Selected records shift to a pale blue border.
- **Internal Padding:** Dense records use 10–13px; section headers and primary work surfaces use 16–21px.

### Inputs / Fields

- **Style:** Inputs are 32px high with a white or transparent surface, Hairline stroke, compact horizontal padding, and small-radius corners.
- **Focus:** Border and focus ring shift to Signal Blue with a translucent outer ring.
- **Error / Disabled:** Errors use Controlled Rose for stroke and ring; disabled fields lower opacity and remove interaction.

### Navigation

The desktop rail is a recessed equipment strip with 42px items. The active destination becomes a white lifted surface with Primary Ink and a blue icon; inactive destinations remain muted and reveal a pale surface on hover. On mobile, the rail becomes a horizontally scrollable 54px strip while preserving readable text labels.

### Opportunity Flow

The signature topology presents four semantic stages connected by ordered handoffs. Foundry opportunity cards carry identifiers, plain-language titles, workflow status, and freshness. Committee agents and saved exchanges appear as discrete artifacts rather than as simulated private reasoning. Animated blue handoff dots may traverse connector lines when work is active; reduced-motion settings collapse the animation.

### Evidence Inspector

The inspector is a durable reading surface with Brief, Evidence, and Record tabs. Its near-black ground, quiet white dividers, and desaturated text distinguish saved evidence from current operations. The footer repeats the research-only and capital-disabled boundary, and raw data uses the mono role inside a deeper inset surface.

### Replay Ribbon

The replay ribbon anchors history beneath the live field. It combines a labeled durable-event count, current event readout, blue progress track, time bounds, and a “Live now” control. On mobile it stacks into a single column instead of compressing the timeline.

## Do's and Don'ts

### Do

- **Do** reserve Signal Blue for active selection, focus, progress, and primary operator action.
- **Do** pair every colored status with explicit words, an icon, or both.
- **Do** preserve the pale live-workspace / dark evidence-plane contrast when adding new record detail.
- **Do** keep Opportunity reasoning, assessment, and handoff artifacts visible before carrier or position details.
- **Do** re-compose dense lifecycle views into explicit stage navigation on narrow screens.
- **Do** honor reduced-motion preferences for handoff, loading, and pulse animation.

### Don't

- **Don't** introduce extra accent hues, gradients, or decorative market-chart colors.
- **Don't** use hard offset shadows, heavy borders, glass effects, or glossy finance-terminal chrome.
- **Don't** imply private chain-of-thought; label saved summaries, artifacts, and normalized records honestly.
- **Don't** present Shadow, replay, or simulated outcomes as live trading performance.
- **Don't** collapse stages into an undifferentiated card feed or hide lifecycle order on mobile.
- **Don't** allow decorative density to push operational facts below the established readability floor.
