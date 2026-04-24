"""CLI to mint a user invite and print the share-ready URL.

Usage:
    python -m src.scripts.create_invite \
        --email arturo@intuno.ai \
        --note "beta-2026-04" \
        --max-uses 1

Writes the new row directly to the DB via the repository layer. Use
this instead of the HTTP admin endpoint for operator tasks (no need to
hold the service key in a shell env when you're already root on the box).
"""

import argparse
import asyncio
from datetime import datetime, timezone

from src.database import async_session_factory
from src.repositories.invite import InviteRepository
from src.models.user_invite import UserInvite
from src.services.invite import _build_url, _gen_token


async def _run(email: str | None, note: str | None, max_uses: int) -> None:
    async with async_session_factory() as session:
        repo = InviteRepository(session)
        invite = UserInvite(
            token=_gen_token(),
            email=email,
            note=note,
            max_uses=max_uses,
            use_count=0,
        )
        saved = await repo.create(invite)

    print(f"Invite created: {saved.id}")
    print(f"  token: {saved.token}")
    print(f"  email: {saved.email or '(any)'}")
    print(f"  max_uses: {saved.max_uses}")
    print(f"  note: {saved.note or ''}")
    print(f"  URL:  {_build_url(saved.token)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a user invite.")
    parser.add_argument("--email", help="Email to lock the invite to (optional)")
    parser.add_argument("--note", help="Internal label (optional)")
    parser.add_argument(
        "--max-uses",
        type=int,
        default=1,
        help="How many times the invite can be redeemed (default: 1)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.email, args.note, args.max_uses))


if __name__ == "__main__":
    main()
