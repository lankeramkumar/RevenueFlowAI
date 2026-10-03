import { CONTACT_EMAIL, ISSUES_URL, REPO_URL } from "../ui/contact";

interface Screen {
  name: string;
  path: string;
  purpose: string;
  steps: string[];
  roles: string;
}

const SCREENS: Screen[] = [
  {
    name: "Dashboard",
    path: "/",
    purpose: "Invoice aging for your business unit, shown per currency. Amounts in different currencies are never added together.",
    steps: [
      "Check the as-of date to see how current the numbers are.",
      "Use the aging buckets to find invoices that are overdue, then open Exceptions or Customers to dig in.",
    ],
    roles: "All roles",
  },
  {
    name: "Investigate",
    path: "/chat",
    purpose: "Ask questions in plain English. Every answer cites the records it is based on.",
    steps: [
      "Type a question and press Enter. Shift+Enter adds a new line.",
      "Click a citation to open the underlying record.",
      "Ask follow-ups such as \"Is there a dispute on it?\". The app remembers the invoice from the previous answer.",
      "Press Stop to cancel an answer that is still being prepared.",
      "Choose a customer ID in the hint box (for example DEMO-CUST-000001) to focus a question on one customer.",
    ],
    roles: "All roles",
  },
  {
    name: "Exceptions",
    path: "/workbench",
    purpose: "Two lists that show where billing and cash are blocked: unbilled shipments, and active order holds.",
    steps: [
      "Type in the filter box above each list to narrow the rows.",
      "Use Previous and Next to move between pages.",
      "Click Show evidence on a row to see the fields behind it. Click Hide evidence to close it.",
    ],
    roles: "All roles",
  },
  {
    name: "Customers",
    path: "/customers",
    purpose: "A single customer's balances, invoices, and history.",
    steps: [
      "Enter the customer's external ID, for example DEMO-CUST-000001, and choose Look up.",
      "Review the invoices and their open balances, credit memos, and recent activity.",
    ],
    roles: "All roles",
  },
  {
    name: "Tasks",
    path: "/tasks",
    purpose: "Follow-up items that someone needs to act on.",
    steps: [
      "Type a title in New task title and choose Create.",
      "The list shows each task and its current status.",
      "Tasks are internal records. Nothing here posts payments, sends emails, or releases holds.",
    ],
    roles: "All roles can view. Creating tasks depends on your role.",
  },
  {
    name: "Documents",
    path: "/documents",
    purpose: "Source documents, such as remittance notes or emails, that answers can cite.",
    steps: [
      "Choose a .txt or .pdf file, up to 10 MB. The upload starts when you pick it.",
      "Choose View to read the extracted text, or Download original to save the file.",
      "When an investigation mentions an ID that appears in a document, the answer cites that document.",
    ],
    roles: "Upload: Admin and Analyst. View and download: all roles.",
  },
  {
    name: "Import",
    path: "/imports",
    purpose: "Loads a new set of CSV exports as the active data for your business unit.",
    steps: [
      "Set the snapshot date for the data.",
      "Choose the CSV files and select Upload.",
      "A bundle with errors never replaces the active data. Fix the reported rows and upload again.",
    ],
    roles: "Admin only",
  },
  {
    name: "Admin",
    path: "/admin",
    purpose: "Business units, users, and the investigation planner status.",
    steps: [
      "Use Add a user to give someone access, with a role and the business units they can see.",
      "The Users table lists who has access and their roles.",
      "The Planner section shows whether live mode is configured. It never shows the key itself.",
    ],
    roles: "Admin only",
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "What do DEMO and LIVE mean on an answer?",
    a: "DEMO means the question was routed by fixed rules. LIVE means Claude chose the routing. The figures and citations come from the same records in both modes.",
  },
  {
    q: "Can the app change my financial data?",
    a: "No. It reads imported data and records internal tasks. It does not post payments, send emails, or release holds.",
  },
  {
    q: "I can't see a screen I expected.",
    a: "What you can see depends on your role and business-unit access. Ask an admin to check them.",
  },
];

export function HelpPage() {
  return (
    <section className="help">
      <h2>Help and overview</h2>
      <p className="page-subtitle">
        RevenueFlow AI shows where billing and cash are blocked, and answers questions with the records behind each
        answer. This page explains each screen.
      </p>

      <div className="card help-start">
        <h3>Getting started</h3>
        <ol>
          <li>Start on the Dashboard to see the current aging.</li>
          <li>Open Exceptions to see what is blocked, or Customers to look at one account.</li>
          <li>Ask Investigate about anything you want explained, and open the citations to check the records.</li>
          <li>Record follow-ups as Tasks, and attach supporting notes under Documents.</li>
        </ol>
      </div>

      {SCREENS.map((s) => (
        <div key={s.name} className="card help-screen">
          <div className="help-screen__head">
            <h3>
              <a href={s.path}>{s.name}</a>
            </h3>
            <span className="badge">{s.roles}</span>
          </div>
          <p>{s.purpose}</p>
          <ul>
            {s.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
      ))}

      <h3>What this app can and cannot do</h3>
      <div className="card">
        <ul>
          <li>
            <strong>Can:</strong> explain balances, invoice and order status, shipments that are not yet billed,
            order holds, receipts that match or don't match invoices, and customer summaries, each with citations.
          </li>
          <li>
            <strong>Cannot:</strong> change records, approve or pay anything, release holds, send emails or
            messages, or give advice on what to do with a customer.
          </li>
          <li>
            <strong>Personal data:</strong> questions that include personal details (an email, phone number,
            card or bank number, or SSN) are refused before anything is sent to a model. Requests for personal
            details about people are refused too. Use record IDs instead.
          </li>
          <li>
            <strong>Off-topic questions</strong> (weather, general knowledge, writing requests) are declined with
            examples of what to ask.
          </li>
          <li>
            <strong>Live mode</strong> adds Amazon Bedrock Guardrails on top of these rules. It can make mistakes
            in routing, so check the citations before acting on an answer.
          </li>
        </ul>
      </div>

      <h3>Frequently asked questions</h3>
      {FAQ.map((item) => (
        <div key={item.q} className="card help-faq">
          <strong>{item.q}</strong>
          <p>{item.a}</p>
        </div>
      ))}

      <h3>Contact</h3>
      <div className="card">
        <p>Questions, bug reports, and feedback are welcome.</p>
        <ul>
          <li>
            Report a problem or suggest a feature:{" "}
            <a href={ISSUES_URL} target="_blank" rel="noreferrer">GitHub issues</a>
          </li>
          <li>
            Source code and documentation:{" "}
            <a href={REPO_URL} target="_blank" rel="noreferrer">{REPO_URL.replace("https://", "")}</a>
          </li>
          {CONTACT_EMAIL && (
            <li>
              Email: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
            </li>
          )}
        </ul>
        <p className="help-note">This is a portfolio demonstration. It uses synthetic data only.</p>
      </div>
    </section>
  );
}
