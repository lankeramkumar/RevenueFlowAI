import { useQuery } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { useApi } from "../hooks/useApi";

interface AgingSummaryResponse {
  dataset_version_id: string | null;
  snapshot_date: string | null;
  as_of_date: string;
  totals_by_currency_bucket: Record<string, Record<string, string>>;
}

const BUCKET_ORDER = ["not_due", "1-30", "31-60", "61-90", "91+"];

/**
 * Real aging dashboard: calls the SQL-backed /api/v1/dashboard/aging-summary
 * endpoint (domain/services.py) for the caller's business unit and renders
 * whatever currency/bucket totals come back — no mock data, no client-side
 * math on amounts (money stays a decimal string end to end).
 */
export function DashboardPage({ businessUnitId }: { businessUnitId: string }) {
  const apiFetch = useApi();
  const auth = useAuth();

  const query = useQuery({
    queryKey: ["aging-summary", businessUnitId],
    queryFn: () =>
      apiFetch<AgingSummaryResponse>(
        `/api/v1/dashboard/aging-summary?business_unit_id=${businessUnitId}`,
      ),
    enabled: auth.isAuthenticated,
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
      <p>
        As of {summary.as_of_date} · dataset snapshot {summary.snapshot_date}
      </p>
      {currencies.length === 0 ? (
        <p>No open invoice balances in the active dataset.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Currency</th>
              {BUCKET_ORDER.map((bucket) => (
                <th key={bucket}>{bucket}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currencies.map((currency) => (
              <tr key={currency}>
                <td>{currency}</td>
                {BUCKET_ORDER.map((bucket) => (
                  <td key={bucket}>
                    {summary.totals_by_currency_bucket[currency][bucket] ?? "0.00"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
