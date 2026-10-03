import { Fragment, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";
import { useAuth } from "react-oidc-context";
import { ApiError } from "../api/client";
import { streamPost } from "../api/stream";
import { cellStyle, numericCellStyle, tableStyle } from "../ui/tableStyles";

interface Evidence {
  source_type: string;
  record_type: string;
  record_id: string;
}

interface Finding {
  statement: string;
  evidence: Evidence[];
}

interface Metric {
  name: string;
  value: string;
  unit_or_currency: string;
  calculation_provenance: string;
}

interface SpecialistStatus {
  domain: string;
  status: string;
  unavailable_reason: string | null;
}

interface InvestigateResponse {
  conversation_id: string;
  summary: string;
  provider_mode: string;
  findings: Finding[];
  metrics: Metric[];
  specialist_status: SpecialistStatus[];
  evidence: Evidence[];
  missing_data: string[];
  dataset_version_id: string | null;
  as_of_date: string;
}

interface StoredMessage {
  role: string;
  content: string;
  provider_mode: string | null;
  findings: Finding[];
  metrics: Metric[];
  specialist_status: SpecialistStatus[];
  evidence: Evidence[];
  missing_data: string[];
}

interface EvidenceRecord {
  record_type: string;
  record_id: string;
  fields: Record<string, unknown>;
  related: { label: string; rows: Record<string, unknown>[] }[];
}

type Bubble =
  | { kind: "user"; key: string; text: string }
  | { kind: "assistant"; key: string; data: StoredMessage }
  | { kind: "error"; key: string; text: string };

const STARTER_QUESTIONS = [
  "Which shipments have been unbilled for more than five days?",
  "Why is this invoice overdue, and is there a dispute?",
  "Which invoices might match this receipt?",
  "Why is this order on hold?",
  "Summarize this customer's outstanding invoices, cash, disputes, and holds.",
];

const FOLLOW_UPS_BY_TYPE: Record<string, string[]> = {
  invoice: ["Is there a dispute on it?", "Which receipts were applied to it?"],
  receipt: ["Which invoices might match this receipt?"],
  customer: ["Summarize this customer's outstanding invoices, cash, disputes, and holds."],
  order_hold: ["Which shipments are unbilled for this order?"],
  shipment_line: ["Which shipments have been unbilled for more than five days?"],
};

function followUpsFor(evidence: Evidence[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const e of evidence) {
    for (const q of FOLLOW_UPS_BY_TYPE[e.record_type] ?? []) {
      if (!seen.has(q)) {
        seen.add(q);
        out.push(q);
      }
    }
  }
  return out.slice(0, 4);
}

function toStored(r: InvestigateResponse): StoredMessage {
  return {
    role: "assistant",
    content: r.summary,
    provider_mode: r.provider_mode,
    findings: r.findings,
    metrics: r.metrics,
    specialist_status: r.specialist_status,
    evidence: r.evidence,
    missing_data: r.missing_data,
  };
}

function EvidenceChip({ e, onOpen }: { e: Evidence; onOpen: (e: Evidence) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(e)}
      style={{
        border: "1px solid #cbd5e1", background: "#f8fafc", borderRadius: 999,
        padding: "2px 10px", margin: "2px 4px 2px 0", fontSize: 12, cursor: "pointer",
      }}
    >
      {e.record_type}: {e.record_id}
    </button>
  );
}

