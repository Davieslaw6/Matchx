"""CLI-only owner provisioning. Run from backend: python -m app.owner_cli create-owner|reset-owner-password."""
import argparse
import asyncio
from getpass import getpass
from argon2 import PasswordHasher
from sqlalchemy import delete, select
from app.db import SessionLocal
from app.models import OwnerAccount, Session, utcnow

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

def read_password() -> str:
    password = getpass("Owner password (minimum 14 characters): ")
    confirm = getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 14:
        raise SystemExit("Password must contain at least 14 characters.")
    return password

async def provision(reset: bool) -> None:
    password = read_password()
    async with SessionLocal() as db:
        owner = await db.scalar(select(OwnerAccount).limit(1))
        if owner and not reset:
            raise SystemExit("An owner already exists. Use reset-owner-password to rotate it.")
        if owner:
            owner.password_hash = hasher.hash(password)
            owner.password_changed_at = utcnow()
            await db.execute(delete(Session))
        else:
            db.add(OwnerAccount(id=1, password_hash=hasher.hash(password)))
        await db.commit()
    print("Owner credentials updated. No password was written to disk.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-owner", "reset-owner-password"])
    args = parser.parse_args()
    asyncio.run(provision(reset=args.command == "reset-owner-password"))

if __name__ == "__main__":
    main()
