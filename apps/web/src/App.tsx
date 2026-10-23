import { useEffect, useState } from "react";

import { type Me, SESSION_EXPIRED_EVENT, api } from "./api";
import { ROLE_LABELS } from "./format";
import { AcceptInvitePage } from "./pages/AcceptInvitePage";
import { AgentsPage } from "./pages/AgentsPage";
import { LoginPage } from "./pages/LoginPage";
import { MembersPage } from "./pages/MembersPage";
import { OccurrencesPage } from "./pages/OccurrencesPage";
import { useRoute } from "./router";
import { AppHeader, Button, Callout, type NavItem, NavTabs } from "./ui";

const SECTIONS: Array<NavItem & { permission: string }> = [
  { href: "/", label: "Ocorrências", permission: "occurrences:read" },
  { href: "/agentes", label: "Agentes", permission: "agents:manage" },
  { href: "/membros", label: "Membros", permission: "members:manage" },
];

export function App() {
  const [path, navigate] = useRoute();
  // undefined: verificando a sessão; null: sem sessão.
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [switchError, setSwitchError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setMe, () => setMe(null));
    const expired = () => setMe(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, expired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expired);
  }, []);

  if (path === "/convite") {
    return (
      <AcceptInvitePage
        token={window.location.hash.slice(1)}
        onAccepted={(next) => {
          setMe(next);
          navigate("/");
        }}
      />
    );
  }
  if (me === undefined) {
    return <p className="loading text-small">Carregando…</p>;
  }
  if (me === null) {
    return <LoginPage onLogin={setMe} />;
  }

  const sections = SECTIONS.filter((section) => me.permissions.includes(section.permission));
  const section = SECTIONS.find((s) => s.href === path);
  const allowed = section ? me.permissions.includes(section.permission) : false;
  const organization = me.memberships.find((m) => m.organization_id === me.active_organization_id);

  const logout = async () => {
    await api.logout().catch(() => undefined);
    setMe(null);
    navigate("/");
  };

  const switchOrganization = async (organizationId: string) => {
    setSwitchError(null);
    try {
      setMe(await api.switchOrganization(organizationId));
    } catch (err) {
      setSwitchError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="page">
      <AppHeader
        section={organization?.organization_name}
        nav={sections.length > 1 ? <NavTabs items={sections} current={path} onNavigate={navigate} /> : undefined}
        aside={
          <>
            {me.memberships.length > 1 && (
              <select
                className="av-field__input av-field__select header-select"
                aria-label="Organização"
                value={me.active_organization_id ?? ""}
                onChange={(event) => switchOrganization(event.target.value)}
              >
                {!me.active_organization_id && <option value="">Escolha a organização</option>}
                {me.memberships.map((m) => (
                  <option key={m.organization_id} value={m.organization_id}>
                    {m.organization_name}
                  </option>
                ))}
              </select>
            )}
            <span>
              {me.name}
              {me.role && <span className="secondary"> · {ROLE_LABELS[me.role]}</span>}
            </span>
            <Button size="sm" variant="ghost" onClick={logout}>
              Sair
            </Button>
          </>
        }
      />

      <main className="page-main">
        {switchError && <Callout tone="danger">{switchError}</Callout>}
        {!me.active_organization_id ? (
          <Callout tone="neutral" title="Nenhuma organização ativa">
            {me.memberships.length > 0
              ? "Escolha uma organização no topo da página."
              : "Sua conta não faz parte de nenhuma organização no momento. Peça um convite a quem administra."}
          </Callout>
        ) : !section ? (
          <Callout tone="neutral" title="Página não encontrada">
            <a href="/" onClick={(event) => (event.preventDefault(), navigate("/"))}>
              Voltar para a Central de ocorrências
            </a>
          </Callout>
        ) : !allowed ? (
          <Callout tone="neutral" title="Sem acesso a esta área">
            Seu papel nesta organização não inclui esta área. Peça a um administrador se precisar.
          </Callout>
        ) : section.href === "/agentes" ? (
          <AgentsPage key={me.active_organization_id} />
        ) : section.href === "/membros" ? (
          <MembersPage key={me.active_organization_id} me={me} />
        ) : (
          <OccurrencesPage key={me.active_organization_id} canReview={me.permissions.includes("occurrences:review")} />
        )}
      </main>
    </div>
  );
}
