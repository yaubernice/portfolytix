"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import StartCard from "../../components/StartCard";
import { useDisplayCurrency } from "../../components/DisplayCurrency";
import { usePortfolio } from "../../components/usePortfolio";
import {
  AllocationChart,
  BucketChart,
  AttentionMark,
  CompanyLogo,
  EmptyState,
  ErrorState,
  number,
  percent,
  Skeleton,
  TickerIdentity,
  TimeSeriesChart,
  dateTime,
} from "../../components/UI";
import { api } from "../../lib/api";
import { hasReturnSample, positionRefreshMs, quoteAllocation, sharpeNote, usMarketIsOpen, volatilityNote } from "../../lib/figures";

export default function DashboardPage() {
  const { portfolios, portfolioId, ready, error: portfolioError } = usePortfolio();
  const { money } = useDisplayCurrency();
  const [analytics, setAnalytics] = useState(null);
  const [historyNote, setHistoryNote] = useState("");
  const [positions, setPositions] = useState(null);
  const [listedQuotes, setListedQuotes] = useState([]);
  const [marketOverview, setMarketOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ready) return undefined;
    if (!portfolioId) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setError("");
    setHistoryNote("");
    api(`/portfolios/${portfolioId}/analytics`)
      .then((body) => {
        if (!cancelled) setAnalytics(body);
      })
      .catch((err) => {
        if (!cancelled) {
          setAnalytics(null);
          setHistoryNote(err.message);
        }
      });
    let timer = 0;
    const loadPositions = () => {
      api(`/portfolios/${portfolioId}/positions`)
        .then(async (body) => {
          if (cancelled) return;
          setPositions(body);
          window.clearInterval(timer);
          const session = await api("/market/session").catch(() => null);
          const wait = positionRefreshMs(body, new Date(), session ? session.open : null);
          timer = wait ? window.setInterval(loadPositions, wait) : 0;
        })
        .catch((err) => {
          if (!cancelled) {
            setPositions(null);
            setError(err.message);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };
    loadPositions();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [portfolioId, ready]);

  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    api("/market/overview")
      .then((body) => {
        if (!cancelled) setMarketOverview(body);
      })
      .catch((err) => {
        if (!cancelled && !portfolioId) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [portfolioId, ready]);

  useEffect(() => {
    let cancelled = false;
    async function loadListed() {
      const symbols = new Set((positions?.positions || []).map((row) => row.ticker).filter(Boolean));
      try {
        const page = await api("/watchlists?limit=100");
        const details = await Promise.all(
          (page.items || []).slice(0, 5).map((list) => api(`/watchlists/${list.id}?limit=100`)),
        );
        for (const detail of details) {
          for (const item of detail.items || []) {
            if (item.ticker) symbols.add(item.ticker);
          }
        }
      } catch {
        // Holdings can still fill the list.
      }
      if (!symbols.size) {
        for (const row of [
          ...(marketOverview?.gainers || []),
          ...(marketOverview?.losers || []),
        ]) {
          if (row.ticker) symbols.add(row.ticker);
        }
      }
      const tickers = [...symbols].slice(0, 8);
      if (!tickers.length) {
        if (!cancelled) setListedQuotes([]);
        return;
      }
      try {
        const body = await api(`/quotes?tickers=${encodeURIComponent(tickers.join(","))}`);
        if (!cancelled) setListedQuotes(body.quotes || []);
      } catch {
        if (!cancelled) setListedQuotes([]);
      }
    }
    loadListed();
    let timer = 0;
    api("/market/session").then((session) => {
      if (!cancelled && session.open) timer = setInterval(loadListed, 60000);
    }).catch(() => {
      if (!cancelled && usMarketIsOpen()) timer = setInterval(loadListed, 60000);
    });
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [marketOverview, positions]);

  const portfolio = portfolios.find((row) => row.id === portfolioId);
  const series = (analytics?.series || []).filter((point) => point.value !== null && point.value !== undefined);
  const quote = listedQuotes[0];
  const mark = positions?.positions?.find((row) => row.freshness)?.freshness;
  const timeliness = String(quote?.timeliness || mark?.timeliness || "").toLowerCase();
  const quoteKind = timeliness === "realtime" || timeliness === "live" ? "Real-time quote" : timeliness === "delayed" ? "Delayed quote" : timeliness ? `${timeliness} quote` : "";
  const stamp = quote?.provider_timestamp || quote?.timestamp || mark?.as_of;
  const freshness = quoteKind
    ? `${quoteKind} · ${quote?.source || mark?.source || "source unavailable"}${stamp ? ` · as of ${dateTime(stamp)}` : ""}. A delayed quote stays delayed until a newer print arrives.`
    : "";
  const contributors = positions?.top_contributors || [];
  const detractors = positions?.top_detractors || [];
  const hasPositions = Boolean(positions?.positions?.length);
  const allocationRows = quoteAllocation(positions);
  const shownAllocation = allocationRows.length ? allocationRows : (analytics?.allocation || []);
  const showMarketOverview = !portfolioId || (!loading && !hasPositions);

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">{portfolio?.name || "Markets"}</p>
            <h1>{portfolioId && (loading || hasPositions) ? "How this portfolio stands" : "What the market is doing"}</h1>
            <p className="muted">
              {hasPositions
                ? (freshness || "Waiting for a provider quote.")
                : "Market figures below are not your portfolio until you buy a share."}
              {" "}Not a forecast and not a buy or sell instruction. <Link href="/data">Data status</Link>
            </p>
          </div>
        </header>
        <ErrorState message={error || portfolioError} />
        {loading && portfolioId ? <Skeleton lines={3} label="Loading dashboard" /> : null}
        {showMarketOverview ? (
          <StartCard
            title={portfolios.length ? "Add your first holding" : "Set up your portfolio"}
            lead="Once you record a buy, this page switches to your value, day change, and movers."
          />
        ) : null}
        {showMarketOverview && marketOverview ? (
          <>
            <div className="cards">
              <section className="kpi-card"><p className="kpi-label">Names covered</p><p className="kpi-value">{number(marketOverview.covered_members)} / {number(marketOverview.active_members)}</p><p className="kpi-detail">With stored daily bars</p></section>
              <section className="kpi-card"><p className="kpi-label">Up today</p><p className="kpi-value up">{number(marketOverview.advancing)}</p><p className="kpi-detail">Latest close versus prior close</p></section>
              <section className="kpi-card"><p className="kpi-label">Down today</p><p className="kpi-value down">{number(marketOverview.declining)}</p><p className="kpi-detail">Latest close versus prior close</p></section>
              <section className="kpi-card"><p className="kpi-label">Last session</p><p className="kpi-value">{marketOverview.latest_bar_date || "—"}</p><p className="kpi-detail">{marketOverview.provider} · delayed</p></section>
            </div>
            <div className="record-grid">
              <section className="workspace-block">
                <div className="block-head"><h2>Recent market movers</h2><p className="muted">Stored daily closes</p></div>
                {[...(marketOverview.gainers || []), ...(marketOverview.losers || [])].length ? (
                  <ul className="quote-lines">
                    {[...(marketOverview.gainers || []), ...(marketOverview.losers || [])].slice(0, 8).map((row) => (
                      <li key={row.ticker}><Link href={`/securities/${row.ticker}`}><CompanyLogo ticker={row.ticker} size={28} /><strong>{row.ticker}</strong><span>{money(row.latest_close)}</span><span className={Number(row.change) < 0 ? "down" : Number(row.change) > 0 ? "up" : ""}>{money(row.change)} · {percent(row.change_percent)}</span><small>{row.latest_bar_date} · {row.source || marketOverview.provider}</small></Link></li>
                    ))}
                  </ul>
                ) : <p className="compact-note">Refresh the market universe and ingest at least two daily bars to calculate movers.</p>}
              </section>
              <section className="workspace-block">
                <div className="block-head"><h2>Latest quote prints</h2><p className="muted">Configured quote provider</p></div>
                {listedQuotes.length ? <ul className="quote-lines">{listedQuotes.map((row) => <li key={row.ticker}><Link href={`/securities/${row.ticker}`}><CompanyLogo ticker={row.ticker} size={28} /><strong>{row.ticker}</strong><span>{money(row.price)}</span><span>{row.timeliness || "unavailable"}</span><small>{row.source || "source unavailable"}</small></Link></li>)}</ul> : <p className="compact-note">The quote worker has not published a current provider quote for these names yet.</p>}
              </section>
            </div>
            <p className="compact-note">Market data does not mean you own these companies.</p>
          </>
        ) : null}
        {portfolioId && hasPositions ? (
          <>
            <section className="hero" aria-labelledby="portfolio-value-title">
              <div className="hero-main">
                <p className="hero-label" id="portfolio-value-title">Worth today</p>
                <p className="hero-value">{money(positions?.market_value)}</p>
                <p className="muted">Latest provider quote. Day change is since the previous close. Total return needs stored daily closes.</p>
              </div>
              <dl className="hero-side">
                <div>
                  <dt><LearnTerm slug="day-pl">Up or down today</LearnTerm></dt>
                  <dd className={positions?.day_pl == null ? "" : Number(positions.day_pl) < 0 ? "down" : Number(positions.day_pl) > 0 ? "up" : ""}>
                    {Number(positions?.day_pl) < 0 ? <AttentionMark /> : null}
                    {positions?.day_pl == null ? "—" : money(positions.day_pl)}
                  </dd>
                </div>
                <div>
                  <dt><LearnTerm slug="time-weighted-return">Total return</LearnTerm></dt>
                  <dd className={Number(analytics?.total_return) < 0 ? "down" : ""}>{!hasReturnSample(analytics) || analytics?.total_return == null ? "—" : percent(analytics.total_return)}</dd>
                </div>
              </dl>
            </section>
            <p className="compact-note dashboard-links">
              <Link href="/portfolio">Full portfolio</Link>
              {" · "}
              <Link href="/portfolio?tab=transactions">Transactions</Link>
              {" · "}
              <Link href="/portfolio?tab=goals">Goals</Link>
              {" · "}
              <Link href="/ask">Ask</Link>
            </p>
            <section className="workspace-block" aria-labelledby="history-title">
              <div className="block-head">
                <h2 id="history-title">Value over time</h2>
                <Link href="/portfolio">Open the full record</Link>
              </div>
              {series.length >= 2 ? (
                <>
                  <TimeSeriesChart points={analytics.series} valueKey="value" label="Portfolio value" format={money} />
                  {series[0]?.date && series[series.length - 1]?.date ? (
                    <p className="compact-note chart-caption">
                      Stored daily closes run from {money(series[0].value)} on {series[0].date} to {money(series[series.length - 1].value)} on {series[series.length - 1].date}. Total return and volatility use this series, not the quote above.
                    </p>
                  ) : null}
                </>
              ) : (
                <>
                <div className="chart-placeholder" aria-hidden="true"><svg viewBox="0 0 640 120" preserveAspectRatio="none"><line x1="16" x2="624" y1="96" y2="96" /></svg></div>
                <p className="compact-note">
                  {historyNote || "Stored daily history is still too short for a chart."}
                  {" "}
                  {analytics?.observation_count != null ? `${analytics.observation_count} return observation${analytics.observation_count === 1 ? "" : "s"} so far.` : ""}
                  {" "}
                  The figure above uses the latest provider quote. Daily closes are filled after the US session.
                </p>
                </>
              )}
              {analytics?.benchmark?.length >= 2 ? (
                <>
                  <h3>Compared with SPY</h3>
                  <TimeSeriesChart
                    points={analytics.series}
                    valueKey="cumulative_return"
                    label="Portfolio return"
                    format={percent}
                    comparePoints={analytics.benchmark.map((point) => ({ date: point.date, value: point.indexed_return }))}
                    compareLabel="SPY"
                  />
                  <p className="compact-note">Both lines start at zero on the first shared stored close. SPY is the stored S&amp;P 500 proxy. This is not a forecast.</p>
                </>
              ) : series.length >= 2 ? (
                <p className="compact-note">No stored SPY closes overlap this portfolio, so there is no S&amp;P 500 line.</p>
              ) : null}
            </section>
            <details className="advanced-panel">
              <summary>Risk detail — volatility, Sharpe, drawdown</summary>
              <dl className="metric-strip">
                <div>
                  <dt><LearnTerm slug="volatility">Volatility</LearnTerm></dt>
                  <dd>{analytics?.volatility == null ? "—" : percent(analytics.volatility)}</dd>
                  <p>{analytics?.volatility == null ? "Not enough daily returns to annualize." : volatilityNote(analytics)}</p>
                </div>
                <div>
                  <dt><LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm></dt>
                  <dd>{analytics?.sharpe_ratio == null ? "—" : number(analytics.sharpe_ratio, { maximumFractionDigits: 2 })}</dd>
                  <p>{analytics?.sharpe_ratio == null ? "Needs at least two daily returns." : sharpeNote(analytics)}</p>
                </div>
                <div>
                  <dt><LearnTerm slug="max-drawdown">Max drawdown</LearnTerm></dt>
                  <dd className={Number(analytics?.max_drawdown) < 0 ? "down" : ""}>
                    {Number(analytics?.max_drawdown) < 0 ? <AttentionMark /> : null}
                    {!hasReturnSample(analytics) || analytics?.max_drawdown == null ? "—" : percent(analytics.max_drawdown)}
                  </dd>
                  <p>{!hasReturnSample(analytics) || analytics?.max_drawdown == null ? "Needs a longer stored return series." : "Peak to trough on the return index."}</p>
                </div>
              </dl>
            </details>
            <div className="record-grid">
              <section className="workspace-block" aria-labelledby="movers-title">
                <div className="block-head"><h2 id="movers-title">Today&apos;s movers</h2></div>
                {!contributors.length && !detractors.length ? (
                  <p className="compact-note">A previous close is needed before a holding can be called a daily mover.</p>
                ) : (
                  <div className="mover-columns">
                    <div>
                      <h3 className="up">Helped</h3>
                      {contributors.length ? contributors.map((row) => (
                        <Link className="mover-line" key={`up-${row.ticker}`} href={`/securities/${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="up">{money(row.day_pl)}</span>
                        </Link>
                      )) : <p className="muted">No holding is up today.</p>}
                    </div>
                    <div>
                      <h3 className="down">Hurt</h3>
                      {detractors.length ? detractors.map((row) => (
                        <Link className="mover-line" key={`down-${row.ticker}`} href={`/securities/${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="down"><AttentionMark />{money(row.day_pl)}</span>
                        </Link>
                      )) : <p className="muted">No holding is down today.</p>}
                    </div>
                  </div>
                )}
              </section>
              <section className="workspace-block" aria-labelledby="exposure-title">
                <div className="block-head"><h2 id="exposure-title">Where the value sits</h2><p className="muted">Same latest quotes as the positions</p></div>
                {positions?.warnings?.length ? <ul className="compact-note">{positions.warnings.map((note) => <li key={note}>{note}</li>)}</ul> : null}
                {shownAllocation.length ? <AllocationChart rows={shownAllocation} /> : <p className="compact-note">Buy at least one share to see how the portfolio is split.</p>}
                <h3>Sector</h3>
                <BucketChart rows={positions?.sector_allocation} empty="Sector weights appear with priced holdings." />
                <h3>Asset class</h3>
                <BucketChart rows={positions?.asset_allocation} empty="Asset-class weights appear with priced holdings." />
                <h3>Currency</h3>
                <BucketChart rows={positions?.currency_allocation} empty="Currency weights appear with priced holdings." />
              </section>
            </div>
            <section className="workspace-block" aria-labelledby="market-title">
              <div className="block-head">
                <h2 id="market-title">Prices in view</h2>
                <p className="muted">Holdings and watchlist symbols. Quotes reload once a minute while the US market is open, and not while it is closed.</p>
              </div>
              {listedQuotes.length === 0 ? (
                <p className="compact-note">Buy a holding or add a symbol to a watchlist. The latest provider price will show here.</p>
              ) : (
                <ul className="quote-lines">
                  {listedQuotes.map((row) => {
                    const change = Number(row.change);
                    const tone = change > 0 ? "up" : change < 0 ? "down" : "";
                    return (
                      <li key={row.ticker}>
                        <Link href={`/securities/${row.ticker}`}>
                          <CompanyLogo ticker={row.ticker} size={28} />
                          <strong>{row.ticker}</strong>
                          <span className={tone}>{money(row.price)}</span>
                          <span className={tone}>{money(row.change)} · {percent(row.change_percent)}</span>
                          <small>{String(row.timeliness || "").toLowerCase() === "realtime" ? "Real-time" : row.timeliness || "unavailable"} · {row.source || "source unavailable"}</small>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </>
        ) : null}
      </main>
    </>
  );
}
