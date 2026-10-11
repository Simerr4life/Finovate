/**
 * Auth0 Post User Registration Action → Finovate signup backup webhook.
 *
 * Secrets (Action settings):
 *   FINOVATE_BACKUP_URL     e.g. https://finovate.biz/accounts/auth0/hooks/signup/
 *   FINOVATE_ACTION_SECRET  same value as Finovate AUTH0_ACTION_SECRET
 *
 * Deployed by scripts/configure_auth0_dashboard.py (or paste into Auth0 UI).
 */
exports.onExecutePostUserRegistration = async (event, api) => {
  const url = event.secrets.FINOVATE_BACKUP_URL;
  const secret = event.secrets.FINOVATE_ACTION_SECRET;
  if (!url || !secret) return;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${secret}`,
    },
    body: JSON.stringify({
      user: {
        user_id: event.user.user_id,
        email: event.user.email,
        email_verified: event.user.email_verified === true,
        name: event.user.name || event.user.nickname || "",
        given_name: event.user.given_name || "",
        family_name: event.user.family_name || "",
        nickname: event.user.nickname || "",
        created_at: event.user.created_at,
        identities: event.user.identities || [],
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`finovate_backup_${response.status}`);
  }
};
