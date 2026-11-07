"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerText, EvidenceList, answerOrigin } from "../../components/EvidenceList";
import GeneratingStatus, { ASK_PHASES } from "../../components/GeneratingStatus";
import Nav from "../../components/Nav";
import { ErrorState, StatusBadge } from "../../components/UI";
import { api, authenticatedEventStream } from "../../lib/api";

export default function AskPage() {
  const [portfolios, setPortfolios] = useState([]);
  const [portfolioId, setPortfolioId] = useState("");
  const [scope, setScope] = useState("market");
  const [text, setText] = useState("");
  const [asked, setAsked] = useState("");
  const [evidence, setEvidence] = useState(null);
  const [error, setError] = useState("");
  const [state, setState] = useState("idle");
  const controllerRef = useRef(null);

  useEffect(() => {
    api("/portfolios").then((rows) => {
      setPortfolios(rows);
      if (rows[0]) {
        setPortfolioId(rows[0].id);
        setScope("portfolio");
      }
    }).catch((err) => setError(err.message));
  }, []);

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setAsked(String(form.get("question") || ""));
    setError("");
    setText("");
    setEvidence(null);
    setState("thinking");
    try {
      if (scope === "market") {
        const body = await api("/assistant/research", {
          method: "POST",
          body: JSON.stringify({ question: form.get("question") }),
          signal: controller.signal,
        });
        setEvidence({
          interpretation_source: body.interpretation_source,
          disclaimer: body.disclaimer,
          sources: body.sources,
          research_provider: body.research_provider,
          model: body.model,
        });
        setText(body.interpretation);
        setState("complete");
        return;
      }
      for await (const message of authenticatedEventStream(
        `/portfolios/${portfolioId}/ask/stream`,
        { question: form.get("question") },
        { signal: controller.signal },
      )) {
        if (message.event === "evidence") setEvidence(message.data);
        if (message.event === "text") {
          setState("streaming");
          setText((current) => current + (message.data.delta || ""));
        }
        if (message.event === "done") {
          setState("complete");
          if (message.data.interpretation_source) {
            setEvidence((current) => (
              current ? { ...current, interpretation_source: message.data.interpretation_source } : current
            ));
          }
        }
        if (message.event === "error") throw new Error(message.data.message || "Assistant provider failed");
      }
    } catch (err) {
      if (err.name === "AbortError") {
        setState("cancelled");
      } else {
        setError(err.message);
        setState("error");
      }
    } finally {
      controllerRef.current = null;
    }
  }

  return (
    <>
      <Nav />
      <main id="main-content" className="content">
        <header className="page-header"><div><p className="eyebrow">Assistant</p><h1>Ask Portfolytix</h1><p className="muted">Portfolio answers use your stored transactions and prices. Market research uses retrieved sources first, then organizes them into a short briefing. Source links are listed as titles, not raw addresses.</p></div><StatusBadge value={state} /></header>
        <div className="split-grid">
          <section className="panel">
            <form onSubmit={submit}>
              <label className="field">Answer from<select value={scope} onChange={(event) => setScope(event.target.value)}><option value="market">Cited market research</option><option value="portfolio" disabled={!portfolios.length}>My portfolio</option></select></label>
              {scope === "portfolio" ? <label className="field">Portfolio<select value={portfolioId} onChange={(event) => setPortfolioId(event.target.value)}>{portfolios.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label> : null}
              <label className="field">Question<textarea name="question" rows={4} maxLength={500} required placeholder={scope === "market" ? "What recent developments affect semiconductor companies?" : "What is the overall ROE of my portfolio?"} /></label>
              <div className="row">
                <button className="primary" type="submit" disabled={(scope === "portfolio" && !portfolioId) || ["thinking", "streaming"].includes(state)}>Ask Portfolytix</button>
                {["thinking", "streaming"].includes(state) ? <button type="button" onClick={() => controllerRef.current?.abort()}>Cancel</button> : null}
              </div>
            </form>
            <p className="muted compact-note">{scope === "portfolio" ? "Figures are calculated for this portfolio before any wording is written. A future line is not drawn." : "Public web results are retrieved first. The model may organize only those sources. Numbered chips in the answer open the matching source title."}</p>
            <ErrorState message={error} />
          </section>
          <section className="panel answer-panel" aria-live="polite" aria-busy={["thinking", "streaming"].includes(state)}>
            <div className="panel-header"><h2>Answer</h2>{evidence?.interpretation_source ? <p className="answer-origin">{answerOrigin(evidence.interpretation_source)}</p> : null}</div>
            {state === "thinking" ? <GeneratingStatus phases={ASK_PHASES} /> : null}
            {state === "idle" ? <p className="muted">Ask a question to see a short briefing here.</p> : null}
            {state === "cancelled" && !text ? <p className="muted">Response cancelled. Ask again when you want to continue.</p> : null}
            {text ? <AnswerText text={text} evidence={evidence} question={asked} streaming={state === "streaming"} /> : null}
            {evidence?.disclaimer ? <p className="muted compact-note">{evidence.disclaimer}</p> : null}
          </section>
        </div>
        {evidence?.facts || evidence?.metrics ? (
          <details className="panel evidence-panel">
            <summary>Supporting figures</summary>
            <EvidenceList facts={evidence.facts} metrics={evidence.metrics} />
          </details>
        ) : null}
      </main>
    </>
  );
}
