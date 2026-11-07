"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import LogoMark from "../components/Logo";
import { api, readToken, writeToken } from "../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState("signin");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    if (password.length < 8) {
      setError("Use at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "register") {
        await api("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setMode("signin");
        setShowPassword(false);
        setNotice("Account created. Sign in with the same password.");
        return;
      }
      const body = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      writeToken(body.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (readToken()) router.replace("/dashboard");
  }, [router]);

  const signingIn = mode === "signin";

  return (
    <main className="auth-page">
      <section className="auth-welcome" aria-labelledby="auth-brand">
        <div className="auth-welcome-copy">
          <p className="auth-brand" id="auth-brand">
            <LogoMark size={44} />
            <span>Portfolytix</span>
          </p>
          <h1>Clarity for what you already own.</h1>
          <p className="auth-lead">
            Stored transactions and prices, explained in plain language — not tips, not forecasts.
          </p>
        </div>
      </section>
      <section className="auth-form-wrap">
        <form className="auth-form" onSubmit={submit} aria-busy={busy}>
          <div className="auth-switch" role="group" aria-label="Account action">
            <button type="button" aria-pressed={signingIn} onClick={() => { setMode("signin"); setError(""); }}>Sign in</button>
            <button type="button" aria-pressed={!signingIn} onClick={() => { setMode("register"); setError(""); setNotice(""); }}>Create account</button>
          </div>
          <h2>{signingIn ? "Welcome back" : "Create account"}</h2>
          <p className="muted">{signingIn ? "Sign in to open your workspace." : "Use an email and a password of at least 8 characters."}</p>
          <label className="field" htmlFor="auth-email">Email
            <input id="auth-email" name="email" type="email" required autoComplete="username" inputMode="email" disabled={busy} />
          </label>
          <div className="field">
            <label htmlFor="auth-password">Password</label>
            <span className="auth-password">
              <input
                id="auth-password"
                name="password"
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                autoComplete={signingIn ? "current-password" : "new-password"}
                disabled={busy}
              />
              <button type="button" aria-pressed={showPassword} aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((current) => !current)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </span>
          </div>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? (signingIn ? "Signing in…" : "Creating account…") : (signingIn ? "Sign in" : "Create account")}
          </button>
          {notice ? <p className="auth-notice" role="status">{notice}</p> : null}
          <p className="error" role={error ? "alert" : undefined}>{error}</p>
        </form>
      </section>
    </main>
  );
}
