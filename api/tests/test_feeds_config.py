import pytest
import yaml
from pydantic import ValidationError

from config.clustering import DEFAULT_PATH as CLUSTERING_PATH
from config.clustering import load_clustering_params
from config.feeds import load_feeds


def _write(tmp_path, feeds):
    path = tmp_path / "feeds.yaml"
    path.write_text(yaml.safe_dump({"feeds": feeds}), encoding="utf-8")
    return path


def test_default_feed_list_is_valid_and_has_about_a_dozen_media():
    feeds = load_feeds()
    assert len(feeds) >= 10
    assert all(f.feed_url.startswith("https://") for f in feeds)


def test_valid_entries_are_loaded(tmp_path):
    feeds = load_feeds(_write(tmp_path, [{"name": " A ", "feed_url": "http://a.example/rss"}]))
    assert [(f.name, f.feed_url) for f in feeds] == [("A", "http://a.example/rss")]


@pytest.mark.parametrize(
    "feeds",
    [
        [{"name": "A", "feed_url": "ftp://a.example/rss"}],
        [{"name": "A", "feed_url": "not a url"}],
        [{"name": "A", "feed_url": "https://"}],
        [{"name": " ", "feed_url": "https://a.example/rss"}],
        [{"name": "A"}],
        [{"name": "A", "feed_url": "https://a.example/rss", "extra": 1}],
        [
            {"name": "A", "feed_url": "https://a.example/rss"},
            {"name": "B", "feed_url": "https://A.example/rss"} | {"feed_url": "https://a.example/rss"},
        ],
        [
            {"name": "A", "feed_url": "https://a.example/rss"},
            {"name": "a", "feed_url": "https://b.example/rss"},
        ],
    ],
)
def test_invalid_feed_lists_are_refused(tmp_path, feeds):
    with pytest.raises(ValidationError):
        load_feeds(_write(tmp_path, feeds))


def test_clustering_defaults():
    p = load_clustering_params()
    assert (p.similarity_threshold, p.window_hours, p.min_sources_for_front) == (0.35, 48, 2)


@pytest.mark.parametrize("overrides", [{"similarity_threshold": 0}, {"similarity_threshold": 1}, {"window_hours": 0}, {"min_sources_for_front": 0}, {"foo": 1}])
def test_clustering_out_of_bounds_refused(tmp_path, overrides):
    data = yaml.safe_load(CLUSTERING_PATH.read_text()) | overrides
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError):
        load_clustering_params(path)
