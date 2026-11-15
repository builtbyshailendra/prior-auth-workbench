"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Role } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";
import { useSession } from "../../session";

type User = { username: string; display_name: string; role: Role; active: boolean };

export default function UsersPage() {
  const { me } = useSession();
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({ username: "", display_name: "", role: "nurse_reviewer", password: "" });
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    try {
      setUsers(await api<User[]>("/api/users"));
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Couldn't load users");
    }
  }, []);

  useEffect(() => {
    if (me?.role === "admin") void load();
  }, [me, load]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    try {
      await api("/api/users", { method: "POST", body: form });
      setForm({ username: "", display_name: "", role: "nurse_reviewer", password: "" });
      setMessage("User created.");
      await load();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Couldn't create the user");
    }
  }

  async function deactivate(username: string) {
    try {
      await api(`/api/users/${username}/deactivate`, { method: "POST", body: {} });
      await load();
    } catch (e) {
      setMessage(e instanceof ApiError ? e.message : "Couldn't deactivate");
    }
  }

  if (!me) return null;
  if (me.role !== "admin") return <p className="card">Only admins manage users.</p>;

  return (
    <div className="two-columns">
      <form className="card" onSubmit={create}>
        <h2>Add a person</h2>
        <label>
          Username
          <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        </label>
        <label>
          Name
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
        </label>
        <label>
          Role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {Object.entries(ROLE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Temporary password (12+ characters)
          <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </label>
        <button type="submit">Add</button>
        {message && <p className="small">{message}</p>}
      </form>
      <section className="card">
        <h2>Staff</h2>
        <table className="queue">
          <tbody>
            {users.map((u) => (
              <tr key={u.username}>
                <td>
                  {u.display_name}
                  <div className="muted small">{u.username}</div>
                </td>
                <td>{ROLE_LABEL[u.role]}</td>
                <td>
                  {u.active ? (
                    u.username !== me.username && (
                      <button type="button" className="link" onClick={() => deactivate(u.username)}>
                        Deactivate
                      </button>
                    )
                  ) : (
                    <span className="muted">Deactivated</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
