"use client";

import Link from "next/link";

export default function StartCard({
  title = "Get started",
  lead = "Three steps to see your own numbers here.",
}) {
  return (
    <section className="start-card panel" aria-labelledby="start-card-title">
      <h2 id="start-card-title">{title}</h2>
      <p className="muted">{lead}</p>
      <ol className="start-steps">
        <li>
          <strong>Create a portfolio</strong>
          <span>A real book or a practice book.</span>
          <Link href="/portfolio">Open Portfolio</Link>
        </li>
        <li>
          <strong>Search a company</strong>
          <span>Use the search box in the top bar.</span>
        </li>
        <li>
          <strong>Record a buy</strong>
          <span>From the company page, or on Transactions.</span>
          <Link href="/portfolio?tab=transactions">Add a trade</Link>
        </li>
      </ol>
    </section>
  );
}
