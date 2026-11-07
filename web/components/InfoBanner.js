"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const KEY = "portfolytix-data-note";

export default function InfoBanner() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setOpen(window.localStorage.getItem(KEY) !== "hidden");
  }, []);

  if (!open) return null;
  return (
    <aside className="info-banner">
      <p>Figures come from stored transactions and prices. A delayed quote stays delayed. A missing figure is a dash, not a zero. This is not investment advice.</p>
      <Link href="/data">Data status</Link>
      <button
        type="button"
        onClick={() => {
          window.localStorage.setItem(KEY, "hidden");
          setOpen(false);
        }}
      >
        Dismiss
      </button>
    </aside>
  );
}
