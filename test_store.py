"""Offline SQLite tests. Run after installing requirements."""
import tempfile
from pathlib import Path
from bot import Store

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'test.sqlite3'
    store = Store(path)
    assert store.settings(-1)['rp'] == 1
    store.set(-1, 'rp', 0)
    assert store.settings(-1)['rp'] == 0
    assert store.settings(-2)['rp'] == 1
    store.user(-1, 1, 'A')
    store.user(-1, 2, 'B')
    store.user(-2, 1, 'A elsewhere')
    assert store.activity(-1, 1, 'A renamed', 1000)
    assert not store.activity(-1, 1, 'A renamed', 1030)
    assert store.activity(-1, 1, 'A renamed', 1060)
    assert store.get(-1, 1)['xp'] == 10
    assert store.get(-2, 1)['xp'] == 0
    assert store.give_rep(-1, 1, 2, '2026-10-25')
    assert not store.give_rep(-1, 1, 2, '2026-10-25')
    assert store.give_rep(-1, 1, 2, '2026-10-26')
    assert store.get(-1, 2)['rep'] == 2
    assert store.warns(-1, 2) == 1
    assert store.warns(-1, 2, reset=True) == 0
    store.allow_rp(-1, 2, False)
    assert not store.get(-1, 2)['rp_allowed']
    assert store.top(-1)[0]['uid'] == 1
    store.db.close()
    store = Store(path)
    assert store.get(-1, 1)['xp'] == 10
    assert store.settings(-1)['rp'] == 0
    store.db.close()
print('PASS: settings, chat isolation, XP cooldown, daily reputation, warnings, RP consent, persistence')
