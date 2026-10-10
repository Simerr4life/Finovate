"""Interactive terminal chat loop against the assistant — no Photon
required. This is the fully-working way to demo/test the messaging
assistant today, independent of whether the real iMessage wiring ends up
matching the documented-but-unverified webhook shape.

Usage: python manage.py chat_demo --username demo
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from assistant.services import handle_incoming_message


class Command(BaseCommand):
    help = "Interactive terminal chat loop against the Finovate assistant (no Photon needed)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            self.stderr.write(f"No such user '{options['username']}'. Run seed_demo first.")
            return

        self.stdout.write(self.style.SUCCESS(
            f"Chatting as '{user.username}'. Type 'help' for commands, Ctrl+C or 'quit' to exit."
        ))
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("\nBye.")
                break
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            reply = handle_incoming_message(user, text)
            self.stdout.write(f"finovate> {reply}")
