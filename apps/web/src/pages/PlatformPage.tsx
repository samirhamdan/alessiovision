import { type FormEvent, useState } from "react";

import {
  type Contract,
  type Equipment,
  type EquipmentInput,
  type EquipmentKind,
  type EquipmentStatus,
  type Option,
  type OrganizationOverview,
  type Ownership,
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
} from "../format";
import { Badge, Button, Callout, type Column, DataTable, Panel, SelectField, TextField } from "../ui";
import { useResource } from "../useResource";
import { EquipmentTable, SummaryStrip } from "./equipmentShared";

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
    { key: "comodato", header: "Em comodato", align: "end", render: (o) => o.summary.comodato },
    { key: "fee", header: "Comodato por mês", align: "end", render: (o) => formatMoney(o.summary.comodato_monthly_cents) },
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
  const [number, setNumber] = useState("");
  const [startsOn, setStartsOn] = useState(today());
  const [ending, setEnding] = useState<{ id: string; date: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<Contract[]>) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await action());
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (await run(() => api.platform.addContract(orgId, { number: number.trim(), starts_on: startsOn, ends_on: null, notes: null }))) {
      setNumber("");
    }
  };

  const columns: Column<Contract>[] = [
    { key: "number", header: "Contrato", render: (c) => c.number },
    { key: "period", header: "Vigência", data: true, render: (c) => `${formatDay(c.starts_on)} a ${c.ends_on ? formatDay(c.ends_on) : "—"}` },
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
    { key: "items", header: "Itens", align: "end", render: (c) => c.equipment_count },
    { key: "fee", header: "Por mês", align: "end", render: (c) => formatMoney(c.monthly_fee_cents) },
    {
      key: "actions",
      header: "Ações",
      render: (c) =>
        c.status !== "active" ? null : ending?.id === c.id ? (
          <span className="row-actions">
            <input
              type="date"
              className="av-field__input table-select"
              aria-label={`Data de término do contrato ${c.number}`}
              value={ending.date}
              onChange={(event) => setEnding({ id: c.id, date: event.target.value })}
            />
            <Button
              size="sm"
              variant="danger"
              disabled={busy || !ending.date}
              onClick={async () => {
                if (await run(() => api.platform.endContract(orgId, c.id, ending.date))) setEnding(null);
              }}
            >
              Encerrar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEnding(null)}>
              Cancelar
            </Button>
          </span>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setEnding({ id: c.id, date: today() })}>
            Encerrar contrato
          </Button>
        ),
    },
  ];

  return (
    <Panel title="Contratos de comodato" meta={`${contracts.length}`}>
      <div className="stack">
        {error && <Callout tone="danger">{error}</Callout>}
        <form className="inline-form" onSubmit={create}>
          <TextField id="contract-number" label="Número do contrato" placeholder="Ex.: CT-2026-001" value={number} onChange={(e) => setNumber(e.target.value)} />
          <TextField id="contract-start" label="Início" type="date" value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
          <Button type="submit" disabled={busy || !number.trim() || !startsOn}>
            Novo contrato
          </Button>
        </form>
        <DataTable caption="Contratos de comodato" columns={columns} rows={contracts} rowKey={(c) => c.id} empty="Nenhum contrato. Equipamentos em comodato precisam de um." />
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
  onSaved,
}: {
  orgId: string;
  contracts: Contract[];
  context: { sites: Option[]; cameras: Option[]; agents: Option[] };
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
          <SummaryStrip summary={equipment.data.summary} />
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

function OrganizationDetail({ org, onBack }: { org: OrganizationOverview; onBack: () => void }) {
  const contracts = useResource(() => api.platform.contracts(org.id));
  const context = useResource(() => api.platform.context(org.id));
  const [contractList, setContractList] = useState<Contract[] | null>(null);
  const currentContracts = contractList ?? contracts.data ?? [];

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
        <h1 className="page-title text-display">{org.name}</h1>
      </div>
      {(contracts.error || context.error) && <Callout tone="danger">Falha ao carregar: {contracts.error ?? context.error}</Callout>}
      <ContractsPanel orgId={org.id} contracts={currentContracts} onChange={setContractList} />
      {context.data && (
        <EquipmentPanel
          orgId={org.id}
          contracts={currentContracts}
          context={context.data}
          onSaved={() => api.platform.contracts(org.id).then(setContractList, () => undefined)}
        />
      )}
    </>
  );
}

export function PlatformPage() {
  const [selected, setSelected] = useState<OrganizationOverview | null>(null);
  if (selected) return <OrganizationDetail key={selected.id} org={selected} onBack={() => setSelected(null)} />;
  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Plataforma</h1>
        <p className="text-small secondary">Área da equipe Alessio: contratos de comodato e equipamentos de cada cliente.</p>
      </div>
      <OrganizationList onOpen={setSelected} />
    </>
  );
}
