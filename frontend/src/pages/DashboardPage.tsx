import { useQuery } from "@tanstack/react-query";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

interface AgingSummaryResponse {
  dataset_version_id: string | null;
  snapshot_date: string | null;
  as_of_date: string;
  totals_by_currency_bucket: Record<string, Record<string, string>>;
}

const BUCKETS: { key: string; label: string }[] = [
  { key: "not_due", label: "Not due" },
  { key: "1-30", label: "1–30 days" },
  { key: "31-60", label: "31–60 days" },
  { key: "61-90", label: "61–90 days" },
  { key: "91+", label: "91+ days" },
];

function formatMoney(raw: string | undefined): string {
  const value = Number(raw ?? "0");
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const cell = { padding: "8px 14px", borderBottom: "1px solid #e2e8f0" } as const;
const numeric = { ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" } as const;

/**
 * Real aging dashboard: calls the SQL-backed /api/v1/dashboard/aging-summary
 * endpoint (domain/services.py) for the caller's business unit. Amounts stay
 * decimal strings in the data; formatting happens only at display time, and
 * currencies are never combined.
 */
export function DashboardPage() {
  const apiFetch = useApi();
  const me = useMe();
  const businessUnitId = me.business_units[0].id;

  const query = useQuery({
    queryKey: ["aging-summary", businessUnitId],
    queryFn: () =>
      apiFetch<AgingSummaryResponse>(
        `/api/v1/dashboard/aging-summary?business_unit_id=${businessUnitId}`,
      ),
  });

  if (query.isLoading) return <p>Loading aging summary…</p>;
  if (query.isError) return <p role="alert">Could not load the aging summary.</p>;

  const summary = query.data!;
  const currencies = Object.keys(summary.totals_by_currency_bucket).sort();

  if (summary.dataset_version_id === null) {
    return <p>No active dataset yet for this business unit. Upload a CSV bundle first.</p>;
  }

  return (
    <section>
      <h2>Invoice Aging</h2>
      <p style={{ color: "#64748b", marginTop: 0 }}>
        As of {summary.as_of_date} · dataset snapshot {summary.snapshot_date} · currencies are never combined
      </p>
      {currencies.length === 0 ? (
        <p>No open invoice balances in the active dataset.</p>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
              <th style={cell}>Currency</th>
              {BUCKETS.map((bucket) => (
                <th key={bucket.key} style={{ ...cell, textAlign: "right" }}>{bucket.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currencies.map((currency) => {
              const buckets = summary.totals_by_currency_bucket[currency];
              return (
                <tr key={currency}>
                  <td style={{ ...cell, fontWeight: 600, textAlign: "left" }}>{currency}</td>
                  {BUCKETS.map((bucket) => (
                    <td key={bucket.key} style={numeric}>{formatMoney(buckets[bucket.key])}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
