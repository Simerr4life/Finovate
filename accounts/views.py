import hmac
import json
import logging
import time

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from auth0_server_python.auth_types import LogoutOptions, StartInteractiveLoginOptions
from auth0_server_python.error import ApiError

from assistant.linking import code_is_active, issue_link_code
from assistant.models import MessagingLinkCode

from budgets.services import build_budget_plan

from core.display import display_name, user_initials

from .auth0 import apply_auth0_cookies, auth0_configured, get_auth0_client, logout_return_url
from .auth0_backup import upsert_from_auth0_event
from .forms import (
    DisplayNameForm,
    EmailLoginForm,
    EmailSignUpForm,
    ManualSetupForm,
    OnboardingForm,
    ProfileSettingsForm,
    RegistrationForm,
)
from .manual_setup import apply_manual_setup, initial_from_existing
from .models import THEME_CHOICES
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
from .supabase_auth import (
    EMAIL_NOT_CONFIRMED,
    INVALID_CREDENTIALS,
    RATE_LIMITED,
    WEAK_PASSWORD,
    SupabaseAuthError,
    legacy_user_for,
    migrate_legacy_password,
    profile_for_supabase_user,
    sign_in,
    sign_up,
    supabase_configured,
)
from .verification import apply_authoritative_verification, resend_verification_email

logger = logging.getLogger(__name__)

_VERIFY_STATES = frozenset(
    {"pending", "verified", "already_verified", "expired", "invalid", "failed", "unavailable"}
)


_EMAIL_ERRORS = {
    INVALID_CREDENTIALS: "That email and password don't match an account.",
    EMAIL_NOT_CONFIRMED: "Confirm your email first. Use the link Supabase sent when you signed up.",
    WEAK_PASSWORD: "Choose a stronger password.",
    RATE_LIMITED: "Too many attempts. Please wait a moment and try again.",
}
_EMAIL_UNAVAILABLE = "Email sign-in is unavailable right now. Please try again."


def _session_login(request, user):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")


def _wants_json(request):
    accept = request.headers.get("Accept", "")
    return "application/json" in accept or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def signup(request):
    """Auth0 is the recommended way to register. Email-and-password
    registration through Supabase Auth is offered beside it. Finovate
    stores no password either way.
    """
    if request.user.is_authenticated:
        return redirect(destination_for(request.user))
    auth0_ready = auth0_configured()
    email_ready = supabase_configured()
    nxt = safe_next(request.POST.get("next") or request.GET.get("next"))
    form = RegistrationForm() if auth0_ready else None
    email_form = EmailSignUpForm() if email_ready else None
    status = 200
    rate_limited = False
    use_email = email_ready and (request.POST.get("method") == "email" or not auth0_ready)
    if request.method == "POST":
        if _rate_limited(request, "signup", limit=10, period=600):
            rate_limited, status = True, 429
        elif use_email:
            email_form = EmailSignUpForm(request.POST)
            if email_form.is_valid():
                data = email_form.cleaned_data
                try:
                    supabase_user = sign_up(data["email"], data["password1"], data["name"])
                except SupabaseAuthError as exc:
                    email_form.add_error(None, _EMAIL_ERRORS.get(exc.code, _EMAIL_UNAVAILABLE))
                else:
                    if supabase_user is None:
                        messages.success(
                            request,
                            "Check your email for a confirmation link, then log in. "
                            "If you already have an account, log in instead.",
                        )
                        return redirect("accounts:login")
                    profile = profile_for_supabase_user(supabase_user)
                    _session_login(request, profile.user)
                    return redirect(destination_for(profile.user, nxt))
        elif auth0_ready:
            form = RegistrationForm(request.POST)
            if form.is_valid():
                request.session["auth0_pending"] = {
                    "name": form.cleaned_data["name"],
                    "phone": form.cleaned_data["phone"],
                }
                request.session["auth_status"] = REGISTRATION_STARTED
                return _begin_auth0(
                    request,
                    screen_hint="signup",
                    login_hint=form.cleaned_data["email"],
                    next_url=nxt,
                )
    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
            "email_form": email_form,
            "auth0_ready": auth0_ready,
            "email_ready": email_ready,
            "rate_limited": rate_limited,
            "next": nxt,
        },
        status=status,
    )


