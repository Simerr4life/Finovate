"""Retry failed Auth0 signup backups and reconcile drift from Profile rows.

Usage:
  python manage.py reconcile_auth0_backups
  python manage.py reconcile_auth0_backups --limit 200
"""

from django.core.management.base import BaseCommand

from accounts.auth0_backup import reconcile_from_profiles


class Command(BaseCommand):
    help = "Reconcile Auth0 user backup rows in Supabase/Postgres and retry failures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum profiles / pending rows to process (default 500).",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        result = reconcile_from_profiles(limit=limit)
        self.stdout.write(
            self.style.SUCCESS(
                "auth0 backups reconcile "
                f"created={result['created']} updated={result['updated']} "
                f"synced={result['synced']} failed={result['failed']}"
            )
        )
