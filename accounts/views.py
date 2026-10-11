import logging
import time

from asgiref.sync import async_to_sync
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from auth0_server_python.auth_types import LogoutOptions, StartInteractiveLoginOptions
from auth0_server_python.error import ApiError

from assistant.linking import code_is_active, issue_link_code
from assistant.models import MessagingLinkCode

from budgets.services import build_budget_plan

from .auth0 import apply_auth0_cookies, auth0_configured, get_auth0_client, logout_return_url
from .forms import ManualSetupForm, OnboardingForm, ProfileSettingsForm, RegistrationForm
from .manual_setup import apply_manual_setup, initial_from_existing
from .identity import (
    ACCOUNT_BLOCKED,
    AUTHENTICATION_FAILED,
    AUTHENTICATION_SUCCESSFUL,
    REGISTRATION_STARTED,
    access_token_expiry,
    claims_from_login_result,
    destination_for,
    safe_next,
    sync_profile_from_claims,
)
from .verification import resend_verification_email

logger = logging.getLogger(__name__)


def signup(request):
    """Collect name, email, and an optional phone number, then send the
    person to Auth0 Universal Login. This view never creates a user.
    """
    if request.user.is_authenticated:
        return redirect(destination_for(request.user))
    if not auth0_configured():
        return render(request, "accounts/signup.html", {"form": None, "auth0_ready": False})
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            if _rate_limited(request, "signup", limit=10, period=600):
                return render(
                    request,
                    "accounts/signup.html",
                    {"form": form, "auth0_ready": True, "rate_limited": True},
                    status=429,
                )
            request.session["auth0_pending"] = {
                "name": form.cleaned_data["name"],
                "phone": form.cleaned_data["phone"],
            }
            request.session["auth_status"] = REGISTRATION_STARTED
            return _begin_auth0(
                request,
                screen_hint="signup",
                login_hint=form.cleaned_data["email"],
                next_url=safe_next(request.POST.get("next")),
            )
    else:
        form = RegistrationForm()
    return render(request, "accounts/signup.html", {"form": form, "auth0_ready": True})


def login_view(request):
    nxt = safe_next(request.POST.get("next") or request.GET.get("next"))
    if request.user.is_authenticated:
        return redirect(destination_for(request.user, nxt))
    if not auth0_configured():
        return render(request, "accounts/login.html", {"auth0_ready": False, "next": nxt})
    if request.method == "POST" or nxt:
        if _rate_limited(request, "login", limit=20, period=600):
            return render(
                request,
                "accounts/login.html",
                {"auth0_ready": True, "next": nxt, "rate_limited": True},
                status=429,
            )
        return _begin_auth0(request, next_url=nxt)
    return render(request, "accounts/login.html", {"auth0_ready": True, "next": nxt})


def auth0_login(request):
    if request.user.is_authenticated:
        return redirect(destination_for(request.user, safe_next(request.GET.get("next"))))
    if get_auth0_client() is None:
        messages.error(request, "Auth0 isn't configured, so sign-in is unavailable.")
        return redirect("accounts:login")
    screen_hint = request.GET.get("screen_hint") if request.GET.get("screen_hint") in {"signup", "login"} else None
    return _begin_auth0(
        request,
        screen_hint=screen_hint,
        next_url=safe_next(request.GET.get("next")),
    )


def auth0_callback(request):
    """Finish Auth0 login after the SDK checks the authorization code and tokens.

    A Finovate profile is created only when Auth0 returns a subject. Lookup
    is by that subject, never by email or phone.
    """
    client = get_auth0_client()
    if client is None:
        messages.error(request, "Auth0 isn't configured, so sign-in is unavailable.")
        return redirect("accounts:login")

    try:
        result = async_to_sync(client.complete_interactive_login)(
            url=request.build_absolute_uri(),
            store_options={"request": request},
        )
    except ApiError as exc:
        logger.warning("auth0 callback rejected code=%s", getattr(exc, "code", "error"))
        return _auth_failure(request, exc)
    except Exception:
        logger.warning("auth0 callback failed")
        return _auth_failure(request, None)

    claims = claims_from_login_result(result)
    if not claims.get("sub"):
        return _auth_failure(request, None)

    from django.conf import settings

    if settings.AUTH0_AUDIENCE and access_token_expiry(result, settings.AUTH0_AUDIENCE) is None:
        logger.warning("auth0 callback missing api access token")
        return _auth_failure(request, None)

    pending = request.session.pop("auth0_pending", None) or {}
    try:
        profile, _created = sync_profile_from_claims(claims, pending)
    except Exception:
        logger.warning("auth0 profile sync failed")
        return _auth_failure(request, None)

    login(request, profile.user)
    request.session["logged_in_via_auth0"] = True
    request.session["auth_status"] = AUTHENTICATION_SUCCESSFUL
    expires_at = access_token_expiry(result, settings.AUTH0_AUDIENCE)
    request.session["auth0_access_exp"] = expires_at or int(time.time()) + 3600
    app_state = (result or {}).get("app_state") or {}
    if hasattr(app_state, "model_dump"):
        app_state = app_state.model_dump()
    nxt = safe_next(app_state.get("next") if isinstance(app_state, dict) else "")
    response = redirect(destination_for(profile.user, nxt))
    return apply_auth0_cookies(request, response)


