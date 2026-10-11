# Interface

**Last reviewed:** 2026-10-11

## Stack

Server-rendered Django templates + `/static/css/finovate.css` (DM Sans / Manrope via Google Fonts import) + progressive JS (`finovate.js`, live quote pollers, market charts).

## Theme

Profile `theme`: light / dark / system → `data-theme` attribute. Dark capture:

![Dark theme](assets/screenshots/raw/theme-dark-mode.png)

## Navigation

Sidebar desktop; mobile toggle. Brand logo partial `partials/brand_logo.html`.

## Motions / interactions

- Mobile menu open/close
- Review modal (client-side; does not persist a plan)
- Surplus allocation slider / portfolio projection calculator in `finovate.js`
- Chart scrubber on Explore

## Responsive

Desktop and mobile screenshots under `assets/screenshots/`.

![Mobile dashboard](assets/screenshots/mobile/mobile-dashboard.png)
