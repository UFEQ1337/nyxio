"""Testy parsera wyjścia generatora poToken (tools/pot_refresher).

Parser jest jedynym miejscem, które zakłada cokolwiek o formacie wyjścia
obcego obrazu — czyli tym, co najpewniej pęknie przy jego aktualizacji.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "pot_refresher" / "refresher.py"


def _load():
    spec = importlib.util.spec_from_file_location("pot_refresher", _MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def refresher():
    return _load()


def test_parses_key_value_output(refresher):
    text = "visitor_data: CgtBBBBBBBBBBBB%3D%3D\npo_token: MnQ0aaaaaaaaaaaa\n"
    assert refresher.parse_pot(text) == ("CgtBBBBBBBBBBBB%3D%3D", "MnQ0aaaaaaaaaaaa")


def test_parses_json_output(refresher):
    text = '{"visitorData": "abc", "poToken": "xyz"}'
    assert refresher.parse_pot(text) == ("abc", "xyz")


def test_parses_json_with_snake_case_keys(refresher):
    text = 'jakis szum\n{"visitor_data": "abc", "potoken": "xyz"}\nkoniec'
    assert refresher.parse_pot(text) == ("abc", "xyz")


def test_ignores_noise_around_pair(refresher):
    text = (
        "[INFO] uruchamiam przegladarke\n"
        "visitor_data = AAA\n"
        "[INFO] gotowe\n"
        "po_token = BBB\n"
    )
    assert refresher.parse_pot(text) == ("AAA", "BBB")


def test_half_pair_is_rejected(refresher):
    """Niesparowana wartość jest gorsza niż jej brak — YouTube zwraca wtedy
    'Video player configuration error', co trudno powiązać z przyczyną."""
    assert refresher.parse_pot("visitor_data: AAA\n") is None
    assert refresher.parse_pot("po_token: BBB\n") is None


def test_empty_output(refresher):
    assert refresher.parse_pot("") is None
