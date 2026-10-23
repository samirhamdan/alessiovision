import { api } from "../api";
import { Callout, Panel } from "../ui";
import { useResource } from "../useResource";
import { EquipmentTable, ServicesTable, SummaryStrip } from "./equipmentShared";

/** O que o cliente contratou: serviços Vision por câmera e equipamentos (próprios ou em comodato). */
export function EquipmentPage() {
  const equipment = useResource(api.equipment);
  const services = useResource(api.services);
  const error = equipment.error ?? services.error;
  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Contrato</h1>
        <p className="text-small secondary">
          Serviços Vision por câmera e equipamentos instalados, seus ou da Alessio em comodato. Para mudanças, fale com
          a equipe Alessio.
        </p>
      </div>
      {error && <Callout tone="danger">Falha ao carregar: {error}</Callout>}
      {equipment.data && services.data && (
        <Panel title="Resumo">
          <SummaryStrip summary={equipment.data.summary} servicesMonthly={services.data.services_monthly_cents} />
        </Panel>
      )}
      {services.data && (
        <Panel title="Serviços Vision por câmera">
          <ServicesTable overview={services.data} />
        </Panel>
      )}
      {equipment.data && (
        <Panel title="Equipamentos" meta={`${equipment.data.items.length}`}>
          <EquipmentTable items={equipment.data.items} />
        </Panel>
      )}
    </>
  );
}
