"""Testy trwałej konfiguracji per-gildia."""

from __future__ import annotations

from nyxio.core.guild_config import GuildConfigStore


async def test_default_volume(tmp_path):
    store = GuildConfigStore(str(tmp_path / "cfg.json"))
    await store.load()
    assert store.get_default_volume(1) == 100  # domyślna
    await store.set_default_volume(1, 45)
    assert store.get_default_volume(1) == 45


async def test_autoplay_default_and_persist(tmp_path):
    path = str(tmp_path / "cfg.json")
    store = GuildConfigStore(path)
    await store.load()
    assert store.get_autoplay(5) is False
    await store.set_autoplay(5, True)
    assert store.get_autoplay(5) is True

    reloaded = GuildConfigStore(path)
    await reloaded.load()
    assert reloaded.get_autoplay(5) is True


async def test_default_volume_persists(tmp_path):
    path = str(tmp_path / "cfg.json")
    store = GuildConfigStore(path)
    await store.load()
    await store.set_default_volume(7, 60)

    reloaded = GuildConfigStore(path)
    await reloaded.load()
    assert reloaded.get_default_volume(7) == 60


async def test_dj_and_volume_coexist(tmp_path):
    store = GuildConfigStore(str(tmp_path / "cfg.json"))
    await store.load()
    await store.set_dj_role_id(9, 111)
    await store.set_default_volume(9, 80)
    assert store.get_dj_role_id(9) == 111
    assert store.get_default_volume(9) == 80


async def test_set_and_get(tmp_path):
    store = GuildConfigStore(str(tmp_path / "cfg.json"))
    await store.load()
    assert store.get_dj_role_id(1) is None
    await store.set_dj_role_id(1, 999)
    assert store.get_dj_role_id(1) == 999


async def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "cfg.json")
    store = GuildConfigStore(path)
    await store.load()
    await store.set_dj_role_id(42, 777)

    reloaded = GuildConfigStore(path)
    await reloaded.load()
    assert reloaded.get_dj_role_id(42) == 777


async def test_clear_role(tmp_path):
    store = GuildConfigStore(str(tmp_path / "cfg.json"))
    await store.load()
    await store.set_dj_role_id(5, 123)
    await store.set_dj_role_id(5, None)
    assert store.get_dj_role_id(5) is None


async def test_corrupt_file_is_tolerated(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("{ not valid json", encoding="utf-8")
    store = GuildConfigStore(str(path))
    await store.load()  # nie rzuca
    assert store.get_dj_role_id(1) is None
