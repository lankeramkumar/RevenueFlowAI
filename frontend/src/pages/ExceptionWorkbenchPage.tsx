import { Fragment, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";
import { cellStyle, headerRowStyle, numericCellStyle, tableStyle } from "../ui/tableStyles";

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

type SortDirection = "asc" | "desc";

const PAGE_SIZE = 10;

function sortRows<T>(
  rows: T[],
  sortKey: keyof T | null,
  direction: SortDirection,
): T[] {
  if (!sortKey) return rows;
  const copy = [...rows];
  copy.sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return direction === "asc" ? -1 : 1;
    if (bv == null) return direction === "asc" ? 1 : -1;
    if (typeof av === "number" && typeof bv === "number") {
      return direction === "asc" ? av - bv : bv - av;
    }
    const as = String(av);
    const bs = String(bv);
    return direction === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
  });
  return copy;
}

function SortableHeader<T>({
  label,
  columnKey,
  sortKey,
  direction,
  onSort,
}: {
  label: string;
  columnKey: keyof T;
  sortKey: keyof T | null;
  direction: SortDirection;
  onSort: (key: keyof T) => void;
}) {
  const active = sortKey === columnKey;
  return (
    <th style={cellStyle}>
      <button
        type="button"
        onClick={() => onSort(columnKey)}
        style={{ background: "none", border: "none", cursor: "pointer", font: "inherit", padding: 0 }}
      >
        {label}{active ? (direction === "asc" ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
}

function Pager({
  page,
  pageCount,
  onPageChange,
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  if (pageCount <= 1) return null;
  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", margin: "0.5rem 0" }}>
      <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pageCount}
      </span>
      <button type="button" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>
        Next
      </button>
    </div>
  );
}

/**
 * Real exception workbench: unbilled shipments and active order holds,
 * both from SQL-backed domain services (domain/shipment_service.py,
 * domain/holds_service.py) over the active dataset version. Filtering,
 * sorting, and pagination are applied client-side over the real rows
 * returned by those services -- no row is invented here.
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

  // Unbilled shipments: filter/sort/paginate + evidence drawer.
  const [shipmentFilter, setShipmentFilter] = useState("");
  const [shipmentSortKey, setShipmentSortKey] = useState<keyof UnbilledShipment | null>(null);
  const [shipmentSortDir, setShipmentSortDir] = useState<SortDirection>("asc");
  const [shipmentPage, setShipmentPage] = useState(1);
  const [expandedShipmentId, setExpandedShipmentId] = useState<string | null>(null);

  const filteredShipments = useMemo(() => {
    const rows = shipmentsQuery.data ?? [];
    const needle = shipmentFilter.trim().toLowerCase();
    const filtered = needle
      ? rows.filter((r) =>
          r.shipment_external_id.toLowerCase().includes(needle) ||
          (r.order_line_external_id ?? "").toLowerCase().includes(needle),
        )
      : rows;
    return sortRows(filtered, shipmentSortKey, shipmentSortDir);
  }, [shipmentsQuery.data, shipmentFilter, shipmentSortKey, shipmentSortDir]);

  const shipmentPageCount = Math.max(1, Math.ceil(filteredShipments.length / PAGE_SIZE));
  const shipmentPageRows = filteredShipments.slice(
    (shipmentPage - 1) * PAGE_SIZE,
    shipmentPage * PAGE_SIZE,
  );

  function onSortShipments(key: keyof UnbilledShipment) {
    if (shipmentSortKey === key) {
      setShipmentSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setShipmentSortKey(key);
      setShipmentSortDir("asc");
    }
  }

  // Order holds: filter/sort/paginate + evidence drawer.
  const [holdFilter, setHoldFilter] = useState("");
  const [holdSortKey, setHoldSortKey] = useState<keyof OrderHoldRow | null>(null);
  const [holdSortDir, setHoldSortDir] = useState<SortDirection>("asc");
  const [holdPage, setHoldPage] = useState(1);
  const [expandedHoldId, setExpandedHoldId] = useState<string | null>(null);

  const filteredHolds = useMemo(() => {
    const rows = holdsQuery.data ?? [];
    const needle = holdFilter.trim().toLowerCase();
    const filtered = needle
      ? rows.filter((r) =>
          r.order_external_id.toLowerCase().includes(needle) ||
          r.hold_reason.toLowerCase().includes(needle),
        )
      : rows;
    return sortRows(filtered, holdSortKey, holdSortDir);
  }, [holdsQuery.data, holdFilter, holdSortKey, holdSortDir]);

  const holdPageCount = Math.max(1, Math.ceil(filteredHolds.length / PAGE_SIZE));
  const holdPageRows = filteredHolds.slice((holdPage - 1) * PAGE_SIZE, holdPage * PAGE_SIZE);

  function onSortHolds(key: keyof OrderHoldRow) {
    if (holdSortKey === key) {
      setHoldSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setHoldSortKey(key);
      setHoldSortDir("asc");
    }
  }

  return (
    <section>
      <h2>Exception Workbench</h2>
      <p className="page-subtitle">Open billing and cash exceptions in the active dataset. Filter and sort each list, and open the evidence behind any row.</p>

      <h3>Unbilled Shipments</h3>
      {shipmentsQuery.isLoading && <p>Loading…</p>}
      {shipmentsQuery.isError && <p role="alert">Could not load unbilled shipments.</p>}
      {shipmentsQuery.data && shipmentsQuery.data.length === 0 && <p>No unbilled shipment exceptions.</p>}
      {shipmentsQuery.data && shipmentsQuery.data.length > 0 && (
        <>
          <input
            type="text"
            placeholder="Filter by shipment or order line…"
            value={shipmentFilter}
            onChange={(e) => {
              setShipmentFilter(e.target.value);
              setShipmentPage(1);
            }}
            aria-label="Filter unbilled shipments"
          />
          <div className="card card--flush"><table style={tableStyle}>
            <thead>
              <tr style={headerRowStyle}>
                <SortableHeader<UnbilledShipment>
                  label="Shipment" columnKey="shipment_external_id"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <SortableHeader<UnbilledShipment>
                  label="Shipped" columnKey="shipped_quantity"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <SortableHeader<UnbilledShipment>
                  label="Billed" columnKey="billed_quantity"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <SortableHeader<UnbilledShipment>
                  label="Unbilled" columnKey="unbilled_quantity"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <SortableHeader<UnbilledShipment>
                  label="Est. Value" columnKey="estimated_value"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <SortableHeader<UnbilledShipment>
                  label="Evidence" columnKey="sufficient_evidence"
                  sortKey={shipmentSortKey} direction={shipmentSortDir} onSort={onSortShipments}
                />
                <th style={cellStyle} />
              </tr>
            </thead>
            <tbody>
              {shipmentPageRows.map((row) => {
                const isExpanded = expandedShipmentId === row.shipment_line_external_id;
                return (
                  <Fragment key={row.shipment_line_external_id}>
                    <tr style={headerRowStyle}>
                      <td style={cellStyle}>{row.shipment_external_id}</td>
                      <td style={numericCellStyle}>{row.shipped_quantity}</td>
                      <td style={numericCellStyle}>{row.billed_quantity}</td>
                      <td style={numericCellStyle}>{row.unbilled_quantity}</td>
                      <td style={numericCellStyle}>{row.estimated_value}</td>
                      <td style={cellStyle}>{row.sufficient_evidence ? "sufficient" : "insufficient — not asserted"}</td>
                      <td style={cellStyle}>
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedShipmentId(isExpanded ? null : row.shipment_line_external_id)
                          }
                        >
                          {isExpanded ? "Hide evidence" : "Show evidence"}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={headerRowStyle}>
                        <td style={cellStyle} colSpan={7}>
                          <dl style={{ display: "grid", gridTemplateColumns: "max-content auto", gap: "0.25rem 1rem" }}>
                            <dt>Shipment line</dt>
                            <dd>{row.shipment_line_external_id}</dd>
                            <dt>Order line</dt>
                            <dd>{row.order_line_external_id ?? "— (no source link)"}</dd>
                            <dt>Shipment date</dt>
                            <dd>{row.shipment_date}</dd>
                            <dt>Evidence sufficiency</dt>
                            <dd>
                              {row.sufficient_evidence
                                ? "Shipment record plus billed/unbilled quantities reconcile directly."
                                : "Not asserted as sufficient by domain/shipment_service.py -- quantities alone don't fully substantiate this exception."}
                            </dd>
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table></div>
          <Pager page={shipmentPage} pageCount={shipmentPageCount} onPageChange={setShipmentPage} />
        </>
      )}

      <h3>Active Order Holds</h3>
      {holdsQuery.isLoading && <p>Loading…</p>}
      {holdsQuery.isError && <p role="alert">Could not load order holds.</p>}
      {holdsQuery.data && holdsQuery.data.length === 0 && <p>No active holds.</p>}
      {holdsQuery.data && holdsQuery.data.length > 0 && (
        <>
          <input
            type="text"
            placeholder="Filter by order or reason…"
            value={holdFilter}
            onChange={(e) => {
              setHoldFilter(e.target.value);
              setHoldPage(1);
            }}
            aria-label="Filter order holds"
          />
          <div className="card card--flush"><table style={tableStyle}>
            <thead>
              <tr style={headerRowStyle}>
                <SortableHeader<OrderHoldRow>
                  label="Order" columnKey="order_external_id"
                  sortKey={holdSortKey} direction={holdSortDir} onSort={onSortHolds}
                />
                <SortableHeader<OrderHoldRow>
                  label="Reason" columnKey="hold_reason"
                  sortKey={holdSortKey} direction={holdSortDir} onSort={onSortHolds}
                />
                <SortableHeader<OrderHoldRow>
                  label="Age (days)" columnKey="age_days"
                  sortKey={holdSortKey} direction={holdSortDir} onSort={onSortHolds}
                />
                <SortableHeader<OrderHoldRow>
                  label="Linked invoice" columnKey="linked_invoice_id"
                  sortKey={holdSortKey} direction={holdSortDir} onSort={onSortHolds}
                />
                <th style={cellStyle} />
              </tr>
            </thead>
            <tbody>
              {holdPageRows.map((row) => {
                const isExpanded = expandedHoldId === row.order_external_id;
                return (
                  <Fragment key={row.order_external_id}>
                    <tr style={headerRowStyle}>
                      <td style={cellStyle}>{row.order_external_id}</td>
                      <td style={cellStyle}>{row.hold_reason}</td>
                      <td style={numericCellStyle}>{row.age_days}</td>
                      <td style={cellStyle}>{row.linked_invoice_id ?? "— (no source link)"}</td>
                      <td style={cellStyle}>
                        <button
                          type="button"
                          onClick={() => setExpandedHoldId(isExpanded ? null : row.order_external_id)}
                        >
                          {isExpanded ? "Hide evidence" : "Show evidence"}
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr style={headerRowStyle}>
                        <td style={cellStyle} colSpan={5}>
                          <dl style={{ display: "grid", gridTemplateColumns: "max-content auto", gap: "0.25rem 1rem" }}>
                            <dt>Order</dt>
                            <dd>{row.order_external_id}</dd>
                            <dt>Hold reason</dt>
                            <dd>{row.hold_reason}</dd>
                            <dt>Currently active</dt>
                            <dd>{row.is_active ? "yes" : "no"}</dd>
                            <dt>Linked invoice</dt>
                            <dd>
                              {row.linked_invoice_id ??
                                "No invoice link recorded in order_holds.csv for this hold."}
                            </dd>
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table></div>
          <Pager page={holdPage} pageCount={holdPageCount} onPageChange={setHoldPage} />
        </>
      )}
    </section>
  );
}
