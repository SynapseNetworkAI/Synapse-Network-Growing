# Design System Specification: The Sovereign Command

## 1. Overview & Creative North Star
The "Sovereign Command" is the creative North Star for this design system. In the context of mission-critical AI Operations, the UI must transcend the "standard dashboard" and move into the realm of a high-end digital cockpit. It is designed to feel authoritative, precise, and deterministic.

Unlike traditional SaaS products that rely on friendly rounded corners and bright fills, this system embraces a **Terminal-Modern** aesthetic. It breaks the "template" look through:
*   **Intentional Asymmetry:** Data-heavy streams balanced against expansive, quiet control panels.
*   **Tonal Depth:** Moving away from flat surfaces to a "layered glass" architecture.
*   **The Technical Boundary:** A deliberate typographic split between human-readable UI (Sans-Serif) and machine-readable reasoning (Monospace).

This is not a platform for casual browsing; it is a high-trust environment for managing autonomous systems.

---

## 2. Colors & Surface Architecture
The palette is rooted in the deep obsidian of a terminal, punctuated by surgical strikes of high-visibility color.

### The "No-Line" Rule
Standard 1px solid borders are strictly prohibited for sectioning. In this system, boundaries are defined by **background shifts** or **tonal transitions**. Structure is created through the relationship between `surface_container_lowest` (#0b0e14) and `surface_container_low` (#191c22).

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers.
*   **Base Layer:** `surface` (#10131a).
*   **Secondary Content:** `surface_container_low` (#191c22).
*   **Interactive/Elevated Modules:** `surface_container_high` (#272a31).
Nesting an inner container (e.g., a log viewer) should use a lower tier than its parent to create a "recessed" or "carved" look, suggesting depth without shadows.

### The "Glass & Gradient" Rule
To achieve a premium, technical "soul," utilize Glassmorphism for floating elements (modals, popovers, or active agent states).
*   **Execution:** Use `surface_container` with a 70-80% opacity and a `20px` backdrop-blur.
*   **Signature Textures:** Main CTAs or mission-critical "Go" gates should utilize a subtle linear gradient from `primary` (#adc6ff) to `primary_container` (#4d8eff) at a 135-degree angle.

---

## 3. Typography
Typography is the primary tool for distinguishing between "System Command" and "Agent Reasoning."

*   **Human-UI (Inter):** Used for all labels, navigation, and headline elements.
    *   *Creative Tip:* Use `display-lg` for high-level system health metrics to create a sense of scale. Use `label-sm` for metadata to maintain a clean, professional density.
*   **Machine-Data (JetBrains Mono):** Reserved for YAML specs, real-time logs, and "Blackboard" data.
    *   *The Editorial Mix:* Pair a `headline-sm` in Inter with a sub-label in JetBrains Mono to create a "technical datasheet" aesthetic.

---

## 4. Elevation & Depth
We eschew traditional material shadows in favor of **Tonal Layering** and **Ambient Glows.**

### The Layering Principle
Depth is achieved by "stacking." A card should not "float" with a shadow; it should exist as a `surface_container_highest` block sitting on a `surface_dim` background. This creates a soft, natural lift.

### Ambient Shadows & Light
When a floating effect is mandatory (e.g., a critical alert modal), use an **Ambient Glow**:
*   **Shadow Color:** A tinted version of the `primary` color at 5-8% opacity.
*   **Shadow Specs:** 0px offset, 40px blur. This mimics the light emitted from a high-resolution terminal screen.

### The "Ghost Border" Fallback
If a border is required for accessibility, it must be a "Ghost Border." Use the `outline_variant` token (#424754) at **15% opacity**. Never use 100% opaque, high-contrast borders; they clutter the precise technical aesthetic.

---

## 5. Components

### Buttons
*   **Primary:** High-visibility `primary` (#adc6ff). Use a `sm` (0.125rem) corner radius for a sharp, technical feel. On hover, apply a subtle `primary` outer glow (4px blur).
*   **Secondary:** Outline-only using the Ghost Border technique.
*   **Tertiary:** Text-only in `on_surface_variant`, shifting to `on_surface` on hover.

### The Reasoning Card (Custom Component)
For AI "Agent Reasoning" blocks, use a `surface_container_lowest` background with a `secondary` (#4edea3) left-accent bar (2px wide). Typography inside must be JetBrains Mono. This signals to the user that they are looking at "raw" intelligence rather than static UI.

### Chips & Status Indicators
*   **Active Agent State:** Use a `secondary` (#4edea3) chip with a 1px "Ghost Border." Add a pulsing 2px dot of `secondary_fixed` to indicate live computation.
*   **Risk Gates:** `tertiary` (#ffb95f) background with `on_tertiary` text. These must be sharp-edged (`none` or `sm` radius) to feel like a warning sign.

### Input Fields
Avoid the "boxed" look. Use a `surface_container_low` fill with a bottom-only border of `outline_variant` at 40% opacity. When focused, the bottom border should transition to `primary` with a subtle vertical gradient fill.

### Cards & Lists
**Forbid the use of divider lines.** Separate list items using vertical white space (8px or 16px) or by alternating background tints between `surface_container_low` and `surface_container`.

---

## 6. Do's and Don'ts

### Do
*   **DO** use JetBrains Mono for any value that changes in real-time (telemetry).
*   **DO** use intentional asymmetry; align your primary controls to the left and your monitoring logs to the right.
*   **DO** lean into "Breathing Room." Mission-critical data requires space to be interpreted correctly.

### Don't
*   **DON'T** use `full` (9999px) rounded corners except for very specific status dots. It softens the "authoritative cockpit" vibe too much.
*   **DON'T** use pure white (#FFFFFF) for text. Use `on_surface` (#e1e2eb) to reduce eye strain in dark environments.
*   **DON'T** use standard "Drop Shadows." If it needs to pop, use a tonal shift or a tinted glow.
*   **DON'T** use 1px solid, opaque borders. They are the enemy of this system's "Terminal-Modern" sophistication.