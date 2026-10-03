import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

interface InvoiceSummary {
  invoice_external_id: string;
  invoice_date: string;
  due_date: string;
  currency: string;
  invoice_amount: string;
  status: string;
  open_balance: string | null;
  aging_bucket: string | null;
}

interface CreditMemoSummary {
  credit_memo_external_id: string;
  invoice_external_id: string | null;
  currency: string;
  credit_amount: string;
  status: string;
}

interface TimelineEvent {
  event_date: string;
  event_type: string;
  external_id: string;
  description: string;
  amount: string | null;
  currency: string | null;
  status: string;
}

interface CustomerDetail {
  dataset_version_id: string | null;
  customer_external_id: string;
  customer_name: string | null;
  account_number: string | null;
  payment_terms_days: number | null;
  invoices: InvoiceSummary[];
  credit_memos: CreditMemoSummary[];
  timeline: TimelineEvent[];
}

/**
 * Customer detail/timeline screen. Looked up by the customer's CSV
 * external_id (e.g. "S01-CUST" or "DEMO-CUST-000001"); there is no
 * customer-list endpoint yet, so this is a direct-lookup search rather
 * than a browsable directory -- the data underneath is real
 * (domain/customer_service.py over the active dataset version).
 */
export function CustomerDetailPage() {
  const apiFetch = useApi();
  const me = useMe();
  const businessUnitId = me.business_units[0].id;
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const [searchValue, setSearchValue] = useState(customerId ?? "");

  const query = useQuery({
    queryKey: ["customer-detail", businessUnitId, customerId],
    queryFn: () =>
      apiFetch<CustomerDetail>(
        `/api/v1/customers/${encodeURIComponent(customerId!)}?business_unit_id=${businessUnitId}`,
      ),
    enabled: !!customerId,
  });

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = searchValue.trim();
    if (trimmed) navigate(`/customers/${encodeURIComponent(trimmed)}`);
  }

  return (
    <section>
      <h2>Customer Detail</h2>
      <form onSubmit={onSearch} style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <input
          type="text"
          placeholder="Customer external ID, e.g. S01-CUST"
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          aria-label="Customer external ID"
        />
        <button type="submit">Look up</button>
      </form>

      {!customerId && <p>Enter a customer external ID to view their timeline.</p>}
      {customerId && query.isLoading && <p>Loading…</p>}
      {customerId && query.isError && (
        <p role="alert">Could not load customer "{customerId}" (not found, or no access).</p>
      )}

      {query.data && (
        <>
          <h3>{query.data.customer_name ?? query.data.customer_external_id}</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "max-content auto", gap: "0.25rem 1rem" }}>
            <dt>External ID</dt>
            <dd>{query.data.customer_external_id}</dd>
            <dt>Account number</dt>
            <dd>{query.data.account_number ?? "—"}</dd>
            <dt>Payment terms</dt>
            <dd>{query.data.payment_terms_days != null ? `${query.data.payment_terms_days} days` : "—"}</dd>
          </dl>

          <h4>Invoices</h4>
          {query.data.invoices.length === 0 && <p>No invoices on record.</p>}
          {query.data.invoices.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Invoice date</th>
                  <th>Due date</th>
                  <th>Amount</th>
                  <th>Open balance</th>
                  <th>Aging bucket</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {query.data.invoices.map((inv) => (
                  <tr key={inv.invoice_external_id}>
                    <td>{inv.invoice_external_id}</td>
                    <td>{inv.invoice_date}</td>
                    <td>{inv.due_date}</td>
                    <td>{inv.currency} {inv.invoice_amount}</td>
                    <td>{inv.open_balance != null ? `${inv.currency} ${inv.open_balance}` : "— (no open balance)"}</td>
                    <td>{inv.aging_bucket ?? "—"}</td>
                    <td>{inv.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h4>Credit memos</h4>
          {query.data.credit_memos.length === 0 && <p>No credit memos on record.</p>}
          {query.data.credit_memos.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Credit memo</th>
                  <th>Linked invoice</th>
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {query.data.credit_memos.map((cm) => (
                  <tr key={cm.credit_memo_external_id}>
                    <td>{cm.credit_memo_external_id}</td>
                    <td>{cm.invoice_external_id ?? "—"}</td>
                    <td>{cm.currency} {cm.credit_amount}</td>
                    <td>{cm.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h4>Timeline</h4>
          {query.data.timeline.length === 0 && <p>No timeline events on record.</p>}
          {query.data.timeline.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {query.data.timeline.map((ev, i) => (
                <li key={`${ev.event_type}-${ev.external_id}-${i}`} style={{ padding: "0.4rem 0", borderBottom: "1px solid #eee" }}>
                  <strong>{ev.event_date}</strong> — [{ev.event_type}] {ev.description}
                  {ev.amount != null && ` (${ev.currency ?? ""} ${ev.amount})`.trim()}
                  {" "}<em>({ev.status})</em>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
