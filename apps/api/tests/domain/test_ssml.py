from xml.etree import ElementTree as ET

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.ssml import build_ssml, tts_hash

NS = "{http://www.w3.org/2001/10/synthesis}"


def test_markup_in_text_is_escaped_not_parsed():
    ssml = build_ssml("</voice><audio src='http://x'/>", voice="en-US-JennyNeural", locale="en-US")
    root = ET.fromstring(ssml)
    assert root.find(f".//{NS}audio") is None and len(root.findall(f".//{NS}voice")) == 1


@given(st.text(min_size=1, max_size=200))
def test_any_text_gives_well_formed_ssml_that_speaks_the_cleaned_text(text):
    cleaned = "".join(c for c in text if c in "\t\n\r" or ord(c) >= 0x20 and c not in "￾￿")
    if not cleaned.strip():
        return
    root = ET.fromstring(build_ssml(text, voice="en-US-JennyNeural", locale="en-US"))
    assert "".join(root.itertext()) == cleaned


def test_rate_adds_prosody_only_when_nonzero():
    assert "prosody" not in build_ssml("hi", voice="en-US-JennyNeural", locale="en-US")
    assert "<prosody rate='-25%'>" in build_ssml(
        "hi", voice="en-US-JennyNeural", locale="en-US", rate_percent=-25
    )


@pytest.mark.parametrize("kw", [{"voice": "en-US-Jenny'Neural"}, {"locale": "en_US"}, {"rate_percent": -51}])
def test_rejects_bad_voice_locale_rate(kw):
    with pytest.raises(ValueError):
        build_ssml("hi", **({"voice": "en-US-JennyNeural", "locale": "en-US"} | kw))


def test_tts_hash_is_hex_and_depends_on_every_field():
    h = tts_hash("vest", voice="en-US-JennyNeural", rate_percent=0)
    assert len(h) == 64 and int(h, 16) >= 0
    assert len(
        {
            h,
            tts_hash("west", voice="en-US-JennyNeural", rate_percent=0),
            tts_hash("vest", voice="en-US-AvaNeural", rate_percent=0),
            tts_hash("vest", voice="en-US-JennyNeural", rate_percent=-25),
        }
    ) == 4
