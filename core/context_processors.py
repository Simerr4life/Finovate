from accounts.auth0 import auth0_configured
from accounts.models import ConnectedAccountPlaceholder
from core.display import display_name, user_initials
from investing.services import compute_investable_surplus


NAV_MAP = {
    "dashboard": "overview",
    "insights": "insights",
    "budgets:index": "insights",
    "budgets:transaction_list": "transactions",
    "budgets:transaction_add": "transactions",
    "budgets:transaction_edit": "transactions",
    "budgets:transaction_delete": "transactions",
    "transactions:statement_list": "transactions",
    "transactions:statement_detail": "transactions",
    "imports:history": "transactions",
    "imports:upload": "transactions",
    "imports:choose_account": "transactions",
    "imports:map_columns": "transactions",
    "imports:preview": "transactions",
    "imports:batch_detail": "transactions",
    "savings:index": "savings",
    "savings:pools": "pools",
    "savings:goals": "goals",
    "savings:goal_add": "goals",
    "savings:goal_edit": "goals",
    "savings:goal_detail": "goals",
    "savings:goal_delete": "goals",
    "investing:index": "investments",
    "investing:historical_demo": "investments",
    "investing:market_data": "investments",
    "accounts:settings": "settings",
}


def app_context(request):
    """Expose a few safe, non-secret settings to every template."""
    nav_active = ""
    user_label = ""
    initials = ""
    banks_connected = False
    unread_notifications = 0
    surplus = None
    if getattr(request, "resolver_match", None) and request.resolver_match.view_name:
        nav_active = NAV_MAP.get(request.resolver_match.view_name, "")
    if getattr(request, "user", None) and request.user.is_authenticated:
        user_label = display_name(request.user)
        initials = user_initials(request.user)
        banks_connected = request.user.connected_accounts.filter(
            status=ConnectedAccountPlaceholder.Status.CONNECTED
        ).exists()
        unread_notifications = request.user.notification_events.filter(read_at__isnull=True).count()
        surplus = compute_investable_surplus(request.user)
    return {
        "nav_active": nav_active,
        "user_display_name": user_label,
        "user_initials": initials,
        "banks_connected": banks_connected,
        "unread_notifications": unread_notifications,
        "surplus": surplus,
        "AUTH0_ENABLED": auth0_configured(),
    }
