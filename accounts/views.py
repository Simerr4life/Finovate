from asgiref.sync import async_to_sync
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from auth0_server_python.auth_types import LogoutOptions, StartInteractiveLoginOptions

from assistant.linking import code_is_active, issue_link_code
from assistant.models import MessagingLinkCode

from .auth0 import apply_auth0_cookies, auth0_configured, get_auth0_client, logout_return_url
from .forms import OnboardingForm, ProfileSettingsForm, SignUpForm
from .models import Profile


def signup(request):
    """Local demo-auth signup. See the banner on this page: this is a
    plain Django session login for local development, not a production
    identity provider. Auth0 (or similar) is the documented future option.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("accounts:onboarding")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


def auth0_login(request):
    client = get_auth0_client()
    if client is None:
        messages.error(request, "Auth0 isn't configured yet. Use local login/signup instead.")
        return redirect("accounts:login")
    authorization_params = {}
    screen_hint = request.GET.get("screen_hint")
    if screen_hint:
        authorization_params["screen_hint"] = screen_hint
    try:
        url = async_to_sync(client.start_interactive_login)(
            options=StartInteractiveLoginOptions(
                authorization_params=authorization_params or None
            ),
            store_options={"request": request},
        )
    except Exception:
        messages.error(request, "Auth0 sign-in could not be started. Please try again.")
        return redirect("accounts:login")
    return apply_auth0_cookies(request, redirect(url))


def auth0_callback(request):
    """Finish the Auth0 login (code exchange and token checks are done by
    the Auth0 SDK), then map the verified `sub` claim to a Finovate user.
    A new user is created on first login and is never matched by email.
    """
    client = get_auth0_client()
    if client is None:
        messages.error(request, "Auth0 isn't configured.")
        return redirect("accounts:login")

    try:
        result = async_to_sync(client.complete_interactive_login)(
            url=request.build_absolute_uri(),
            store_options={"request": request},
        )
    except Exception:
        messages.error(request, "Auth0 sign-in failed or was cancelled. Please try again.")
        return redirect("accounts:login")

    claims = _claims(result)
    if not claims or not claims.get("sub"):
        messages.error(request, "Auth0 didn't return a verified identity. Please try again.")
        return redirect("accounts:login")

    sub = claims["sub"]
    profile = Profile.objects.filter(auth0_sub=sub).first()
    if profile is not None:
        user = profile.user
    else:
        base_username = f"auth0_{sub}".replace("|", "_")[:150]
        user = User.objects.create_user(username=base_username, email=claims.get("email") or "")
        user.profile.auth0_sub = sub
        user.profile.save(update_fields=["auth0_sub", "updated_at"])

    login(request, user)
    request.session["logged_in_via_auth0"] = True
    if not user.profile.onboarding_completed:
        response = redirect("accounts:onboarding")
    else:
        response = redirect("dashboard")
    return apply_auth0_cookies(request, response)


def _claims(result):
    state = (result or {}).get("state_data") or {}
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    user = state.get("user") or {}
    if hasattr(user, "model_dump"):
        user = user.model_dump()
    return user


@require_POST
def auth0_logout(request):
    """Clear the Django session, then log out of Auth0 too if that's how
    this session was established.
    """
    from django.contrib.auth import logout as django_logout

    came_from_auth0 = request.session.get("logged_in_via_auth0")
    client = get_auth0_client() if came_from_auth0 and auth0_configured() else None
    logout_url = None
    if client is not None:
        logout_url = async_to_sync(client.logout)(
            options=LogoutOptions(return_to=logout_return_url()),
            store_options={"request": request},
        )
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
