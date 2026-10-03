import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

interface SpecialistStatus {
  domain: string;
  status: string;
  unavailable_reason: string | null;
}

interface Evidence {
  source_type: string;
  record_type: string;
  record_id: string;
}

interface InvestigateResponse {
  conversation_id: string;
  summary: string;
  provider_mode: string;
  specialist_status: SpecialistStatus[];
  evidence: Evidence[];
  missing_data: string[];
  dataset_version_id: string | null;
  as_of_date: string;
}

interface Turn {
  question: string;
  response: InvestigateResponse;
}

const SUGGESTED_QUESTIONS = [
  "Which shipments have been unbilled for more than five days?",
  "Why is this invoice overdue, and is there a dispute?",
  "Which invoices might match this receipt?",
  "Why is this order on hold?",
  "Summarize this customer's outstanding invoices, cash, disputes, and holds.",
];

/**
 * Investigation chat: calls the real Supervisor (POST /api/v1/chat/investigate),
 * which dispatches Order/AR/Cash specialists and returns deterministic,
 * SQL-backed findings. Demo mode uses a regex planner (no API key); live
 * mode uses a real Anthropic call to classify the question -- the mode is
 * always labeled on each response, never implied.
 */
export function ChatPage() {
  const apiFetch = useApi();
  const me = useMe();
  const businessUnitId = me.business_units[0].id;
  const [question, setQuestion] = useState("");
  const [customerIdHint, setCustomerIdHint] = useState("");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);

  const investigateMutation = useMutation({
    mutationFn: (q: string) =>
      apiFetch<InvestigateResponse>("/api/v1/chat/investigate", {
        method: "POST",
        body: JSON.stringify({
          business_unit_id: businessUnitId,
          question: q,
          conversation_id: conversationId,
          customer_id_hint: customerIdHint || undefined,
          mode,
        }),
      }),
    onSuccess: (response, q) => {
      setConversationId(response.conversation_id);
      setTurns((prev) => [...prev, { question: q, response }]);
      setQuestion("");
    },
  });

  return (
    <section>
      <h2>Investigate</h2>

      <div>
        <label>
          Mode:{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value as "demo" | "live")}>
            <option value="demo">Demo (deterministic, no API key)</option>
            <option value="live">Live (Anthropic-backed)</option>
          </select>
        </label>
        {"  "}
        <label>
          Customer ID (for summary questions):{" "}
          <input value={customerIdHint} onChange={(e) => setCustomerIdHint(e.target.value)} placeholder="e.g. S01-CUST" />
        </label>
      </div>

      <p>Try: {SUGGESTED_QUESTIONS.map((q, i) => (
        <span key={q}>
          {i > 0 && " · "}
          <button type="button" onClick={() => setQuestion(q)}>{q}</button>
        </span>
      ))}</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) investigateMutation.mutate(question.trim());
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about orders, invoices, receipts…"
          style={{ width: "60%" }}
        />
        <button type="submit" disabled={investigateMutation.isPending}>
          {investigateMutation.isPending ? "Investigating…" : "Ask"}
        </button>
      </form>

      {investigateMutation.isError && <p role="alert">Investigation failed.</p>}

      <div>
        {turns.map((turn, i) => (
          <div key={i} style={{ border: "1px solid #ddd", padding: "0.75rem", margin: "0.75rem 0" }}>
            <p><strong>Q:</strong> {turn.question}</p>
            <p>
              <strong>A ({turn.response.provider_mode} mode):</strong> {turn.response.summary}
            </p>
            <p>
              Specialists consulted:{" "}
              {turn.response.specialist_status
                .map((s) => `${s.domain} (${s.status}${s.unavailable_reason ? `: ${s.unavailable_reason}` : ""})`)
                .join(", ") || "none"}
            </p>
            {turn.response.evidence.length > 0 && (
              <p>
                Evidence: {turn.response.evidence.map((e) => `${e.record_type}:${e.record_id}`).join(", ")}
              </p>
            )}
            {turn.response.missing_data.length > 0 && (
              <p>Missing/ambiguous: {turn.response.missing_data.join("; ")}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
