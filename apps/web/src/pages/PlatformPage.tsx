import { type FormEvent, useState } from "react";

import {
  type CameraServices,
  type ClientCreated,
  type Contract,
  type Equipment,
  type EquipmentInput,
  type EquipmentKind,
  type EquipmentStatus,
  type Option,
  type OrganizationOverview,
  type Ownership,
  type ServicesOverview,
  type VisionService,
  api,
} from "../api";
import {
  centsToInput,
  EQUIPMENT_STATUS_LABELS,
  formatDay,
  formatMoney,
  KIND_LABELS,
  OWNERSHIP_LABELS,
  parseMoney,
  SERVICE_LABELS,
} from "../format";
import { Badge, Button, Callout, type Column, DataTable, NavTabs, Panel, SelectField, TextField } from "../ui";
import { useResource } from "../useResource";
import { EquipmentTable, ServicesTable, SummaryStrip } from "./equipmentShared";
import { ClientForm, ContractForm, InviteResult, PAYMENT_LABELS, SitesAndCameras } from "./PlatformRegistration";

const today = () => new Date().toISOString().slice(0, 10);

function options(list: Option[], empty: string) {
  return [{ value: "", label: empty }, ...list.map((o) => ({ value: o.id, label: o.name }))];
}

function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

// --- Lista de clientes ----------------------------------------------------------------------

function OrganizationList({ onOpen }: { onOpen: (org: OrganizationOverview) => void }) {
  const organizations = useResource(api.platform.organizations);
  const columns: Column<OrganizationOverview>[] = [
    { key: "name", header: "Cliente", render: (o) => o.name },
    { key: "total", header: "Em operação", align: "end", render: (o) => o.summary.total },
    { key: "vision", header: "Câmeras com Vision", align: "end", render: (o) => o.cameras_with_vision },
    { key: "comodato", header: "Em comodato", align: "end", render: (o) => o.summary.comodato },
    { key: "fee", header: "Mensalidade", align: "end", render: (o) => formatMoney(o.total_monthly_cents) },
    { key: "contracts", header: "Contratos ativos", align: "end", render: (o) => o.active_contracts },
    {
      key: "open",
      header: "Ações",
      render: (o) => (
        <Button size="sm" variant="secondary" onClick={() => onOpen(o)}>
          Abrir
        </Button>
      ),
    },
  ];
  return (
    <>
      {organizations.error && <Callout tone="danger">Falha ao carregar: {organizations.error}</Callout>}
      <Panel title="Clientes" meta={organizations.data ? `${organizations.data.length}` : undefined}>
        <DataTable
          caption="Clientes da plataforma"
          columns={columns}
          rows={organizations.data ?? []}
          rowKey={(o) => o.id}
          empty="Nenhum cliente. Crie com python -m alessio_api.admin create-organization."
        />
      </Panel>
    </>
  );
}

// --- Contratos ------------------------------------------------------------------------------

