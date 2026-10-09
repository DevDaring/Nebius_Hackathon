"""Numeric grounding verifier (agent/verifier.py)."""

from __future__ import annotations

import pytest

from nemotwins.agent.verifier import extract_numbers, normalise_digits, verify

TOOLS = [{
    "estimate": 156.4, "band": {"lo": 131.2, "hi": 181.7}, "p_high_2h": {"p": 0.32, "lo": 0.2, "hi": 0.45},
    "peak": {"t": "2026-10-05T21:40", "value": 157.8}, "now": "2026-10-05T19:30",
    "expected_gain_pct": 23.4,
}]


@pytest.mark.parametrize("text,expected", [
    ("血糖値はおよそ１５６です", [156.0]),          # full-width digits
    ("血糖値はおよそ156です", [156.0]),             # a number between kana / kanji is still a number
    ("15分後にもう一度", [15.0]),
    ("7,2 mmol/L", [7.2]),                          # decimal comma
    ("HbA1c", []),                                  # not a number inside a Latin word
    ("between 131 and 182", [131.0, 182.0]),
    ("1,200 steps", [1200.0]),
    ("peak 157.8", [157.8]),
    ("at 9:40 pm", [9.0, 40.0]),
])
def test_extract_numbers(text: str, expected: list[float]) -> None:
    assert extract_numbers(text) == expected


def test_normalise_digits_full_width() -> None:
    assert normalise_digits("０１２３４５６７８９ ２１：４０ ７，２") == "0123456789 21:40 7,2"


@pytest.mark.parametrize("reply", [
    "Right now your glucose is about 156, most likely between 131 and 182.",
    "Ahora mismo su glucosa está en torno a 156, lo más probable entre 131 y 182.",
    "Ihr Blutzucker liegt gerade bei etwa 156, sehr wahrscheinlich zwischen 131 und 182.",
    "現在の血糖値はおよそ１５６で、131から182の間である可能性が高いです。",
    "Su glucosa podría alcanzar un pico cercano a 158 hacia las 21:40.",  # 24-hour clock
    "La probabilità di superare 180 è circa 3 volte su 10.",
    "Your glucose may peak near 158 around 9:40 pm.",           # rounding + time from an ISO string
    "It may peak at about 160 around 9:40 pm.",                 # 157.8 -> "about 160" is fine
    "The chance of going above 180 is about 3 times out of 10.",  # p=0.32 -> "3 in 10"
    "The chance is 32 percent; the next reading cuts uncertainty by 23 percent.",
    "Less than 1 time in 10; target 70 to 180.",
])
def test_grounded_replies_pass(reply: str) -> None:
    g = verify(reply, TOOLS)
    assert g["passed"], g


@pytest.mark.parametrize("reply,bad", [
    ("Your glucose will reach 250 tonight.", "250"),
    ("It may peak near 170.", "170"),          # 157.8 is not "about 170"
    ("Take a reading at 6:15 am.", "15"),      # 6 is not a tool time either, 15 definitely not
    ("血糖値は２１０になるかもしれません", "210"),  # full-width digits, ungrounded
    ("Call 108 now.", "108"),                    # no hard-coded emergency number is "fixed"
    ("Su glucosa llegará a 250,5.", "250.5"),      # decimal comma read as a decimal
    ("The chance is 55 percent.", "55"),
])
def test_ungrounded_numbers_caught(reply: str, bad: str) -> None:
    g = verify(reply, TOOLS)
    assert not g["passed"]
    assert bad in g["ungrounded"]


def test_numbers_from_user_message_are_allowed() -> None:
    g = verify("Thanks, I added your reading of 212.", TOOLS, user_text="血糖値は２１２でした")
    assert g["passed"], g


def test_signed_change_is_grounded() -> None:
    g = verify("Your peak changes by -12 and the chance moves from 62 to 50 percent.",
               [{"delta_peak": -12.3, "p_high_baseline": 0.618, "p_high_scenario": 0.502}])
    assert g["passed"], g


@pytest.mark.parametrize("text,lang,problems", [
    ("Your peak may reach 180 around 9 pm.", "en-US", []),
    ("ok.", "en-US", ["too_short"]),
    ("Your peak may reach 180 around", "en-US", ["unfinished"]),
    ("Peak 175:\nYour sugar may rise tonight.", "en-US", ["fragment_line"]),
    ("180:\nYour sugar may rise tonight.", "en-US", ["fragment_line"]),
    ("Su glucosa está en torno a 155 ahora.", "es-ES", []),
    ("La glycémie pourrait atteindre 180 vers 21:40 ?", "fr-FR", []),
    ("現在の血糖値はおよそ155です。", "ja-JP", []),
    ("Your sugar is about 155 today.", "ja-JP", ["wrong_script"]),
    ("現在の血糖値はおよそ155です。", "de-DE", ["wrong_script"]),
    ("現在の血糖値はおよそ155です", "ja-JP", ["unfinished"]),
])
def test_sanity(text: str, lang: str, problems: list[str]) -> None:
    from nemotwins.agent.verifier import sanity

    assert sanity(text, lang) == problems