function AssistantMessage({
  data, onOpenEvidence, onFollowUp,
}: {
  data: StoredMessage;
  onOpenEvidence: (e: Evidence) => void;
  onFollowUp: (q: string) => void;
}) {
  const isLive = data.provider_mode === "live";
  const followUps = followUpsFor(data.evidence);
  const noAnswer = data.findings.length === 0 && data.metrics.length === 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span
        style={{
          alignSelf: "flex-start", fontSize: 11, fontWeight: 600, borderRadius: 4, padding: "1px 6px",
          background: isLive ? "#dcfce7" : "#fef3c7", color: isLive ? "#166534" : "#92400e",
        }}
      >
        {isLive ? "LIVE · Claude planned this question" : "DEMO · deterministic routing, no model call"}
      </span>

      {noAnswer ? (
        <p style={{ margin: 0 }}>{data.content}</p>
      ) : (
        <>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {data.findings.map((f, i) => (
              <li key={i} style={{ marginBottom: 6 }}>
                {f.statement}
                {f.evidence.length > 0 && (
                  <div>{f.evidence.map((e, j) => <EvidenceChip key={j} e={e} onOpen={onOpenEvidence} />)}</div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {data.metrics.length > 0 && (
        <table style={{ ...tableStyle, fontSize: 13 }}>
          <thead>
            <tr>
              <th style={cellStyle}>Metric</th>
              <th style={{ ...cellStyle, textAlign: "right" }}>Value</th>
              <th style={cellStyle}>Currency</th>
            </tr>
          </thead>
          <tbody>
            {data.metrics.map((m, i) => (
              <tr key={i} title={m.calculation_provenance}>
                <td style={cellStyle}>{m.name}</td>
                <td style={numericCellStyle}>
                  {Number(m.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td style={cellStyle}>{m.unit_or_currency}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data.specialist_status.length > 0 && (
        <div style={{ fontSize: 12, color: "#475569" }}>
          Consulted:{" "}
          {data.specialist_status.map((s, i) => (
            <span key={i}>
              {i > 0 && " · "}
              {s.domain} ({s.status}
              {s.unavailable_reason ? `: ${s.unavailable_reason}` : ""})
            </span>
          ))}
        </div>
      )}

      {data.missing_data.length > 0 && (
        <div style={{ fontSize: 12, color: "#9a3412" }}>
          Missing or ambiguous: {data.missing_data.join("; ")}
        </div>
      )}

      {followUps.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {followUps.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onFollowUp(q)}
              style={{
                border: "1px solid #94a3b8", background: "white", borderRadius: 8,
                padding: "4px 10px", fontSize: 12, cursor: "pointer",
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceDrawer({
  evidence, businessUnitId, onClose,
}: {
  evidence: Evidence;
  businessUnitId: string;
  onClose: () => void;
}) {
  const apiFetch = useApi();
  const query = useQuery({
    queryKey: ["evidence", evidence.record_type, evidence.record_id, businessUnitId],
    queryFn: () =>
      apiFetch<EvidenceRecord>(
        `/api/v1/evidence/${encodeURIComponent(evidence.record_type)}/${encodeURIComponent(evidence.record_id)}?business_unit_id=${businessUnitId}`,
      ),
  });

  return (
    <aside
      role="dialog"
      aria-label="Evidence"
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 380, background: "white",
        borderLeft: "1px solid #cbd5e1", boxShadow: "-4px 0 12px rgba(0,0,0,0.08)",
        padding: 16, overflowY: "auto", zIndex: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>
          {evidence.record_type}: {evidence.record_id}
        </strong>
        <button type="button" onClick={onClose}>Close</button>
      </div>
      <p style={{ fontSize: 12, color: "#64748b" }}>Stored record from the active dataset, read-only.</p>

      {query.isLoading && <p>Loading…</p>}
      {query.isError && <p role="alert">This record could not be loaded.</p>}
      {query.data && (
        <>
          <dl style={{ display: "grid", gridTemplateColumns: "max-content auto", gap: "4px 12px", fontSize: 13 }}>
            {Object.entries(query.data.fields).map(([k, v]) => (
              <Fragment key={k}>
                <dt style={{ color: "#64748b" }}>{k}</dt>
                <dd style={{ margin: 0, wordBreak: "break-all" }}>{v == null ? "—" : String(v)}</dd>
              </Fragment>
            ))}
          </dl>
          {query.data.related.map((group) => (
            <div key={group.label} style={{ marginTop: 16 }}>
              <strong style={{ fontSize: 13 }}>
                {group.label} ({group.rows.length})
              </strong>
              {group.rows.length === 0 && <p style={{ fontSize: 12, color: "#64748b" }}>None on record.</p>}
              {group.rows.map((row, i) => (
                <pre key={i} style={{ fontSize: 11, background: "#f8fafc", padding: 6, overflowX: "auto" }}>
                  {Object.entries(row)
                    .map(([k, v]) => `${k}: ${v == null ? "—" : String(v)}`)
                    .join("\n")}
                </pre>
              ))}
            </div>
          ))}
        </>
      )}
    </aside>
  );
}

export function ChatPage() {
  const apiFetch = useApi();
  const me = useMe();
  const queryClient = useQueryClient();
  const businessUnitId = me.business_units[0].id;
  const [searchParams, setSearchParams] = useSearchParams();
  const conversationId = searchParams.get("c");

  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [customerHint, setCustomerHint] = useState("");
  const [pending, setPending] = useState<Bubble[]>([]);
  const [openEvidence, setOpenEvidence] = useState<Evidence | null>(null);
  const threadEnd = useRef<HTMLDivElement>(null);

  const history = useQuery({
    queryKey: ["chat-history", conversationId],
    queryFn: () => apiFetch<StoredMessage[]>(`/api/v1/chat/${conversationId}/messages`),
    enabled: !!conversationId,
  });

  const stored: Bubble[] = (history.data ?? []).map((m, i) =>
    m.role === "user"
      ? { kind: "user", key: `h-${i}`, text: m.content }
      : { kind: "assistant", key: `h-${i}`, data: m },
  );
  const auth = useAuth();
  const abortRef = useRef<AbortController | null>(null);
  const [progress, setProgress] = useState<{ plan: string[]; done: string[] }>({ plan: [], done: [] });

  const ask = useMutation({
    mutationFn: async (q: string): Promise<InvestigateResponse> => {
      const controller = new AbortController();
      abortRef.current = controller;
      setProgress({ plan: [], done: [] });
      let result: InvestigateResponse | null = null;
      await streamPost(
        "/api/v1/chat/investigate/stream",
        {
          business_unit_id: businessUnitId,
          question: q,
          conversation_id: conversationId,
          customer_id_hint: customerHint.trim() || undefined,
          mode,
        },
        auth.user?.access_token,
        (event) => {
          if (event.event === "plan") setProgress((p) => ({ ...p, plan: event.dispatches }));
          if (event.event === "specialist") {
            setProgress((p) => ({ ...p, done: [...p.done, `${event.domain}: ${event.status}`] }));
          }
          if (event.event === "result") result = event.data as InvestigateResponse;
          if (event.event === "error") throw new ApiError(event.status, "investigation_failed", String(event.detail));
        },
        controller.signal,
      );
      if (!result) throw new Error("The investigation ended without a result.");
      return result;
    },
    onMutate: (q) => {
      setPending([{ kind: "user", key: "pending-user", text: q }]);
      setDraft("");
    },
    onSuccess: (response, q) => {
      const id = response.conversation_id;
      const prior = queryClient.getQueryData<StoredMessage[]>(["chat-history", id]) ?? [];
      const userMsg: StoredMessage = {
        role: "user", content: q, provider_mode: null, findings: [], metrics: [],
        specialist_status: [], evidence: [], missing_data: [],
      };
      queryClient.setQueryData<StoredMessage[]>(["chat-history", id], [
        ...prior, userMsg, toStored(response),
      ]);
      setPending([]);
      if (id !== conversationId) setSearchParams({ c: id });
    },
    onError: () => {
      if (abortRef.current?.signal.aborted) {
        setPending([{ kind: "error", key: "pending-stopped", text: "Stopped. Nothing was saved." }]);
        return;
      }
      setPending([{
        kind: "error",
        key: "pending-error",
        text: "The investigation failed. Check that a dataset is active, then try again.",
      }]);
    },
  });

  const bubbles: Bubble[] = [...stored, ...pending];

  useEffect(() => {
    threadEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [bubbles.length, ask.isPending]);

  function send(text: string) {
    const trimmed = text.trim();
    if (trimmed && !ask.isPending) ask.mutate(trimmed);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 110px)", minHeight: 480, textAlign: "left", fontSize: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 8 }}>
        <div>
          <h2 style={{ margin: 0 }}>Investigate</h2>
          <p className="page-subtitle" style={{ margin: 0 }}>Every answer cites the stored records behind it. Demo and live modes share the same evidence.</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <label>
            Mode{" "}
            <select value={mode} onChange={(e) => setMode(e.target.value as "demo" | "live")}>
              <option value="demo">Demo</option>
              <option value="live">Live (Claude)</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => {
              setPending([]);
              setSearchParams({});
            }}
          >
            New conversation
          </button>
        </div>
      </div>

      <div
        style={{
          flex: 1, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 10, boxShadow: "var(--shadow-card)",
          padding: 16, background: "var(--surface)", display: "flex", flexDirection: "column", gap: 14,
        }}
      >
        {bubbles.length === 0 && (
          <div>
            <p style={{ color: "#475569" }}>
              Ask about orders, invoices, receipts, shipments, or holds. Answers cite the stored records behind them;
              click any citation to see the record.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {STARTER_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => send(q)}
                  style={{
                    border: "1px solid #94a3b8", background: "white", borderRadius: 8,
                    padding: "6px 10px", fontSize: 13, cursor: "pointer", textAlign: "left",
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {bubbles.map((b) => {
          if (b.kind === "user") {
            return (
              <div key={b.key} style={{ alignSelf: "flex-end", maxWidth: "75%", background: "#1e293b", color: "white", borderRadius: "12px 12px 2px 12px", padding: "8px 12px" }}>
                {b.text}
              </div>
            );
          }
          if (b.kind === "error") {
            return (
              <div key={b.key} role="alert" style={{ alignSelf: "flex-start", maxWidth: "80%", color: "#991b1b" }}>
                {b.text}
              </div>
            );
          }
          return (
            <div key={b.key} style={{ alignSelf: "flex-start", maxWidth: "85%", background: "white", border: "1px solid #e2e8f0", borderRadius: "12px 12px 12px 2px", padding: "10px 14px", textAlign: "left" }}>
              <AssistantMessage
                data={b.data}
                onOpenEvidence={setOpenEvidence}
                onFollowUp={(q) => send(q)}
              />
            </div>
          );
        })}

        {ask.isPending && (
          <div className="card" style={{ alignSelf: "flex-start", fontSize: 13, minWidth: 280 }}>
            <div style={{ color: "var(--ink-faint)", marginBottom: 6 }}>Investigating…</div>
            {progress.plan.map((d) => {
              const domain = d.split(":")[0];
              const finished = progress.done.find((x) => x.startsWith(`${domain}:`));
              return (
                <div key={d} style={{ display: "flex", gap: 8, padding: "2px 0" }}>
                  <span>{finished ? "✓" : "…"}</span>
                  <span>
                    {d.replace(":", " · ")}
                    {finished ? ` (${finished.split(": ")[1]})` : ""}
                  </span>
                </div>
              );
            })}
            <button type="button" onClick={() => abortRef.current?.abort()} style={{ marginTop: 8 }}>
              Stop
            </button>
          </div>
        )}
        <div ref={threadEnd} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
        style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "flex-end" }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          rows={2}
          placeholder="Ask a follow-up or a new question. Enter sends, Shift+Enter adds a line."
          aria-label="Question"
          style={{ flex: 1, padding: 8, borderRadius: 8, border: "1px solid #cbd5e1", resize: "none", fontFamily: "inherit" }}
        />
        <button type="submit" disabled={ask.isPending || !draft.trim()} style={{ padding: "8px 16px" }}>
          Send
        </button>
      </form>
      <details style={{ fontSize: 12, marginTop: 4, color: "#475569" }}>
        <summary>Advanced</summary>
        <label>
          Customer ID for customer-summary questions{" "}
          <input value={customerHint} onChange={(e) => setCustomerHint(e.target.value)} placeholder="e.g. DEMO-CUST-000001" />
        </label>
      </details>

      {openEvidence && (
        <EvidenceDrawer evidence={openEvidence} businessUnitId={businessUnitId} onClose={() => setOpenEvidence(null)} />
      )}
    </div>
  );
}
