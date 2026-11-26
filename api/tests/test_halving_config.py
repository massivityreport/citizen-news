import pytest
import yaml
from pydantic import ValidationError

from config.halving import DEFAULT_PATH, load_halving_params


def test_default_file_loads_with_expected_values():
    p = load_halving_params()
    assert p.min_votes_first_decision == 20
    assert p.keep_ratio == 0.5
    assert p.waves == 3
    assert p.new_topic_traffic_share == 0.30
    assert p.rescue_share == 0.10


def _write(tmp_path, **overrides):
    data = yaml.safe_load(DEFAULT_PATH.read_text()) | overrides
    path = tmp_path / "halving.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_override_is_applied(tmp_path):
    assert load_halving_params(_write(tmp_path, waves=5)).waves == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_votes_first_decision": 0},
        {"keep_ratio": 0},
        {"keep_ratio": 1},
        {"keep_ratio": 1.5},
        {"waves": 0},
        {"new_topic_traffic_share": -0.1},
        {"new_topic_traffic_share": 1.1},
        {"rescue_share": 2},
        {"new_topic_traffic_share": 0.8, "rescue_share": 0.5},
        {"waves": "many"},
        {"unknown_param": 1},
    ],
)
def test_out_of_bounds_rejected(tmp_path, overrides):
    with pytest.raises(ValidationError):
        load_halving_params(_write(tmp_path, **overrides))
