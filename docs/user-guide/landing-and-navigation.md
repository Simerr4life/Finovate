# Landing and navigation

![Annotated landing page](assets/screenshots/annotated/landing-annotated.png)

## Where to find it

- Public URL: `/`
- Authenticated users are directed into the app (dashboard / post-login destination)

## Interface elements

| Element | Behavior |
|---|---|
| Brand / logo | Product identity (hero-level on landing) |
| Sign in | Navigates to `/accounts/login/` |
| Sign up | Navigates to `/accounts/signup/` |
| Primary CTA | Starts signup / product entry |

## In-app navigation

After login, the left sidebar (desktop) or mobile menu lists Overview, Transactions, Savings, Pools, Investments, Financial Goals, Insights, Settings. Footer status shows “No bank connected” when no live bank integration is present.

![Mobile navigation](assets/screenshots/mobile/mobile-navigation.png)

## Responsive behavior

- Desktop (~1440px): persistent sidebar
- Mobile (~390px): compact header + toggle menu

## Errors / edge cases

- Without Auth0/Supabase configuration, login/signup pages render but cannot complete identity creation (messages instruct configuration / email sign-in availability).
