"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { API_URL, api, clearToken, readToken } from "../lib/api";
import { usePortfolio } from "./usePortfolio";
import InfoBanner from "./InfoBanner";
import Tour from "./Tour";
import LogoMark from "./Logo";
import { useDisplayCurrency } from "./DisplayCurrency";
import { CompanyLogo } from "./UI";

const GROUPS = [
  ["Your money", [
    ["/dashboard", "Dashboard", "dashboard"],
    ["/portfolio", "Overview", "portfolio"],
    ["/portfolio?tab=transactions", "Transactions", "transactions"],
    ["/portfolio?tab=goals", "Goals", "goals"],
    ["/watchlist", "Watchlist", "watchlist"],
  ]],
  ["Discover", [
    ["/ideas", "Ideas", "ideas"],
    ["/news", "News", "news"],
    ["/screen", "Screening", "screen"],
    ["/ask", "Ask", "ask"],
  ]],
  ["Workspace", [
    ["/data", "Data status", "status"],
  ]],
];

function NavGlyph({ name }) {
  const pen = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.6,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  return (
    <svg className="nav-glyph" viewBox="0 0 16 16" aria-hidden="true">
      {name === "dashboard" ? (
        <>
          <rect x="2" y="2" width="5" height="5" {...pen} />
          <rect x="9" y="2" width="5" height="5" {...pen} />
          <rect x="2" y="9" width="5" height="5" {...pen} />
          <rect x="9" y="9" width="5" height="5" {...pen} />
        </>
      ) : null}
      {name === "portfolio" ? <path d="M2 12.5h4M2 10c2.2-.2 3.4-2.6 4.8-3s2 .8 3.2.2 1.4-2.2 2-2.8" {...pen} /> : null}
      {name === "transactions" ? <path d="M3 4.5h10M3 8h10M3 11.5h7M11 10.5l2 1.5-2 1.5" {...pen} /> : null}
      {name === "goals" ? <path d="M8 2.5v11M4.5 6.5 8 3l3.5 3.5" {...pen} /> : null}
      {name === "watchlist" ? <path d="M3 4.5h10M3 8h10M3 11.5h6" {...pen} /> : null}
      {name === "ideas" ? <path d="M8 2.5v2M4 8.5a4 4 0 1 1 8 0c0 1.6-1 2.4-1.6 3.2H5.6C5 10.9 4 10.1 4 8.5ZM6 13.2h4" {...pen} /> : null}
      {name === "news" ? <path d="M3.5 3.5h9v9h-9zM5.5 6.5h5M5.5 9h5" {...pen} /> : null}
      {name === "screen" ? <path d="M2.5 3.5h11l-4 5v3.2l-3 .8V8.5z" {...pen} /> : null}
      {name === "ask" ? <path d="M3 3.5h10v7H7l-2.5 2.2V10.5H3z" {...pen} /> : null}
      {name === "status" ? <path d="M3 12.5V8M8 12.5V4M13 12.5V6.5" {...pen} /> : null}
    </svg>
  );
}

function navActive(pathname, searchParams, href) {
  const [path, query = ""] = href.split("?");
  if (pathname !== path && !(path !== "/dashboard" && pathname.startsWith(`${path}/`))) {
    return false;
  }
  if (path !== "/portfolio") {
    return pathname === path || pathname.startsWith(`${path}/`);
  }
  const tab = searchParams.get("tab") || "overview";
  const wanted = new URLSearchParams(query).get("tab") || "overview";
  return tab === wanted;
}

function NavInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { portfolios, portfolioId, selectPortfolio, email } = usePortfolio();
  const { currency, currencies, setCurrency, asOf } = useDisplayCurrency();
  const [ready, setReady] = useState(false);
  const [theme, setTheme] = useState("light");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [resultTotal, setResultTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [exportNote, setExportNote] = useState("");

  async function exportAccount() {
    setExportNote("");
    try {
      const token = readToken();
      const response = await fetch(`${API_URL}/auth/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        if (response.status === 401) {
          clearToken();
          window.dispatchEvent(new Event("finsight:auth-expired"));
        }
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || response.statusText || "Export failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "portfolytix-report.pdf";
      link.click();
      URL.revokeObjectURL(url);
      setExportNote("PDF downloaded");
    } catch (error) {
      setExportNote(error instanceof Error ? error.message : "Export failed");
    }
  }

  async function deleteAccount() {
    if (!window.confirm("Delete this account and its portfolios? This cannot be undone.")) return;
    await api("/auth/me", { method: "DELETE" });
    clearToken();
    router.replace("/");
  }

  useEffect(() => {
    if (!readToken()) {
      router.replace("/");
      return;
    }
    const savedTheme = localStorage.getItem("finsight_theme");
    const nextTheme = savedTheme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = nextTheme;
    setTheme(nextTheme);
    setReady(true);
  }, [router]);

  useEffect(() => {
    const expired = () => router.replace("/");
    window.addEventListener("finsight:auth-expired", expired);
    return () => window.removeEventListener("finsight:auth-expired", expired);
  }, [router]);

  useEffect(() => {
    if (query.trim().length < 1) {
      setResults([]);
      setResultTotal(0);
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const body = await api(`/securities/search?q=${encodeURIComponent(query.trim())}&limit=12`, {
          signal: controller.signal,
        });
        setResults(body.items || []);
        setResultTotal(Number(body.total) || 0);
      } catch (error) {
        if (error.name !== "AbortError") {
          setResults([]);
          setResultTotal(0);
        }
      } finally {
        setSearching(false);
      }
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("finsight_theme", next);
    document.documentElement.dataset.theme = next;
  }

  if (!ready) return null;

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`} aria-label="Primary navigation">
        <Link className="brand" href="/dashboard" onClick={() => setMenuOpen(false)}>
          <LogoMark />
          <span>
            <strong>Portfolytix</strong>
            <small>Clarity for what you own</small>
          </span>
        </Link>
        <nav>
          {GROUPS.map(([label, links]) => (
            <div className="nav-group" key={label}>
              <p className="nav-label">{label}</p>
              {links.map(([href, name, glyph]) => {
                const active = navActive(pathname, searchParams, href);
                return (
                  <Link key={href} href={href} aria-current={active ? "page" : undefined} onClick={() => setMenuOpen(false)}>
                    <NavGlyph name={glyph} />
                    {name}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="user-label" title={email || "Signed in"}>{email || "Signed in"}</span>
          {email ? (
            <div className="export-block">
              <button type="button" onClick={exportAccount}>Download PDF report</button>
              {exportNote ? <p className="compact-note">{exportNote}</p> : null}
            </div>
          ) : null}
          <button
            type="button"
            className="text-button"
            onClick={() => {
              clearToken();
              router.replace("/");
            }}
          >
            Log out
          </button>
          {email ? (
            <button type="button" className="danger-text" onClick={deleteAccount}>
              Delete account
            </button>
          ) : null}
        </div>
      </aside>
      {menuOpen ? <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} /> : null}
      <header className="topbar">
        <button className="menu-button" type="button" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
          Menu
        </button>
        {portfolios.length ? (
          <label className="field portfolio-switch">
            Portfolio
            <select aria-label="Portfolio" value={portfolioId} onChange={(event) => selectPortfolio(event.target.value)}>
              {portfolios.map((row) => <option key={row.id} value={row.id}>{row.is_paper ? `${row.name} (practice)` : row.name}</option>)}
            </select>
          </label>
        ) : null}
        <label className="field currency-switch" title={asOf ? `FX as of ${asOf}` : "Display currency"}>
          Currency
          <select
            aria-label="Display currency"
            value={currency}
            onChange={(event) => setCurrency(event.target.value)}
          >
            {currencies.map((code) => (
              <option key={code} value={code}>{code}</option>
            ))}
          </select>
        </label>
        <div className="global-search">
          <label className="sr-only" htmlFor="security-search">Search securities</label>
          <input
            id="security-search"
            type="search"
            placeholder="Search any US ticker or company"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setQuery("");
                event.currentTarget.blur();
              }
            }}
            role="combobox"
            aria-autocomplete="list"
            aria-controls="security-search-results"
            aria-expanded={Boolean(query)}
            autoComplete="off"
          />
          {query ? (
            <>
              <p className="sr-only" aria-live="polite">{searching ? "Searching" : `${resultTotal} results`}</p>
              <div id="security-search-results" className="search-results" role="listbox" aria-label="Security results">
                {results.map((item) => (
                  <Link key={item.id} href={`/securities/${item.ticker}`} role="option" onClick={() => setQuery("")}>
                    <CompanyLogo ticker={item.ticker} size={24} />
                    <strong>{item.ticker}</strong>
                    <span>{item.name}</span>
                    <small>{item.exchange}</small>
                  </Link>
                ))}
                {!searching && resultTotal > results.length ? (
                  <p className="search-more">Showing {results.length} of {resultTotal}. Type more letters to narrow.</p>
                ) : null}
              </div>
              {!searching && results.length === 0 ? <p className="search-empty">No matching securities in the US listings catalog</p> : null}
            </>
          ) : null}
        </div>
        <button type="button" className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </header>
      <InfoBanner />
      <Tour />
    </>
  );
}

export default function Nav() {
  return (
    <Suspense fallback={null}>
      <NavInner />
    </Suspense>
  );
}
