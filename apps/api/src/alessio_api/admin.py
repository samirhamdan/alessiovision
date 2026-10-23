"""Comandos administrativos de linha de comando.

Criar uma organização com o primeiro proprietário (o painel não permite criar
organizações; isso é tarefa de quem opera a plataforma):

    python -m alessio_api.admin create-organization --name "Acme" \\
        --owner-email ana@acme.com.br --owner-name "Ana Souza"

A senha vem de ALESSIO_OWNER_PASSWORD ou é pedida no terminal. Se a pessoa já
tiver conta, ela só ganha o papel de proprietária na nova organização.

Dar ou tirar acesso à área Plataforma (equipe Alessio: contratos de comodato e
equipamentos de todos os clientes):

    python -m alessio_api.admin grant-staff --email voce@alessio.com.br
    python -m alessio_api.admin revoke-staff --email voce@alessio.com.br
"""

import argparse
import getpass
import os
import sys
import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from alessio_api import audit
from alessio_api.db import get_sessionmaker
from alessio_api.models import Membership, Organization, Site, User
from alessio_api.security import hash_password, password_problem
from alessio_api.tenancy import set_tenant


@dataclass(frozen=True)
class CreatedOrganization:
    organization: Organization
    site: Site
    owner: User


def create_organization(
    db: Session,
    name: str,
    owner_email: str,
    owner_name: str,
    owner_password: str | None,
    site_name: str = "Matriz",
    timezone: str = "America/Sao_Paulo",
    organization_id: uuid.UUID | None = None,
) -> CreatedOrganization:
    ZoneInfo(timezone)
    email = owner_email.strip().lower()
    owner = db.scalar(select(User).where(User.email == email))
    if owner is None:
        problem = password_problem(owner_password or "")
        if problem:
            raise ValueError(problem)
        owner = User(
            email=email, name=owner_name.strip(), password_hash=hash_password(owner_password)
        )
        db.add(owner)

    organization = Organization(id=organization_id or uuid.uuid4(), name=name.strip())
    db.add(organization)
    db.flush()
    db.add(Membership(organization_id=organization.id, user_id=owner.id, role="owner"))
    set_tenant(db, organization.id)
    site = Site(organization_id=organization.id, name=site_name.strip(), timezone=timezone)
    db.add(site)
    db.flush()
    audit.record(
        db, organization.id, owner.id, "organization.created", "organization", organization.id
    )
    db.commit()
    return CreatedOrganization(organization, site, owner)


def set_platform_staff(db: Session, email: str, enabled: bool) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise LookupError(f"nenhuma conta com o e-mail {email}; crie a conta antes")
    user.is_platform_staff = enabled
    db.commit()
    return user


def _read_password() -> str:
    password = os.environ.get("ALESSIO_OWNER_PASSWORD")
    if password:
        return password
    first = getpass.getpass("Senha do proprietário: ")
    if first != getpass.getpass("Repita a senha: "):
        raise SystemExit("erro: as senhas não conferem")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alessio_api.admin")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-organization", help="cria organização e proprietário")
    create.add_argument("--name", required=True)
    create.add_argument("--owner-email", required=True)
    create.add_argument("--owner-name", required=True)
    create.add_argument("--site-name", default="Matriz")
    create.add_argument("--timezone", default="America/Sao_Paulo")
    for name, text in (
        ("grant-staff", "dá acesso à área Plataforma"),
        ("revoke-staff", "tira o acesso"),
    ):
        staff = commands.add_parser(name, help=text)
        staff.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    if args.command in ("grant-staff", "revoke-staff"):
        with get_sessionmaker()() as db:
            try:
                user = set_platform_staff(db, args.email, args.command == "grant-staff")
            except LookupError as exc:
                print(f"erro: {exc}", file=sys.stderr)
                return 1
        state = "tem" if user.is_platform_staff else "não tem mais"
        print(f"{user.email} {state} acesso à área Plataforma.")
        return 0

    with get_sessionmaker()() as db:
        existing = db.scalar(select(User).where(User.email == args.owner_email.strip().lower()))
        password = None if existing else _read_password()
        try:
            created = create_organization(
                db,
                args.name,
                args.owner_email,
                args.owner_name,
                password,
                args.site_name,
                args.timezone,
            )
        except ValueError as exc:
            print(f"erro: {exc}", file=sys.stderr)
            return 1
    print(f"organização {created.organization.name}: {created.organization.id}")
    print(f"proprietário: {created.owner.email}")
    print(f"local: {created.site.name} ({created.site.timezone})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
