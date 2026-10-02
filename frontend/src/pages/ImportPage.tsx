import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../hooks/useApi";
import { ApiError } from "../api/client";

interface ImportJobResponse {
  id: string;
  status: string;
  snapshot_date: string;
  error_code: string | null;
  validation_summary: { error_count: number; errors: unknown[] } | null;
  activated_dataset_version_id: string | null;
}

/**
 * Upload a CSV bundle to POST /api/v1/imports and poll its status until the
 * worker finishes. Real upload + real polling against the real backend —
 * no mocked progress bar.
 */
export function ImportPage({ businessUnitId }: { businessUnitId: string }) {
  const apiFetch = useApi();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<FileList | null>(null);
  const [snapshotDate, setSnapshotDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const jobQuery = useQuery({
    queryKey: ["import-job", jobId],
    queryFn: () => apiFetch<ImportJobResponse>(`/api/v1/imports/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "activated" || status === "rejected" || status === "failed" ? false : 1000;
    },
  });

  async function handleUpload() {
    if (!files || files.length === 0) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      for (const file of Array.from(files)) {
        formData.append("files", file);
      }
      const idempotencyKey = `ui-upload-${Date.now()}`;
      const params = new URLSearchParams({
        business_unit_id: businessUnitId,
        idempotency_key: idempotencyKey,
        snapshot_date: snapshotDate,
      });
      const result = await apiFetch<ImportJobResponse>(`/api/v1/imports?${params}`, {
        method: "POST",
        body: formData,
      });
      setJobId(result.id);
      void queryClient.invalidateQueries({ queryKey: ["aging-summary"] });
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section>
      <h2>Import CSV Bundle</h2>
      <label>
        Snapshot date{" "}
        <input
          type="date"
          value={snapshotDate}
          onChange={(e) => setSnapshotDate(e.target.value)}
        />
      </label>
      <br />
      <input
        type="file"
        multiple
        accept=".csv"
        onChange={(e) => setFiles(e.target.files)}
      />
      <br />
      <button onClick={handleUpload} disabled={isUploading || !files || files.length === 0}>
        {isUploading ? "Uploading…" : "Upload"}
      </button>

      {uploadError && <p role="alert">{uploadError}</p>}

      {jobId && jobQuery.data && (
        <div>
          <p>Job {jobId}: {jobQuery.data.status}</p>
          {jobQuery.data.status === "activated" && (
            <p>Activated as dataset {jobQuery.data.activated_dataset_version_id}.</p>
          )}
          {jobQuery.data.status === "rejected" && jobQuery.data.validation_summary && (
            <div role="alert">
              <p>{jobQuery.data.validation_summary.error_count} validation error(s):</p>
              <ul>
                {jobQuery.data.validation_summary.errors.slice(0, 10).map((e, i) => (
                  <li key={i}>{JSON.stringify(e)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