function ContractsPanel({
  orgId,
  contracts,
  onChange,
}: {
  orgId: string;
  contracts: Contract[];
  onChange: (next: Contract[]) => void;
}) {
  const [editing, setEditing] = useState<Contract | null>(null);
  const [ending, setEnding] = useState<{ id: string; date: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const end = async (contract: Contract, date: string) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await api.platform.endContract(orgId, contract.id, date));
      setEnding(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<Contract>[] = [
    { key: "number", header: "Contrato", render: (c) => c.number },
    { key: "period", header: "Vigência", data: true, render: (c) => `${formatDay(c.starts_on)} a ${c.ends_on ? formatDay(c.ends_on) : "—"}` },
    {
      key: "terms",
      header: "Condições",
      render: (c) => (
        <span className="text-small">
          {[
            c.term_months ? `${c.term_months} meses${c.auto_renew ? ", renova" : ""}` : null,
            c.billing_day ? `vence dia ${c.billing_day}` : null,
            c.payment_method ? PAYMENT_LABELS[c.payment_method] : null,
          ]
            .filter(Boolean)
            .join(" · ") || "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Situação",
      render: (c) =>
        c.status === "active" ? (
          <Badge tone="ok">Ativo</Badge>
        ) : c.pending_return > 0 ? (
          <Badge tone="warn">{`Encerrado · ${c.pending_return} a devolver`}</Badge>
        ) : (
          <Badge tone="neutral">Encerrado</Badge>
        ),
    },
    {
      key: "items",
      header: "Itens",
      render: (c) => `${c.service_count} serviço${c.service_count === 1 ? "" : "s"} · ${c.equipment_count} equip.`,
    },
    { key: "fee", header: "Por mês", align: "end", render: (c) => formatMoney(c.monthly_fee_cents) },
    {
      key: "actions",
      header: "Ações",
      render: (c) =>
        ending?.id === c.id ? (
          <span className="row-actions">
            <input
              type="date"
              className="av-field__input table-select"
              aria-label={`Data de término do contrato ${c.number}`}
              value={ending.date}
              onChange={(event) => setEnding({ id: c.id, date: event.target.value })}
            />
            <Button size="sm" variant="danger" disabled={busy || !ending.date} onClick={() => end(c, ending.date)}>
              Encerrar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEnding(null)}>
              Cancelar
            </Button>
          </span>
        ) : (
          <span className="row-actions">
            <Button size="sm" variant="secondary" onClick={() => setEditing(c)}>
              Editar
            </Button>
            {c.status === "active" && (
              <Button size="sm" variant="ghost" onClick={() => setEnding({ id: c.id, date: today() })}>
                Encerrar contrato
              </Button>
            )}
          </span>
        ),
    },
  ];

  return (
    <>
      {error && <Callout tone="danger">{error}</Callout>}
      <Panel title="Contratos" meta={`${contracts.length}`}>
        <DataTable
          caption="Contratos"
          columns={columns}
          rows={contracts}
          rowKey={(c) => c.id}
          empty="Nenhum contrato. Serviços Vision e equipamentos em comodato precisam de um."
        />
      </Panel>
      <Panel title={editing ? `Editar contrato ${editing.number}` : "Novo contrato"}>
        <ContractForm
          key={editing?.id ?? "new"}
          orgId={orgId}
          contract={editing ?? undefined}
          onCancel={editing ? () => setEditing(null) : undefined}
          onSaved={(next) => {
            onChange(next);
            setEditing(null);
          }}
        />
      </Panel>
    </>
  );
}

// --- Serviços Vision por câmera --------------------------------------------------------------

function ServicesPanel({
  orgId,
  overview,
  contracts,
  onChange,
}: {
  orgId: string;
  overview: ServicesOverview;
  contracts: Contract[];
  onChange: (next: ServicesOverview) => void;
}) {
  const active = contracts.filter((c) => c.status === "active");
  const [cameraId, setCameraId] = useState("");
  const [service, setService] = useState<VisionService>("security");
  const [contractId, setContractId] = useState("");
  const [fee, setFee] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [ending, setEnding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const feeValue = parseMoney(fee);

  const run = async (action: () => Promise<ServicesOverview>, done?: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      onChange(await action());
      if (done) setNotice(done);
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const contract = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(
      () =>
        api.platform.contractService(orgId, {
          camera_id: cameraId,
          service,
          contract_id: contractId,
          monthly_fee_cents: feeValue,
          starts_on: startsOn || null,
        }),
      "Serviço contratado. O agente passa a analisar a câmera na próxima vez que carregar a configuração.",
    );
    if (ok) setFee("");
  };

  const actions = (camera: CameraServices, which: VisionService) => {
    const line = camera[which];
    if (line) {
      return ending === line.id ? (
        <span className="row-actions">
          <Button size="sm" variant="danger" disabled={busy} onClick={() => run(() => api.platform.endService(orgId, line.id, null)).then(() => setEnding(null))}>
            Encerrar agora
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEnding(null)}>
            Cancelar
          </Button>
        </span>
      ) : (
        <Button size="sm" variant="ghost" onClick={() => setEnding(line.id)}>
          Encerrar
        </Button>
      );
    }
    return (
      <span className="row-actions">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setCameraId(camera.camera_id);
            setService(which);
          }}
        >
          Contratar
        </Button>
        {!camera.trials_used.includes(which) && (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => run(() => api.platform.startTrial(orgId, camera.camera_id, which), `Teste de ${SERVICE_LABELS[which]} liberado por 3 dias.`)}
          >
            Teste 3 dias
          </Button>
        )}
      </span>
    );
  };

  const cameraOptions = [{ value: "", label: "Escolha a câmera" }, ...overview.cameras.map((c) => ({ value: c.camera_id, label: c.camera_name }))];
  const serviceOptions = (Object.keys(SERVICE_LABELS) as VisionService[]).map((k) => ({ value: k, label: SERVICE_LABELS[k] }));
  const contractOptions = [
    { value: "", label: active.length ? "Escolha o contrato" : "Crie um contrato acima" },
    ...active.map((c) => ({ value: c.id, label: c.number })),
  ];

  return (
    <Panel title="Serviços Vision por câmera" meta={`${formatMoney(overview.services_monthly_cents)}/mês`}>
      <div className="stack">
        {error && <Callout tone="danger">{error}</Callout>}
        {notice && <Callout tone="ok">{notice}</Callout>}
        <form className="form-grid" onSubmit={contract}>
          <SelectField id="svc-camera" label="Câmera" options={cameraOptions} value={cameraId} onChange={(e) => setCameraId(e.target.value)} />
          <SelectField id="svc-service" label="Serviço" options={serviceOptions} value={service} onChange={(e) => setService(e.target.value as VisionService)} />
          <SelectField id="svc-contract" label="Contrato" options={contractOptions} value={contractId} onChange={(e) => setContractId(e.target.value)} />
          <TextField
            id="svc-fee"
            label="Valor mensal negociado (R$)"
            inputMode="decimal"
            placeholder="120,00"
            error={Number.isNaN(feeValue) ? "Use um valor como 120,00." : undefined}
            value={fee}
            onChange={(e) => setFee(e.target.value)}
          />
          <TextField id="svc-start" label="Início (vazio = agora)" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
          <div className="form-grid__action">
            <Button type="submit" disabled={busy || !cameraId || !contractId || Number.isNaN(feeValue)}>
              Contratar serviço
            </Button>
          </div>
        </form>
        <ServicesTable overview={overview} actions={actions} />
      </div>
    </Panel>
  );
}

