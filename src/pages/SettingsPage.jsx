import { ArrowRight, Check, KeyRound, Save, ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button, Card, ErrorState, Field, PageHeader } from "../components/ui";
import { api, userFacingErrorMessage } from "../lib/api";

export function SettingsPage() {
  const { user, updateUser, signOut } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const saveProfile = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await api.updateProfile({
        full_name: name.trim(),
        email: email.trim(),
      });
      updateUser(updated);
      setName(updated.full_name);
      setEmail(updated.email);
      setNotice("Account details saved.");
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not update your account."));
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      signOut();
      navigate("/login", { replace: true });
    } catch (cause) {
      setError(userFacingErrorMessage(cause, "Could not change your password."));
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Personal"
        title="Account settings"
        description="Manage your profile and account security."
      />
      {error && <ErrorState message={error} />}
      {notice && <div className="success-banner"><Check size={16} /> {notice}</div>}
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          <a className="settings-nav-link settings-nav-active" href="#profile"><UserRound size={16} />Profile</a>
          <a className="settings-nav-link" href="#security"><ShieldCheck size={16} />Security</a>
        </nav>
        <div className="settings-panels">
          <Card className="settings-panel" id="profile">
            <div className="settings-panel-heading">
              <span className="settings-panel-icon"><UserRound size={17} /></span>
              <div><h2>Profile</h2><p>Your personal details used in this workspace.</p></div>
            </div>
            <form className="settings-form" onSubmit={(event) => void saveProfile(event)}>
              <Field label="Full name" id="profile-name">
                <input id="profile-name" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} />
              </Field>
              <Field label="Email address" id="profile-email" hint="Used to sign in to your account.">
                <input id="profile-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
              </Field>
              <div className="settings-form-footer">
                <span>Profile updates are saved to your account.</span>
                <Button type="submit" disabled={busy || !name.trim() || !email.trim()}><Save size={15} />{busy ? "Saving…" : "Save profile"}</Button>
              </div>
            </form>
          </Card>
          <Card className="settings-panel" id="security">
            <div className="settings-panel-heading">
              <span className="settings-panel-icon"><KeyRound size={17} /></span>
              <div><h2>Password & security</h2><p>Change your password to keep your account secure.</p></div>
            </div>
            <form className="settings-form" onSubmit={(event) => void changePassword(event)}>
              <Field label="Current password" id="current-password">
                <input id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required maxLength={128} />
              </Field>
              <Field label="New password" id="new-password" hint="Use at least 8 characters.">
                <input id="new-password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required minLength={8} maxLength={128} />
              </Field>
              <Field label="Confirm new password" id="confirm-new-password">
                <input id="confirm-new-password" type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required minLength={8} maxLength={128} />
              </Field>
              <div className="settings-form-footer">
                <span>You’ll need to sign in again after changing your password.</span>
                <Button type="submit" variant="secondary" disabled={busy || !currentPassword || newPassword.length < 8 || !confirmPassword}>
                  <KeyRound size={15} />{busy ? "Updating…" : "Update password"}
                </Button>
              </div>
            </form>
          </Card>
          <Card className="settings-panel settings-business-panel">
            <div className="settings-panel-heading">
              <span className="settings-panel-icon"><ShieldCheck size={17} /></span>
              <div><h2>Workspace settings</h2><p>Business configuration and team access are managed separately.</p></div>
            </div>
            <Link to="/businesses" className="settings-link-row"><span>Manage businesses</span><ArrowRight size={16} /></Link>
            <Link to="/team" className="settings-link-row"><span>Manage team members</span><ArrowRight size={16} /></Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
