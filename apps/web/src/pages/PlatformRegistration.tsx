import { type FormEvent, useState } from "react";

import {
  type Address,
  type Client,
  type ClientCreated,
  type ClientInput,
  type Contract,
  type ContractInput,
  type EnrollmentCode,
  type Ownership,
  type PlatformSite,
  type ServiceChoice,
  type VisionService,
  api,
} from "../api";
import { formatDate, OWNERSHIP_LABELS, parseMoney, SERVICE_LABELS } from "../format";
import { Badge, Button, Callout, type Column, DataTable, Panel, SecretField, SelectField, TextField } from "../ui";
import { useResource } from "../useResource";

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
const today = () => new Date().toISOString().slice(0, 10);
const text = (v: string) => v.trim() || null;
const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));
const YES_NO = [
  { value: "yes", label: "Sim" },
  { value: "no", label: "Não" },
];

// --- Endereço -------------------------------------------------------------------------------

const EMPTY_ADDRESS: Address = {
  postal_code: null,
  street: null,
  street_number: null,
  complement: null,
  district: null,
  city: null,
  state: null,
};

function AddressFields({ prefix, value, onChange }: { prefix: string; value: Address; onChange: (a: Address) => void }) {
  const set = (key: keyof Address, v: string) => onChange({ ...value, [key]: text(v) });
  return (
    <>
      <TextField id={`${prefix}-cep`} label="CEP" inputMode="numeric" placeholder="00000-000" value={value.postal_code ?? ""} onChange={(e) => set("postal_code", e.target.value)} />
      <TextField id={`${prefix}-street`} label="Logradouro" value={value.street ?? ""} onChange={(e) => set("street", e.target.value)} />
      <TextField id={`${prefix}-number`} label="Número" value={value.street_number ?? ""} onChange={(e) => set("street_number", e.target.value)} />
      <TextField id={`${prefix}-complement`} label="Complemento" value={value.complement ?? ""} onChange={(e) => set("complement", e.target.value)} />
      <TextField id={`${prefix}-district`} label="Bairro" value={value.district ?? ""} onChange={(e) => set("district", e.target.value)} />
      <TextField id={`${prefix}-city`} label="Cidade" value={value.city ?? ""} onChange={(e) => set("city", e.target.value)} />
      <SelectField
        id={`${prefix}-state`}
        label="UF"
        options={[{ value: "", label: "—" }, ...UFS.map((uf) => ({ value: uf, label: uf }))]}
        value={value.state ?? ""}
        onChange={(e) => set("state", e.target.value)}
      />
    </>
  );
}

// --- Cliente --------------------------------------------------------------------------------

const EMPTY_CLIENT: ClientInput = {
  name: "",
  person_type: "pj",
  document: "",
  legal_name: "",
  state_registration: null,
  email: null,
  phone: null,
  contact_name: null,
  contact_email: null,
  contact_phone: null,
  address: EMPTY_ADDRESS,
  notes: null,
  status: "active",
};

function toClientInput(c: Client): ClientInput {
  const { id: _id, document_formatted, created_at: _created, ...rest } = c;
  return { ...rest, document: document_formatted ?? rest.document ?? "" };
}

