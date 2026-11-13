"""Choose each skill's focus and the day's one re-check probe (ARCHITECTURE §6.6).

The choice is Thompson sampling: each candidate key draws a miss rate from its Beta state and
the draw is weighted by impact. The randomness is seeded from the date, so a plan is fixed for
its day and reproducible in tests.
"""

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from random import Random
from typing import Literal

from nosolear.domain.packs import LanguagePack
from nosolear.domain.profile import Profile, ProfileEntry
from nosolear.domain.rechecks import RecheckState
from nosolear.domain.status import Status
from nosolear.domain.taxonomy import KeyDefinition, Skill, Taxonomy

SKILL_ORDER: tuple[Skill, ...] = (Skill.SOUNDS, Skill.ON_THE_SPOT, Skill.ARTICULATE)


@dataclass(frozen=True, slots=True)
class SelectionConfig:
    max_streak: int = 3
    streak_ratio: float = 2.0
    focus_statuses: frozenset[Status] = frozenset({Status.ACTIVE, Status.IMPROVING, Status.UNKNOWN})


DEFAULT_SELECTION = SelectionConfig()


@dataclass(frozen=True, slots=True)
class Focus:
    skill: Skill
    error_key: str
    impact: int
    status: Status
    p_hat: float
    sampled_rate: float
    score: float
    runner_up_score: float | None
    provisional: bool
    source: Literal["profile", "fallback"]


@dataclass(frozen=True, slots=True)
class RecheckProbe:
    skill: Skill
    error_key: str
    due_at: datetime


@dataclass(frozen=True, slots=True)
class Selection:
    foci: tuple[Focus, ...]
    probe: RecheckProbe | None


def seed_for_date(day: date) -> int:
    """A 64-bit seed from the ISO date. Python's `hash()` is salted per process, so it is not used."""
    digest = hashlib.sha256(day.isoformat().encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True, slots=True)
class _Candidate:
    definition: KeyDefinition
    a: float
    b: float
    p_hat: float
    status: Status
    provisional: bool
    source: Literal["profile", "fallback"]


@dataclass(frozen=True, slots=True)
class _Scored:
    candidate: _Candidate
    rate: float
    score: float


def _require_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def _score(seed: int, candidate: _Candidate) -> _Scored:
    """One generator per key, so a key's draw does not depend on the other keys or their order.

    That keeps a day's plan stable when unrelated keys appear or disappear, and makes the result
    independent of the order the profile lists its entries in.
    """
    key = candidate.definition.key
    rate = Random(f"{seed}:{key}").betavariate(candidate.a, candidate.b)
    return _Scored(candidate, rate, rate * candidate.definition.impact)


def _from_entry(entry: ProfileEntry) -> _Candidate:
    return _Candidate(
        definition=entry.definition,
        a=entry.state.a,
        b=entry.state.b,
        p_hat=entry.estimate.p_hat,
        status=entry.status,
        provisional=entry.provisional,
        source="profile",
    )


def _fallback_pool(
    *,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    skill: Skill,
    owned: frozenset[str],
    is_scored: Callable[[str], bool],
) -> list[_Candidate]:
    """Defined keys the learner has no profile entry for: sampled from the pack's prior."""
    pool: list[_Candidate] = []
    for definition in taxonomy.defined():
        if definition.skill is not skill or definition.key in owned:
            continue
        if not is_scored(definition.key):
            continue
        prior = pack.prior_for(definition.key)
        pool.append(
            _Candidate(
                definition=definition,
                a=prior.a0,
                b=prior.b0,
                p_hat=prior.a0 / (prior.a0 + prior.b0),
                status=Status.UNKNOWN,
                provisional=False,
                source="fallback",
            )
        )
    return pool


