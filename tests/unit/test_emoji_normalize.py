from titania.services.emoji_registry import _normalize_emoji_name


def test_strips_extension():
    assert _normalize_emoji_name("PrismaGrakata.png") == "wf_prismagrakata"


def test_lowercases_and_replaces_non_alnum():
    assert _normalize_emoji_name("Ki'Teer Sentinel Mask.png") == "wf_ki_teer_sentinel_mask"


def test_collapses_repeated_underscores():
    assert _normalize_emoji_name("Foo---Bar  Baz.png") == "wf_foo_bar_baz"


def test_clamps_to_thirty_two_chars():
    out = _normalize_emoji_name("ThisIsAReallyLongItemNameThatWouldExceedDiscordLimits.png")
    assert len(out) <= 32
    assert out.startswith("wf_")


def test_empty_or_punctuation_only_falls_back_to_item():
    assert _normalize_emoji_name("---.png") == "wf_item"
