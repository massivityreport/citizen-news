"""Command line: python -m app.cli {ingest,cluster,refresh,close-edition,run,seed-demo}."""

import argparse
import logging
import os
import signal
import threading
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db import get_engine
from config.settings import get_settings
from app.services.clustering import cluster
from app.services.aggregation import aggregate
from app.services.demo import seed_demo
from app.services.edition_calendar import edition_state, pending_editions
from app.services.edition_close import close_due_edition
from app.services.ingest import ingest

log = logging.getLogger("app.cli")
DEFAULT_INTERVAL_MINUTES = 15
CLOSE_TICK_SECONDS = 60


def run_ingest() -> int:
    with Session(get_engine()) as session:
        report = ingest(session)
    for feed in report.feeds:
        status = f"erreur : {feed.error}" if feed.error else f"{feed.fetched} articles"
        log.info("flux %s : %s", feed.name, status)
    log.info(
        "ingestion : %d nouveaux articles, %d flux en erreur sur %d",
        report.new_articles, len(report.failed), len(report.feeds),
    )
    # Exit code 1 only when nothing could be fetched at all.
    return 1 if report.feeds and len(report.failed) == len(report.feeds) else 0


def run_cluster() -> int:
    with Session(get_engine()) as session:
        report = cluster(session)
    log.info(
        "regroupement : %d articles rattachés, %d nouveaux sujets, %d sujets mis à jour",
        report.attached, report.new_topics, report.updated_topics,
    )
    return 0


def run_seed_demo(seed: int = 1) -> int:
    settings = get_settings()
    if settings.cookie_secure or not settings.demo_seed:
        log.error("seed-demo est réservé au développement : définissez DEMO_SEED=true (refusé avec COOKIE_SECURE=true)")
        return 2
    with Session(get_engine()) as session:
        report = seed_demo(session, seed=seed)
    log.info(
        "démo : %d sujets", report.topics,
    )
    return 0


def run_close(dry_run: bool = False, now: datetime | None = None) -> int:
    """Publish the most recent due edition (dry run: print the ranking, publish nothing)."""
    now = now or datetime.now(UTC)
    with Session(get_engine()) as session:
        if not dry_run:
            edition = close_due_edition(session, now)
            if edition is None:
                log.info("clôture : aucune édition à publier")
            return 0
        pending = pending_editions(session, now)
        target = pending[-1] if pending else edition_state(session, now).edition_date
        result = aggregate(session, target, now)
    print(f"édition {target} ({'due' if pending else 'pas encore due'}) : {result.participants} participants, {len(result.ranking)} sujets classés")
    for t in result.ranking:
        cut = " --- coupure ---" if t.rank == result.top else ""
        tie = f" égalité, départagé par {t.broken_by}" if t.broken_by else ""
        print(f"{t.rank:>3}. [{t.topic_id}] {t.score} approbations ({t.proportion:.1%}), {t.source_count} médias : {t.title}{tie}{cut}")
    return 0


def run_refresh() -> int:
    # Both steps always run; the exit code is the first non-zero one (no failure is masked).
    ingested = run_ingest()
    clustered = run_cluster()
    return ingested or clustered


def run_loop(interval_minutes: float, stop: threading.Event) -> int:
    log.info("boucle périodique : toutes les %g minutes", interval_minutes)
    while not stop.is_set():
        try:
            run_refresh()
        except Exception:  # keep the worker alive: the next round may succeed
            log.exception("échec du cycle")
        stop.wait(interval_minutes * 60)
    return 0


def run_close_loop(stop: threading.Event, interval_seconds: float = CLOSE_TICK_SECONDS) -> int:
    """Closing tick, every minute, separate from the (slow) ingestion: a late or stuck ingestion never delays the closing.
    The first tick is immediate, so a worker that was stopped catches up at once."""
    while not stop.is_set():
        try:
            run_close()
        except Exception:  # keep ticking: the next minute may succeed
            log.exception("échec de la clôture")
        stop.wait(interval_seconds)
    return 0


def run_worker(interval_minutes: float, stop: threading.Event) -> int:
    ticker = threading.Thread(target=run_close_loop, args=(stop,), name="close-tick", daemon=True)
    ticker.start()
    try:
        return run_loop(interval_minutes, stop)
    finally:
        stop.set()
        ticker.join(timeout=30)


def _default_interval() -> float:
    raw = os.environ.get("INGEST_INTERVAL_MINUTES", "")
    if not raw.strip():
        return DEFAULT_INTERVAL_MINUTES
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"INGEST_INTERVAL_MINUTES invalide : « {raw} » (nombre de minutes attendu)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Alimentation en sujets de Citizen News")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="récupère les flux RSS")
    sub.add_parser("cluster", help="regroupe les articles en sujets")
    sub.add_parser("refresh", help="ingest puis cluster")
    demo = sub.add_parser("seed-demo", help="crée des médias et des sujets fictifs (développement, DEMO_SEED=true)")
    demo.add_argument("--seed", type=int, default=1, help="graine du générateur (défaut 1)")
    close = sub.add_parser("close-edition", help="publie l'édition due la plus récente (idempotent)")
    close.add_argument("--dry-run", action="store_true", help="affiche le classement sans rien publier")
    run = sub.add_parser("run", help="refresh en boucle + clôture de l'édition chaque minute")
    run.add_argument(
        "--interval-minutes",
        type=float,
        default=_default_interval(),
        help=f"pause entre deux cycles (défaut : $INGEST_INTERVAL_MINUTES ou {DEFAULT_INTERVAL_MINUTES})",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per HTTP request is noise
    if args.command == "run":
        if args.interval_minutes <= 0:
            parser.error("--interval-minutes doit être positif")
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        return run_worker(args.interval_minutes, stop)
    if args.command == "close-edition":
        return run_close(args.dry_run)
    if args.command == "seed-demo":
        return run_seed_demo(args.seed)
    return {"ingest": run_ingest, "cluster": run_cluster, "refresh": run_refresh}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
