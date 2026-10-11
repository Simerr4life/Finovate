# Settings

![Settings annotated](assets/screenshots/annotated/settings-profile-annotated.png)

![Dark theme preview](assets/screenshots/raw/theme-dark-mode.png)

## Location

`/accounts/settings/`

## Controls

| Area | Fields / actions |
|---|---|
| Preferences | Income cadence, risk comfort, cash reserve target, budget warning % |
| Theme | `light` / `dark` / `system` → `data-theme` on html/body |
| Notifications | Toggles for budget warnings, goal milestones, simulated orders |
| Messaging | Issue / unlink Photon link code |
| Connected accounts | Placeholders (bank/brokerage) — status only |
| Notification events | In-app recorded list |

## Persistence

Saved on `accounts.Profile`. Theme applies immediately via template context.
