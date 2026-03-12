"""
Inject per-agent API key credentials for all registered agents.

Use when wisdom-agents uses AGENTS_API_KEY and the broker needs per-agent
credentials. Matches the key wisdom-agents expects so broker→agent calls succeed.

Prerequisites:
  - Wisdom backend DB migrated (agent_credentials table exists)
  - At least one agent registered

Usage:
  cd wisdom
  python scripts/inject_agent_credentials.py --api-key "your-agents-api-key"
  AGENTS_API_KEY="..." python scripts/inject_agent_credentials.py

  To use wisdom-agents .env:
  export AGENTS_API_KEY=$(grep '^AGENTS_API_KEY=' ../wisdom-agents/.env | cut -d= -f2- | tr -d '"')
  python scripts/inject_agent_credentials.py
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root for imports
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Inject per-agent API key for all agents")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AGENTS_API_KEY"),
        help="API key to inject (must match wisdom-agents AGENTS_API_KEY)",
    )
    parser.add_argument("--header", default=None, help="Header name (e.g. X-API-Key). Default: X-API-Key")
    parser.add_argument("--scheme", default=None, help="Scheme (e.g. Bearer for Authorization header)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: --api-key or AGENTS_API_KEY env required", file=sys.stderr)
        return 1

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    from src.core.settings import settings
    from src.core.credential_crypto import encrypt_credential
    from src.models.registry import Agent, AgentCredential

    if not settings.DATABASE_URL:
        print("Error: DATABASE_URL not set", file=sys.stderr)
        return 1

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.is_active)
        )
        agents = list(result.scalars().all())

    if not agents:
        print("No active agents found. Register agents first.")
        return 0

    encrypted = encrypt_credential(args.api_key)

    if args.dry_run:
        for a in agents:
            print(f"Would upsert api_key for agent {a.agent_id} ({a.name})")
        return 0

    async with async_session() as session:
        for agent in agents:
            existing = await session.execute(
                select(AgentCredential).where(
                    AgentCredential.agent_id == agent.id,
                    AgentCredential.credential_type == "api_key",
                )
            )
            cred = existing.scalar_one_or_none()
            if cred:
                cred.encrypted_value = encrypted
                cred.auth_header = args.header
                cred.auth_scheme = args.scheme
            else:
                session.add(
                    AgentCredential(
                        agent_id=agent.id,
                        credential_type="api_key",
                        encrypted_value=encrypted,
                        auth_header=args.header,
                        auth_scheme=args.scheme,
                    )
                )
        await session.commit()

    print(f"Injected api_key credential for {len(agents)} agent(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
