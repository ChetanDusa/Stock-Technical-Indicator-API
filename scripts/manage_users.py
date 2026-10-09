"""Local administrative account management. Generated API keys are shown once."""

import argparse
import re
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.security import generate_api_key, hash_api_key
from app.core.tiers import TIER_LIMITS
from database import SessionLocal
from models import User


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--tier", choices=TIER_LIMITS, default="free")
    for name in ("rotate", "revoke"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
    tier = commands.add_parser("set-tier")
    tier.add_argument("--username", required=True)
    tier.add_argument("--tier", choices=TIER_LIMITS, required=True)
    commands.add_parser("list")
    args = parser.parse_args()

    if hasattr(args, "username") and not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", args.username):
        parser.error("Username must contain 1-64 letters, digits, dots, dashes or underscores")

    try:
        with SessionLocal() as session, session.begin():
            if args.command == "list":
                for user in session.scalars(select(User).order_by(User.id)):
                    print(f"{user.id}\t{user.username}\t{user.subscription}")
                return
            user = session.scalar(select(User).where(User.username == args.username))
            if args.command == "create":
                if user is not None:
                    parser.exit(1, "Username already exists\n")
                api_key = generate_api_key()
                session.add(
                    User(
                        username=args.username,
                        api_key_hash=hash_api_key(api_key),
                        subscription=args.tier,
                    )
                )
            else:
                if user is None:
                    parser.exit(1, "User not found\n")
                if args.command == "rotate":
                    api_key = generate_api_key()
                    user.api_key_hash = hash_api_key(api_key)
                elif args.command == "revoke":
                    session.delete(user)
                else:
                    user.subscription = args.tier
        # Display secrets only after the transaction commits successfully.
        if args.command in {"create", "rotate"}:
            print(f"API key for {args.username} (save it now): {api_key}")
        else:
            print(f"{args.command} completed for {args.username}")
    except IntegrityError:
        print("Account conflicts with an existing username or API key", file=sys.stderr)
        raise SystemExit(1) from None
    except SQLAlchemyError:
        print("Database operation failed; verify configuration and run migrations", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
