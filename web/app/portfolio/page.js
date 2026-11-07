"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import LearnTerm from "../../components/LearnTerm";
import Nav from "../../components/Nav";
import PortfolioAssistant from "../../components/PortfolioAssistant";
import Ledger from "../../components/Ledger";
import Planning from "../../components/Planning";
import StartCard from "../../components/StartCard";
import { useDisplayCurrency } from "../../components/DisplayCurrency";
import { usePortfolio } from "../../components/usePortfolio";
import {
  ageLabel,
  AllocationChart,
  BucketChart,
  CorrelationHeatmap,
  AttentionMark,
  EmptyState,
  ErrorState,
  KpiCard,
  number,
  percent,
  Skeleton,
  StatusBadge,
  TickerIdentity,
  TimeSeriesChart,
  Toast,
} from "../../components/UI";
import { api } from "../../lib/api";
import { hasReturnSample, positionRefreshMs, quoteAllocation, sharpeNote, volatilityNote } from "../../lib/figures";

const TABS = [
  ["overview", "Overview"],
  ["positions", "Positions"],
  ["transactions", "Transactions"],
  ["goals", "Goals"],
  ["ask", "Ask"],
];

function signedTone(value) {
  if (value == null || value === "") return "";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount === 0) return "";
  return amount > 0 ? "up" : "down";
}

