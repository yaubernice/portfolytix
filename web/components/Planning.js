"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useDisplayCurrency } from "./DisplayCurrency";
import { percent } from "./UI";

export default function Planning({ portfolioId }) {
  const { money } = useDisplayCurrency();
  const [goals, setGoals] = useState([]);
  const [goal, setGoal] = useState({ name: "", target_amount: "", target_date: "", monthly_contribution: "" });
  const [plan, setPlan] = useState({ monthly: "200", months: "12" });
  const [preview, setPreview] = useState(null);
  const [look, setLook] = useState(null);
  const [behavior, setBehavior] = useState(null);
  const [note, setNote] = useState({ ticker: "", note: "" });
  const [income, setIncome] = useState([]);
  const [share, setShare] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!portfolioId) return undefined;
    let cancelled = false;
    Promise.all([
      api(`/portfolios/${portfolioId}/goals`),
      api(`/portfolios/${portfolioId}/look-through`),
      api(`/portfolios/${portfolioId}/behavior`),
      api(`/portfolios/${portfolioId}/income-events`),
    ]).then(([goalRows, lookRows, behaviorRows, incomeRows]) => {
      if (cancelled) return;
      setGoals(goalRows);
      setLook(lookRows);
      setBehavior(behaviorRows);
      setIncome(incomeRows);
    }).catch((err) => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, [portfolioId]);

  async function saveGoal(event) {
    event.preventDefault();
    setError("");
    try {
      const created = await api(`/portfolios/${portfolioId}/goals`, {
        method: "POST",
        body: JSON.stringify({
          name: goal.name.trim(),
          target_amount: goal.target_amount,
          target_date: goal.target_date,
          monthly_contribution: goal.monthly_contribution || "0",
        }),
      });
      setGoals((current) => [...current, created]);
      setGoal({ name: "", target_amount: "", target_date: "", monthly_contribution: "" });
    } catch (err) {
      setError(err.message);
    }
  }

  async function previewContribution(event) {
    event.preventDefault();
    setError("");
    try {
      const body = await api(`/portfolios/${portfolioId}/contribution?monthly=${encodeURIComponent(plan.monthly)}&months=${encodeURIComponent(plan.months)}`);
      setPreview(body);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshFunds() {
    setError("");
    try {
      setLook(await api(`/portfolios/${portfolioId}/look-through/refresh`, { method: "POST" }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveNote(event) {
    event.preventDefault();
    setError("");
    try {
      const created = await api(`/portfolios/${portfolioId}/journal`, {
        method: "POST",
        body: JSON.stringify({ note: note.note.trim(), ticker: note.ticker.trim() || null }),
      });
      setBehavior((current) => current ? { ...current, entries: [created, ...(current.entries || [])] } : current);
      setNote({ ticker: "", note: "" });
    } catch (err) {
      setError(err.message);
    }
  }

  async function createShare() {
    setError("");
    try {
      const body = await api(`/portfolios/${portfolioId}/share`, { method: "POST" });
      setShare(`${window.location.origin}${body.path}`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Goals</h2>
          <p className="muted">Progress uses current market value. Scenario rates are assumptions, not a forecast.</p>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <h3>Set a goal</h3>
      <form className="stack-form" onSubmit={saveGoal}>
        <div className="form-grid">
          <input aria-label="Goal name" value={goal.name} onChange={(event) => setGoal({ ...goal, name: event.target.value })} placeholder="Goal name" required maxLength={200} />
          <input aria-label="Target amount" value={goal.target_amount} onChange={(event) => setGoal({ ...goal, target_amount: event.target.value })} placeholder="Target amount" inputMode="decimal" required />
          <input aria-label="Target date" type="date" value={goal.target_date} onChange={(event) => setGoal({ ...goal, target_date: event.target.value })} required />
          <input aria-label="Monthly contribution" value={goal.monthly_contribution} onChange={(event) => setGoal({ ...goal, monthly_contribution: event.target.value })} placeholder="Monthly amount" inputMode="decimal" />
        </div>
        <button className="primary" type="submit">Save goal</button>
      </form>
      {goals.map((row) => (
        <article key={row.id} className="goal-card">
          <strong>{row.name}</strong>
          <p>Target {money(row.target_amount)} by {row.target_date}. Progress {row.progress == null ? "—" : percent(row.progress)}. {row.months_remaining} months left.</p>
          <p>At 0% the gap needs {row.required_monthly_at_zero == null ? "—" : money(row.required_monthly_at_zero)} a month. At a 4% assumption it needs {row.required_monthly_at_four_percent == null ? "—" : money(row.required_monthly_at_four_percent)} a month.</p>
          <ul>{row.scenarios.map((item) => <li key={item.annual_rate}>{item.label}: {money(item.future_value)} if {money(item.monthly_contribution)} continues.</li>)}</ul>
          <p className="compact-note">{row.note}</p>
        </article>
      ))}

      <details className="planning-section">
        <summary>Contribution planner</summary>
      <form className="stack-form" onSubmit={previewContribution}>
        <div className="form-grid">
          <input aria-label="Monthly amount" value={plan.monthly} onChange={(event) => setPlan({ ...plan, monthly: event.target.value })} inputMode="decimal" required />
          <input aria-label="Months" value={plan.months} onChange={(event) => setPlan({ ...plan, months: event.target.value })} inputMode="numeric" required />
        </div>
        <button type="submit">Calculate</button>
      </form>
      {preview ? (
        <div>
          <p>{money(preview.monthly)} a month for {preview.months} months is {money(preview.contributed)} contributed.{preview.shares != null ? ` At the latest stored price ${money(preview.price)} that buys ${preview.shares} shares of the only holding.` : ""}</p>
          {preview.equal_weight?.length ? <ul>{preview.equal_weight.map((row) => <li key={row.ticker}>{row.ticker}: {money(row.amount)} toward an equal share of the current names.</li>)}</ul> : <p className="compact-note">The current names are already at or above an equal share, or there is nothing to split.</p>}
          <p className="compact-note">{preview.note}</p>
        </div>
      ) : null}
      </details>

      <details className="planning-section">
        <summary>Fund look-through</summary>
      <p className="muted">A fund is expanded only when its constituents are stored. Nothing is estimated.</p>
      <button type="button" onClick={refreshFunds}>Refresh stored fund holdings</button>
      {look?.notes?.map((item) => <p className="compact-note" key={item}>{item}</p>)}
      {look?.rows?.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>Ticker</th><th className="numeric">Direct</th><th className="numeric">Look-through</th></tr></thead>
          <tbody>{look.rows.map((row) => <tr key={row.ticker}><td>{row.ticker}</td><td className="numeric">{percent(row.direct_weight)}</td><td className="numeric">{percent(row.look_through_weight)}</td></tr>)}</tbody>
        </table></div>
      ) : <p className="compact-note">No priced holdings yet.</p>}
      </details>

      <details className="planning-section">
        <summary>Stored dividends</summary>
      <p className="muted">Earnings dates are not stored.</p>
      {income.length ? (
        <ul>{income.map((row) => <li key={`${row.timestamp}-${row.ticker}`}>{row.timestamp.slice(0, 10)} {row.ticker || "Cash"} {money(row.amount)}</li>)}</ul>
      ) : <p className="compact-note">No dividend cash is stored.</p>}
      </details>

      <details className="planning-section">
        <summary>Decision journal</summary>
      {behavior ? <p>{behavior.trade_count} stored fills. Average open lot {behavior.average_holding_days == null ? "—" : `${Number(behavior.average_holding_days).toFixed(0)} days`}. Buys at least 10% above an earlier stored close: {behavior.buys_after_runup == null ? "—" : behavior.buys_after_runup} of {behavior.buys_with_history} with history.</p> : null}
      <p className="compact-note">{behavior?.note}</p>
      <form className="stack-form" onSubmit={saveNote}>
        <div className="form-grid">
          <input aria-label="Journal ticker" value={note.ticker} onChange={(event) => setNote({ ...note, ticker: event.target.value })} placeholder="Ticker (optional)" maxLength={16} />
          <input aria-label="Journal note" value={note.note} onChange={(event) => setNote({ ...note, note: event.target.value })} placeholder="What you decided" required maxLength={2000} />
        </div>
        <button type="submit">Save note</button>
      </form>
      <ul>{(behavior?.entries || []).map((row) => <li key={row.id}>{row.ticker ? `${row.ticker}: ` : ""}{row.note}</li>)}</ul>
      </details>

      <details className="planning-section">
        <summary>Read-only share link</summary>
      <button type="button" onClick={createShare}>Create a read-only link</button>
      {share ? <p className="share-once">Copy this now — it is shown once. Anyone with it can view positions, not edit them.<br /><code>{share}</code></p> : null}
      </details>
    </section>
  );
}
