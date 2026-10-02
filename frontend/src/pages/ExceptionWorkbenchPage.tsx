import { useQuery } from "@tanstack/react-query";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

interface UnbilledShipment {
  shipment_external_id: string;
  shipment_line_external_id: string;
  order_line_external_id: string | null;
  shipped_quantity: string;
  billed_quantity: string;
  unbilled_quantity: string;
  estimated_value: string;
  sufficient_evidence: boolean;
  shipment_date: string;
}

interface OrderHoldRow {
  order_external_id: string;
  hold_reason: string;
  is_active: boolean;
  age_days: number | null;
  linked_invoice_id: string | null;
}

/**
 * Real exception workbench: unbilled shipments and active order holds,
 * both from SQL-backed domain services (domain/shipment_service.py,
 * domain/holds_service.py) over the active dataset version.
 */
export function ExceptionWorkbenchPage() {
  const apiFetch = useApi();
  const me = useMe();
  const businessUnitId = me.business_units[0].id;

  const shipmentsQuery = useQuery({
    queryKey: ["unbilled-shipments", businessUnitId],
    queryFn: () =>
      apiFetch<UnbilledShipment[]>(
        `/api/v1/dashboard/unbilled-shipments?business_unit_id=${businessUnitId}`,
      ),
  });

  const holdsQuery = useQuery({
    queryKey: ["order-holds", businessUnitId],
    queryFn: () =>
      apiFetch<OrderHoldRow[]>(`/api/v1/dashboard/order-holds?business_unit_id=${businessUnitId}`),
  });

  return (
    <section>
      <h2>Exception Workbench</h2>

      <h3>Unbilled Shipments</h3>
      {shipmentsQuery.isLoading && <p>Loading…</p>}
      {shipmentsQuery.isError && <p role="alert">Could not load unbilled shipments.</p>}
      {shipmentsQuery.data && shipmentsQuery.data.length === 0 && <p>No unbilled shipment exceptions.</p>}
      {shipmentsQuery.data && shipmentsQuery.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Shipment</th>
              <th>Shipped</th>
              <th>Billed</th>
              <th>Unbilled</th>
              <th>Est. Value</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {shipmentsQuery.data.map((row) => (
              <tr key={row.shipment_line_external_id}>
                <td>{row.shipment_external_id}</td>
                <td>{row.shipped_quantity}</td>
                <td>{row.billed_quantity}</td>
                <td>{row.unbilled_quantity}</td>
                <td>{row.estimated_value}</td>
                <td>{row.sufficient_evidence ? "sufficient" : "insufficient — not asserted"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Active Order Holds</h3>
      {holdsQuery.isLoading && <p>Loading…</p>}
      {holdsQuery.isError && <p role="alert">Could not load order holds.</p>}
      {holdsQuery.data && holdsQuery.data.length === 0 && <p>No active holds.</p>}
      {holdsQuery.data && holdsQuery.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Order</th>
              <th>Reason</th>
              <th>Age (days)</th>
              <th>Linked invoice</th>
            </tr>
          </thead>
          <tbody>
            {holdsQuery.data.map((row) => (
              <tr key={row.order_external_id}>
                <td>{row.order_external_id}</td>
                <td>{row.hold_reason}</td>
                <td>{row.age_days}</td>
                <td>{row.linked_invoice_id ?? "— (no source link)"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
