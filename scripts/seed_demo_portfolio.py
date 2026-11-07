"""Create the labelled demo account and its two sample buys.

Does not download prices and does not write a price bar. After it
succeeds, ingest real daily bars with:

    python scripts/ingest_market_data.py --ticker AAPL --ticker GOOGL

The password is read from DEMO_USER_PASSWORD and is not printed.
Set it in the shell for this command only. Do not put it in Vercel.

    DEMO_USER_PASSWORD='choose-a-demo-password' python scripts/seed_demo_portfolio.py

An account that already owns a different portfolio is left unchanged.
Running the command again does not duplicate the sample buys.
"""

from __future__ import annotations

import os
import sys

from app.core.cache import commit_and_invalidate, get_cache
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.demo_portfolio import seed_demo_portfolio
from app.db.session import SessionLocal


def main() -> int:
    setup_logging(settings.log_level)
    password = os.environ.get("DEMO_USER_PASSWORD", "")
    if len(password) < 8:
        print(
            "Set DEMO_USER_PASSWORD to at least 8 characters. "
            "It is used only for the demo account and is not printed.",
            file=sys.stderr,
        )
        return 2
    session = SessionLocal()
    try:
        result = seed_demo_portfolio(session, password=password)
        if result.refused:
            session.rollback()
        else:
            commit_and_invalidate(session, get_cache())
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if result.refused:
        print(
            f"Refused: {result.email} already has a portfolio that is not "
            "the labelled demo book. No transactions were added."
        )
        return 2
    print(
        "Demo book ready: "
        f"user_created={result.created_user} "
        f"portfolio_created={result.created_portfolio} "
        f"transactions_inserted={result.transactions_inserted} "
        f"portfolio_id={result.portfolio_id}"
    )
    if result.created_user:
        print(f"Sign in as {result.email} with the DEMO_USER_PASSWORD you set.")
    else:
        print(
            f"{result.email} already existed. Its password was not changed."
        )
    print(
        "No market prices were written. Run "
        "scripts/ingest_market_data.py --ticker AAPL --ticker GOOGL "
        "to store provider daily bars."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