// --- Equipamentos ---------------------------------------------------------------------------

type Draft = {
  kind: EquipmentKind;
  ownership: Ownership;
  brand: string;
  model: string;
  serial_number: string;
  asset_tag: string;
  site_id: string;
  camera_id: string;
  agent_id: string;
  contract_id: string;
  status: EquipmentStatus;
  reference_value: string;
  monthly_fee: string;
  delivered_on: string;
  notes: string;
};

const EMPTY: Draft = {
  kind: "camera",
  ownership: "client",
  brand: "",
  model: "",
  serial_number: "",
  asset_tag: "",
  site_id: "",
  camera_id: "",
  agent_id: "",
  contract_id: "",
  status: "in_use",
  reference_value: "",
  monthly_fee: "",
  delivered_on: "",
  notes: "",
};

function toDraft(e: Equipment): Draft {
  return {
    kind: e.kind,
    ownership: e.ownership,
    brand: e.brand ?? "",
    model: e.model ?? "",
    serial_number: e.serial_number ?? "",
    asset_tag: e.asset_tag ?? "",
    site_id: e.site_id ?? "",
    camera_id: e.camera_id ?? "",
    agent_id: e.agent_id ?? "",
    contract_id: e.contract_id ?? "",
    status: e.status,
    reference_value: centsToInput(e.reference_value_cents),
    monthly_fee: centsToInput(e.monthly_fee_cents),
    delivered_on: e.delivered_on ?? "",
    notes: e.notes ?? "",
  };
}

