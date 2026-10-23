import { api } from "../api";
import { Callout, Panel } from "../ui";
import { useResource } from "../useResource";
import { EquipmentTable, SummaryStrip } from "./equipmentShared";

export function EquipmentPage() {
  const equipment = useResource(api.equipment);
  return (
    <>
      <div className="page-heading">
        <h1 className="page-title text-display">Equipamentos</h1>
        <p className="text-small secondary">
          O que está instalado na sua operação, seu ou da Alessio em comodato. Para mudanças, fale com a equipe Alessio.
        </p>
      </div>
      {equipment.error && <Callout tone="danger">Falha ao carregar: {equipment.error}</Callout>}
      {equipment.data && (
        <>
          <Panel title="Resumo">
            <SummaryStrip summary={equipment.data.summary} />
          </Panel>
          <Panel title="Lista" meta={`${equipment.data.items.length}`}>
            <EquipmentTable items={equipment.data.items} />
          </Panel>
        </>
      )}
    </>
  );
}