/** Formulário do cadastro do cliente. Sem ``client``, cria; com ``client``, edita. */
export function ClientForm({
  client,
  onCreated,
  onSaved,
}: {
  client?: Client;
  onCreated?: (created: ClientCreated) => void;
  onSaved?: (client: Client) => void;
}) {
  const [data, setData] = useState<ClientInput>(client ? toClientInput(client) : EMPTY_CLIENT);
  const [siteName, setSiteName] = useState("Matriz");
  const [siteVision, setSiteVision] = useState("yes");
  const [invite, setInvite] = useState("yes");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof ClientInput>(key: K, value: ClientInput[K]) => setData((d) => ({ ...d, [key]: value }));
  const opt = (key: keyof ClientInput) => (e: { target: { value: string } }) => set(key, text(e.target.value) as never);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (client) {
        onSaved?.(await api.platform.updateClient(client.id, data));
        setNotice("Cadastro salvo.");
      } else {
        onCreated?.(
          await api.platform.createClient({
            ...data,
            site_name: siteName,
            site_vision_planned: siteVision === "yes",
            invite_contact: invite === "yes",
          }),
        );
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const pj = data.person_type === "pj";
  return (
    <form className="stack" onSubmit={submit}>
      {error && <Callout tone="danger">{error}</Callout>}
      {notice && <Callout tone="ok">{notice}</Callout>}
      <Panel title="Dados do cliente">
        <div className="form-grid">
          <SelectField
            id="cl-type"
            label="Tipo"
            options={[
              { value: "pj", label: "Pessoa jurídica (CNPJ)" },
              { value: "pf", label: "Pessoa física (CPF)" },
            ]}
            value={data.person_type}
            onChange={(e) => set("person_type", e.target.value as "pj" | "pf")}
          />
          <TextField
            id="cl-document"
            label={pj ? "CNPJ" : "CPF"}
            hint={pj ? "Aceita o CNPJ alfanumérico." : undefined}
            value={data.document}
            onChange={(e) => set("document", e.target.value)}
          />
          <TextField id="cl-legal" label={pj ? "Razão social" : "Nome completo"} value={data.legal_name} onChange={(e) => set("legal_name", e.target.value)} />
          <TextField id="cl-name" label={pj ? "Nome fantasia" : "Nome de exibição"} hint="Como o cliente aparece no painel." value={data.name} onChange={(e) => set("name", e.target.value)} />
          {pj && <TextField id="cl-ie" label="Inscrição estadual" value={data.state_registration ?? ""} onChange={opt("state_registration")} />}
          <TextField id="cl-email" label="E-mail (financeiro)" type="email" value={data.email ?? ""} onChange={opt("email")} />
          <TextField id="cl-phone" label="Telefone" inputMode="tel" placeholder="(11) 3333-4444" value={data.phone ?? ""} onChange={opt("phone")} />
          {client && (
            <SelectField
              id="cl-status"
              label="Situação"
              options={[
                { value: "active", label: "Ativo" },
                { value: "inactive", label: "Inativo" },
              ]}
              value={data.status}
              onChange={(e) => set("status", e.target.value as "active" | "inactive")}
            />
          )}
        </div>
      </Panel>
      <Panel title="Responsável">
        <div className="form-grid">
          <TextField id="cl-contact" label="Nome" value={data.contact_name ?? ""} onChange={opt("contact_name")} />
          <TextField id="cl-contact-email" label="E-mail" type="email" value={data.contact_email ?? ""} onChange={opt("contact_email")} />
          <TextField id="cl-contact-phone" label="Celular" inputMode="tel" placeholder="(11) 98888-7777" value={data.contact_phone ?? ""} onChange={opt("contact_phone")} />
          {!client && (
            <SelectField
              id="cl-invite"
              label="Convidar como proprietário do painel?"
              options={YES_NO}
              hint="Gera um link de convite para o e-mail do responsável."
              value={invite}
              onChange={(e) => setInvite(e.target.value)}
            />
          )}
        </div>
      </Panel>
      <Panel title="Endereço">
        <div className="form-grid">
          <AddressFields prefix="cl" value={data.address} onChange={(address) => set("address", address)} />
        </div>
      </Panel>
      {!client && (
        <Panel title="Local principal">
          <div className="form-grid">
            <TextField id="cl-site" label="Nome do local" hint="Criado com o endereço acima." value={siteName} onChange={(e) => setSiteName(e.target.value)} />
            <SelectField id="cl-site-vision" label="Haverá serviço Vision neste local?" options={YES_NO} value={siteVision} onChange={(e) => setSiteVision(e.target.value)} />
          </div>
        </Panel>
      )}
      <Panel title="Observações">
        <TextField id="cl-notes" label="Observações internas" value={data.notes ?? ""} onChange={opt("notes")} />
      </Panel>
      <div>
        <Button type="submit" disabled={busy || !data.name.trim() || !data.document.trim() || !data.legal_name.trim()}>
          {busy ? "Salvando…" : client ? "Salvar cadastro" : "Cadastrar cliente"}
        </Button>
      </div>
    </form>
  );
}

export function InviteResult({ result }: { result: ClientCreated }) {
  if (!result.invite_token) {
    return result.owner_email ? (
      <Callout tone="ok">{result.owner_email} já tinha conta e agora é proprietário deste cliente.</Callout>
    ) : null;
  }
  return (
    <Panel title="Convite do responsável">
      <div className="stack">
        <Callout tone="neutral" title="Envie este link para o responsável">
          Ele aparece só agora, vale uma vez e expira em 72 horas.
        </Callout>
        <SecretField label="Link de convite" value={`${window.location.origin}/convite#${result.invite_token}`} hint={`Para ${result.owner_email}`} />
      </div>
    </Panel>
  );
}

// --- Contratos ------------------------------------------------------------------------------

const PAYMENT = [
  { value: "", label: "—" },
  { value: "boleto", label: "Boleto" },
  { value: "pix", label: "Pix" },
  { value: "cartao", label: "Cartão" },
  { value: "transferencia", label: "Transferência" },
];
const ADJUSTMENT = [
  { value: "", label: "—" },
  { value: "ipca", label: "IPCA" },
  { value: "igpm", label: "IGP-M" },
  { value: "none", label: "Sem reajuste" },
];
export const PAYMENT_LABELS: Record<string, string> = Object.fromEntries(PAYMENT.map((p) => [p.value, p.label]));

const EMPTY_CONTRACT: ContractInput = {
  number: "",
  starts_on: today(),
  ends_on: null,
  signed_on: null,
  term_months: 12,
  auto_renew: true,
  billing_day: 10,
  payment_method: "boleto",
  adjustment_index: "ipca",
  notes: null,
};

export function ContractForm({
  orgId,
  contract,
  onSaved,
  onCancel,
}: {
  orgId: string;
  contract?: Contract;
  onSaved: (contracts: Contract[]) => void;
  onCancel?: () => void;
}) {
  const [data, setData] = useState<ContractInput>(contract ? { ...contract } : EMPTY_CONTRACT);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof ContractInput>(key: K, value: ContractInput[K]) => setData((d) => ({ ...d, [key]: value }));
  const int = (v: string) => (v.trim() ? Number(v) : null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSaved(await (contract ? api.platform.updateContract(orgId, contract.id, data) : api.platform.addContract(orgId, data)));
      if (!contract) setData(EMPTY_CONTRACT);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="stack" onSubmit={submit}>
      {error && <Callout tone="danger">{error}</Callout>}
      <div className="form-grid">
        <TextField id="ct-number" label="Número do contrato" placeholder="Ex.: CT-2026-001" value={data.number} onChange={(e) => set("number", e.target.value)} />
        <TextField id="ct-signed" label="Assinado em" type="date" value={data.signed_on ?? ""} onChange={(e) => set("signed_on", e.target.value || null)} />
        <TextField id="ct-start" label="Início da vigência" type="date" value={data.starts_on} onChange={(e) => set("starts_on", e.target.value)} />
        <TextField id="ct-term" label="Prazo (meses)" inputMode="numeric" value={data.term_months?.toString() ?? ""} onChange={(e) => set("term_months", int(e.target.value))} />
        <SelectField id="ct-renew" label="Renovação automática" options={YES_NO} value={data.auto_renew ? "yes" : "no"} onChange={(e) => set("auto_renew", e.target.value === "yes")} />
        <TextField id="ct-billing" label="Dia de vencimento" hint="De 1 a 28." inputMode="numeric" value={data.billing_day?.toString() ?? ""} onChange={(e) => set("billing_day", int(e.target.value))} />
        <SelectField id="ct-payment" label="Forma de pagamento" options={PAYMENT} value={data.payment_method ?? ""} onChange={(e) => set("payment_method", (e.target.value || null) as ContractInput["payment_method"])} />
        <SelectField id="ct-index" label="Índice de reajuste" options={ADJUSTMENT} value={data.adjustment_index ?? ""} onChange={(e) => set("adjustment_index", (e.target.value || null) as ContractInput["adjustment_index"])} />
        <TextField id="ct-notes" label="Observações" value={data.notes ?? ""} onChange={(e) => set("notes", text(e.target.value))} />
      </div>
      <div className="row-actions">
        <Button type="submit" disabled={busy || !data.number.trim() || !data.starts_on}>
          {busy ? "Salvando…" : contract ? "Salvar contrato" : "Criar contrato"}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
        )}
      </div>
    </form>
  );
}

