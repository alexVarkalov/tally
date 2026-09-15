from __future__ import annotations

import pytest

from tally.i18n import _MESSAGES, LOCALE, t


def test_single_locale_table() -> None:
    assert set(_MESSAGES) == {LOCALE}


def test_t_interpolates() -> None:
    assert "Europe/Warsaw" in t("timezone_updated", timezone="Europe/Warsaw")


def test_t_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        t("no_such_key")
