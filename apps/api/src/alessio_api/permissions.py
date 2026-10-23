"""Papéis e permissões. Cada papel inclui as permissões do anterior."""

from enum import StrEnum


class Permission(StrEnum):
    OCCURRENCES_READ = "occurrences:read"
    CAMERAS_READ = "cameras:read"
    METRICS_READ = "metrics:read"
    OCCURRENCES_REVIEW = "occurrences:review"
    AGENTS_MANAGE = "agents:manage"
    SITES_MANAGE = "sites:manage"
    MEMBERS_MANAGE = "members:manage"
    AUDIT_READ = "audit:read"
    OWNERS_MANAGE = "owners:manage"


ROLES = ("viewer", "operator", "admin", "owner")

_VIEWER = {Permission.OCCURRENCES_READ, Permission.CAMERAS_READ, Permission.METRICS_READ}
_OPERATOR = _VIEWER | {Permission.OCCURRENCES_REVIEW}
_ADMIN = _OPERATOR | {
    Permission.AGENTS_MANAGE,
    Permission.SITES_MANAGE,
    Permission.MEMBERS_MANAGE,
    Permission.AUDIT_READ,
}
_OWNER = _ADMIN | {Permission.OWNERS_MANAGE}

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "viewer": frozenset(_VIEWER),
    "operator": frozenset(_OPERATOR),
    "admin": frozenset(_ADMIN),
    "owner": frozenset(_OWNER),
}
