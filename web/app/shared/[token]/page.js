"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useDisplayCurrency } from "../../../components/DisplayCurrency";
import { api } from "../../../lib/api";
import { percent } from "../../../components/UI";

export default function SharedPage() {
  const params = useParams();
  const { money } = useDisplayCurrency();
  const [book, setBook] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.token) return;
    api(`/shared/${params.token}`)
      .then(setBook)
      .catch((err) => setError(err.message));
  }, [params.token]);

  return (
    <main className="content shared-page">
      {error ? <p className="error">{error}</p> : null}
      {!book && !error ? <p>Loading the shared book.</p> : null}
      {book ? (
        <>
          <h1>{book.name}{book.is_paper ? " · Practice" : ""}</h1>
          <p>Market value {book.market_value == null ? "—" : money(book.market_value)}. Time-weighted return {book.total_return == null ? "—" : percent(book.total_return)}.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Ticker</th><th className="numeric">Shares</th><th className="numeric">Weight</th><th className="numeric">Value</th></tr></thead>
            <tbody>{book.positions.map((row) => (
              <tr key={row.ticker}><td>{row.ticker}</td><td className="numeric">{row.quantity}</td><td className="numeric">{percent(row.weight)}</td><td className="numeric">{money(row.market_value)}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="compact-note">{book.disclaimer}</p>
        </>
      ) : null}
    </main>
  );
}
