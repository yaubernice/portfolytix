function significantCount(unsigned) {
  const [whole, fraction] = unsigned.split(".");
  if (fraction != null) {
    return `${whole}${fraction}`.replace(/^0+/, "").length;
  }
  return whole.replace(/^0+/, "").replace(/0+$/, "").length || 1;
}

export const SHORT_RETURN_SAMPLE = 21;

export function usMarketIsOpen(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const read = (type) => parts.find((part) => part.type === type)?.value || "";
  const weekday = read("weekday");
  if (weekday === "Sat" || weekday === "Sun") return false;
  const minutes = Number(read("hour")) * 60 + Number(read("minute"));
  return minutes >= 9 * 60 + 30 && minutes < 16 * 60;
}

export function positionRefreshMs(positions, now = new Date(), sessionOpen = null) {
  if (sessionOpen === false) return null;
  if (sessionOpen !== true && !usMarketIsOpen(now)) return null;
  const ages = (positions?.positions || [])
    .map((row) => Number(row.freshness?.age_seconds))
    .filter((value) => Number.isFinite(value));
  if (ages.length && Math.min(...ages) > 3 * 60 * 60) return 5 * 60 * 1000;
  return 60 * 1000;
}

export function quoteAllocation(positions) {
  return (positions?.positions || [])
    .filter((row) => Number(row.quantity) > 0 && row.weight != null && row.market_value != null)
    .map((row) => ({
      ticker: row.ticker,
      weight: row.weight,
      market_value: row.market_value,
    }));
}

export function hasReturnSample(analytics) {
  return Number(analytics?.observation_count) > 0;
}

export function volatilityNote(analytics) {
  if (analytics?.volatility == null) return "Needs at least two daily returns.";
  return shortSampleNote(analytics.observation_count, "Annualized from stored daily returns.", true);
}

export function sharpeNote(analytics) {
  if (analytics?.sharpe_ratio == null) return "Needs at least two daily returns.";
  return shortSampleNote(analytics.observation_count, "From stored daily returns.", false);
}

function shortSampleNote(count, ready, annualized) {
  const n = Number(count);
  if (!Number.isFinite(n) || n <= 0 || n >= SHORT_RETURN_SAMPLE) return ready;
  const noun = n === 1 ? "return" : "returns";
  const lead = annualized ? "Annualized from" : "From";
  const scale = annualized ? " A short sample can make this number very large." : "";
  return `${lead} ${n} stored daily ${noun}.${scale} It is not a long-run risk figure.`;
}

export function roundFigures(text, digits = 4, final = true) {
  if (text == null || text === "") return text ?? "";
  const source = String(text);
  return source.replace(/-?\$?\d[\d,]*(?:\.\d+)?%?/g, (token, offset) => {
    if (!final && offset + token.length >= source.length) return token;
    const percent = token.endsWith("%");
    const dollar = token.includes("$");
    const negative = token.startsWith("-");
    const unsigned = token.replace(/[^0-9.]/g, "");
    if (!unsigned || unsigned === "." || significantCount(unsigned) <= digits) return token;
    const value = Number(unsigned);
    if (!Number.isFinite(value) || value === 0) return token;
    const rounded = Number((negative ? -value : value).toPrecision(digits));
    const formatted = Math.abs(rounded).toLocaleString("en-US", {
      maximumSignificantDigits: digits,
      useGrouping: dollar || Math.abs(rounded) >= 10000,
    });
    return `${rounded < 0 ? "-" : ""}${dollar ? "$" : ""}${formatted}${percent ? "%" : ""}`;
  });
}
