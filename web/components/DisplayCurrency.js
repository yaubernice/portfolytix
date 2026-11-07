"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatMoney } from "../lib/formatMoney";

const KEY = "finsight_display_currency";
const DisplayCurrencyContext = createContext({
  currency: "USD",
  currencies: ["USD"],
  usdPerUnit: 1,
  asOf: null,
  setCurrency: () => {},
  money: formatMoney,
  ready: false,
});

export function DisplayCurrencyProvider({ children }) {
  const [currency, setCurrencyState] = useState("USD");
  const [rates, setRates] = useState({ USD: 1 });
  const [currencies, setCurrencies] = useState(["USD"]);
  const [asOf, setAsOf] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(KEY);
    if (saved) setCurrencyState(saved);
    let cancelled = false;
    api("/market/fx")
      .then((body) => {
        if (cancelled) return;
        const next = { USD: 1 };
        for (const [code, value] of Object.entries(body.rates || {})) {
          const rate = Number(value);
          if (Number.isFinite(rate) && rate > 0) next[code] = rate;
        }
        setRates(next);
        setCurrencies(Array.isArray(body.currencies) && body.currencies.length ? body.currencies : Object.keys(next));
        setAsOf(body.as_of || null);
        if (saved && !next[saved]) {
          setCurrencyState("USD");
          window.localStorage.setItem(KEY, "USD");
        }
      })
      .catch(() => {
        if (!cancelled) setRates({ USD: 1 });
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setCurrency = useCallback((code) => {
    const next = String(code || "USD").toUpperCase();
    setCurrencyState(next);
    window.localStorage.setItem(KEY, next);
  }, []);

  const usdPerUnit = rates[currency] || 1;

  const money = useCallback((value, explicitCurrency) => {
    if (explicitCurrency) return formatMoney(value, explicitCurrency);
    if (value === null || value === undefined || value === "") return "—";
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";
    const converted = currency === "USD" ? amount : amount / usdPerUnit;
    return formatMoney(converted, currency);
  }, [currency, usdPerUnit]);

  const value = useMemo(
    () => ({ currency, currencies, usdPerUnit, asOf, setCurrency, money, ready }),
    [currency, currencies, usdPerUnit, asOf, setCurrency, money, ready],
  );

  return (
    <DisplayCurrencyContext.Provider value={value}>
      {children}
    </DisplayCurrencyContext.Provider>
  );
}

export function useDisplayCurrency() {
  return useContext(DisplayCurrencyContext);
}
