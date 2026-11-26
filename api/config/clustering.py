"""Typed, validated loader for config/clustering.yaml."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PATH = Path(__file__).with_name("clustering.yaml")


class ClusteringParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    similarity_threshold: float = Field(0.35, gt=0, lt=1)
    window_hours: int = Field(48, ge=1, le=24 * 30)
    min_sources_for_front: int = Field(2, ge=1, le=100)


def load_clustering_params(path: Path | str = DEFAULT_PATH) -> ClusteringParams:
    """Load and validate clustering parameters; raises pydantic.ValidationError if out of bounds."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return ClusteringParams.model_validate(data)
