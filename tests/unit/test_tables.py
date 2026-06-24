from datetime import timedelta

import pytest

from titania.i18n.translator import Translator
from titania.presentation.tables import humanize_remaining


@pytest.fixture
def en() -> Translator:
    return Translator("en")


@pytest.fixture
def it() -> Translator:
    return Translator("it")


def test_humanize_under_an_hour_english(en: Translator):
    assert humanize_remaining(timedelta(minutes=23), en) == "in 23m"


def test_humanize_over_an_hour_english(en: Translator):
    assert humanize_remaining(timedelta(hours=1, minutes=5), en) == "in 1h 05m"


def test_humanize_zero_or_negative_is_expired_english(en: Translator):
    assert humanize_remaining(timedelta(seconds=0), en) == "expired"
    assert humanize_remaining(timedelta(seconds=-1), en) == "expired"


def test_humanize_under_an_hour_italian(it: Translator):
    assert humanize_remaining(timedelta(minutes=23), it) == "tra 23m"


def test_humanize_over_an_hour_italian(it: Translator):
    assert humanize_remaining(timedelta(hours=1, minutes=5), it) == "tra 1h 05m"


def test_humanize_expired_italian(it: Translator):
    assert humanize_remaining(timedelta(seconds=-1), it) == "scaduto"