def _email_login(request, form):
    """Sign in through Supabase. An account that predates Supabase is
    checked against its old Django password and moved across on the spot.
    Returns the Finovate user, or None after adding an error to the form.
    """
    identifier = form.cleaned_data["email"].strip()
    password = form.cleaned_data["password"]
    legacy = legacy_user_for(identifier, password)
    if legacy is not None:
        # The old password was correct, so the person is who they say they
        # are whether or not the move to Supabase can finish just now.
        if not migrate_legacy_password(legacy, password) and legacy.profile.supabase_uid:
            messages.info(
                request,
                "Check your email for a confirmation link from Supabase to finish moving your login.",
            )
        return legacy
    if "@" not in identifier:
        form.add_error(None, _EMAIL_ERRORS[INVALID_CREDENTIALS])
        return None
    try:
        supabase_user = sign_in(identifier, password)
    except SupabaseAuthError as exc:
        form.add_error(None, _EMAIL_ERRORS.get(exc.code, _EMAIL_UNAVAILABLE))
        return None
    return profile_for_supabase_user(supabase_user).user


def login_view(request):
    nxt = safe_next(request.POST.get("next") or request.GET.get("next"))
    if request.user.is_authenticated:
        return redirect(destination_for(request.user, nxt))
    auth0_ready = auth0_configured()
    email_ready = supabase_configured()
    email_form = EmailLoginForm() if email_ready else None
    status = 200
    rate_limited = False
    use_email = email_ready and (request.POST.get("method") == "email" or not auth0_ready)
    if request.method == "POST":
        if _rate_limited(request, "login", limit=20, period=600):
            rate_limited, status = True, 429
        elif use_email:
            email_form = EmailLoginForm(request.POST)
            if email_form.is_valid():
                user = _email_login(request, email_form)
                if user is not None:
                    _session_login(request, user)
                    return redirect(destination_for(user, nxt))
        elif auth0_ready:
            return _begin_auth0(request, next_url=nxt)
    return render(
        request,
        "accounts/login.html",
        {
            "email_form": email_form,
            "auth0_ready": auth0_ready,
            "email_ready": email_ready,
            "rate_limited": rate_limited,
            "next": nxt,
        },
        status=status,
    )


def auth0_login(request):
    if request.user.is_authenticated:
        return redirect(destination_for(request.user, safe_next(request.GET.get("next"))))
    if get_auth0_client() is None:
        messages.error(request, "Auth0 isn't configured on this server. Use email sign-in instead.")
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
        messages.error(request, "Auth0 isn't configured on this server. Use email sign-in instead.")
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

    if settings.AUTH0_AUDIENCE and access_token_expiry(result, settings.AUTH0_AUDIENCE) is None:
        logger.warning("auth0 callback missing api access token")
        return _auth_failure(request, None)

    pending = request.session.pop("auth0_pending", None) or {}
    try:
        profile, _created = sync_profile_from_claims(claims, pending)
    except Exception:
        logger.warning("auth0 profile sync failed")
        return _auth_failure(request, None)

    # Fresh ID-token claims can upgrade verification; they never prove it alone
    # when false — Management API refresh covers the email-link return path.
    if claims.get("email_verified") is True and not profile.email_verified:
        from .verification import mark_verified_from_trusted_claims

        mark_verified_from_trusted_claims(profile, claims)
        profile.refresh_from_db()
    elif not profile.email_verified:
        apply_authoritative_verification(profile)
        profile.refresh_from_db()

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
        messages.error(request, "Auth0 isn't configured on this server. Use email sign-in instead.")
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


