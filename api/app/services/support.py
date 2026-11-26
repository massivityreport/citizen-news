"""Support level and reason shown on the front page.

PROVISIONAL: there is no vote yet, so every topic is "low support, 0 votes, emerging". The votes/halving
task replaces `support_for` (same signature) with the real computation; nothing else depends on how it works.
"""

from collections.abc import Sequence

from app.models.entities import Topic
from app.schemas import ReasonOut, SupportOut

REASON_LABELS = {
    "common_priority": "Priorité commune",
    "strong_mobilisation": "Forte mobilisation",
    "under_the_radar": "Sous les radars",
    "emerging": "Sujet émergent",
}


def support_for(topics: Sequence[Topic]) -> dict[int, tuple[SupportOut, ReasonOut]]:
    """Return {topic id: (support, reason)} for the given topics, in one pass."""
    support = SupportOut(level="low", votes_count=0)
    reason = ReasonOut(code="emerging", label=REASON_LABELS["emerging"])
    return {t.id: (support, reason) for t in topics}
