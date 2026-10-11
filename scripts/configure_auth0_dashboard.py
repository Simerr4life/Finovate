#!/usr/bin/env python3
"""Apply Auth0 tenant settings for Finovate verification + signup backup.

Requires Management API credentials with scopes:
  read:users, update:users, create:user_tickets,
  read:email_templates, update:email_templates,
  read:actions, create:actions, update:actions,
  read:actions_triggers, update:actions_triggers,
  read:clients, read:client_grants, create:client_grants, update:client_grants

Environment:
  AUTH0_DOMAIN
  AUTH0_MGMT_CLIENT_ID
  AUTH0_MGMT_CLIENT_SECRET
  APP_BASE_URL                 (default https://finovate.biz)
  AUTH0_ACTION_SECRET          (shared with Finovate + Action secret)
  AUTH0_MGMT_CLIENT_ID         (also used as the M2M app to authorize)

Usage:
  python scripts/configure_auth0_dashboard.py
  python scripts/configure_auth0_dashboard.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ACTION_NAME = "Finovate Signup Backup"
TRIGGER_ID = "post-user-registration"
REQUIRED_SCOPES = [
    "read:users",
    "update:users",
    "create:user_tickets",
]
ACTION_CODE_PATH = Path(__file__).resolve().parent / "auth0" / "post-user-registration-action.js"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _request(method: str, url: str, token: str | None = None, body: dict | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"message": raw}
        return exc.code, payload


def management_token(domain: str, client_id: str, client_secret: str) -> str:
    status, payload = _request(
        "POST",
        f"https://{domain}/oauth/token",
        body={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": f"https://{domain}/api/v2/",
        },
    )
    if status != 200 or not payload.get("access_token"):
        raise SystemExit(f"token_failed status={status} body={payload}")
    return payload["access_token"]


def ensure_email_template(domain: str, token: str, result_url: str, dry_run: bool) -> None:
    status, current = _request(
        "GET",
        f"https://{domain}/api/v2/email-templates/verify_email",
        token=token,
    )
    if status == 404:
        print("verify_email template missing; creating enabled template")
        body = {
            "template": "verify_email",
            "enabled": True,
            "syntax": "liquid",
            "from": "",
            "subject": "Verify your email for Finovate",
            "body": (
                "<html><body>"
                "<p>Please verify your email by clicking the link below.</p>"
                '<p><a href="{{ url }}">Verify email</a></p>'
                "</body></html>"
            ),
            "urlLifetime": 432000,
            "resultUrl": result_url,
        }
        if dry_run:
            print(f"[dry-run] POST email-templates {body}")
            return
        status, payload = _request(
            "POST",
            f"https://{domain}/api/v2/email-templates",
            token=token,
            body=body,
        )
        if status not in (200, 201):
            raise SystemExit(f"create_email_template_failed status={status} body={payload}")
        print("created verify_email template with resultUrl")
        return
    if status != 200:
        raise SystemExit(f"get_email_template_failed status={status} body={current}")
    if current.get("resultUrl") == result_url and current.get("enabled") is not False:
        print(f"verify_email resultUrl already {result_url}")
        return
    patch = {"resultUrl": result_url, "enabled": True}
    if dry_run:
        print(f"[dry-run] PATCH email-templates/verify_email {patch}")
        return
    status, payload = _request(
        "PATCH",
        f"https://{domain}/api/v2/email-templates/verify_email",
        token=token,
        body=patch,
    )
    if status != 200:
        raise SystemExit(f"patch_email_template_failed status={status} body={payload}")
    print(f"set verify_email resultUrl → {result_url}")


def ensure_m2m_scopes(domain: str, token: str, mgmt_client_id: str, dry_run: bool) -> None:
    audience = f"https://{domain}/api/v2/"
    status, grants = _request(
        "GET",
        f"https://{domain}/api/v2/client-grants?client_id={mgmt_client_id}&audience={urllib_quote(audience)}",
        token=token,
    )
    if status != 200:
        raise SystemExit(f"list_client_grants_failed status={status} body={grants}")
    grant = grants[0] if isinstance(grants, list) and grants else None
    if grant is None:
        body = {
            "client_id": mgmt_client_id,
            "audience": audience,
            "scope": REQUIRED_SCOPES,
        }
        if dry_run:
            print(f"[dry-run] POST client-grants {body}")
            return
        status, payload = _request(
            "POST",
            f"https://{domain}/api/v2/client-grants",
            token=token,
            body=body,
        )
        if status not in (200, 201):
            raise SystemExit(f"create_client_grant_failed status={status} body={payload}")
        print(f"created Management API grant with {REQUIRED_SCOPES}")
        return
    existing = set(grant.get("scope") or [])
    needed = sorted(existing | set(REQUIRED_SCOPES))
    if set(needed) == existing:
        print(f"M2M grant already has required scopes: {sorted(existing & set(REQUIRED_SCOPES))}")
        return
    if dry_run:
        print(f"[dry-run] PATCH client-grants/{grant['id']} scope={needed}")
        return
    status, payload = _request(
        "PATCH",
        f"https://{domain}/api/v2/client-grants/{grant['id']}",
        token=token,
        body={"scope": needed},
    )
    if status != 200:
        raise SystemExit(f"patch_client_grant_failed status={status} body={payload}")
    print(f"updated Management API scopes → {needed}")


def urllib_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def ensure_action(
    domain: str,
    token: str,
    backup_url: str,
    action_secret: str,
    dry_run: bool,
) -> None:
    code = ACTION_CODE_PATH.read_text(encoding="utf-8")
    status, actions = _request(
        "GET",
        f"https://{domain}/api/v2/actions/actions?triggerId={TRIGGER_ID}&actionName={urllib_quote(ACTION_NAME)}",
        token=token,
    )
    if status != 200:
        raise SystemExit(f"list_actions_failed status={status} body={actions}")
    items = actions.get("actions") if isinstance(actions, dict) else actions
    action = None
    for item in items or []:
        if item.get("name") == ACTION_NAME:
            action = item
            break
    secrets = [
        {"name": "FINOVATE_BACKUP_URL", "value": backup_url},
        {"name": "FINOVATE_ACTION_SECRET", "value": action_secret},
    ]
    body = {
        "name": ACTION_NAME,
        "supported_triggers": [{"id": TRIGGER_ID, "version": "v2"}],
        "code": code,
        "runtime": "node22",
        "secrets": secrets,
        "dependencies": [],
    }
    if action is None:
        if dry_run:
            print(f"[dry-run] POST actions/actions name={ACTION_NAME}")
            action_id = "dry-run"
        else:
            status, payload = _request(
                "POST",
                f"https://{domain}/api/v2/actions/actions",
                token=token,
                body=body,
            )
            if status not in (200, 201):
                raise SystemExit(f"create_action_failed status={status} body={payload}")
            action = payload
            action_id = action["id"]
            print(f"created Action {ACTION_NAME} id={action_id}")
    else:
        action_id = action["id"]
        if dry_run:
            print(f"[dry-run] PATCH actions/actions/{action_id}")
        else:
            status, payload = _request(
                "PATCH",
                f"https://{domain}/api/v2/actions/actions/{action_id}",
                token=token,
                body={
                    "code": code,
                    "runtime": "node22",
                    "secrets": secrets,
                    "dependencies": [],
                },
            )
            if status != 200:
                raise SystemExit(f"patch_action_failed status={status} body={payload}")
            print(f"updated Action {ACTION_NAME} id={action_id}")

    if not dry_run:
        status, payload = _request(
            "POST",
            f"https://{domain}/api/v2/actions/actions/{action_id}/deploy",
            token=token,
            body={},
        )
        if status not in (200, 201):
            raise SystemExit(f"deploy_action_failed status={status} body={payload}")
        print(f"deployed Action {ACTION_NAME}")

    status, bindings = _request(
        "GET",
        f"https://{domain}/api/v2/actions/triggers/{TRIGGER_ID}/bindings",
        token=token,
    )
    if status != 200:
        raise SystemExit(f"get_bindings_failed status={status} body={bindings}")
    current = bindings.get("bindings") if isinstance(bindings, dict) else bindings
    current = list(current or [])
    already = any(
        (b.get("action") or {}).get("id") == action_id
        or (b.get("ref") or {}).get("value") == ACTION_NAME
        for b in current
    )
    if already:
        print(f"Action already bound to {TRIGGER_ID}")
        return
    new_bindings = current + [
        {
            "ref": {"type": "action_name", "value": ACTION_NAME},
            "display_name": ACTION_NAME,
        }
    ]
    if dry_run:
        print(f"[dry-run] PATCH trigger bindings count={len(new_bindings)}")
        return
    status, payload = _request(
        "PATCH",
        f"https://{domain}/api/v2/actions/triggers/{TRIGGER_ID}/bindings",
        token=token,
        body={"bindings": new_bindings},
    )
    if status != 200:
        raise SystemExit(f"bind_action_failed status={status} body={payload}")
    print(f"bound Action to {TRIGGER_ID}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    domain = _env("AUTH0_DOMAIN")
    client_id = _env("AUTH0_MGMT_CLIENT_ID")
    client_secret = _env("AUTH0_MGMT_CLIENT_SECRET")
    base = _env("APP_BASE_URL", "https://finovate.biz").rstrip("/")
    action_secret = _env("AUTH0_ACTION_SECRET")
    if not domain or not client_id or not client_secret:
        print(
            "Missing AUTH0_DOMAIN / AUTH0_MGMT_CLIENT_ID / AUTH0_MGMT_CLIENT_SECRET",
            file=sys.stderr,
        )
        return 2
    if not action_secret:
        print("Missing AUTH0_ACTION_SECRET", file=sys.stderr)
        return 2
    if not ACTION_CODE_PATH.is_file():
        print(f"Missing Action code at {ACTION_CODE_PATH}", file=sys.stderr)
        return 2

    result_url = f"{base}/accounts/verify/result/"
    backup_url = f"{base}/accounts/auth0/hooks/signup/"
    print(f"tenant={domain} base={base}")
    token = management_token(domain, client_id, client_secret)
    ensure_m2m_scopes(domain, token, client_id, args.dry_run)
    ensure_email_template(domain, token, result_url, args.dry_run)
    ensure_action(domain, token, backup_url, action_secret, args.dry_run)
    print("Auth0 dashboard configuration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
