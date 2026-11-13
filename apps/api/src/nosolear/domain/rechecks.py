"""The re-check schedule for mastered keys (ARCHITECTURE §6.7).

`RecheckState` lives here so the selection policy can read it without importing the schedule
logic, which is added in the next task.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecheckState:
    stage: int
    next_at: datetime
