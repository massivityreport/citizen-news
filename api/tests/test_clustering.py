from datetime import timedelta

from sqlalchemy import func, select

from app.models.entities import Article, Topic
from app.services.clustering import cluster
from config.clustering import ClusteringParams
from tests.helpers import FOOT, METEO, NOW, RETRAITES, make_article, make_sources

PARAMS = ClusteringParams()


def topics_of(session, *articles):
    session.expire_all()
    return [session.get(Article, a.id).topic_id for a in articles]


def test_close_articles_are_grouped_and_distant_ones_separated(session):
    s1, s2, s3 = make_sources(session, "A", "B", "C")
    r1 = make_article(session, s1, 1, *RETRAITES[0], hours_ago=5)
    r2 = make_article(session, s2, 2, *RETRAITES[1], hours_ago=4)
    r3 = make_article(session, s3, 3, *RETRAITES[2], hours_ago=3)
    foot = make_article(session, s1, 4, *FOOT, hours_ago=2)
    meteo = make_article(session, s2, 5, *METEO, hours_ago=1)
    session.commit()

    report = cluster(session, PARAMS, now=NOW)

    t = topics_of(session, r1, r2, r3, foot, meteo)
    assert t[0] == t[1] == t[2]
    assert len({t[0], t[3], t[4]}) == 3
    assert (report.attached, report.new_topics) == (5, 3)
    topic = session.get(Topic, t[0])
    assert topic.title in {a[0] for a in RETRAITES}
    assert 0 < len(topic.summary) <= 280


def test_topic_dates_follow_its_articles(session):
    s1, s2 = make_sources(session, "A", "B")
    make_article(session, s1, 1, *RETRAITES[0], hours_ago=10)
    make_article(session, s2, 2, *RETRAITES[1], hours_ago=2)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    topic = session.scalars(select(Topic)).one()
    assert topic.first_seen_at == NOW - timedelta(hours=10)
    assert topic.updated_at == NOW - timedelta(hours=2)


def test_rerun_is_idempotent(session):
    s1, s2 = make_sources(session, "A", "B")
    make_article(session, s1, 1, *RETRAITES[0], hours_ago=3)
    make_article(session, s2, 2, *RETRAITES[1], hours_ago=2)
    make_article(session, s2, 3, *FOOT, hours_ago=1)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    before = sorted((a.id, a.topic_id) for a in session.scalars(select(Article)))
    report = cluster(session, PARAMS, now=NOW)
    session.expire_all()
    assert (report.attached, report.new_topics) == (0, 0)
    assert before == sorted((a.id, a.topic_id) for a in session.scalars(select(Article)))
    assert session.scalar(select(func.count()).select_from(Topic)) == 2


def test_new_article_joins_existing_topic_and_updates_it(session):
    s1, s2 = make_sources(session, "A", "B")
    make_article(session, s1, 1, *RETRAITES[0], hours_ago=6)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    late = make_article(session, s2, 2, *RETRAITES[1], hours_ago=1)
    session.commit()
    report = cluster(session, PARAMS, now=NOW)
    topic = session.scalars(select(Topic)).one()
    assert topics_of(session, late) == [topic.id]
    assert (report.new_topics, report.updated_topics) == (0, 1)
    assert topic.updated_at == NOW - timedelta(hours=1)


def test_topic_without_recent_article_no_longer_accepts_articles(session):
    s1, s2 = make_sources(session, "A", "B")
    old = make_article(session, s1, 1, *RETRAITES[0], hours_ago=60)
    session.commit()
    cluster(session, PARAMS, now=NOW - timedelta(hours=20))  # topic created when still in the window
    fresh = make_article(session, s2, 2, *RETRAITES[1], hours_ago=1)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    assert topics_of(session, old)[0] != topics_of(session, fresh)[0]


def test_articles_older_than_window_are_ignored(session):
    (s1,) = make_sources(session, "A")
    old = make_article(session, s1, 1, *RETRAITES[0], hours_ago=49)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    assert topics_of(session, old) == [None]


def test_window_is_configurable(session):
    (s1,) = make_sources(session, "A")
    a = make_article(session, s1, 1, *RETRAITES[0], hours_ago=10)
    session.commit()
    cluster(session, ClusteringParams(window_hours=6), now=NOW)
    assert topics_of(session, a) == [None]
    cluster(session, ClusteringParams(window_hours=12), now=NOW)
    assert topics_of(session, a)[0] is not None


def test_threshold_is_configurable(session):
    s1, s2 = make_sources(session, "A", "B")
    a = make_article(session, s1, 1, *RETRAITES[0], hours_ago=3)
    b = make_article(session, s2, 2, *RETRAITES[1], hours_ago=2)
    session.commit()
    cluster(session, ClusteringParams(similarity_threshold=0.95), now=NOW)
    assert len(set(topics_of(session, a, b))) == 2  # too strict: not grouped
    session.execute(Article.__table__.update().values(topic_id=None))
    session.execute(Topic.__table__.delete())
    session.commit()
    cluster(session, ClusteringParams(similarity_threshold=0.1), now=NOW)
    assert len(set(topics_of(session, a, b))) == 1


def test_accents_and_stop_words_do_not_create_similarity(session):
    s1, s2 = make_sources(session, "A", "B")
    a = make_article(session, s1, 1, "Élysée : le président reçoit les maires", "")
    b = make_article(session, s2, 2, "ELYSEE : les maires reçus par le président", "")
    c = make_article(session, s2, 3, "Le chat de la voisine est dans le jardin", "")
    d = make_article(session, s1, 4, "Les enfants de la ville sont dans le bus", "")
    session.commit()
    cluster(session, PARAMS, now=NOW)
    t = topics_of(session, a, b, c, d)
    assert t[0] == t[1]
    assert t[2] != t[3]  # only « le/la/dans/est/de » in common


def test_same_source_articles_are_clustered_but_sources_stay_distinct(session):
    (s1,) = make_sources(session, "A")
    make_article(session, s1, 1, *RETRAITES[0], hours_ago=3)
    make_article(session, s1, 2, *RETRAITES[1], hours_ago=2)
    session.commit()
    cluster(session, PARAMS, now=NOW)
    topic = session.scalars(select(Topic)).one()
    sources = session.scalar(
        select(func.count(func.distinct(Article.source_id))).where(Article.topic_id == topic.id)
    )
    assert sources == 1


def test_clustering_is_deterministic(session):
    s1, s2, s3 = make_sources(session, "A", "B", "C")
    arts = [
        make_article(session, s1, 1, *RETRAITES[0], hours_ago=5),
        make_article(session, s2, 2, *FOOT, hours_ago=5),
        make_article(session, s3, 3, *RETRAITES[1], hours_ago=4),
        make_article(session, s1, 4, *METEO, hours_ago=3),
    ]
    session.commit()
    cluster(session, PARAMS, now=NOW)
    first = [t for t in topics_of(session, *arts)]
    session.execute(Article.__table__.update().values(topic_id=None))
    session.execute(Topic.__table__.delete())
    session.commit()
    cluster(session, PARAMS, now=NOW)
    second = topics_of(session, *arts)
    # same partition (topic ids differ between runs)
    assert [first.index(x) for x in first] == [second.index(x) for x in second]
