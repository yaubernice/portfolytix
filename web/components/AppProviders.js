"use client";

import { DisplayCurrencyProvider } from "./DisplayCurrency";

export default function AppProviders({ children }) {
  return <DisplayCurrencyProvider>{children}</DisplayCurrencyProvider>;
}
