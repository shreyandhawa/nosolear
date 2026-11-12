"""Recording sets for the Phase 0b spikes. Item ids follow the controller's R13 ruling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationItem:
    id: str
    word: str
    error_key: str
    deliberate: bool
    instruction: str


# error_key -> (sound description, [(word, respelling), ...])
_SPEC: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "sound.sub.v.w": ("W instead of V", [("vest", "west"), ("very", "werry"), ("van", "wan")]),
    "sound.sub.w.v": ("V instead of W", [("west", "vest"), ("wine", "vine")]),
    "sound.sub.f.p": ("P instead of F", [("fan", "pan"), ("fine", "pine"), ("coffee", "coppee")]),
    "sound.sub.θ.t": ("T instead of TH", [("think", "tink"), ("three", "tree"), ("thanks", "tanks")]),
    "sound.sub.ð.d": ("D instead of the voiced TH", [("this", "dis"), ("they", "day")]),
    "sound.sub.ʃ.s": ("S instead of SH", [("ship", "sip"), ("she", "see"), ("shop", "sop")]),
    "sound.sub.s.ʃ": ("SH instead of S", [("sip", "ship"), ("see", "she")]),
    "sound.sub.z.dʒ": ("a J sound instead of Z", [("zoo", "joo"), ("zero", "jero")]),
    "sound.sub.z.s": ("S instead of Z", [("zip", "sip"), ("buzz", "buss")]),
    "sound.ins.epenthesis_sC": (
        "a vowel before it",
        [("school", "ischool"), ("speak", "ispeak"), ("street", "istreet"), ("sport", "isport")],
    ),
}


def _build() -> list[CalibrationItem]:
    items: list[CalibrationItem] = []
    for key, (desc, words) in _SPEC.items():
        for word, respelled in words:
            items.append(
                CalibrationItem(
                    f"{word}__correct", word, key, False,
                    f'Say "{word}" as correctly as possible, in General American.',
                )
            )
            for n in (1, 2):
                if key == "sound.ins.epenthesis_sC":
                    text = f'Say "{word}" with {desc} — "{respelled}"'
                else:
                    text = f'Say "{word}" with {desc} — sounds like "{respelled}"'
                items.append(CalibrationItem(f"{word}__err{n}", word, key, True, f"{text} (take {n} of 2)"))
    return items


CALIBRATION: list[CalibrationItem] = _build()

READ_ALOUD: list[str] = [
    "Seven vivid vans veered west through the village.",
    "Fifty fine coffee fans found fresh fish for lunch.",
    "These three thin brothers thought they should thank them.",
    "She sells shiny ships in the shop near the sea.",
    "Zoe's zero-zip score buzzed on the screen at school.",
]

FREE_TALK_PROMPT = "Describe a place you love to visit and why."

assert len(CALIBRATION) == 78 and len({c.id for c in CALIBRATION}) == 78
assert all(len(s.split()) < 15 for s in READ_ALOUD) and len(READ_ALOUD) == 5
