"""Command line: python -m app.cli {ingest,cluster,halve,refresh,run,seed-demo}."""

import argparse
import logging
import os
import signal
import threading
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.db import get_engine
from config.settings import get_settings
from app.services.clustering import cluster
from app.services.demo import seed_demo
from app.services.halving import halve
from app.services.ingest import ingest

log = logging.getLogger("app.cli")
DEFAULT_INTERVAL_MINUTES = 15


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


def run_halve() -> int:
    with Session(get_engine()) as session:
        report = halve(session)
    log.info(
        "halving : %d sujets évalués, %d promus (dont %d émergents), %d mis en réserve",
        report.evaluated, report.promoted, report.emerged, report.demoted,
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
        "démo : %d sujets, %d comptes, %d votes ; halving : %d promus (dont %d émergents), %d en réserve",
        report.topics, report.accounts, report.votes, report.halving.promoted, report.halving.emerged, report.halving.demoted,
    )
    return 0


def run_refresh() -> int:
    # The three steps always run; the exit code is the first non-zero one (no failure is masked).
    ingested = run_ingest()
    clustered = run_cluster()
    halved = run_halve()
    return ingested or clustered or halved


def run_loop(interval_minutes: float, stop: threading.Event) -> int:
    log.info("boucle périodique : toutes les %g minutes", interval_minutes)
    while not stop.is_set():
        try:
            run_refresh()
        except Exception:  # keep the worker alive: the next round may succeed
            log.exception("échec du cycle")
        stop.wait(interval_minutes * 60)
    return 0


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
    sub.add_parser("halve", help="recalcule l'état et la vague des sujets d'après les votes")
    sub.add_parser("refresh", help="ingest, cluster puis halve")
    demo = sub.add_parser("seed-demo", help="crée des sujets, comptes et votes fictifs (développement, DEMO_SEED=true)")
    demo.add_argument("--seed", type=int, default=1, help="graine du générateur (défaut 1)")
    run = sub.add_parser("run", help="refresh en boucle")
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
        return run_loop(args.interval_minutes, stop)
    if args.command == "seed-demo":
        return run_seed_demo(args.seed)
    return {"ingest": run_ingest, "cluster": run_cluster, "halve": run_halve, "refresh": run_refresh}[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
