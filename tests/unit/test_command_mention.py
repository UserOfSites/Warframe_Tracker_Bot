import logging
from types import SimpleNamespace

from titania.bot import TitaniaBot


def _stub(ids):
    # command_mention only touches _app_command_ids / _warned_missing_mentions,
    # so a lightweight stand-in avoids constructing a full discord bot.
    return SimpleNamespace(_app_command_ids=ids, _warned_missing_mentions=set())


def test_mention_resolves_when_command_id_known():
    obj = _stub({"vendors": 42})
    assert TitaniaBot.command_mention(obj, "vendors inventory") == "</vendors inventory:42>"


def test_mention_none_when_command_id_missing():
    obj = _stub({})
    assert TitaniaBot.command_mention(obj, "vendors inventory") is None


def test_mention_warns_once_per_root(caplog):
    obj = _stub({})
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            TitaniaBot.command_mention(obj, "vendors inventory")
        TitaniaBot.command_mention(obj, "vendors baro")  # same root -> no new warn
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "vendors" in warnings[0].getMessage()
