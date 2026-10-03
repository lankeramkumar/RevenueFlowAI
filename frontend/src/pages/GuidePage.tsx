import { useAuth } from "react-oidc-context";
import { apiToken } from "../auth/apiToken";
import { ISSUES_URL } from "../ui/contact";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const SPECIALISTS = [
  {
    name: "Order specialist",
    does: "Checks whether shipped goods have been invoiced, and lists active order holds.",
    intents: "Unbilled shipments (shipped, not yet billed, older than 5 days by default); order holds; order trace.",
    limit: "If a shipment has no link to an invoice line, the app reports it as insufficient evidence rather than as fully unbilled.",
  },
  {
    name: "AR (receivables) specialist",
    does: "Explains what customers owe: overdue invoices, open disputes, aging, and customer balances.",
    intents: "Overdue invoices and disputes; aging summary; customer summary; invoice details.",
    limit: "Balances count only posted invoices and applications. Draft, void, and reversed items are ignored.",
  },
  {
    name: "Cash application specialist",
    does: "Looks at receipts that are not fully applied, and proposes which invoices they might match.",
    intents: "Receipt details; receipt match proposals (one invoice or several); residual amounts; customer summary.",
    limit: "Proposals only. The app never applies cash. If several matches are possible, it asks which receipt you mean.",
  },
];

interface DataFile {
  file: string;
  required: string;
}

const DATA_FILES: DataFile[] = [
  { file: "customers.csv", required: "customer_id, account_number, customer_name" },
  { file: "orders.csv", required: "order_id, customer_id, order_date, currency, status" },
  { file: "order_lines.csv", required: "order_line_id, order_id, item_code, ordered_quantity, unit_price, line_amount" },
  { file: "shipments.csv", required: "shipment_id, order_id, shipment_date, status" },
  { file: "shipment_lines.csv", required: "shipment_line_id, shipment_id, order_line_id, shipped_quantity" },
  { file: "invoices.csv", required: "invoice_id, customer_id, invoice_date, due_date, currency, invoice_amount, status" },
  { file: "invoice_lines.csv", required: "invoice_line_id, invoice_id, line_amount" },
  { file: "receipts.csv", required: "receipt_id, customer_id, receipt_date, currency, receipt_amount, status" },
  { file: "receipt_applications.csv", required: "application_id, receipt_id, invoice_id, applied_amount, application_date, status" },
  { file: "credit_memos.csv", required: "credit_memo_id, customer_id, currency, credit_amount, status" },
  { file: "credit_applications.csv", required: "credit_application_id, credit_memo_id, invoice_id, applied_amount, application_date, status" },
  { file: "disputes.csv", required: "dispute_id, invoice_id, disputed_amount, reason, status, opened_date" },
  { file: "order_holds.csv", required: "hold_id, order_id, hold_reason, status, applied_date" },
];

async function downloadTemplate(file: string, token: string | undefined): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/templates/${file}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    window.alert(`Could not download ${file} (HTTP ${response.status}).`);
    return;
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = file;
  link.click();
  URL.revokeObjectURL(url);
}