def _auth_failure(request, exc):
    request.session["auth_status"] = AUTHENTICATION_FAILED
    description = ""
    code = ""
    if exc is not None:
        code = str(getattr(exc, "code", "") or "")
        description = str(getattr(exc, "message", "") or exc)
    if "blocked" in f"{code} {description}".lower():
        request.session["auth_status"] = ACCOUNT_BLOCKED
        messages.error(request, "This account is blocked or disabled.")
    else:
        messages.error(request, "Authentication failed. Please try again.")
    return redirect("accounts:login")


def _begin_auth0(request, screen_hint=None, login_hint=None, next_url="", max_age=None):
    client = get_auth0_client()
    if client is None:
        messages.error(request, "Auth0 isn't configured, so sign-in is unavailable.")
        return redirect("accounts:login")
    authorization_params = {}
    if screen_hint:
        authorization_params["screen_hint"] = screen_hint
    if login_hint:
        authorization_params["login_hint"] = login_hint
    if max_age is not None:
        authorization_params["max_age"] = max_age
    try:
        url = async_to_sync(client.start_interactive_login)(
            options=StartInteractiveLoginOptions(
                app_state={"next": next_url} if next_url else None,
                authorization_params=authorization_params or None,
            ),
            store_options={"request": request},
        )
    except Exception:
        logger.warning("auth0 login could not be started")
        messages.error(request, "Authentication failed. Please try again.")
        request.session["auth_status"] = AUTHENTICATION_FAILED
        return redirect("accounts:login")
    return apply_auth0_cookies(request, redirect(url))


def _rate_limited(request, action, limit, period):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = (forwarded.split(",")[0].strip() if forwarded else "") or request.META.get("REMOTE_ADDR", "")
    key = f"auth-rl:{action}:{ip}"
    current = cache.get(key, 0)
    if current >= limit:
        return True
    cache.set(key, current + 1, period)
    return False


@login_required
@require_GET
def verification_pending(request):
    profile = request.user.profile
    if not profile.auth0_sub or profile.email_verified:
        return redirect(destination_for(request.user))
    return render(
        request,
        "accounts/verify.html",
        {
            "identity_status": profile.identity_status or "verification_pending",
            "email_verified": profile.email_verified,
        },
    )


@login_required
@require_POST
def verification_resend(request):
    if _rate_limited(request, f"resend:{request.user.pk}", limit=3, period=900):
        messages.error(request, "Please wait before requesting another verification email.")
        return redirect("accounts:verify")
    result = resend_verification_email(request.user.profile.auth0_sub)
    if result == "sent":
        messages.success(request, "Auth0 accepted a new verification email. Check your inbox.")
    elif result == "not_configured":
        messages.error(
            request,
            "Use the verification email Auth0 sent when the account was created. Resend is not configured on this server.",
        )
    else:
        messages.error(request, "A new verification email could not be sent. Wait a few minutes and try again.")
    return redirect("accounts:verify")


@login_required
@require_POST
def verification_refresh(request):
    """Return to Auth0 so the next callback can read a fresh email_verified claim.

    This does not mark the account verified by itself.
    """
    return _begin_auth0(request, max_age=0)


