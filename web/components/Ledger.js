"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useDisplayCurrency } from "./DisplayCurrency";
import { dateTime, number } from "./UI";

const EMPTY_TRADE = { ticker: "", transaction_type: "BUY", quantity: "1", price: "", timestamp: "" };

function downloadCsv(trades) {
  const header = "ticker,side,quantity,price,timestamp";
  const lines = trades.map((row) => [row.ticker, row.transaction_type, row.quantity, row.price, row.timestamp].join(","));
  const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "fills.csv";
  link.click();
  URL.revokeObjectURL(url);
}
const EMPTY_CASH = { kind: "deposit", amount: "", currency: "USD", fx_rate: "", ticker: "", timestamp: "", note: "" };
const EMPTY_SPLIT = { ticker: "", numerator: "2", denominator: "1", timestamp: "" };

export default function Ledger({ portfolioId, lots = [], onChange }) {
  const { money } = useDisplayCurrency();
  const [trades, setTrades] = useState([]);
  const [cash, setCash] = useState([]);
  const [splits, setSplits] = useState([]);
  const [trade, setTrade] = useState(EMPTY_TRADE);
  const [editing, setEditing] = useState("");
  const [cashForm, setCashForm] = useState(EMPTY_CASH);
  const [splitForm, setSplitForm] = useState(EMPTY_SPLIT);
  const [error, setError] = useState("");
  const [importNote, setImportNote] = useState("");

  const load = useCallback(async () => {
    const [tradeRows, cashRows, splitRows] = await Promise.all([
      api(`/portfolios/${portfolioId}/transactions`),
      api(`/portfolios/${portfolioId}/cash`),
      api(`/portfolios/${portfolioId}/splits`),
    ]);
    setTrades(tradeRows);
    setCash(cashRows);
    setSplits(splitRows);
  }, [portfolioId]);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  async function saveTrade(event) {
    event.preventDefault();
    setError("");
    const payload = {
      ticker: trade.ticker.trim().toUpperCase(),
      transaction_type: trade.transaction_type,
      quantity: trade.quantity,
      price: trade.price,
      timestamp: trade.timestamp ? new Date(trade.timestamp).toISOString() : null,
      price_basis: "entered",
    };
    try {
      if (editing) {
        const { ticker: _ticker, ...changes } = payload;
        await api(`/portfolios/${portfolioId}/transactions/${editing}`, {
          method: "PATCH",
          body: JSON.stringify(changes),
        });
      } else {
        await api(`/portfolios/${portfolioId}/transactions`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setTrade(EMPTY_TRADE);
      setEditing("");
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeTrade(row) {
    setError("");
    try {
      await api(`/portfolios/${portfolioId}/transactions/${row.id}`, { method: "DELETE" });
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function importFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setImportNote("");
    const text = await file.text();
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    const start = /ticker/i.test(lines[0] || "") ? 1 : 0;
    const rows = [];
    for (const line of lines.slice(start)) {
      const [ticker, side, quantity, price, timestamp] = line.split(",").map((part) => part.trim());
      if (!ticker || !side || !quantity || !price) {
        setError("Each CSV row needs ticker, side, quantity, and price.");
        return;
      }
      rows.push({
        ticker,
        transaction_type: side.toUpperCase(),
        quantity,
        price,
        timestamp: timestamp ? new Date(timestamp).toISOString() : null,
        price_basis: "entered",
      });
    }
    if (!rows.length) {
      setError("The CSV has no fill rows.");
      return;
    }
    try {
      const saved = await api(`/portfolios/${portfolioId}/transactions/import`, {
        method: "POST",
        body: JSON.stringify({ rows }),
      });
      setImportNote(`Stored ${saved.length} fill${saved.length === 1 ? "" : "s"} at the prices in the file.`);
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveCash(event) {
    event.preventDefault();
    setError("");
    const payload = {
      kind: cashForm.kind,
      amount: cashForm.amount,
      currency: cashForm.currency.trim().toUpperCase() || "USD",
      fx_rate: cashForm.currency.trim().toUpperCase() === "USD" ? null : cashForm.fx_rate,
      ticker: cashForm.kind === "dividend" ? cashForm.ticker.trim().toUpperCase() : null,
      timestamp: cashForm.timestamp ? new Date(cashForm.timestamp).toISOString() : null,
      note: cashForm.note.trim() || null,
    };
    try {
      await api(`/portfolios/${portfolioId}/cash`, { method: "POST", body: JSON.stringify(payload) });
      setCashForm(EMPTY_CASH);
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveSplit(event) {
    event.preventDefault();
    setError("");
    try {
      await api(`/portfolios/${portfolioId}/splits`, {
        method: "POST",
        body: JSON.stringify({
          ticker: splitForm.ticker.trim().toUpperCase(),
          numerator: Number(splitForm.numerator),
          denominator: Number(splitForm.denominator),
          timestamp: splitForm.timestamp ? new Date(splitForm.timestamp).toISOString() : null,
        }),
      });
      setSplitForm(EMPTY_SPLIT);
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeRow(path) {
    setError("");
    try {
      await api(path, { method: "DELETE" });
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel" aria-labelledby="ledger-title">
      <div className="panel-header">
        <div>
          <h2 id="ledger-title">Record buys and sells</h2>
          <button type="button" onClick={() => downloadCsv(trades)}>Export fills CSV</button>
          <p className="muted">Enter the price you paid. Cash, dividends, and splits are below. A split changes shares already held and does not invent a price.</p>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {importNote ? <p className="compact-note">{importNote}</p> : null}
      <form className="stack-form trade-form" onSubmit={saveTrade}>
        <div className="form-grid">
          <label className="field">Ticker<input value={trade.ticker} onChange={(event) => setTrade({ ...trade, ticker: event.target.value })} required placeholder="AAPL" /></label>
          <label className="field">Side<select value={trade.transaction_type} onChange={(event) => setTrade({ ...trade, transaction_type: event.target.value })}><option>BUY</option><option>SELL</option></select></label>
          <label className="field">Shares<input type="number" min="1" step="1" value={trade.quantity} onChange={(event) => setTrade({ ...trade, quantity: event.target.value })} required /></label>
          <label className="field">Price<input inputMode="decimal" value={trade.price} onChange={(event) => setTrade({ ...trade, price: event.target.value })} required /></label>
          <label className="field">When<input type="datetime-local" value={trade.timestamp} onChange={(event) => setTrade({ ...trade, timestamp: event.target.value })} /></label>
        </div>
        <div className="row">
          <button className="primary" type="submit">{editing ? "Save fill" : "Add fill"}</button>
          {editing ? <button type="button" onClick={() => { setEditing(""); setTrade(EMPTY_TRADE); }}>Cancel</button> : null}
        </div>
      </form>
      <label className="field">Import CSV
        <input type="file" accept=".csv,text/csv" onChange={importFile} />
      </label>
      <p className="muted">Columns: ticker, side, quantity, price, timestamp. The header row is optional.</p>
      {trades.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>Ticker</th><th>Side</th><th className="numeric">Shares</th><th className="numeric">Price</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{trades.map((row) => (
            <tr key={row.id}>
              <td>{dateTime(row.timestamp)}</td>
              <td>{row.ticker}</td>
              <td>{row.transaction_type}</td>
              <td className="numeric">{number(row.quantity, { maximumFractionDigits: 0 })}</td>
              <td className="numeric">{money(row.price)}</td>
              <td className="numeric">
                <button type="button" onClick={() => { setEditing(row.id); setTrade({ ticker: row.ticker, transaction_type: row.transaction_type, quantity: String(row.quantity), price: String(row.price), timestamp: "" }); }}>Edit</button>
                <button type="button" onClick={() => removeTrade(row)}>Delete</button>
              </td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <p className="compact-note">No fills stored on this portfolio yet.</p>}

      <h3>Cash and dividends</h3>
      <form className="row" onSubmit={saveCash}>
        <label className="field">Kind<select value={cashForm.kind} onChange={(event) => setCashForm({ ...cashForm, kind: event.target.value })}><option value="deposit">Deposit</option><option value="withdrawal">Withdrawal</option><option value="dividend">Dividend</option></select></label>
        <label className="field">Amount<input inputMode="decimal" value={cashForm.amount} onChange={(event) => setCashForm({ ...cashForm, amount: event.target.value })} required /></label>
        <label className="field">Currency<input maxLength={3} value={cashForm.currency} onChange={(event) => setCashForm({ ...cashForm, currency: event.target.value })} /></label>
        {cashForm.currency.trim().toUpperCase() !== "USD" ? <label className="field">USD per unit<input inputMode="decimal" value={cashForm.fx_rate} onChange={(event) => setCashForm({ ...cashForm, fx_rate: event.target.value })} required /></label> : null}
        {cashForm.kind === "dividend" ? <label className="field">Ticker<input value={cashForm.ticker} onChange={(event) => setCashForm({ ...cashForm, ticker: event.target.value })} required /></label> : null}
        <label className="field">When<input type="datetime-local" value={cashForm.timestamp} onChange={(event) => setCashForm({ ...cashForm, timestamp: event.target.value })} /></label>
        <label className="field">Note<input value={cashForm.note} onChange={(event) => setCashForm({ ...cashForm, note: event.target.value })} maxLength={300} /></label>
        <button type="submit">Add cash</button>
      </form>
      {cash.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>Kind</th><th>Ticker</th><th className="numeric">Amount</th><th>Currency</th><th className="numeric">USD</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{cash.map((row) => (
            <tr key={row.id}>
              <td>{dateTime(row.timestamp)}</td>
              <td>{row.kind}</td>
              <td>{row.ticker || "—"}</td>
              <td className="numeric">{number(row.amount, { maximumFractionDigits: 2 })}</td>
              <td>{row.currency}</td>
              <td className="numeric">{row.usd_amount == null ? "—" : money(row.usd_amount)}</td>
              <td className="numeric"><button type="button" onClick={() => removeRow(`/portfolios/${portfolioId}/cash/${row.id}`)}>Delete</button></td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <p className="compact-note">No cash movement is stored.</p>}

      <h3>Splits</h3>
      <form className="row" onSubmit={saveSplit}>
        <label className="field">Ticker<input value={splitForm.ticker} onChange={(event) => setSplitForm({ ...splitForm, ticker: event.target.value })} required /></label>
        <label className="field">New shares<input type="number" min="1" value={splitForm.numerator} onChange={(event) => setSplitForm({ ...splitForm, numerator: event.target.value })} required /></label>
        <label className="field">Old shares<input type="number" min="1" value={splitForm.denominator} onChange={(event) => setSplitForm({ ...splitForm, denominator: event.target.value })} required /></label>
        <label className="field">When<input type="datetime-local" value={splitForm.timestamp} onChange={(event) => setSplitForm({ ...splitForm, timestamp: event.target.value })} /></label>
        <button type="submit">Add split</button>
      </form>
      {splits.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>Ticker</th><th>Ratio</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{splits.map((row) => (
            <tr key={row.id}><td>{dateTime(row.timestamp)}</td><td>{row.ticker}</td><td>{row.numerator}-for-{row.denominator}</td><td className="numeric"><button type="button" onClick={() => removeRow(`/portfolios/${portfolioId}/splits/${row.id}`)}>Delete</button></td></tr>
          ))}</tbody>
        </table></div>
      ) : <p className="compact-note">No split is stored.</p>}

      <h3>Tax lots</h3>
      <p className="muted">Open and closed lots use first-in, first-out. The position row still shows average cost. A long holding period is more than 365 days and is not tax advice. Editing a fill keeps the old row and writes a replacement.</p>
      {lots.length ? (
        <div className="table-wrap"><table>
          <thead><tr><th>Ticker</th><th>Status</th><th className="numeric">Shares</th><th className="numeric">Cost</th><th className="numeric">Sell</th><th className="numeric">Realized</th><th>Opened</th><th>Held</th></tr></thead>
          <tbody>{lots.map((row) => (
            <tr key={`${row.ticker}-${row.status}-${row.opened_at}-${row.quantity}`}>
              <td>{row.ticker}</td>
              <td>{row.status}</td>
              <td className="numeric">{number(row.quantity, { maximumFractionDigits: 4 })}</td>
              <td className="numeric">{money(row.cost_price)}</td>
              <td className="numeric">{row.sell_price == null ? "—" : money(row.sell_price)}</td>
              <td className="numeric">{row.realized_pl == null ? "—" : money(row.realized_pl)}</td>
              <td>{dateTime(row.opened_at)}</td>
              <td>{row.held_days == null ? "—" : `${row.held_days}d ${row.holding_period || ""}`}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <p className="compact-note">Lots appear after a fill is stored.</p>}
    </section>
  );
}
