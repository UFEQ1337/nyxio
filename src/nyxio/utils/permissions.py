"""Kontrola dostępu do komend muzycznych.

Reguła: administrator gildii zawsze może. Jeśli skonfigurowano rolę DJ
(NYXIO_DJ_ROLE_ID), dodatkowo dozwoleni są jej posiadacze, a wszyscy
pozostali — zablokowani. Brak roli DJ = dostęp dla każdego.
"""

from __future__ import annotations

import discord


def is_allowed(member: discord.Member, dj_role_id: int | None) -> bool:
    if member.guild_permissions.administrator:
        return True
    if dj_role_id is None:
        return True
    return any(role.id == dj_role_id for role in member.roles)
