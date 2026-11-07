"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const STEPS = [
  {
    title: "Start with a portfolio",
    body: "Create a book for the shares you own — or a practice book to try without real money.",
    href: "/portfolio",
    cta: "Open Portfolio",
  },
  {
    title: "Find a company",
    body: "Use search in the top bar for a ticker or company name. Open the page, then buy a share into your book.",
    href: "/dashboard",
    cta: "Go to Dashboard",
  },
  {
    title: "Record trades and set goals",
    body: "Transactions and Goals live under Portfolio. Ask answers from your stored fills and prices — not a forecast.",
    href: "/portfolio?tab=transactions",
    cta: "Add a trade",
  },
];

const TOUR_KEY = "portfolytix-tour-v2";

export default function Tour() {
  const [step, setStep] = useState(-1);

  useEffect(() => {
    if (window.localStorage.getItem(TOUR_KEY) === "done") return;
    setStep(0);
  }, []);

  if (step < 0) return null;

  const current = STEPS[step];

  function finish() {
    window.localStorage.setItem(TOUR_KEY, "done");
    setStep(-1);
  }

  return (
    <div className="tour" role="dialog" aria-label="Getting started">
      <p className="tour-step">Step {step + 1} of {STEPS.length}</p>
      <h2 className="tour-title">{current.title}</h2>
      <p>{current.body}</p>
      <div className="tour-actions">
        <Link className="primary tour-cta" href={current.href} onClick={finish}>
          {current.cta}
        </Link>
        <div className="row">
          <button type="button" onClick={finish}>Skip</button>
          {step < STEPS.length - 1 ? (
            <button type="button" onClick={() => setStep(step + 1)}>Next</button>
          ) : (
            <button className="primary" type="button" onClick={finish}>Done</button>
          )}
        </div>
      </div>
    </div>
  );
}
