from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .auth0 import auth0_configured, get_auth0_client
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
    redirect_uri = request.build_absolute_uri(reverse("accounts:auth0_callback"))
    return client.authorize_redirect(request, redirect_uri)


def auth0_callback(request):
    """Exchange the authorization code for tokens and validate the ID
    token (signature/issuer/audience/expiry, via authlib + Auth0's JWKS),
    then map the verified `sub` claim to a Finovate user -- creating one
    on first login, never by matching email.
    """
    client = get_auth0_client()
    if client is None:
        messages.error(request, "Auth0 isn't configured.")
        return redirect("accounts:login")

    try:
        token = client.authorize_access_token(request)
    except Exception:
        messages.error(request, "Auth0 sign-in failed or was cancelled. Please try again.")
        return redirect("accounts:login")

    claims = token.get("userinfo")
    if not claims or not claims.get("sub"):
        messages.error(request, "Auth0 didn't return a verified identity. Please try again.")
        return redirect("accounts:login")

    sub = claims["sub"]
    profile = Profile.objects.filter(auth0_sub=sub).first()
    if profile is not None:
        user = profile.user
    else:
        base_username = f"auth0_{sub}".replace("|", "_")[:150]
        user = User.objects.create_user(username=base_username, email=claims.get("email", ""))
        user.profile.auth0_sub = sub
        user.profile.save(update_fields=["auth0_sub", "updated_at"])

    login(request, user)
    request.session["logged_in_via_auth0"] = True
    if not user.profile.onboarding_completed:
        return redirect("accounts:onboarding")
    return redirect("dashboard")


@require_POST
def auth0_logout(request):
    """Clear the Django session, then federated-log-out of Auth0 too if
    that's how this session was established (so a shared browser doesn't
    silently stay signed into Auth0 after leaving Finovate).
    """
    from django.contrib.auth import logout as django_logout

    came_from_auth0 = request.session.get("logged_in_via_auth0")
    django_logout(request)
    if came_from_auth0 and auth0_configured():
        return_to = request.build_absolute_uri(reverse("landing"))
        params = urlencode({"returnTo": return_to, "client_id": settings.AUTH0_CLIENT_ID})
        return redirect(f"https://{settings.AUTH0_DOMAIN}/v2/logout?{params}")
    return redirect("landing")


@login_required
def onboarding(request):
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
    return render(
        request,
        "accounts/settings.html",
        {
            "form": form,
            "connected_accounts": connected_accounts,
            "roundup_settings": roundup_settings,
        },
    )
