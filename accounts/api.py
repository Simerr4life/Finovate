"""Protected API. Callers must present an Auth0 access token for the API audience.

The Django session cookie is not a substitute, and neither is an ID token.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from transactions.models import Transaction

from .models import Profile
from .tokens import TokenValidationError, validate_access_token


@require_GET
def api_me(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return JsonResponse({"error": "authentication_failed"}, status=401)
    token = header[7:].strip()
    try:
        claims = validate_access_token(token)
    except TokenValidationError:
        return JsonResponse({"error": "authentication_failed"}, status=401)
    profile = Profile.objects.filter(auth0_sub=claims["sub"]).select_related("user").first()
    if profile is None:
        return JsonResponse({"error": "authentication_failed"}, status=401)
    if not profile.email_verified:
        return JsonResponse(
            {
                "identity_status": profile.identity_status or "verification_pending",
                "email_verified": False,
            },
            status=403,
        )
    return JsonResponse(
        {
            "identity_status": profile.identity_status,
            "email_verified": True,
            "transaction_count": Transaction.objects.filter(user=profile.user).count(),
        }
    )
