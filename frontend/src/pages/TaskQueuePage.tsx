import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe } from "../auth/MeContext";
import { useApi } from "../hooks/useApi";

interface Task {
  id: string;
  title: string;
  description: string;
  status: string;
  assignee_user_id: string | null;
  related_record_type: string | null;
  related_record_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

const NEXT_STATUSES: Record<string, string[]> = {
  proposed: ["approved", "rejected", "in_progress"],
  in_progress: ["resolved", "rejected"],
  approved: ["in_progress", "resolved"],
};

/**
 * Internal follow-up task queue. Approve/reject/resolve only record a
 * decision -- intent.md: never implies an ERP write, payment, or email.
 */
export function TaskQueuePage() {
  const apiFetch = useApi();
  const queryClient = useQueryClient();
  const me = useMe();
  const businessUnitId = me.business_units[0].id;
  const [title, setTitle] = useState("");

  const tasksQuery = useQuery({
    queryKey: ["tasks", businessUnitId],
    queryFn: () => apiFetch<Task[]>(`/api/v1/tasks?business_unit_id=${businessUnitId}`),
  });

  const createMutation = useMutation({
    mutationFn: (newTitle: string) =>
      apiFetch<Task>("/api/v1/tasks", {
        method: "POST",
        body: JSON.stringify({ business_unit_id: businessUnitId, title: newTitle }),
      }),
    onSuccess: () => {
      setTitle("");
      void queryClient.invalidateQueries({ queryKey: ["tasks", businessUnitId] });
    },
  });

  const transitionMutation = useMutation({
    mutationFn: ({ taskId, newStatus }: { taskId: string; newStatus: string }) =>
      apiFetch<Task>(`/api/v1/tasks/${taskId}/transition`, {
        method: "POST",
        body: JSON.stringify({ new_status: newStatus }),
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["tasks", businessUnitId] }),
  });

  return (
    <section>
      <h2>Follow-up Tasks</h2>
      <p>Approving or resolving a task records an internal decision only — it never posts cash, releases a hold, or sends an email.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) createMutation.mutate(title.trim());
        }}
      >
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="New task title"
        />
        <button type="submit" disabled={createMutation.isPending}>Create</button>
      </form>

      {tasksQuery.isLoading && <p>Loading…</p>}
      {tasksQuery.isError && <p role="alert">Could not load tasks.</p>}
      {tasksQuery.data && tasksQuery.data.length === 0 && <p>No tasks yet.</p>}
      {tasksQuery.data && tasksQuery.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tasksQuery.data.map((task) => (
              <tr key={task.id}>
                <td>{task.title}</td>
                <td>{task.status}</td>
                <td>{new Date(task.created_at).toLocaleString()}</td>
                <td>
                  {(NEXT_STATUSES[task.status] ?? []).map((next) => (
                    <button
                      key={next}
                      onClick={() => transitionMutation.mutate({ taskId: task.id, newStatus: next })}
                      disabled={transitionMutation.isPending}
                    >
                      {next}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
