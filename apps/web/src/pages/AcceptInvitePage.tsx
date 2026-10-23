import { type FormEvent, useState } from "react";

import { type Me, api } from "../api";
import { Button, Callout, Logo, TextField } from "../ui";

const MIN_PASSWORD = 10;

export function AcceptInvitePage({ token, onAccepted }: { token: string; onAccepted: (me: Me) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const passwordError =
    password && password.length < MIN_PASSWORD ? `Use pelo menos ${MIN_PASSWORD} caracteres.` : undefined;
  const confirmError = confirm && confirm !== password ? "As senhas não conferem." : undefined;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api.acceptInvite(token, name, password);
      window.history.replaceState(null, "", "/");
      onAccepted(me);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <main className="auth">
        <div className="auth__card">
          <Callout tone="danger" title="Link de convite incompleto">
            Abra o link exatamente como você o recebeu, ou peça um novo convite.
          </Callout>
        </div>
      </main>
    );
  }

  return (
    <main className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <Logo variant="stacked" height={132} />
        </div>
        <h1 className="text-title auth__title">Ativar sua conta</h1>
        <form className="auth__form" onSubmit={submit} noValidate>
          {error && <Callout tone="danger">{error}</Callout>}
          <TextField
            id="invite-name"
            label="Seu nome"
            autoComplete="name"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <TextField
            id="invite-password"
            label="Crie uma senha"
            type="password"
            autoComplete="new-password"
            hint={`Pelo menos ${MIN_PASSWORD} caracteres. Uma frase longa é mais fácil de lembrar.`}
            error={passwordError}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <TextField
            id="invite-confirm"
            label="Repita a senha"
            type="password"
            autoComplete="new-password"
            error={confirmError}
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
          <Button
            type="submit"
            disabled={busy || !name.trim() || password.length < MIN_PASSWORD || password !== confirm}
          >
            {busy ? "Ativando…" : "Ativar conta"}
          </Button>
        </form>
      </div>
    </main>
  );
}
