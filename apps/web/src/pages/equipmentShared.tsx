import type { ReactNode } from "react";

import type { CameraServices, Equipment, EquipmentSummary, ServiceLine, ServicesOverview, VisionService } from "../api";
import {
  EQUIPMENT_STATUS_LABELS,
  formatDate,
  formatDay,
  formatMoney,
  KIND_LABELS,
  OWNERSHIP_LABELS,
  SERVICE_LABELS,
} from "../format";
import { Badge, type Column, DataTable } from "../ui";

export function SummaryStrip({ summary, servicesMonthly }: { summary: EquipmentSummary; servicesMonthly?: number }) {
  const monthly =
    servicesMonthly === undefined
      ? []
      : [
          { label: "Serviços Vision por mês", value: formatMoney(servicesMonthly) },
          { label: "Mensalidade total", value: formatMoney(servicesMonthly + summary.comodato_monthly_cents) },
        ];
  const items = [
    { label: "Em operação", value: String(summary.total) },
    { label: "Do cliente", value: String(summary.client_owned) },
    { label: "Em comodato", value: String(summary.comodato) },
    { label: "Comodato por mês", value: formatMoney(summary.comodato_monthly_cents) },
    { label: "Valor de reposição (comodato)", value: formatMoney(summary.comodato_reference_cents) },
    ...monthly,
  ];
  return (
    <dl className="summary">
      {items.map((item) => (
        <div key={item.label} className="summary__item">
          <dt className="text-label">{item.label}</dt>
          <dd className="summary__value text-data">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function equipmentColumns(actions?: (item: Equipment) => ReactNode): Column<Equipment>[] {
  const columns: Column<Equipment>[] = [
    {
      key: "ownership",
      header: "Propriedade",
      render: (e) => <Badge tone={e.ownership === "comodato" ? "accent" : "neutral"}>{OWNERSHIP_LABELS[e.ownership]}</Badge>,
    },
    {
      key: "item",
      header: "Equipamento",
      render: (e) => (
        <>
          {KIND_LABELS[e.kind]}
          <div className="secondary text-small">
            {[e.brand, e.model].filter(Boolean).join(" ") || "Sem marca/modelo"}
            {e.serial_number ? ` · nº ${e.serial_number}` : ""}
          </div>
        </>
      ),
    },
    {
      key: "where",
      header: "Onde",
      render: (e) => [e.site_name, e.camera_name && `câmera ${e.camera_name}`, e.agent_name && `agente ${e.agent_name}`].filter(Boolean).join(" · ") || "—",
    },
    {
      key: "contract",
      header: "Contrato",
      render: (e) => e.contract_number ?? "—",
    },
    { key: "fee", header: "Por mês", align: "end", render: (e) => formatMoney(e.monthly_fee_cents) },
    {
      key: "status",
      header: "Situação",
      render: (e) => (
        <>
          {EQUIPMENT_STATUS_LABELS[e.status]}
          {e.status === "returned" && <div className="secondary text-small">em {formatDay(e.returned_on)}</div>}
        </>
      ),
    },
  ];
  if (actions) columns.push({ key: "actions", header: "Ações", render: actions });
  return columns;
}

export function EquipmentTable({ items, actions }: { items: Equipment[]; actions?: (item: Equipment) => ReactNode }) {
  return (
    <DataTable
      caption="Equipamentos do cliente"
      columns={equipmentColumns(actions)}
      rows={items}
      rowKey={(e) => e.id}
      empty="Nenhum equipamento cadastrado."
    />
  );
}

export function ServiceStatus({ line }: { line: ServiceLine | null }) {
  if (!line) return <span className="secondary">Sem contratação</span>;
  if (line.source === "trial") {
    return (
      <>
        <Badge tone="warn">Teste grátis</Badge>
        <div className="secondary text-small">até {formatDate(line.ends_at)}</div>
      </>
    );
  }
  return (
    <>
      <Badge tone={line.state === "active" ? "ok" : "neutral"}>{line.state === "active" ? "Contratado" : "A partir de " + formatDate(line.starts_at)}</Badge>
      <div className="secondary text-small">
        {formatMoney(line.monthly_fee_cents ?? 0)}/mês · {line.contract_number}
        {line.ends_at ? ` · até ${formatDate(line.ends_at)}` : ""}
      </div>
    </>
  );
}

export function ServicesTable({
  overview,
  actions,
}: {
  overview: ServicesOverview;
  actions?: (camera: CameraServices, service: VisionService) => ReactNode;
}) {
  const cell = (camera: CameraServices, service: VisionService) => (
    <div className="service-cell">
      <ServiceStatus line={camera[service]} />
      {actions?.(camera, service)}
    </div>
  );
  const columns: Column<CameraServices>[] = [
    { key: "camera", header: "Câmera", render: (c) => c.camera_name },
    { key: "security", header: SERVICE_LABELS.security, render: (c) => cell(c, "security") },
    { key: "operation", header: SERVICE_LABELS.operation, render: (c) => cell(c, "operation") },
  ];
  return (
    <DataTable
      caption="Serviços Vision por câmera"
      columns={columns}
      rows={overview.cameras}
      rowKey={(c) => c.camera_id}
      empty="Nenhuma câmera cadastrada neste cliente."
    />
  );
}
