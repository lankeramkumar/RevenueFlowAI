import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "react-oidc-context";
import { apiToken } from "../auth/apiToken";
import { useMe } from "../auth/MeContext";
import { ApiError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { cellStyle, numericCellStyle, tableStyle } from "../ui/tableStyles";

interface DocumentSummary {
  id: string;
  filename: string;
  content_type: string;
  byte_size: number;
  sha256: string;
  created_at: string;
}

interface DocumentDetail extends DocumentSummary {
  text: string;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function DocumentsPage() {
  const apiFetch = useApi();
  const me = useMe();
  const auth = useAuth();
  const queryClient = useQueryClient();
  const businessUnitId = me.business_units[0].id;
  const canUpload = me.role === "admin" || me.role === "analyst";
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["documents", businessUnitId],
    queryFn: () => apiFetch<DocumentSummary[]>(`/api/v1/documents?business_unit_id=${businessUnitId}`),
  });

  const detail = useQuery({
    queryKey: ["document", selected],
    queryFn: () => apiFetch<DocumentDetail>(`/api/v1/documents/${selected}`),
    enabled: !!selected,
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("business_unit_id", businessUnitId);
      form.append("file", file);
      const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
        method: "POST",
        headers: apiToken(auth.user) ? { Authorization: `Bearer ${apiToken(auth.user)}` } : {},
        body: form,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new ApiError(response.status, body?.detail?.error_code ?? "upload_failed", body?.detail?.message ?? "Upload failed.");
      }
      return (await response.json()) as DocumentSummary;
    },
    onSuccess: (doc) => {
      setError(null);
      setSelected(doc.id);
      queryClient.invalidateQueries({ queryKey: ["documents", businessUnitId] });
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <section>
      <h2>Documents</h2>
      <p className="page-subtitle">
        Source documents (text or PDF) that can be cited as evidence. Each document is stored with its hash and
        the text extracted from it.
      </p>

      {canUpload && (
        <div className="card" style={{ marginBottom: "1rem" }}>
          <label>
            Upload a .txt or .pdf file (up to 10 MB)
            <input
              type="file"
              accept=".txt,.pdf,text/plain,application/pdf"
              disabled={upload.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload.mutate(file);
                e.target.value = "";
              }}
            />
          </label>
          {upload.isPending && <p>Uploading…</p>}
          {error && <p role="alert">{error}</p>}
        </div>
      )}

      {list.isLoading && <p>Loading…</p>}
      {list.isError && <p role="alert">Could not load documents.</p>}
      {list.data && list.data.length === 0 && <p className="empty-state">No documents yet.</p>}
      {list.data && list.data.length > 0 && (
        <div className="card card--flush">
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={cellStyle}>File</th>
                <th style={cellStyle}>Type</th>
                <th style={{ ...cellStyle, textAlign: "right" }}>Size</th>
                <th style={cellStyle}>Uploaded</th>
                <th style={cellStyle} />
              </tr>
            </thead>
            <tbody>
              {list.data.map((doc) => (
                <tr key={doc.id}>
                  <td style={cellStyle}>{doc.filename}</td>
                  <td style={cellStyle}>{doc.content_type}</td>
                  <td style={numericCellStyle}>{(doc.byte_size / 1024).toFixed(1)} KB</td>
                  <td style={cellStyle}>{new Date(doc.created_at).toLocaleString()}</td>
                  <td style={cellStyle}>
                    <button type="button" onClick={() => setSelected(doc.id)}>View</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && detail.data && (
        <div className="card" style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>{detail.data.filename}</h3>
          <p className="page-subtitle">SHA-256 {detail.data.sha256}</p>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", margin: 0 }}>{detail.data.text}</pre>
          <button type="button" onClick={() => void download(detail.data.id, detail.data.filename, apiToken(auth.user))}>Download original</button>
        </div>
      )}
    </section>
  );
}

async function download(id: string, filename: string, token?: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/${id}/content`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) return;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