function toInput(d: Draft, returnedOn: string | null): EquipmentInput {
  const comodato = d.ownership === "comodato";
  const text = (v: string) => v.trim() || null;
  return {
    kind: d.kind,
    ownership: d.ownership,
    brand: text(d.brand),
    model: text(d.model),
    serial_number: text(d.serial_number),
    asset_tag: text(d.asset_tag),
    site_id: d.site_id || null,
    camera_id: d.camera_id || null,
    agent_id: d.agent_id || null,
    contract_id: comodato ? d.contract_id || null : null,
    status: d.status,
    reference_value_cents: parseMoney(d.reference_value),
    monthly_fee_cents: comodato ? parseMoney(d.monthly_fee) : null,
    delivered_on: d.delivered_on || null,
    returned_on: returnedOn,
    notes: text(d.notes),
  };
}

function EquipmentPanel({
  orgId,
  contracts,
  context,
  servicesMonthly,
  onSaved,
}: {
  orgId: string;
  contracts: Contract[];
  context: { sites: Option[]; cameras: Option[]; agents: Option[] };
  servicesMonthly: number | undefined;
  /** Itens e valores dos contratos mudam junto com os equipamentos. */
  onSaved: () => void;
}) {
  const equipment = useResource(() => api.platform.equipment(orgId));
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<Equipment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const activeContracts = contracts.filter((c) => c.status === "active" || c.id === editing?.contract_id);
  const feeError = Number.isNaN(parseMoney(draft.monthly_fee)) ? "Use um valor como 150,00." : undefined;
  const refError = Number.isNaN(parseMoney(draft.reference_value)) ? "Use um valor como 2.500,00." : undefined;
  const missingContract = draft.ownership === "comodato" && !draft.contract_id;

  const save = async (body: EquipmentInput, id?: string) => {
    setBusy(true);
    setError(null);
    try {
      await (id ? api.platform.updateEquipment(orgId, id, body) : api.platform.addEquipment(orgId, body));
      await equipment.reload();
      onSaved();
      setDraft(EMPTY);
      setEditing(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void save(toInput(draft, editing?.returned_on ?? null), editing?.id);
  };

  const markReturned = (item: Equipment) =>
    save({ ...toInput(toDraft(item), today()), status: "returned" }, item.id);

  const actions = (item: Equipment) => (
    <span className="row-actions">
      <Button
        size="sm"
        variant="secondary"
        onClick={() => {
          setEditing(item);
          setDraft(toDraft(item));
          setError(null);
        }}
      >
        Editar
      </Button>
      {item.ownership === "comodato" && (item.status === "in_use" || item.status === "maintenance") && (
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => markReturned(item)}>
          Registrar devolução
        </Button>
      )}
    </span>
  );

  const kindOptions = (Object.keys(KIND_LABELS) as EquipmentKind[]).map((k) => ({ value: k, label: KIND_LABELS[k] }));
  const ownershipOptions = (Object.keys(OWNERSHIP_LABELS) as Ownership[]).map((k) => ({ value: k, label: OWNERSHIP_LABELS[k] }));
  const statusOptions = (Object.keys(EQUIPMENT_STATUS_LABELS) as EquipmentStatus[]).map((k) => ({
    value: k,
    label: EQUIPMENT_STATUS_LABELS[k],
  }));

  return (
    <>
      {equipment.data && (
        <Panel title="Resumo do cliente">
          <SummaryStrip summary={equipment.data.summary} servicesMonthly={servicesMonthly} />
        </Panel>
      )}
      <Panel
        title={editing ? "Editar equipamento" : "Novo equipamento"}
        actions={
          editing ? (
            <Button size="sm" variant="ghost" onClick={() => (setEditing(null), setDraft(EMPTY))}>
              Cancelar edição
            </Button>
          ) : undefined
        }
      >
        <form className="stack" onSubmit={submit}>
          {error && <Callout tone="danger">{error}</Callout>}
          <div className="form-grid">
            <SelectField id="eq-kind" label="Tipo" options={kindOptions} value={draft.kind} onChange={(e) => set("kind", e.target.value as EquipmentKind)} />
            <SelectField
              id="eq-ownership"
              label="Propriedade"
              options={ownershipOptions}
              value={draft.ownership}
              onChange={(e) => set("ownership", e.target.value as Ownership)}
            />
            {draft.ownership === "comodato" && (
              <SelectField
                id="eq-contract"
                label="Contrato"
                options={[{ value: "", label: activeContracts.length ? "Escolha o contrato" : "Crie um contrato acima" }, ...activeContracts.map((c) => ({ value: c.id, label: c.number }))]}
                value={draft.contract_id}
                error={missingContract ? "Comodato precisa de contrato." : undefined}
                onChange={(e) => set("contract_id", e.target.value)}
              />
            )}
            <TextField id="eq-brand" label="Marca" value={draft.brand} onChange={(e) => set("brand", e.target.value)} />
            <TextField id="eq-model" label="Modelo" value={draft.model} onChange={(e) => set("model", e.target.value)} />
            <TextField id="eq-serial" label="Número de série" value={draft.serial_number} onChange={(e) => set("serial_number", e.target.value)} />
            {draft.ownership === "comodato" && (
              <TextField id="eq-asset" label="Patrimônio Alessio" value={draft.asset_tag} onChange={(e) => set("asset_tag", e.target.value)} />
            )}
            <SelectField id="eq-site" label="Local" options={options(context.sites, "Sem local")} value={draft.site_id} onChange={(e) => set("site_id", e.target.value)} />
            <SelectField id="eq-camera" label="Câmera no sistema" options={options(context.cameras, "Nenhuma")} value={draft.camera_id} onChange={(e) => set("camera_id", e.target.value)} />
            <SelectField id="eq-agent" label="Agente no sistema" options={options(context.agents, "Nenhum")} value={draft.agent_id} onChange={(e) => set("agent_id", e.target.value)} />
            {draft.ownership === "comodato" && (
              <TextField
                id="eq-fee"
                label="Valor mensal (R$)"
                inputMode="decimal"
                placeholder="150,00"
                hint="Soma na mensalidade do cliente."
                error={feeError}
                value={draft.monthly_fee}
                onChange={(e) => set("monthly_fee", e.target.value)}
              />
            )}
            <TextField
              id="eq-reference"
              label="Valor de reposição (R$)"
              inputMode="decimal"
              placeholder="2.500,00"
              error={refError}
              value={draft.reference_value}
              onChange={(e) => set("reference_value", e.target.value)}
            />
            <TextField id="eq-delivered" label="Entregue em" type="date" value={draft.delivered_on} onChange={(e) => set("delivered_on", e.target.value)} />
            {editing && (
              <SelectField id="eq-status" label="Situação" options={statusOptions} value={draft.status} onChange={(e) => set("status", e.target.value as EquipmentStatus)} />
            )}
          </div>
          <div>
            <Button type="submit" disabled={busy || missingContract || Boolean(feeError || refError)}>
              {busy ? "Salvando…" : editing ? "Salvar alterações" : "Cadastrar equipamento"}
            </Button>
          </div>
        </form>
      </Panel>
      <Panel title="Equipamentos" meta={equipment.data ? `${equipment.data.items.length}` : undefined}>
        {equipment.error && <Callout tone="danger">Falha ao carregar: {equipment.error}</Callout>}
        <EquipmentTable items={equipment.data?.items ?? []} actions={actions} />
      </Panel>
    </>
  );
}

// --- Página ---------------------------------------------------------------------------------

const TABS = [
  { href: "cadastro", label: "Cadastro" },
  { href: "contratos", label: "Contratos" },
  { href: "locais", label: "Locais e câmeras" },
  { href: "servicos", label: "Serviços" },
  { href: "equipamentos", label: "Equipamentos" },
];

function OrganizationDetail({
  orgId,
  invite,
  onBack,
}: {
  orgId: string;
  invite: ClientCreated | null;
  onBack: () => void;
}) {
  const [tab, setTab] = useState(invite ? "contratos" : "cadastro");
  const client = useResource(() => api.platform.client(orgId));
  const contracts = useResource(() => api.platform.contracts(orgId));
  const context = useResource(() => api.platform.context(orgId));
  const services = useResource(() => api.platform.services(orgId));
  const [contractList, setContractList] = useState<Contract[] | null>(null);
  const [servicesOverview, setServicesOverview] = useState<ServicesOverview | null>(null);
  const currentContracts = contractList ?? contracts.data ?? [];
  const currentServices = servicesOverview ?? services.data;
  const refreshContracts = () => api.platform.contracts(orgId).then(setContractList, () => undefined);
  const refreshServices = () => api.platform.services(orgId).then(setServicesOverview, () => undefined);
  const loadError = client.error ?? contracts.error ?? context.error ?? services.error;

  return (
    <>
      <div className="page-heading">
        <p className="text-small">
          <a
            href="/plataforma"
            onClick={(event) => {
              event.preventDefault();
              onBack();
            }}
          >
            ← Todos os clientes
          </a>
        </p>
        <h1 className="page-title text-display">{client.data?.name ?? "Cliente"}</h1>
        {client.data && (
          <p className="text-small secondary">
            {client.data.legal_name} · {client.data.document_formatted ?? "sem documento"}
          </p>
        )}
      </div>
      {loadError && <Callout tone="danger">Falha ao carregar: {loadError}</Callout>}
      {invite && <InviteResult result={invite} />}
      <div className="tabs">
        <NavTabs items={TABS} current={tab} onNavigate={setTab} />
      </div>

      {tab === "cadastro" && client.data && (
        <ClientForm key={client.data.id} client={client.data} onSaved={() => void client.reload()} />
      )}
      {tab === "contratos" && (
        <ContractsPanel
          orgId={orgId}
          contracts={currentContracts}
          onChange={(next) => {
            setContractList(next);
            void refreshServices();
          }}
        />
      )}
      {tab === "locais" && (
        <SitesAndCameras
          orgId={orgId}
          contracts={currentContracts}
          onChanged={() => {
            void refreshServices();
            void refreshContracts();
            void context.reload();
          }}
        />
      )}
      {tab === "servicos" && currentServices && (
        <ServicesPanel
          orgId={orgId}
          overview={currentServices}
          contracts={currentContracts}
          onChange={(next) => {
            setServicesOverview(next);
            void refreshContracts();
          }}
        />
      )}
      {tab === "equipamentos" && context.data && (
        <EquipmentPanel
          orgId={orgId}
          contracts={currentContracts}
          context={context.data}
          servicesMonthly={currentServices?.services_monthly_cents}
          onSaved={() => void refreshContracts()}
        />
      )}
    </>
  );
}

export function PlatformPage() {
  const [view, setView] = useState<{ kind: "list" } | { kind: "new" } | { kind: "client"; id: string; invite: ClientCreated | null }>({
    kind: "list",
  });
  if (view.kind === "client") {
    return <OrganizationDetail key={view.id} orgId={view.id} invite={view.invite} onBack={() => setView({ kind: "list" })} />;
  }
  if (view.kind === "new") {
    return (
      <>
        <div className="page-heading">
          <p className="text-small">
            <a
              href="/plataforma"
              onClick={(event) => {
                event.preventDefault();
                setView({ kind: "list" });
              }}
            >
              ← Todos os clientes
            </a>
          </p>
          <h1 className="page-title text-display">Novo cliente</h1>
          <p className="text-small secondary">
            Depois do cadastro: contrato, locais e câmeras (com a pergunta sobre o serviço Vision em cada uma).
          </p>
        </div>
        <ClientForm onCreated={(created) => setView({ kind: "client", id: created.client.id, invite: created })} />
      </>
    );
  }
  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Plataforma</h1>
        <p className="text-small secondary">Área da equipe Alessio: cadastro de clientes, contratos, câmeras, serviços e equipamentos.</p>
      </div>
      <div>
        <Button onClick={() => setView({ kind: "new" })}>Novo cliente</Button>
      </div>
      <OrganizationList onOpen={(org) => setView({ kind: "client", id: org.id, invite: null })} />
    </>
  );
}