def _focus_for(
    *,
    seed: int,
    candidates: Sequence[_Candidate],
    recent: Sequence[str],
    config: SelectionConfig,
) -> Focus | None:
    if not candidates:
        return None
    ranked = sorted(
        (_score(seed, c) for c in candidates),
        key=lambda s: (-s.score, s.candidate.definition.key),
    )
    winner = ranked[0]
    streak = config.max_streak > 0 and len(recent) >= config.max_streak
    streak = streak and all(
        key == winner.candidate.definition.key for key in recent[: config.max_streak]
    )
    chosen_index = 0
    if streak and len(ranked) > 1 and winner.score < config.streak_ratio * ranked[1].score:
        chosen_index = 1
    chosen = ranked[chosen_index]
    # The best score among the other candidates: the winner's, when the runner-up was chosen.
    others = [s for i, s in enumerate(ranked) if i != chosen_index]
    runner_up = others[0].score if others else None
    return Focus(
        skill=chosen.candidate.definition.skill,
        error_key=chosen.candidate.definition.key,
        impact=chosen.candidate.definition.impact,
        status=chosen.candidate.status,
        p_hat=chosen.candidate.p_hat,
        sampled_rate=chosen.rate,
        score=chosen.score,
        runner_up_score=runner_up,
        provisional=chosen.candidate.provisional,
        source=chosen.candidate.source,
    )


def _probe(
    *,
    profile: Profile | None,
    rechecks: Mapping[str, RecheckState],
    is_scored: Callable[[str], bool],
    now: datetime,
) -> RecheckProbe | None:
    """The one mastered key due for a re-check: highest impact, then earliest due, then key."""
    if profile is None:
        return None
    due: list[tuple[KeyDefinition, datetime]] = []
    for entry in profile.entries:
        key = entry.definition.key
        state = rechecks.get(key)
        if entry.status is not Status.MASTERED or state is None or state.next_at > now:
            continue
        if not is_scored(key):
            continue
        due.append((entry.definition, state.next_at))
    if not due:
        return None
    definition, due_at = min(
        due, key=lambda item: (-item[0].impact, item[1], item[0].key)
    )
    return RecheckProbe(skill=definition.skill, error_key=definition.key, due_at=due_at)


def select(
    *,
    profile: Profile | None,
    taxonomy: Taxonomy,
    pack: LanguagePack,
    seed: int,
    now: datetime,
    history: Mapping[Skill, Sequence[str]],
    rechecks: Mapping[str, RecheckState],
    is_scored: Callable[[str], bool],
    config: SelectionConfig = DEFAULT_SELECTION,
) -> Selection:
    """The day's focus per skill and its probe.

    Each skill's focus is drawn from its profile candidates (statuses in `focus_statuses`, scored).
    A skill with none draws from its defined keys the profile does not hold, sampled from the
    pack's prior, so a fresh or skipped baseline still gets a focus. `history[skill]` holds the
    previous plans' focus keys, most recent first; the variety rule stops one key winning more
    than `max_streak` days in a row unless it leads by `streak_ratio`.

    Unscored keys (drilled but not measured, §6.8) are never focus or probe, so the plan never
    asks for a change the app cannot see. The probe is taken first and is never also a focus.
    """
    _require_aware(now)
    probe = _probe(profile=profile, rechecks=rechecks, is_scored=is_scored, now=now)
    excluded = frozenset({probe.error_key}) if probe is not None else frozenset()
    entries = profile.entries if profile is not None else ()
    owned = frozenset(e.definition.key for e in entries)
    foci: list[Focus] = []
    for skill in SKILL_ORDER:
        candidates = [
            _from_entry(e)
            for e in entries
            if e.definition.skill is skill
            and e.status in config.focus_statuses
            and e.definition.key not in excluded
            and is_scored(e.definition.key)
        ]
        if not candidates:
            candidates = [
                c
                for c in _fallback_pool(
                    taxonomy=taxonomy, pack=pack, skill=skill, owned=owned, is_scored=is_scored
                )
                if c.definition.key not in excluded
            ]
        focus = _focus_for(
            seed=seed,
            candidates=candidates,
            recent=history.get(skill, ()),
            config=config,
        )
        if focus is not None:
            foci.append(focus)
    return Selection(foci=tuple(foci), probe=probe)