def _client_ip(request):
    # X-Forwarded-For is only trustworthy behind a proxy that sets it (Vercel
    # does). Anywhere else a client could send a fresh value per request and
    # never hit the limit.
    if settings.ON_VERCEL:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _rate_limited(request, action, limit, period):
    ip = _client_ip(request)
    key = f"auth-rl:{action}:{ip}"
    current = cache.get(key, 0)
    if current >= limit:
        return True
    cache.set(key, current + 1, period)
    return False


@login_required
@require_GET
def verification_pending(request):
    """Show verification status and refresh from Auth0's authoritative user record.

    A successful redirect alone never marks the account verified.
    """
    profile = request.user.profile
    if not profile.auth0_sub:
        return redirect(destination_for(request.user))

    state = (request.GET.get("state") or "").strip().lower()
    if state not in _VERIFY_STATES:
        state = ""

    if profile.email_verified:
        if state in ("", "pending"):
            return redirect(destination_for(request.user))
        return render(
            request,
            "accounts/verify.html",
            _verify_context(profile, state="already_verified"),
        )

    # Re-read Auth0 Management API so the email-link path updates without a
    # full re-login when management credentials are configured.
    outcome = apply_authoritative_verification(profile)
    profile.refresh_from_db()
    if outcome in ("verified", "already_verified") or profile.email_verified:
        messages.success(request, "Your email is verified. Welcome back.")
        return redirect(destination_for(request.user))

    # Query-string hints never prove verification. Only failure/pending UI
    # states are accepted while the profile is still unverified.
    if state in ("verified", "already_verified"):
        state = "pending"
    if not state:
        if outcome == "unavailable":
            state = "unavailable"
        else:
            state = "pending"

    return render(request, "accounts/verify.html", _verify_context(profile, state=state))


def verification_result(request):
    """Public landing for Auth0 verification email resultUrl redirects.

    Query params (success / message / error) are display hints only. When the
    visitor is signed in, Auth0 Management API is the source of truth.
    """
    success = (request.GET.get("success") or "").lower()
    error = (request.GET.get("error") or request.GET.get("message") or "").lower()
    if success in {"true", "1", "yes"}:
        hint = "verified"
    elif "expired" in error:
        hint = "expired"
    elif "already" in error:
        hint = "already_verified"
    elif error or success in {"false", "0", "no"}:
        hint = "invalid"
    else:
        hint = "pending"

    if request.user.is_authenticated and getattr(request.user, "profile", None):
        profile = request.user.profile
        if profile.auth0_sub:
            outcome = apply_authoritative_verification(profile)
            profile.refresh_from_db()
            if profile.email_verified or outcome in ("verified", "already_verified"):
                messages.success(request, "Your email is verified.")
                return redirect(destination_for(request.user))
            if outcome == "unavailable" and hint == "verified":
                # Auth0 may have verified the user but Management API is down;
                # force a fresh login so the next ID token can upgrade status.
                return _begin_auth0(request, max_age=0, next_url=reverse("accounts:verify"))
        return redirect(f"{reverse('accounts:verify')}?state={hint}")

    return render(
        request,
        "accounts/verify.html",
        {
            "identity_status": hint,
            "email_verified": False,
            "verify_state": hint,
            "signed_in": False,
        },
    )


def _verify_context(profile, state="pending"):
    return {
        "identity_status": profile.identity_status or "verification_pending",
        "email_verified": profile.email_verified,
        "verify_state": state,
        "signed_in": True,
    }


@login_required
@require_POST
def verification_resend(request):
    if _rate_limited(request, f"resend:{request.user.pk}", limit=3, period=900):
        messages.error(request, "Please wait before requesting another verification email.")
        return redirect(f"{reverse('accounts:verify')}?state=pending")
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
    return redirect(f"{reverse('accounts:verify')}?state=pending")


