import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../hooks/useApi";

interface BusinessUnit {
  id: string;
  code: string;
  name: string;
}

interface AppUserRow {
  id: string;
  oidc_subject: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  granted_business_unit_ids: string[];
}

const ROLES = ["admin", "analyst", "approver", "viewer"];

/**
 * Administration screen: business units + application users within the
 * signed-in admin's own organization. Backed by GET/POST/PATCH
 * /api/v1/admin/* (admin-only, every write audited). Creating a user here
 * replaces the manual SQL step previously needed after first boot to grant
 * a logged-in Keycloak identity application-level access.
 */
export function AdminPage() {
  const apiFetch = useApi();
  const queryClient = useQueryClient();

  const businessUnitsQuery = useQuery({
    queryKey: ["admin-business-units"],
    queryFn: () => apiFetch<BusinessUnit[]>("/api/v1/admin/business-units"),
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AppUserRow[]>("/api/v1/admin/users"),
  });

  const [form, setForm] = useState({
    oidc_subject: "",
    email: "",
    display_name: "",
    role: "viewer",
    business_unit_ids: [] as string[],
  });
  const [formError, setFormError] = useState<string | null>(null);

  const createUser = useMutation({
    mutationFn: () =>
      apiFetch<AppUserRow>("/api/v1/admin/users", {
        method: "POST",
        body: JSON.stringify(form),
      }),
    onSuccess: () => {
      setFormError(null);
      setForm({ oidc_subject: "", email: "", display_name: "", role: "viewer", business_unit_ids: [] });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const updateUser = useMutation({
    mutationFn: (vars: { userId: string; role?: string; is_active?: boolean }) =>
      apiFetch<AppUserRow>(`/api/v1/admin/users/${vars.userId}`, {
        method: "PATCH",
        body: JSON.stringify({ role: vars.role, is_active: vars.is_active }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  function toggleBusinessUnit(id: string) {
    setForm((f) => ({
      ...f,
      business_unit_ids: f.business_unit_ids.includes(id)
        ? f.business_unit_ids.filter((x) => x !== id)
        : [...f.business_unit_ids, id],
    }));
  }

  const businessUnitsById = new Map((businessUnitsQuery.data ?? []).map((bu) => [bu.id, bu]));

  return (
    <section>
      <h2>Administration</h2>
      <p className="page-subtitle">Business units and users in your organization. Every change is written to the audit log.</p>

      <h3>Business Units</h3>
      {businessUnitsQuery.isLoading && <p>Loading…</p>}
      {businessUnitsQuery.isError && <p role="alert">Could not load business units.</p>}
      {businessUnitsQuery.data && (
        <ul>
          {businessUnitsQuery.data.map((bu) => (
            <li key={bu.id}>
              {bu.name} ({bu.code})
            </li>
          ))}
        </ul>
      )}

      <h3>Users</h3>
      {usersQuery.isLoading && <p>Loading…</p>}
      {usersQuery.isError && <p role="alert">Could not load users.</p>}
      {usersQuery.data && (
        <div className="card card--flush"><table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Active</th>
              <th>Business units</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {usersQuery.data.map((u) => (
              <tr key={u.id}>
                <td>{u.display_name}</td>
                <td>{u.email}</td>
                <td>
                  <select
                    value={u.role}
                    onChange={(e) => updateUser.mutate({ userId: u.id, role: e.target.value })}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{u.is_active ? "yes" : "no"}</td>
                <td>
                  {u.granted_business_unit_ids.length === 0
                    ? "— (none; admin role sees all)"
                    : u.granted_business_unit_ids
                        .map((id) => businessUnitsById.get(id)?.code ?? id)
                        .join(", ")}
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => updateUser.mutate({ userId: u.id, is_active: !u.is_active })}
                  >
                    {u.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}

      <h3>Add a user</h3>
      <p>
        Grants application-level access to an identity already authenticated by Keycloak —
        provide their Keycloak subject (<code>sub</code> claim), not a password.
      </p>
      <form className="card"
        onSubmit={(e) => {
          e.preventDefault();
          createUser.mutate();
        }}
        style={{ display: "flex", flexDirection: "column", gap: "0.5rem", maxWidth: 420 }}
      >
        <label>
          Keycloak subject (oidc_subject)
          <input
            type="text"
            required
            value={form.oidc_subject}
            onChange={(e) => setForm((f) => ({ ...f, oidc_subject: e.target.value }))}
          />
        </label>
        <label>
          Email
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
          />
        </label>
        <label>
          Display name
          <input
            type="text"
            required
            value={form.display_name}
            onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
          />
        </label>
        <label>
          Role
          <select value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend>Business unit grants (ignored for admin role, which sees the whole org)</legend>
          {(businessUnitsQuery.data ?? []).map((bu) => (
            <label key={bu.id} style={{ display: "block" }}>
              <input
                type="checkbox"
                checked={form.business_unit_ids.includes(bu.id)}
                onChange={() => toggleBusinessUnit(bu.id)}
              />
              {bu.name} ({bu.code})
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={createUser.isPending}>
          {createUser.isPending ? "Creating…" : "Create user"}
        </button>
        {formError && <p role="alert">{formError}</p>}
      </form>
    </section>
  );
}
