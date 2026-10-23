import { type FormEvent, useState } from "react";

import { type Me, api } from "../api";
import { Button, Callout, Logo, TextField } from "../ui";

export function LoginPage({ onLogin }: { onLogin: (me: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogin(await api.login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <Logo variant="stacked" height={132} />
        </div>
        <h1 className="text-title auth__title">Entrar</h1>
        <form className="auth__form" onSubmit={submit} noValidate>
          {error && <Callout tone="danger">{error}</Callout>}
          <TextField
            id="login-email"
            label="E-mail"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <TextField
            id="login-password"
            label="Senha"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Button type="submit" disabled={busy || !email || !password}>
            {busy ? "Entrando…" : "Entrar"}
          </Button>
        </form>
        <p className="text-small auth__note">
          Não tem acesso? Peça um convite a quem administra a sua organização.
        </p>
      </div>
    </main>
  );
}