function PortfolioPageInner() {
  const searchParams = useSearchParams();
  const tab = TABS.some(([id]) => id === searchParams.get("tab"))
    ? searchParams.get("tab")
    : "overview";
  const { portfolios, setPortfolios, portfolioId, selectPortfolio, ready, error: portfolioError } = usePortfolio();
  const { money } = useDisplayCurrency();
  const [positions, setPositions] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [practice, setPractice] = useState(false);
  const [toast, setToast] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (ready && !portfolioId) setLoading(false);
  }, [ready, portfolioId]);

  async function createPortfolio(event) {
    event.preventDefault();
    if (!name.trim()) return;
    setError("");
    try {
      const created = await api("/portfolios", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          is_paper: practice,
        }),
      });
      setPortfolios((current) => [...current, created]);
      selectPortfolio(created.id);
      setName("");
      setDescription("");
      setPractice(false);
      setToast("Portfolio created — search a ticker, then record a buy");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    if (!portfolioId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    api(`/portfolios/${portfolioId}/analytics`)
      .then((body) => { if (!cancelled) setAnalytics(body); })
      .catch((err) => {
        if (cancelled) return;
        setAnalytics(null);
        if (!/no transactions/i.test(err.message)) setError(err.message);
      });
    let timer = 0;
    const loadPositions = () => api(`/portfolios/${portfolioId}/positions`)
      .then(async (body) => {
        if (cancelled) return;
        setPositions(body);
        window.clearInterval(timer);
        const session = await api("/market/session").catch(() => null);
        const wait = positionRefreshMs(body, new Date(), session ? session.open : null);
        timer = wait ? window.setInterval(loadPositions, wait) : 0;
      })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    loadPositions();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [portfolioId, revision]);

  const allocationRows = quoteAllocation(positions);
  const shownAllocation = allocationRows.length ? allocationRows : (analytics?.allocation || []);
  const hasPositions = Boolean(positions?.positions?.length);
  const paper = portfolios.find((row) => row.id === portfolioId)?.is_paper;

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header">
          <div>
            <p className="eyebrow">Your portfolio</p>
            <h1>
              Worth, holdings, and activity
              {paper ? " · Practice" : ""}
            </h1>
            <p className="muted">
              Start with what the book is worth today. Advanced return and risk figures stay under More detail.
              Choose the portfolio in the top bar.
            </p>
          </div>
        </header>

        {portfolios.length ? (
          <nav className="filter-tabs page-tabs" aria-label="Portfolio sections">
            {TABS.map(([id, label]) => {
              const href = id === "overview" ? "/portfolio" : `/portfolio?tab=${id}`;
              return (
                <Link
                  key={id}
                  href={href}
                  className="tab-link"
                  aria-current={tab === id ? "page" : undefined}
                >
                  {label}
                </Link>
              );
            })}
          </nav>
        ) : null}

        <ErrorState message={error || portfolioError} retry={() => setRevision((value) => value + 1)} />

        {!loading && portfolios.length === 0 ? (
          <>
            <StartCard
              title="Create your first portfolio"
              lead="Then search a company and record a buy so this page can show your numbers."
            />
            <section className="panel">
              <h2>New portfolio</h2>
              <form className="stack-form" onSubmit={createPortfolio}>
                <label className="field" htmlFor="portfolio-name-empty">Name
                  <input id="portfolio-name-empty" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Taxable" maxLength={200} required />
                </label>
                <label className="field" htmlFor="portfolio-description-empty">Description
                  <input id="portfolio-description-empty" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Optional" maxLength={500} />
                </label>
                <label className="field check-field">
                  <input type="checkbox" checked={practice} onChange={(event) => setPractice(event.target.checked)} />
                  Practice book (no real money)
                </label>
                <button className="primary" type="submit">Create portfolio</button>
              </form>
            </section>
          </>
        ) : null}

        {loading ? <Skeleton lines={4} label="Loading portfolio record" /> : null}

        {!loading && portfolios.length && tab === "overview" ? (
          <>
            {!hasPositions ? (
              <StartCard
                title="This book has no holdings yet"
                lead="Search a ticker above, open the company page, and buy a share — or add a trade under Transactions."
              />
            ) : null}
            <div className="cards primary-kpis">
              <KpiCard label="Worth today" value={money(positions?.market_value)} detail="Latest provider quote" provenance={positions?.market_value == null ? "missing" : "delayed"} />
              <KpiCard label={<LearnTerm slug="day-pl">Up or down today</LearnTerm>} value={positions?.day_pl == null ? "—" : money(positions.day_pl)} tone={Number(positions?.day_pl) < 0 ? "down" : Number(positions?.day_pl) > 0 ? "up" : ""} alert={Number(positions?.day_pl) < 0} detail={positions?.day_pl == null ? "No previous close yet." : "Move since the previous close — not since you bought."} />
              <KpiCard label={<LearnTerm slug="unrealized-pl">Gain or loss vs cost</LearnTerm>} value={positions?.unrealized_pl == null ? "—" : money(positions.unrealized_pl)} tone={Number(positions?.unrealized_pl) < 0 ? "down" : Number(positions?.unrealized_pl) > 0 ? "up" : ""} alert={Number(positions?.unrealized_pl) < 0} detail={positions?.cost_basis == null ? "No cost basis yet." : `Versus average cost ${money(positions.cost_basis)}.`} />
              <KpiCard label="Cash" value={positions?.cash == null ? "—" : money(positions.cash)} detail={positions?.cash == null ? "No cash movement stored." : "Deposits, withdrawals, and dividends in USD."} />
            </div>

            <details className="panel advanced-panel">
              <summary>More detail — return, risk, and income</summary>
              <div className="cards">
                <KpiCard label={<LearnTerm slug="time-weighted-return">Time-weighted return</LearnTerm>} value={!hasReturnSample(analytics) || analytics?.total_return == null ? "—" : percent(analytics.total_return)} tone={Number(analytics?.total_return) < 0 ? "down" : Number(analytics?.total_return) > 0 ? "up" : ""} alert={Number(analytics?.total_return) < 0} provenance={!hasReturnSample(analytics) || analytics?.total_return == null ? "missing" : "computed"} detail={!hasReturnSample(analytics) || analytics?.total_return == null ? "Not enough stored daily history." : "Cash flows removed, not annualized."} />
                <KpiCard label={<LearnTerm slug="volatility">Volatility</LearnTerm>} value={analytics?.volatility == null ? "—" : percent(analytics.volatility)} detail={volatilityNote(analytics)} />
                <KpiCard label={<LearnTerm slug="sharpe-ratio">Sharpe ratio</LearnTerm>} value={analytics?.sharpe_ratio == null ? "—" : number(analytics.sharpe_ratio, { maximumFractionDigits: 2 })} detail={sharpeNote(analytics)} />
                <KpiCard label={<LearnTerm slug="max-drawdown">Max drawdown</LearnTerm>} value={!hasReturnSample(analytics) || analytics?.max_drawdown == null ? "—" : percent(analytics.max_drawdown)} tone={Number(analytics?.max_drawdown) < 0 ? "down" : ""} alert={Number(analytics?.max_drawdown) < 0} provenance={!hasReturnSample(analytics) || analytics?.max_drawdown == null ? "missing" : "computed"} detail={!hasReturnSample(analytics) || analytics?.max_drawdown == null ? "Needs a longer stored return series." : "Peak-to-trough on the return index."} />
                <KpiCard label="Beta vs SPY" value={analytics?.benchmark_beta == null ? "—" : number(analytics.benchmark_beta, { maximumFractionDigits: 2 })} provenance={analytics?.benchmark_beta == null ? "missing" : "computed"} detail={analytics?.benchmark_beta == null ? "Needs five overlapping daily returns with stored SPY closes." : "Sample beta versus SPY. Not a forecast."} />
                <KpiCard label="Realized P/L" value={positions?.realized_pl == null ? "—" : money(positions.realized_pl)} detail={positions?.realized_pl == null ? "No sale has closed a lot." : "First-in, first-out on stored sells."} />
                <KpiCard label="Dividends" value={positions?.income == null ? "—" : money(positions.income)} provenance={positions?.income == null ? "missing" : "historical"} detail={positions?.income == null ? "No dividend is stored." : "Cash income. It does not change the share count."} />
                <KpiCard label="Yield on cost" value={positions?.yield_on_cost == null ? "—" : percent(positions.yield_on_cost)} provenance={positions?.yield_on_cost == null ? "missing" : "computed"} detail={positions?.income_note || "Stored dividend cash divided by cost."} />
                <KpiCard label="Projected income" value={positions?.projected_income == null ? "—" : money(positions.projected_income)} provenance={positions?.projected_income == null ? "missing" : "estimated"} detail="Current value times a stored dividend yield. Not a forecast." />
                <KpiCard label="Fund expense" value={positions?.fund_expense == null ? "—" : money(positions.fund_expense)} provenance={positions?.fund_expense == null ? "missing" : "estimated"} detail="Current value times a stored expense ratio." />
              </div>
            </details>

            {!loading && analytics?.series?.filter((point) => point.value != null).length >= 2 ? (
              <div className="portfolio-chart-grid">
                <section className="panel"><div className="panel-header"><h2>Value over time</h2><span className="muted">{analytics?.observation_count ?? 0} return observations</span></div><TimeSeriesChart points={analytics.series} valueKey="value" label="Portfolio value" format={money} /></section>
                <section className="panel"><div className="panel-header"><h2><LearnTerm slug="time-weighted-return">Cumulative return</LearnTerm></h2><span className="muted">{analytics?.benchmark?.length >= 2 ? "Portfolio and stored SPY" : "No overlapping SPY closes"}</span></div><TimeSeriesChart points={analytics.series} valueKey="cumulative_return" label="Portfolio return" format={percent} comparePoints={(analytics.benchmark || []).map((point) => ({ date: point.date, value: point.indexed_return }))} compareLabel={analytics?.benchmark?.length >= 2 ? "SPY" : ""} /></section>
                <section className="panel"><div className="panel-header"><h2>Daily P/L</h2><span className="muted">External cash flows removed</span></div><TimeSeriesChart points={analytics.series} valueKey="daily_pl" label="Daily P/L" format={money} /></section>
                <section className="panel"><div className="panel-header"><h2><LearnTerm slug="max-drawdown">Drawdown</LearnTerm></h2><span className="muted">Point-in-time TWR drawdown</span></div><TimeSeriesChart points={analytics.series} valueKey="drawdown" label="Drawdown" format={percent} tone="down" /></section>
              </div>
            ) : null}
            {!loading && portfolioId && !analytics ? <p className="compact-note">Stored daily history is not available yet. After you buy a share, the nightly history job fills closes.</p> : null}

            <div className="split-grid">
              <section className="panel">
                <div className="panel-header"><h2>Where the value sits</h2><span className="muted">Same quotes as positions</span></div>
                {positions?.warnings?.length ? <ul className="compact-note">{positions.warnings.map((note) => <li key={note}>{note}</li>)}</ul> : null}
                {shownAllocation.length ? <AllocationChart rows={shownAllocation} /> : <p className="compact-note">{loading ? "Loading allocation." : "Buy at least one share to see the split."}</p>}
                <h3>Sector</h3><BucketChart rows={positions?.sector_allocation} empty="Sector weights appear with priced holdings." />
                <h3>Asset class</h3><BucketChart rows={positions?.asset_allocation} empty="Asset-class weights appear with priced holdings." />
                <h3>Currency</h3><BucketChart rows={positions?.currency_allocation} empty="Currency weights appear with priced holdings." />
              </section>
              <section className="panel">
                <div className="panel-header"><h2>Today&apos;s movers</h2><span className="muted">Ranked by day P/L</span></div>
                <div className="movers-grid">
                  <div>
                    <h3 className="up">Helped</h3>
                    {positions?.top_contributors?.length
                      ? positions.top_contributors.map((row) => (
                        <div className="mover-row" key={`up-${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="up">{money(row.day_pl)}</span>
                        </div>
                      ))
                      : <p className="muted">No positive contributors.</p>}
                  </div>
                  <div>
                    <h3 className="down">Hurt</h3>
                    {positions?.top_detractors?.length
                      ? positions.top_detractors.map((row) => (
                        <div className="mover-row" key={`down-${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={22} />
                          <span className="down"><AttentionMark />{money(row.day_pl)}</span>
                        </div>
                      ))
                      : <p className="muted">No detractors.</p>}
                  </div>
                </div>
              </section>
            </div>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Holdings snapshot</h2>
                  <p className="muted">Open Positions for the full table, freshness, and correlations.</p>
                </div>
                <Link href="/portfolio?tab=positions">View all positions</Link>
              </div>
              {!hasPositions ? (
                <EmptyState title="No positions yet">
                  <Link href="/portfolio?tab=transactions">Record a trade</Link>
                </EmptyState>
              ) : (
                <ul className="holding-snapshot">
                  {[...positions.positions]
                    .sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0))
                    .slice(0, 6)
                    .map((row) => (
                      <li key={row.ticker}>
                        <Link href={`/securities/${row.ticker}`}>
                          <TickerIdentity ticker={row.ticker} size={24} />
                          <span className="numeric">{money(row.market_value)}</span>
                          <span className={`numeric ${signedTone(row.day_pl)}`}>
                            {row.day_pl == null ? "—" : money(row.day_pl)}
                          </span>
                        </Link>
                      </li>
                    ))}
                </ul>
              )}
            </section>

            <details className="panel">
              <summary>Create another portfolio</summary>
              <form className="stack-form" onSubmit={createPortfolio}>
                <label className="field" htmlFor="portfolio-name-extra">Name
                  <input id="portfolio-name-extra" value={name} onChange={(event) => setName(event.target.value)} placeholder="New portfolio name" maxLength={200} required />
                </label>
                <label className="field" htmlFor="portfolio-description-extra">Description
                  <input id="portfolio-description-extra" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Optional" maxLength={500} />
                </label>
                <label className="field check-field">
                  <input type="checkbox" checked={practice} onChange={(event) => setPractice(event.target.checked)} />
                  Practice book
                </label>
                <button className="primary" type="submit">Create portfolio</button>
              </form>
            </details>
          </>
        ) : null}

        {!loading && portfolios.length && tab === "positions" ? (
          <>
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h2>Positions</h2>
                  <p className="muted">Quotes refresh about once a minute while the US market is open. A delayed quote stays delayed.</p>
                </div>
              </div>
              {!hasPositions ? (
                <EmptyState title="No positions">
                  <Link href="/portfolio?tab=transactions">Add transactions</Link>
                </EmptyState>
              ) : (
                <>
                  <div className="table-wrap desktop-only">
                    <table>
                      <thead>
                        <tr>
                          <th>Ticker</th>
                          <th className="numeric">Quantity</th>
                          <th className="numeric">Average cost</th>
                          <th className="numeric">Cost basis</th>
                          <th className="numeric">Current price</th>
                          <th className="numeric">Market value</th>
                          <th className="numeric"><LearnTerm slug="unrealized-pl">Unrealized P/L</LearnTerm></th>
                          <th className="numeric"><LearnTerm slug="day-pl">Day P/L</LearnTerm></th>
                          <th className="numeric">Weight</th>
                          <th>Freshness</th>
                        </tr>
                      </thead>
                      <tbody>
                        {positions.positions.map((row) => (
                          <tr key={row.ticker}>
                            <td>
                              <Link className="ticker-link" href={`/securities/${row.ticker}`}>
                                <TickerIdentity ticker={row.ticker} size={24} />
                              </Link>
                            </td>
                            <td className="numeric">{number(row.quantity, { maximumFractionDigits: 6 })}</td>
                            <td className="numeric">{money(row.average_cost)}</td>
                            <td className="numeric">{money(row.cost_basis)}</td>
                            <td className="numeric">{money(row.current_price)}</td>
                            <td className="numeric">{money(row.market_value)}</td>
                            <td className={`numeric ${signedTone(row.unrealized_pl)}`}>
                              {Number(row.unrealized_pl) < 0 ? <AttentionMark /> : null}
                              {money(row.unrealized_pl)}
                            </td>
                            <td className={`numeric ${signedTone(row.day_pl)}`}>
                              {Number(row.day_pl) < 0 ? <AttentionMark /> : null}
                              {money(row.day_pl)}
                            </td>
                            <td className="numeric">{percent(row.weight)}</td>
                            <td>
                              <StatusBadge value={row.freshness?.timeliness || "unavailable"} />
                              <small className="freshness-detail">
                                {row.freshness?.source}
                                {row.freshness?.age_seconds != null ? ` · ${ageLabel(row.freshness.age_seconds)}` : ""}
                              </small>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <ul className="position-cards mobile-only">
                    {positions.positions.map((row) => (
                      <li key={row.ticker} className="position-card">
                        <Link href={`/securities/${row.ticker}`} className="position-card-head">
                          <TickerIdentity ticker={row.ticker} size={28} />
                          <StatusBadge value={row.freshness?.timeliness || "unavailable"} />
                        </Link>
                        <dl className="position-card-grid">
                          <div><dt>Qty</dt><dd>{number(row.quantity, { maximumFractionDigits: 4 })}</dd></div>
                          <div><dt>Value</dt><dd>{money(row.market_value)}</dd></div>
                          <div><dt>Day</dt><dd className={signedTone(row.day_pl)}>{money(row.day_pl)}</dd></div>
                          <div><dt>P/L</dt><dd className={signedTone(row.unrealized_pl)}>{money(row.unrealized_pl)}</dd></div>
                          <div><dt>Weight</dt><dd>{percent(row.weight)}</dd></div>
                          <div><dt>Avg cost</dt><dd>{money(row.average_cost)}</dd></div>
                        </dl>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
            {analytics?.correlations?.length ? (
              <details className="panel">
                <summary>Correlation with the portfolio</summary>
                <p className="muted">Needs five overlapping daily returns. Stored history, not a forecast.</p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th className="numeric">Overlapping days</th>
                        <th className="numeric">Correlation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.correlations.map((row) => (
                        <tr key={row.ticker}>
                          <td>{row.ticker}</td>
                          <td className="numeric">{row.observations}</td>
                          <td className="numeric">{row.value == null ? "—" : number(row.value, { maximumFractionDigits: 2 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {analytics.correlation_pairs?.length ? (
                  <>
                    <h3>Holding pairs</h3>
                    <CorrelationHeatmap
                      tickers={[...new Set(analytics.correlations.map((row) => row.ticker))]}
                      pairs={analytics.correlation_pairs}
                    />
                  </>
                ) : null}
              </details>
            ) : null}
          </>
        ) : null}

        {!loading && portfolios.length && tab === "transactions" && portfolioId ? (
          <Ledger
            portfolioId={portfolioId}
            lots={positions?.lots || []}
            onChange={() => setRevision((value) => value + 1)}
          />
        ) : null}

        {!loading && portfolios.length && tab === "goals" && portfolioId ? (
          <Planning portfolioId={portfolioId} />
        ) : null}

        {!loading && portfolios.length && tab === "ask" && portfolioId ? (
          <PortfolioAssistant portfolioId={portfolioId} />
        ) : null}

        <Toast message={toast} onDismiss={() => setToast("")} />
      </main>
    </>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense fallback={<><Nav /><main id="main-content" className="content"><Skeleton lines={4} label="Loading portfolio" /></main></>}>
      <PortfolioPageInner />
    </Suspense>
  );
}
