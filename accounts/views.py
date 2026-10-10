from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import OnboardingForm, ProfileSettingsForm, SignUpForm


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
