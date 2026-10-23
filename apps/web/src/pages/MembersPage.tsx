import { type FormEvent, useState } from "react";

import { type Me, type Member, type MemberCreated, type Role, api } from "../api";
import { formatDate, ROLE_HINTS, ROLE_LABELS } from "../format";
import { Badge, Button, Callout, type Column, DataTable, Panel, SecretField, SelectField, TextField } from "../ui";
import { useResource } from "../useResource";

const ALL_ROLES: Role[] = ["viewer", "operator", "admin", "owner"];

function InviteLink({ result, onClose }: { result: MemberCreated; onClose: () => void }) {
  const link = `${window.location.origin}/convite#${result.invite_token}`;
  return (
    <Panel
      title={`Convite para ${result.member.name}`}
      actions={
        <Button size="sm" variant="ghost" onClick={onClose}>
          Concluído
        </Button>
      }
    >
      <div className="stack">
        <Callout tone="neutral" title="Envie este link para a pessoa">
          Ele aparece só agora, vale uma única vez e expira em{" "}
          {result.invite_expires_at ? formatDate(result.invite_expires_at) : "alguns dias"}. Com ele, a pessoa cria a
          própria senha.
        </Callout>
        <SecretField label="Link de convite" value={link} hint={`Enviar para ${result.member.email}`} />
      </div>
    </Panel>
  );
}

export function MembersPage({ me }: { me: Me }) {
  const members = useResource(api.members);
  const canManageOwners = me.permissions.includes("owners:manage");
  const assignable = ALL_ROLES.filter((role) => role !== "owner" || canManageOwners);
  const roleOptions = assignable.map((role) => ({ value: role, label: ROLE_LABELS[role] }));

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("operator");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [invite, setInvite] = useState<MemberCreated | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await action();
      await members.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const add = (event: FormEvent) => {
    event.preventDefault();
    void run("add", async () => {
      const result = await api.addMember(email.trim(), name.trim(), role);
      if (result.invite_token) setInvite(result);
      else setNotice(`${result.member.name} já tinha conta e agora faz parte da organização.`);
      setEmail("");
      setName("");
    });
  };

  const editable = (m: Member) => m.role !== "owner" || canManageOwners;

  const columns: Column<Member>[] = [
    {
      key: "name",
      header: "Pessoa",
      render: (m) => (
        <>
          {m.name}
          {m.user_id === me.id && <span className="secondary"> (você)</span>}
          <div className="secondary text-small">{m.email}</div>
        </>
      ),
    },
    {
      key: "role",
      header: "Papel",
      render: (m) =>
        editable(m) ? (
          <select
            className="av-field__input av-field__select table-select"
            aria-label={`Papel de ${m.name}`}
            value={m.role}
            disabled={busy !== null}
            onChange={(event) => run(m.user_id, () => api.changeRole(m.user_id, event.target.value as Role).then(() => {}))}
          >
            {(m.role === "owner" ? ALL_ROLES : assignable).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        ) : (
          ROLE_LABELS[m.role]
        ),
    },
    {
      key: "status",
      header: "Conta",
      render: (m) =>
        m.status === "invited" ? <Badge tone="warn">Convite pendente</Badge> : <Badge tone="ok">Ativa</Badge>,
    },
    { key: "joined", header: "Desde", data: true, render: (m) => formatDate(m.joined_at) },
    {
      key: "actions",
      header: "Ações",
      render: (m) => {
        if (!editable(m)) return null;
        if (confirmRemove === m.user_id) {
          return (
            <span className="row-actions">
              <Button
                size="sm"
                variant="danger"
                disabled={busy !== null}
                onClick={() =>
                  run(m.user_id, async () => {
                    await api.removeMember(m.user_id);
                    setConfirmRemove(null);
                  })
                }
              >
                Confirmar remoção
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(null)}>
                Cancelar
              </Button>
            </span>
          );
        }
        return (
          <span className="row-actions">
            {m.status === "invited" && (
              <Button
                size="sm"
                variant="secondary"
                disabled={busy !== null}
                onClick={() => run(m.user_id, async () => setInvite(await api.reissueInvite(m.user_id)))}
              >
                Novo link
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => setConfirmRemove(m.user_id)}>
              Remover
            </Button>
          </span>
        );
      },
    },
  ];

  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Membros</h1>
        <p className="text-small secondary">Quem acessa esta organização e o que cada pessoa pode fazer.</p>
      </div>
      {error && <Callout tone="danger">{error}</Callout>}
      {notice && <Callout tone="ok">{notice}</Callout>}
      {members.error && <Callout tone="danger">Falha ao carregar: {members.error}</Callout>}
      {invite && <InviteLink result={invite} onClose={() => setInvite(null)} />}

      <Panel title="Adicionar pessoa">
        <form className="inline-form" onSubmit={add}>
          <TextField
            id="member-email"
            label="E-mail"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <TextField id="member-name" label="Nome" value={name} onChange={(event) => setName(event.target.value)} />
          <SelectField
            id="member-role"
            label="Papel"
            options={roleOptions}
            hint={ROLE_HINTS[role]}
            value={role}
            onChange={(event) => setRole(event.target.value as Role)}
          />
          <Button type="submit" disabled={busy !== null || !email.trim() || !name.trim()}>
            {busy === "add" ? "Adicionando…" : "Adicionar"}
          </Button>
        </form>
      </Panel>

      <Panel title="Membros" meta={members.data ? `${members.data.length}` : undefined}>
        <DataTable
          caption="Membros da organização"
          columns={columns}
          rows={members.data ?? []}
          rowKey={(m) => m.user_id}
          empty="Ninguém por aqui ainda."
        />
      </Panel>
    </>
  );
}
