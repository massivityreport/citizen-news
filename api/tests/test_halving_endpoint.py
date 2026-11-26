from app.routers.halving import DESCRIPTIONS
from config.halving import HalvingParams


def test_halving_config_is_public_and_complete(client):
    r = client.get("/api/halving/config")
    assert r.status_code == 200
    body = r.json()
    assert body["params"] == {
        "min_votes_first_decision": 20, "keep_ratio": 0.5, "waves": 3,
        "new_topic_traffic_share": 0.3, "rescue_share": 0.1,
    }
    assert set(body["description"]) == set(body["params"])
    assert all(isinstance(t, str) and len(t) > 20 for t in body["description"].values())


def test_every_parameter_has_a_description():
    assert set(DESCRIPTIONS) == set(HalvingParams.model_fields)


def test_halving_config_reflects_the_yaml(client, tmp_path, monkeypatch):
    path = tmp_path / "halving.yaml"
    path.write_text("min_votes_first_decision: 5\nkeep_ratio: 0.25\nwaves: 2\nnew_topic_traffic_share: 0.4\nrescue_share: 0.2\n")
    import config.halving as module

    monkeypatch.setattr(module, "DEFAULT_PATH", path)
    monkeypatch.setattr(module.load_halving_params, "__defaults__", (path,))
    assert client.get("/api/halving/config").json()["params"]["waves"] == 2
