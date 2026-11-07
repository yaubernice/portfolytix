"""Refresh the market universe and upsert real daily bars.

The provider is ``MARKET_DATA_PROVIDER`` or ``--provider``. An API key
does not select the provider. Yahoo's chart endpoint is unofficial and
returns delayed daily closes, not real-time prices. This command does
not create users, portfolios, transactions, or synthetic bars.

    # Metadata only. Repeatable. Does not delete prices.
    python scripts/ingest_market_data.py --refresh-universe

    # Recent bars for a small batch. One vendor request per symbol.
    MARKET_DATA_PROVIDER=yahoo python scripts/ingest_market_data.py \\
        --universe sp500 --limit 5

    # A longer window after you have reviewed the request count.
    MARKET_DATA_PROVIDER=yahoo python scripts/ingest_market_data.py \\
        --universe sp500 --limit 5 --start 2024-01-02

A name with no holdings is still eligible. The holdings scheduler is a
separate path and does not walk this universe. SnapDeploy sleeps the
API process, so that in-process cron is not the universe schedule.
"""

# ruff: noqa: E402 -- executable bootstrap adds the repository root first.

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.core.cache import commit_and_invalidate, get_cache
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.models import JobStatus, Price
from app.db.session import SessionLocal
from app.jobs.market_data_job import DEFAULT_TICKERS, update_market_data
from app.market_data.errors import ProviderError
from app.market_data.factory import build_provider
from app.market_data.universe import (
    apply_universe,
    download_constituents,
    parse_sp500_constituents,
)


def main(argv: list[str] | None = None) -> int:
    setup_logging(settings.log_level)
    args = _parse(argv)
    if args.universe and args.tickers:
        print("Pass either --universe or --ticker, not both.", file=sys.stderr)
        return 2
    if (args.universe or args.refresh_universe) and not _provider_is_explicit(
        args.provider
    ):
        print(
            "Set MARKET_DATA_PROVIDER or pass --provider. "
            "MARKET_DATA_API_KEY does not select the provider.",
            file=sys.stderr,
        )
        return 2
    try:
        provider = build_provider(args.provider) if _needs_provider(args) else None
    except ProviderError as exc:
        print(_public_error(exc), file=sys.stderr)
        return 2
    if provider is not None:
        print(f"MARKET_DATA_PROVIDER={provider.name}")
        if args.universe and provider.name == "yahoo":
            print(
                "Yahoo bars are delayed daily closes from an unofficial "
                "chart endpoint, not real-time prices."
            )
        if args.universe and provider.name == "alpha_vantage":
            print(
                "Alpha Vantage quotas are small. A broad universe needs "
                "many requests; keep --limit inside the plan you reviewed."
            )
    session = SessionLocal()
    exit_code = 0
    try:
        if args.refresh_universe:
            report = _refresh_universe(session)
            commit_and_invalidate(session, get_cache())
            _print_refresh(report)
        if _should_ingest(args):
            run = _ingest(session, args, provider)
            last_bar = None
            if run.started_at is not None:
                last_bar = session.scalar(
                    select(func.max(Price.timestamp)).where(
                        Price.ingested_at >= run.started_at
                    )
                )
            commit_and_invalidate(session, get_cache())
            _print_run(run, last_bar)
            exit_code = 0 if run.status == JobStatus.SUCCESS else 1
    except Exception as exc:
        session.rollback()
        print(_public_error(exc), file=sys.stderr)
        return 1
    finally:
        session.close()
    return exit_code


def _provider_is_explicit(provider: str | None) -> bool:
    if provider:
        return True
    return bool(os.environ.get("MARKET_DATA_PROVIDER", "").strip())


def _needs_provider(args: argparse.Namespace) -> bool:
    return _should_ingest(args)


def _should_ingest(args: argparse.Namespace) -> bool:
    if args.universe or args.tickers or args.exchange or args.country:
        return True
    return not args.refresh_universe


def _refresh_universe(session):
    payload = download_constituents(settings.universe_source_url)
    listings = parse_sp500_constituents(payload)
    return apply_universe(
        session,
        listings,
        universe=settings.universe_code,
        source="datasets/s-and-p-500-companies",
    )


def _ingest(session, args: argparse.Namespace, provider):
    tickers = args.tickers
    if (
        tickers is None
        and not args.universe
        and not args.exchange
        and not args.country
    ):
        tickers = DEFAULT_TICKERS
    if args.limit is not None and tickers is not None:
        tickers = tickers[: args.limit]
    start = args.start
    if start is None and not args.universe:
        start = date(2024, 1, 2)
    return update_market_data(
        session,
        tickers=tickers,
        exchange=args.exchange,
        country=args.country,
        start=start,
        end=args.end,
        provider=provider,
        trigger="cli",
        universe=args.universe,
        symbol_limit=args.limit,
    )


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-universe",
        action="store_true",
        help="Import constituent metadata. Does not write prices.",
    )
    parser.add_argument(
        "--universe",
        default=None,
        help="Ingest active members of this universe, ignoring holdings.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum symbols for this run. Universe runs have no silent full scan.",
    )
    parser.add_argument(
        "--ticker",
        dest="tickers",
        action="append",
        help=(
            "Ticker to ingest (repeatable). Without --universe, "
            "the legacy default is seven names."
        ),
    )
    parser.add_argument("--exchange", default=None)
    parser.add_argument("--country", default=None)
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--provider",
        default=None,
        help="yahoo, stooq, or alpha_vantage. Overrides MARKET_DATA_PROVIDER.",
    )
    return parser.parse_args(argv)


def _print_refresh(report) -> None:
    skipped = ",".join(report.skipped_tickers)
    print(
        f"universe {report.universe} parsed={report.parsed} "
        f"securities_inserted={report.securities_inserted} "
        f"memberships_upserted={report.memberships_upserted} "
        f"deactivated={report.memberships_deactivated}"
    )
    if skipped:
        print(f"  skipped_tickers={skipped}")


def _print_run(run, last_bar) -> None:
    print(
        f"job_run {run.id} {run.status} via {run.provider} "
        f"{run.window_start} → {run.window_end}"
    )
    if run.error:
        print(f"  error={run.error}")
    print(
        f"  fetched={run.fetched} accepted={run.accepted} "
        f"upserted={run.upserted} dropped={run.skipped_invalid} "
        f"requested={run.symbols_requested} omitted={run.symbols_omitted}"
    )
    print(f"  last_bar_date={last_bar.date() if last_bar is not None else 'none'}")
    if run.symbols_requested == 0 and not run.error:
        print(
            "  No symbols were requested. Pass --ticker or --universe. "
            "Holdings are not required for --universe."
        )
    if run.error == "no_holdings_or_watchlists":
        print(
            "  Nothing was downloaded. The holdings book is empty. "
            "Use --universe sp500 to ingest the maintained list."
        )
    if run.failed_tickers:
        print(f"  failed_tickers={','.join(run.failed_tickers)}")


def _public_error(exc: Exception) -> str:
    message = str(exc)
    if "://" in message or "@" in message:
        return f"{type(exc).__name__}: failure (connection details omitted)"
    return f"{type(exc).__name__}: {message[:300]}"


if __name__ == "__main__":
    sys.exit(main())
