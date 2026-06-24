from titania.i18n.translator import Translator


def test_english_catalog_loads_top_level_key():
    t = Translator("en")
    assert t.t("embed.title") == "Active Void Fissures"


def test_italian_catalog_loads_top_level_key():
    t = Translator("it")
    assert t.t("embed.title") == "Fissure del Vuoto attive"


def test_unknown_locale_falls_back_to_default():
    t = Translator("xx-unknown")
    assert t.locale == "en"
    assert t.t("embed.section.normal") == "Normal"


def test_missing_key_falls_back_to_english_then_to_key_itself():
    t = Translator("it")
    # A key that doesn't exist in either catalog returns the key string itself
    # so the bot never crashes on a typo.
    assert t.t("does.not.exist") == "does.not.exist"


def test_format_substitution_works():
    t = Translator("en")
    assert t.t("humanize.minutes", m=15) == "in 15m"
    assert t.t("humanize.hours_minutes", h=1, m=5) == "in 1h 05m"


def test_italian_humanize_strings_render():
    t = Translator("it")
    assert t.t("humanize.minutes", m=23) == "tra 23m"
    assert t.t("humanize.expired") == "scaduto"
