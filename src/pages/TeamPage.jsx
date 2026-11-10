import { Check, MoreHorizontal, Plus, Shield, Trash2, UsersRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useBusiness } from "../business/BusinessContext";
import { Button, Card, EmptyState, ErrorState, Field, LoadingState, PageHeader, StatusBadge } from "../components/ui";
import { ApiError, api, userFacingErrorMessage } from "../lib/api";

export function TeamPage() {
  const { user } = useAuth();
  const { activeBusiness } = useBusiness();
  const [members, setMembers] = useState([]);
  const [viewerRole, setViewerRole] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadMembers = useCallback(async (businessId) => {
    setLoading(true);
    setError("");
    setForbidden(false);
    try {
      const result = await api.members(businessId);
      setMembers(result);
      setViewerRole(result.find((member) => member.user_id === user?.id)?.role ?? null);
    } catch (cause) {
      setMembers([]);
      setViewerRole(null);
      if (cause instanceof ApiError && cause.status === 403) {
        setForbidden(true);
      } else {
        setError(userFacingErrorMessage(cause, "Could not load team members."));
      }
    } finally {
      setLoading(false);
    }
  }, [user?.id]);

  useEffect(() => {
    if (!activeBusiness) {
      setMembers([]);
      setViewerRole(null);
      setLoading(false);
      return;
    }
    void loadMembers(activeBusiness.id);
  }, [activeBusiness, loadMembers]);

  const canManage = viewerRole === "owner" || viewerRole === "admin";
  const isOwner = viewerRole === "owner";

  const addMember = async (event) => {
    event.preventDefault();
    if (!activeBusiness) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.addMember(activeBusiness.id, email.trim(), role);
      await loadMembers(activeBusiness.id);
      setEmail("");
      setRole("member");
      setAdding(false);
      setNotice("Team member added.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not add team member."));
    } finally {
      setBusy(false);
    }
  };

  const updateMember = async (member, nextRole) => {
    if (!activeBusiness || !nextRole || nextRole === member.role) return;
    setError("");
    setNotice("");
    try {
      await api.updateMember(activeBusiness.id, member.user_id, nextRole);
      await loadMembers(activeBusiness.id);
      setNotice(`${member.full_name}’s role was updated.`);
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not update role."));
    }
  };

  const removeMember = async (member) => {
    if (!activeBusiness) return;
    if (!window.confirm(`Remove ${member.full_name} from ${activeBusiness.name}?`)) return;
    setError("");
    setNotice("");
    try {
      await api.removeMember(activeBusiness.id, member.user_id);
      await loadMembers(activeBusiness.id);
      setNotice(`${member.full_name} was removed from the workspace.`);
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not remove team member."));
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={activeBusiness?.name ?? "Workspace"}
        title="Team"
        description="Manage who can access this business workspace."
        action={canManage && (
          <Button onClick={() => { setAdding(true); setError(""); }}>
            <Plus size={16} /> Add member
          </Button>
        )}
      />
      {error && <ErrorState message={error} onRetry={activeBusiness ? () => void loadMembers(activeBusiness.id) : undefined} />}
      {notice && <div className="success-banner"><Check size={16} /> {notice}</div>}
      {adding && canManage && (
        <Card className="form-card">
          <div className="card-heading">
            <div><h2>Add a team member</h2><p>They must already have an account. Invitations by email are not available.</p></div>
            <button className="icon-button" aria-label="Cancel adding member" onClick={() => setAdding(false)}><MoreHorizontal size={17} /></button>
          </div>
          <form className="inline-form team-add-form" onSubmit={(event) => void addMember(event)}>
            <Field label="Account email" id="member-email">
              <input id="member-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required placeholder="teammate@company.com" />
            </Field>
            <Field label="Role" id="member-role">
              <select id="member-role" value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="member">Member — view business settings</option>
                {isOwner && <option value="admin">Admin — manage settings and calls</option>}
              </select>
            </Field>
            <div className="form-actions"><Button type="button" variant="secondary" onClick={() => setAdding(false)}>Cancel</Button><Button type="submit" disabled={busy || !email.trim()}>{busy ? "Adding…" : "Add member"}</Button></div>
          </form>
        </Card>
      )}
      {!activeBusiness ? (
        <Card><EmptyState title="Choose a business" description="Select a business workspace to see its team." /></Card>
      ) : loading ? (
        <Card><LoadingState label="Loading team" /></Card>
      ) : forbidden ? (
        <Card className="permission-card">
          <div className="permission-icon"><Shield size={20} /></div>
          <h2>Team management is restricted</h2>
          <p>Only business owners and admins can view or manage the team for this workspace.</p>
        </Card>
      ) : members.length === 0 ? (
        <Card><EmptyState title="No team members found" description="This workspace has no accessible member records." action={canManage && <Button onClick={() => setAdding(true)}><Plus size={16} /> Add member</Button>} /></Card>
      ) : (
        <Card className="team-card">
          <div className="card-heading">
            <div><h2>Members</h2><p>{members.length} {members.length === 1 ? "person" : "people"} in this workspace</p></div>
            <span className="team-count"><UsersRound size={15} />{members.length}</span>
          </div>
          <div className="team-table-wrap">
            <table className="data-table team-table">
              <thead><tr><th>Member</th><th>Role</th><th>Joined</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.user_id}>
                    <td>
                      <span className="caller-cell">
                        <span className="user-avatar team-avatar">{member.full_name.slice(0, 1).toUpperCase()}</span>
                        <span><strong>{member.full_name}{member.user_id === user?.id && <small className="you-label">You</small>}</strong><small>{member.email}</small></span>
                      </span>
                    </td>
                    <td>
                      {member.role === "owner" || !isOwner ? <StatusBadge status={member.role} /> : (
                        <select
                          className="role-select"
                          aria-label={`Role for ${member.full_name}`}
                          value={member.role}
                          onChange={(event) => void updateMember(member, event.target.value)}
                        >
                          <option value="admin">Admin</option>
                          <option value="member">Member</option>
                        </select>
                      )}
                    </td>
                    <td>{new Date(member.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</td>
                    <td className="team-actions">
                      {canManage && member.role !== "owner" && (
                        <button className="icon-button danger-icon-button" aria-label={`Remove ${member.full_name}`} title="Remove member" onClick={() => void removeMember(member)}><Trash2 size={16} /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="team-permission-note"><Shield size={15} /> Owners manage roles. Admins can add and manage members but cannot grant admin access.</div>
        </Card>
      )}
    </div>
  );
}