export function GuidePage() {
  const auth = useAuth();
  const token = auth.user ? apiToken(auth.user) : undefined;

  return (
    <section className="help">
      <h2>Guide</h2>
      <p className="page-subtitle">
        What RevenueFlow AI does, what it does not do, the three specialist agents, their limits, and how to prepare
        and submit your data.
      </p>

      <h3>What the app does</h3>
      <div className="card">
        <p>
          RevenueFlow AI reads order-to-cash data (orders, shipments, invoices, receipts, credits, disputes, and
          holds) that you import as a set of CSV files. It finds exceptions, such as shipments that were never
          billed or receipts that don't match an invoice, and answers questions about them. Every figure is
          calculated by fixed rules, and each answer cites the records behind it.
        </p>
        <ul>
          <li>Dashboard: invoice aging by currency for your business unit.</li>
          <li>Investigate: plain-English questions, answered with citations.</li>
          <li>Exceptions: unbilled shipments and active order holds, with evidence for each row.</li>
          <li>Customers: one customer's balances, invoices, and history.</li>
          <li>Tasks: internal follow-ups. Documents: source files that answers can cite.</li>
        </ul>
      </div>

      <h3>What it cannot do</h3>
      <div className="card">
        <ul>
          <li>It does not change your ERP or any record. It cannot post payments, apply cash, approve, refund, release holds, or send emails.</li>
          <li>It does not give personal data about people (contact details, bank or card numbers, addresses, dates of birth). Such questions are refused.</li>
          <li>It does not connect to a live system. It only knows the last data you imported.</li>
          <li>It does not convert currencies, apply tax, forecast cash, or score credit risk.</li>
          <li>It does not answer questions outside orders, shipments, invoices, receipts, holds, and customer balances.</li>
        </ul>
      </div>

      <h3>The three specialist agents</h3>
      <p>
        A supervisor reads each question, sends it to at most three specialists, and merges their results. The
        supervisor is the router, not a fourth specialist. Each specialist can use only its own tools, and each
        question has a 20-second time budget.
      </p>
      {SPECIALISTS.map((s) => (
        <div key={s.name} className="card help-screen">
          <h3 style={{ marginTop: 0 }}>{s.name}</h3>
          <p>{s.does}</p>
          <p><strong>Answers:</strong> {s.intents}</p>
          <p><strong>Limit:</strong> {s.limit}</p>
        </div>
      ))}

      <h3>Limitations</h3>
      <div className="card">
        <ul>
          <li><strong>Snapshot data.</strong> Answers reflect the snapshot date you set on import, not today.</li>
          <li><strong>Currencies.</strong> USD, EUR, and GBP only. Amounts are never added across currencies.</li>
          <li><strong>Demo mode</strong> recognizes fixed phrasing, such as "unbilled shipments", "order hold", "overdue", "dispute", "aging", and "receipt match". Live mode lets Claude route the question, which can misroute. Check the citations before acting.</li>
          <li><strong>Documents.</strong> Text (.txt) and text-based PDF files only. Scanned PDFs have no text to read. Each file is limited to 10 MB.</li>
          <li><strong>Imports.</strong> A bundle is limited to 200 MB. A bundle with any validation error is not activated.</li>
          <li><strong>Evidence, not advice.</strong> The app shows what the records say. Decisions about collections, credit, or write-offs stay with your team.</li>
          <li><strong>Known gaps.</strong> Report issues on <a href={ISSUES_URL} target="_blank" rel="noreferrer">GitHub</a>.</li>
        </ul>
      </div>

      <h3>How to prepare your data</h3>
      <div className="card">
        <ol>
          <li>Use one CSV file per entity, 13 files in total. Each file needs a header row with the column names below, in any order.</li>
          <li>Save every file as UTF-8 CSV. Use commas as separators, and quote any value that contains a comma.</li>
          <li>Write dates as YYYY-MM-DD. Write amounts with a dot as the decimal point and no thousands separators, for example 1250.50.</li>
          <li>Keep IDs as text, including leading zeros. IDs must be unique within their file.</li>
          <li>Use only the supported currencies (USD, EUR, GBP), and only the status values listed below.</li>
          <li>Never enter negative amounts. To reverse a receipt, application, or credit, set its status to reversed.</li>
          <li>Every reference must point to a row that exists in the referenced file. For example, an order's customer_id must appear in customers.csv.</li>
        </ol>

        <h4>Required columns</h4>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--line-strong)" }}>
                <th style={{ padding: "6px 8px" }}>File</th>
                <th style={{ padding: "6px 8px" }}>Required columns</th>
              </tr>
            </thead>
            <tbody>
              {DATA_FILES.map((f) => (
                <tr key={f.file} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
                    <button type="button" onClick={() => void downloadTemplate(f.file, token)}>
                      {f.file}
                    </button>
                  </td>
                  <td style={{ padding: "6px 8px" }}>{f.required}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="help-note">Select a file name to download its empty template with the exact headers. Sign-in is required.</p>

        <h4>Allowed status values</h4>
        <ul>
          <li>orders.csv: open, fulfilled, cancelled</li>
          <li>shipments.csv: shipped, delivered, cancelled</li>
          <li>invoices.csv: draft, posted, void (only posted invoices count toward balances)</li>
          <li>receipts.csv: posted, cancelled</li>
          <li>receipt_applications.csv and credit_applications.csv: posted, reversed</li>
          <li>credit_memos.csv: posted, void</li>
          <li>disputes.csv: open, closed</li>
          <li>order_holds.csv: active, released</li>
        </ul>
      </div>

      <h3>How to submit your data</h3>
      <div className="card">
        <ol>
          <li>Sign in as an administrator. Only admins can import.</li>
          <li>Open <a href="/imports">Import</a>. Set the snapshot date to the date your extract was taken.</li>
          <li>Select all 13 CSV files at once, then choose Upload.</li>
          <li>Wait for validation. The app lists every row it rejected, with the file, row, and reason.</li>
          <li>Fix the rows in your source system or in your files, then upload the full set again.</li>
          <li>When the bundle is valid, it becomes the active data. The Dashboard and Exceptions pages update to the new snapshot.</li>
        </ol>
        <p className="help-note">
          Uploading an identical set of files again is recognized and not imported twice.
        </p>
      </div>

      <h3>Try it</h3>
      <div className="card">
        <ul>
          <li>"Which shipments are unbilled?"</li>
          <li>"Show overdue invoices for DEMO-CUST-000001"</li>
          <li>"Which orders are on hold?"</li>
          <li>"Did receipt RCP-2001 match an invoice?"</li>
          <li>"Summarize the outstanding balance for DEMO-CUST-000001"</li>
        </ul>
      </div>
    </section>
  );
}
