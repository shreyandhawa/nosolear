from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import get_profile_repository
from nosolear.api.schemas import ProfileEntryOut, ProfileOut
from nosolear.domain.profile import ALGO_VERSION, Profile
from nosolear.domain.taxonomy import TAXONOMY_VERSION
from nosolear.persistence.repositories import ProfileRepository

router = APIRouter()


def _to_out(profile: Profile | None) -> ProfileOut:
    if profile is None:
        return ProfileOut(
            as_of=None,
            taxonomy_version=TAXONOMY_VERSION,
            algo_version=ALGO_VERSION,
            entries=[],
        )
    return ProfileOut(
        as_of=profile.as_of,
        taxonomy_version=profile.taxonomy_version,
        algo_version=profile.algo_version,
        entries=[
            ProfileEntryOut(
                error_key=e.definition.key,
                skill=e.definition.skill.value,
                family=e.definition.family.value,
                description=e.definition.description,
                impact=e.definition.impact,
                p_hat=e.estimate.p_hat,
                ci_low=e.estimate.ci_low,
                ci_high=e.estimate.ci_high,
                n_eff=e.estimate.n_eff,
                status=e.status.value,
                priority=e.priority,
                last_seen_at=e.last_seen_at,
                provisional=e.provisional,
            )
            for e in profile.entries
        ],
    )


@router.get("/api/profile", operation_id="getProfile")
def get_profile(
    repo: Annotated[ProfileRepository, Depends(get_profile_repository)],
) -> ProfileOut:
    return _to_out(repo.latest())