@require_POST
def auth0_logout(request):
    """Clear the Django session, then end the Auth0 session when this login used Auth0.

    The return URL is the configured app origin. A posted return address is ignored.
    """
    from django.contrib.auth import logout as django_logout

    came_from_auth0 = request.session.get("logged_in_via_auth0")
    client = get_auth0_client() if came_from_auth0 and auth0_configured() else None
    logout_url = None
    if client is not None:
        try:
            logout_url = async_to_sync(client.logout)(
                options=LogoutOptions(return_to=logout_return_url()),
                store_options={"request": request},
            )
        except Exception:
            logger.warning("auth0 logout redirect could not be built")
    django_logout(request)
    if logout_url:
        return apply_auth0_cookies(request, redirect(logout_url))
    return redirect("landing")


@login_required
def onboarding(request):
    """Step 1: add financial data, or skip. Deliberately has no form of its
    own -- it only routes to the import wizard, to the "coming soon" bank
    connection, or past itself to the preferences step.
    """
    profile = request.user.profile
    if profile.onboarding_completed:
        return redirect("dashboard")
    return render(request, "accounts/onboarding_start.html")


@login_required
def onboarding_preferences(request):
    profile = request.user.profile
    if profile.onboarding_completed:
        return redirect("dashboard")
    if request.method == "POST":
        form = OnboardingForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.onboarding_completed = True
            profile.save()
            messages.success(request, "You're all set up. Welcome to Finovate!")
            return redirect("dashboard")
    else:
        form = OnboardingForm(instance=profile)
    return render(request, "accounts/onboarding.html", {"form": form})


@login_required
def manual_setup(request):
    """Quick income/expense entry for when there's no statement to import
    (or it couldn't be read). Writes IncomeSource/RecurringExpense rows
    budgets.services.build_budget_plan already knows how to read -- this
    view never computes its own surplus estimate.
    """
    from_onboarding = request.GET.get("from") == "onboarding" or request.POST.get("from") == "onboarding"
    if request.method == "POST":
        form = ManualSetupForm(request.POST)
        if form.is_valid():
            apply_manual_setup(request.user, form.cleaned_data)
            messages.success(request, "Saved. Here's your estimate.")
            url = reverse("accounts:manual_setup_summary")
            if from_onboarding:
                url += "?from=onboarding"
            return redirect(url)
    else:
        form = ManualSetupForm(initial=initial_from_existing(request.user))
    return render(request, "accounts/manual_setup.html", {"form": form, "from_onboarding": from_onboarding})


@login_required
def manual_setup_summary(request):
    profile = request.user.profile
    plan = build_budget_plan(request.user)
    from_onboarding = request.GET.get("from") == "onboarding"
    return render(
        request,
        "accounts/manual_setup_summary.html",
        {
            "plan": plan,
            "profile": profile,
            "from_onboarding": from_onboarding,
        },
    )


@login_required
def settings_view(request):
    profile = request.user.profile
    if request.method == "POST":
        form = ProfileSettingsForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("accounts:settings")
    else:
        form = ProfileSettingsForm(instance=profile)
    connected_accounts = request.user.connected_accounts.all()
    roundup_settings = getattr(request.user, "roundup_settings", None)
    link_code = request.session.get("messaging_link_preview") or ""
    if link_code and not code_is_active(request.user, link_code):
        link_code = ""
        request.session.pop("messaging_link_preview", None)
    return render(
        request,
        "accounts/settings.html",
        {
            "form": form,
            "connected_accounts": connected_accounts,
            "roundup_settings": roundup_settings,
            "link_code": link_code,
            "notification_events": request.user.notification_events.all()[:15],
        },
    )


@login_required
@require_POST
def messaging_link_issue(request):
    if request.user.profile.photon_chat_id:
        messages.error(request, "Unlink the current chat before creating a new link code.")
        return redirect("accounts:settings")
    request.session["messaging_link_preview"] = issue_link_code(request.user)
    messages.success(
        request,
        "Send the code below from the chat you want to link. It expires in 15 minutes and works once.",
    )
    return redirect("accounts:settings")


@login_required
@require_POST
def messaging_unlink(request):
    profile = request.user.profile
    profile.photon_chat_id = ""
    profile.messaging_linked_at = None
    profile.save(update_fields=["photon_chat_id", "messaging_linked_at", "updated_at"])
    MessagingLinkCode.objects.filter(user=request.user, used_at__isnull=True).delete()
    request.session.pop("messaging_link_preview", None)
    messages.success(request, "Messaging chat unlinked. It can no longer change this account.")
    return redirect("accounts:settings")
