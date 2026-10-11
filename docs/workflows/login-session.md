# Login and session management

1. User opens `/accounts/login/`
2. Auth0 button/flow or Supabase email POST
3. On success: Django session login (`ModelBackend`); Auth0 sets session flags + cookies via SDK
4. `Auth0SessionMiddleware` may force verify page for unverified Auth0 users
5. `destination_for` routes next
6. Logout clears Django session; Auth0 federated logout when `logged_in_via_auth0`

Rate limit: 20 login attempts / 10 minutes / IP.
