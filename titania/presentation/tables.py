from datetime import timedelta

from titania.i18n.translator import Translator


def humanize_remaining(remaining: timedelta, translator: Translator) -> str:
    total = int(remaining.total_seconds())
    if total <= 0:
        return translator.t("humanize.expired")
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours > 0:
        return translator.t("humanize.hours_minutes", h=hours, m=minutes)
    return translator.t("humanize.minutes", m=minutes)