// --- Locais, agentes e câmeras --------------------------------------------------------------

function SiteForm({ orgId, onSaved }: { orgId: string; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [vision, setVision] = useState("yes");
  const [address, setAddress] = useState<Address>(EMPTY_ADDRESS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.platform.addSite(orgId, { name, timezone: "America/Sao_Paulo", vision_planned: vision === "yes", address });
      setName("");
      setAddress(EMPTY_ADDRESS);
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="stack" onSubmit={submit}>
      {error && <Callout tone="danger">{error}</Callout>}
      <div className="form-grid">
        <TextField id="site-name" label="Nome do local" placeholder="Ex.: Filial Centro" value={name} onChange={(e) => setName(e.target.value)} />
        <SelectField id="site-vision" label="Haverá serviço Vision neste local?" options={YES_NO} value={vision} onChange={(e) => setVision(e.target.value)} />
        <AddressFields prefix="site" value={address} onChange={setAddress} />
      </div>
      <div>
        <Button type="submit" disabled={busy || !name.trim()}>
          Adicionar local
        </Button>
      </div>
    </form>
  );
}

type ServiceMode = "none" | "contract" | "trial";

function CameraInstallForm({
  orgId,
  sites,
  agents,
  contracts,
  onSaved,
}: {
  orgId: string;
  sites: PlatformSite[];
  agents: { id: string; name: string }[];
  contracts: Contract[];
  onSaved: () => void;
}) {
  const active = contracts.filter((c) => c.status === "active");
  const [name, setName] = useState("");
  const [siteId, setSiteId] = useState(sites[0]?.id ?? "");
  const [withVision, setWithVision] = useState("yes");
  const [agentId, setAgentId] = useState(agents[0]?.id ?? "");
  const [sourceRef, setSourceRef] = useState("");
  const [modes, setModes] = useState<Record<VisionService, ServiceMode>>({ security: "contract", operation: "none" });
  const [fees, setFees] = useState<Record<VisionService, string>>({ security: "", operation: "" });
  const [contractId, setContractId] = useState(active[0]?.id ?? "");
  const [withEquipment, setWithEquipment] = useState("yes");
  const [ownership, setOwnership] = useState<Ownership>("client");
  const [equipment, setEquipment] = useState({ brand: "", model: "", serial_number: "", asset_tag: "", monthly_fee: "", reference_value: "" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const site = sites.find((s) => s.id === siteId);
  const visionAllowed = site?.vision_planned ?? false;
  const vision = visionAllowed && withVision === "yes";
  const services = (Object.keys(modes) as VisionService[]).filter((s) => modes[s] !== "none");
  const needsContract = (vision && services.some((s) => modes[s] === "contract")) || (withEquipment === "yes" && ownership === "comodato");
  const moneyInvalid = [...Object.values(fees), equipment.monthly_fee, equipment.reference_value].some((v) => Number.isNaN(parseMoney(v)));
  const invalid =
    !name.trim() ||
    !siteId ||
    (vision && (!agentId || !sourceRef.trim() || services.length === 0)) ||
    (!vision && withEquipment !== "yes") ||
    (needsContract && !contractId) ||
    moneyInvalid;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const choices: ServiceChoice[] = services.map((service) => ({
      service,
      mode: modes[service] as "contract" | "trial",
      contract_id: modes[service] === "contract" ? contractId : null,
      monthly_fee_cents: modes[service] === "contract" ? parseMoney(fees[service]) : null,
    }));
    try {
      await api.platform.installCamera(orgId, {
        name,
        site_id: siteId,
        vision: vision ? { agent_id: agentId, source_ref: sourceRef.trim(), analysis_fps: 5, services: choices } : null,
        equipment:
          withEquipment === "yes"
            ? {
                ownership,
                contract_id: ownership === "comodato" ? contractId : null,
                brand: text(equipment.brand),
                model: text(equipment.model),
                serial_number: text(equipment.serial_number),
                asset_tag: text(equipment.asset_tag),
                reference_value_cents: parseMoney(equipment.reference_value),
                monthly_fee_cents: ownership === "comodato" ? parseMoney(equipment.monthly_fee) : null,
                delivered_on: null,
                notes: null,
              }
            : null,
      });
      setNotice(`Câmera ${name} cadastrada.`);
      setName("");
      setSourceRef("");
      setEquipment({ brand: "", model: "", serial_number: "", asset_tag: "", monthly_fee: "", reference_value: "" });
      onSaved();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const modeOptions = [
    { value: "none", label: "Não" },
    { value: "contract", label: "Sim, contratado" },
    { value: "trial", label: "Sim, teste grátis de 3 dias" },
  ];
  const setEq = (key: keyof typeof equipment) => (e: { target: { value: string } }) => setEquipment((q) => ({ ...q, [key]: e.target.value }));

  return (
    <form className="stack" onSubmit={submit}>
      {error && <Callout tone="danger">{error}</Callout>}
      {notice && <Callout tone="ok">{notice}</Callout>}
      <div className="form-grid">
        <TextField id="cam-name" label="Nome da câmera" placeholder="Ex.: Caixa" value={name} onChange={(e) => setName(e.target.value)} />
        <SelectField id="cam-site" label="Local" options={sites.map((s) => ({ value: s.id, label: s.name }))} value={siteId} onChange={(e) => setSiteId(e.target.value)} />
        {visionAllowed ? (
          <SelectField id="cam-vision" label="Esta câmera terá serviço Vision?" options={YES_NO} value={withVision} onChange={(e) => setWithVision(e.target.value)} />
        ) : (
          <p className="text-small secondary form-note">Este local foi cadastrado sem serviço Vision: a câmera entra só como equipamento.</p>
        )}
      </div>

      {vision && (
        <fieldset className="fieldset">
          <legend className="text-label">Serviço Vision</legend>
          <div className="form-grid">
            <SelectField
              id="cam-agent"
              label="Agente"
              options={agents.length ? agents.map((a) => ({ value: a.id, label: a.name })) : [{ value: "", label: "Crie um agente primeiro" }]}
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
            />
            <TextField
              id="cam-ref"
              label="Apelido no agente"
              hint="O mesmo nome usado no sources.json do agente."
              placeholder="caixa"
              value={sourceRef}
              onChange={(e) => setSourceRef(e.target.value)}
            />
            {(Object.keys(modes) as VisionService[]).map((service) => (
              <div key={service} className="stack-tight">
                <SelectField
                  id={`cam-${service}`}
                  label={SERVICE_LABELS[service]}
                  options={modeOptions}
                  value={modes[service]}
                  onChange={(e) => setModes((m) => ({ ...m, [service]: e.target.value as ServiceMode }))}
                />
                {modes[service] === "contract" && (
                  <TextField
                    id={`cam-${service}-fee`}
                    label="Valor mensal negociado (R$)"
                    inputMode="decimal"
                    placeholder="120,00"
                    error={Number.isNaN(parseMoney(fees[service])) ? "Use um valor como 120,00." : undefined}
                    value={fees[service]}
                    onChange={(e) => setFees((f) => ({ ...f, [service]: e.target.value }))}
                  />
                )}
              </div>
            ))}
          </div>
          {vision && services.length === 0 && <p className="field-error">Escolha pelo menos uma modalidade, ou responda "Não" acima.</p>}
        </fieldset>
      )}

      <fieldset className="fieldset">
        <legend className="text-label">Equipamento</legend>
        <div className="form-grid">
          <SelectField id="cam-eq" label="Registrar o equipamento físico?" options={YES_NO} value={withEquipment} onChange={(e) => setWithEquipment(e.target.value)} />
          {withEquipment === "yes" && (
            <>
              <SelectField
                id="cam-ownership"
                label="Propriedade"
                options={(Object.keys(OWNERSHIP_LABELS) as Ownership[]).map((k) => ({ value: k, label: OWNERSHIP_LABELS[k] }))}
                value={ownership}
                onChange={(e) => setOwnership(e.target.value as Ownership)}
              />
              <TextField id="cam-brand" label="Marca" value={equipment.brand} onChange={setEq("brand")} />
              <TextField id="cam-model" label="Modelo" value={equipment.model} onChange={setEq("model")} />
              <TextField id="cam-serial" label="Número de série" value={equipment.serial_number} onChange={setEq("serial_number")} />
              {ownership === "comodato" && (
                <>
                  <TextField id="cam-asset" label="Patrimônio Alessio" placeholder="ALV-0042" value={equipment.asset_tag} onChange={setEq("asset_tag")} />
                  <TextField id="cam-eq-fee" label="Valor mensal do comodato (R$)" inputMode="decimal" value={equipment.monthly_fee} onChange={setEq("monthly_fee")} />
                </>
              )}
              <TextField id="cam-ref-value" label="Valor de reposição (R$)" inputMode="decimal" value={equipment.reference_value} onChange={setEq("reference_value")} />
            </>
          )}
        </div>
        {!vision && withEquipment !== "yes" && <p className="field-error">Sem serviço Vision, registre o equipamento.</p>}
      </fieldset>

      {needsContract && (
        <SelectField
          id="cam-contract"
          label="Contrato"
          hint="Serviços contratados e comodato entram neste contrato."
          options={active.length ? active.map((c) => ({ value: c.id, label: c.number })) : [{ value: "", label: "Crie um contrato na aba Contratos" }]}
          value={contractId}
          onChange={(e) => setContractId(e.target.value)}
        />
      )}
      <div>
        <Button type="submit" disabled={busy || invalid}>
          {busy ? "Salvando…" : "Cadastrar câmera"}
        </Button>
      </div>
    </form>
  );
}

export function SitesAndCameras({ orgId, contracts, onChanged }: { orgId: string; contracts: Contract[]; onChanged: () => void }) {
  const sites = useResource(() => api.platform.sites(orgId));
  const agents = useResource(() => api.platform.agents(orgId));
  const cameras = useResource(() => api.platform.cameras(orgId));
  const [agentName, setAgentName] = useState("");
  const [agentSite, setAgentSite] = useState("");
  const [code, setCode] = useState<EnrollmentCode | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reloadAll = () => {
    void sites.reload();
    void cameras.reload();
    onChanged();
  };

  const addAgent = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      setCode(await api.platform.addAgent(orgId, agentName.trim(), agentSite || sites.data?.[0]?.id || ""));
      setAgentName("");
      void agents.reload();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const siteColumns: Column<PlatformSite>[] = [
    { key: "name", header: "Local", render: (s) => s.name },
    { key: "vision", header: "Serviço Vision", render: (s) => (s.vision_planned ? <Badge tone="accent">Previsto</Badge> : <Badge tone="neutral">Sem Vision</Badge>) },
    { key: "address", header: "Endereço", render: (s) => [s.address.street, s.address.street_number, s.address.city, s.address.state].filter(Boolean).join(", ") || "—" },
  ];
  const cameraColumns: Column<NonNullable<typeof cameras.data>[number]>[] = [
    { key: "name", header: "Câmera", render: (c) => c.name },
    { key: "site", header: "Local", render: (c) => c.site_name },
    { key: "agent", header: "Agente / apelido", render: (c) => `${c.agent_name} · ${c.source_ref}` },
    {
      key: "services",
      header: "Serviços ativos",
      render: (c) =>
        c.services.length ? (
          <span className="row-actions">
            {c.services.map((s) => (
              <Badge key={s} tone="accent">
                {SERVICE_LABELS[s]}
              </Badge>
            ))}
          </span>
        ) : (
          <span className="secondary">Nenhum</span>
        ),
    },
  ];

  return (
    <>
      {error && <Callout tone="danger">{error}</Callout>}
      <Panel title="Locais" meta={sites.data ? `${sites.data.length}` : undefined}>
        <div className="stack">
          <DataTable caption="Locais do cliente" columns={siteColumns} rows={sites.data ?? []} rowKey={(s) => s.id} empty="Nenhum local." />
          <SiteForm orgId={orgId} onSaved={reloadAll} />
        </div>
      </Panel>
      <Panel title="Agentes" meta={agents.data ? `${agents.data.length}` : undefined}>
        <div className="stack">
          {code && (
            <SecretField
              label={`Comando de ativação de "${code.agent.name}" (vale até ${formatDate(code.enrollment_expires_at)})`}
              value={`alessio-agent enroll --api-url ${window.location.origin} --code ${code.enrollment_code}`}
            />
          )}
          <DataTable
            caption="Agentes do cliente"
            columns={[
              { key: "name", header: "Agente", render: (a) => a.name },
              { key: "site", header: "Local", render: (a) => a.site_name },
              { key: "status", header: "Situação", render: (a) => (a.status === "active" ? <Badge tone="ok">Ativo</Badge> : a.status === "pending" ? <Badge tone="warn">Aguardando ativação</Badge> : <Badge tone="neutral">Revogado</Badge>) },
            ]}
            rows={agents.data ?? []}
            rowKey={(a) => a.id}
            empty="Nenhum agente. Câmeras com serviço Vision precisam de um agente no local."
          />
          <form className="inline-form" onSubmit={addAgent}>
            <TextField id="ag-name" label="Novo agente" placeholder="Ex.: Mini PC da loja" value={agentName} onChange={(e) => setAgentName(e.target.value)} />
            <SelectField id="ag-site" label="Local" options={(sites.data ?? []).map((s) => ({ value: s.id, label: s.name }))} value={agentSite || sites.data?.[0]?.id || ""} onChange={(e) => setAgentSite(e.target.value)} />
            <Button type="submit" disabled={!agentName.trim() || !sites.data?.length}>
              Criar e gerar código
            </Button>
          </form>
        </div>
      </Panel>
      <Panel title="Câmeras com Vision" meta={cameras.data ? `${cameras.data.length}` : undefined}>
        <DataTable caption="Câmeras com serviço Vision" columns={cameraColumns} rows={cameras.data ?? []} rowKey={(c) => c.id} empty="Nenhuma câmera com serviço Vision." />
      </Panel>
      {sites.data && agents.data && (
        <Panel title="Nova câmera">
          <CameraInstallForm
            key={`${sites.data.length}-${agents.data.length}-${contracts.length}`}
            orgId={orgId}
            sites={sites.data}
            agents={agents.data.filter((a) => a.status !== "revoked")}
            contracts={contracts}
            onSaved={reloadAll}
          />
        </Panel>
      )}
    </>
  );
}

