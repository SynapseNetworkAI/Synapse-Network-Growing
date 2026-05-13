# Frontend Workbench Principles

Load this when touching dashboard UI, page layouts, forms, modals, design tokens, screenshots, frontend tests, or browser validation.

## Enterprise Workbench

1. Frontend must be an Enterprise Workbench, not a flat card dashboard.
2. Cards are for individual objects, not every page section.
3. Pages start with workbench skeleton before components: shell, page header, primary workspace, secondary inspector, activity/feed rail, command bar/filters.
4. Each page has one primary focus. Do not give forms, lists, summaries, status, and logs equal visual weight.
5. Requirement, Execution, and Release use distinct page templates.
6. Color communicates state and emphasis, not large decorative surfaces.
7. Reuse workbench shell, section, inspector, activity feed, and state badge structures.
8. New UI should follow `.agents/skills/ui-ux-pro-max/SKILL.md` SaaS/Ops Console guidance while preserving dark cockpit hierarchy, readable forms, low-noise actions, and clear state badges.

## Modal-First Operations

1. List pages do not host long-lived create/edit forms inline.
2. Create, edit, view, and confirm default to `Toolbar + centered Modal/Dialog`.
3. Drawer, Slide-out, Offcanvas, Side Panel, and right-side slide-out details are legacy debt; do not copy them into new UI.
4. Requirement create captures minimal intent; acceptance is generated after creation and can be revised in details.
5. Do not use browser-native `alert` or `confirm`.
6. Dangerous actions use shared confirm dialog; success/failure feedback uses toast where appropriate.

## Anti-Regression Checks

1. UI PR must state whether the page is Requirement, Execution, or Release surface.
2. UI PR must state whether it reused workbench template and tokens.
3. Dashboard-card mosaic, same-weight white-card layout, decorative chips/pills, or competing focal blocks are review rejection signals.
4. Frontend tokens must support surface hierarchy, text hierarchy, stroke hierarchy, state colors, and layout tokens.
5. Inline long-lived create/edit forms need an explicit quick-edit exception.
6. Main pages must have tests for real interactions: primary buttons, tabs, centered modal, detail jump, or empty state.
7. Browser validation should keep screenshots and concise evidence for visual or E2E claims.
