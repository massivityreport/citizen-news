"""Typed, validated loader for config/front.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).with_name("front.yaml")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SupportCfg(_Section):
    medium_min_votes: int = Field(10, ge=1)
    medium_score: float = Field(0.30, ge=0, le=1)
    high_min_votes: int = Field(30, ge=1)
    high_score: float = Field(0.50, ge=0, le=1)

    @model_validator(mode="after")
    def _high_is_above_medium(self):
        if self.high_min_votes < self.medium_min_votes or self.high_score < self.medium_score:
            raise ValueError("support: the high level cannot be easier to reach than the medium one")
        return self


class CommonPriorityCfg(_Section):
    min_votes: int = Field(50, ge=1)
    min_score: float = Field(0.50, ge=0, le=1)


class UnderTheRadarCfg(_Section):
    max_sources: int = Field(2, ge=1)
    min_votes: int = Field(15, ge=1)
    min_score: float = Field(0.50, ge=0, le=1)


class StrongMobilisationCfg(_Section):
    min_more_votes: int = Field(30, ge=1)


class EmergingCfg(_Section):
    trend_hours: float = Field(6, gt=0)
    trend_min_votes: int = Field(10, ge=1)
    trend_share: float = Field(0.5, gt=0, le=1)
    emerged_recent_hours: float = Field(48, gt=0)


class ReasonsCfg(_Section):
    common_priority: CommonPriorityCfg = CommonPriorityCfg()
    under_the_radar: UnderTheRadarCfg = UnderTheRadarCfg()
    strong_mobilisation: StrongMobilisationCfg = StrongMobilisationCfg()
    emerging: EmergingCfg = EmergingCfg()


class RankingCfg(_Section):
    support_weight: float = Field(0.6, ge=0)
    freshness_weight: float = Field(0.4, ge=0)
    freshness_half_life_hours: float = Field(24, gt=0)
    min_votes: int = Field(10, ge=0)
    recent_hours: float = Field(12, gt=0)

    @model_validator(mode="after")
    def _some_weight(self):
        if self.support_weight + self.freshness_weight <= 0:
            raise ValueError("ranking: support_weight and freshness_weight cannot both be 0")
        return self


class FrontParams(_Section):
    support: SupportCfg = SupportCfg()
    reasons: ReasonsCfg = ReasonsCfg()
    ranking: RankingCfg = RankingCfg()


def load_front_params(path: Path | str = DEFAULT_PATH) -> FrontParams:
    """Load and validate; raises pydantic.ValidationError if out of bounds or if a key is unknown."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return FrontParams.model_validate(data)