@login_required
@require_POST
def verification_refresh(request):
    """Re-check Auth0, then force a fresh login when still pending.

    This does not mark the account verified by itself.
    """
    profile = request.user.profile
    outcome = apply_authoritative_verification(profile)
    profile.refresh_from_db()
    if outcome in ("verified", "already_verified") or profile.email_verified:
        messages.success(request, "Your email is verified.")
        return redirect(destination_for(request.user))
    return _begin_auth0(request, max_age=0, next_url=reverse("accounts:verify"))


@csrf_exempt
@require_http_methods(["POST"])
def auth0_signup_webhook(request):
    """Trusted Auth0 Post-User-Registration Action → Supabase backup upsert.

    Authenticated with AUTH0_ACTION_SECRET (Bearer or X-Finovate-Auth0-Secret).
    Never accepts browser session cookies as privilege for this write path.
    """
    expected = (settings.AUTH0_ACTION_SECRET or "").strip()
    if not expected:
        return JsonResponse({"error": "not_configured"}, status=503)
    provided = _action_secret(request)
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if _rate_limited(request, "auth0-action", limit=120, period=60):
        return JsonResponse({"error": "rate_limited"}, status=429)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_json"}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "invalid_payload"}, status=400)
    try:
        record = upsert_from_auth0_event(payload, source="auth0_action")
    except ValueError:
        return JsonResponse({"error": "missing_user_id"}, status=400)
    except Exception:
        logger.warning("auth0 signup webhook failed")
        return JsonResponse({"error": "sync_failed"}, status=503)
    if record is None:
        return JsonResponse({"error": "sync_failed"}, status=503)
    return JsonResponse(
        {
            "ok": True,
            "auth0_user_id": record.auth0_user_id,
            "sync_status": record.sync_status,
            "email_verified": record.email_verified,
        }
    )


def _action_secret(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return (request.META.get("HTTP_X_FINOVATE_AUTH0_SECRET") or "").strip()


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
    name_form = DisplayNameForm(initial={"name": display_name(request.user)})
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
            "name_form": name_form,
            "connected_accounts": connected_accounts,
            "roundup_settings": roundup_settings,
            "link_code": link_code,
            "notification_events": request.user.notification_events.all()[:15],
        },
    )


@login_required
@require_POST
def update_name(request):
    """Change the display name. Touches first_name/last_name only."""
    form = DisplayNameForm(request.POST)
    if not form.is_valid():
        error = form.errors.get("name", ["Enter a valid name."])[0]
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": error}, status=400)
        messages.error(request, error)
        return redirect(reverse("accounts:settings") + "#profile")

    name = form.cleaned_data["name"]
    first, _, rest = name.partition(" ")
    user = request.user
    with transaction.atomic():
        user.first_name = first
        user.last_name = rest
        user.save(update_fields=["first_name", "last_name"])
        profile = user.profile
        profile.name_customized_at = timezone.now()
        profile.save(update_fields=["name_customized_at", "updated_at"])

    payload = {"ok": True, "name": display_name(user), "initials": user_initials(user)}
    if _wants_json(request):
        return JsonResponse(payload)
    messages.success(request, "Your name was updated.")
    return redirect(reverse("accounts:settings") + "#profile")


@login_required
@require_POST
def update_theme(request):
    """Persist the color theme chosen with the header toggle."""
    theme = request.POST.get("theme", "")
    if theme not in {value for value, _ in THEME_CHOICES}:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Unknown theme."}, status=400)
        messages.error(request, "That theme isn't available.")
        return redirect("accounts:settings")
    profile = request.user.profile
    profile.theme = theme
    profile.save(update_fields=["theme", "updated_at"])
    if _wants_json(request):
        return JsonResponse({"ok": True, "theme": theme})
    return redirect(safe_next(request.POST.get("next")) or reverse("accounts:settings"))


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
