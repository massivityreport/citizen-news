"""Typed, validated loader for config/halving.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PATH = Path(__file__).with_name("halving.yaml")


class HalvingParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_votes_first_decision: int = Field(20, ge=1, le=10_000)
    keep_ratio: float = Field(0.5, gt=0, lt=1)
    waves: int = Field(3, ge=1, le=10)
    new_topic_traffic_share: float = Field(0.30, ge=0, le=1)
    rescue_share: float = Field(0.10, ge=0, le=1)

    @model_validator(mode="after")
    def _shares_fit_in_traffic(self):
        if self.new_topic_traffic_share + self.rescue_share > 1:
            raise ValueError("new_topic_traffic_share + rescue_share must not exceed 1")
        return self


def load_halving_params(path: Path | str = DEFAULT_PATH) -> HalvingParams:
    """Load and validate halving parameters; raises pydantic.ValidationError if out of bounds."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return HalvingParams.model_validate(data)
