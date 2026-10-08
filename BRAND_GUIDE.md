# ARC Brand Kit

Monochrome brand assets for Adaptive Resource Contract Engine.

## Brand
- Dark background: `#0B0D10`
- Dark surface: `#121418`
- Raised surface: `#1A1E23`
- Border: `#2A2F36`
- Light foreground: `#F5F7FA`
- Secondary text: `#A0A7B1`
- Muted text: `#6B7280`
- Light theme background: `#F5F7FA`; primary text: `#111318`
- Typography: system sans or Inter for UI; JetBrains Mono or system monospace for technical values. No font binaries included.

## Asset use
- Sidebar/header on dark theme: `arc-logo-horizontal-light.svg` or `arc-mark-light.svg` plus accessible text.
- Sidebar/header on light theme: `arc-logo-horizontal-dark.svg` or `arc-mark-dark.svg`.
- Browser favicon: `favicon.svg`, with `favicon.ico` fallback.
- PWA/icon: `arc-icon-192.png`, `arc-icon-512.png`.
- Vector master: `arc-mark-light.svg` / `arc-mark-dark.svg`.

## Integration
Copy `frontend/public/brand/` from this kit into the repository at the same path.
Use `/brand/arc-logo-horizontal-light.svg` and corresponding dark variant in frontend markup.
Add to `frontend/index.html` (or update existing favicon):
`<link rel="icon" type="image/svg+xml" href="/brand/favicon.svg" />`
`<link rel="alternate icon" href="/brand/favicon.ico" />`

The brand-board PNG is a *visual concept reference*, not the vector source. Vector assets in this kit are a clean geometric interpretation of the same monochrome A-and-sweep motif, not a pixel-exact extraction of the generated board.

No app code is changed by this kit.
