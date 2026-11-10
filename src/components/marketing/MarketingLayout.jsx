import { ArrowUpRight, Headphones, Menu, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

export function MarketingHeader({ user, activePage }) {
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  return (
    <header className="marketing-header">
      <div className="marketing-nav-shell">
        <Link className="marketing-brand" to="/" onClick={closeMenu} aria-label="Relay home">
          <span className="marketing-brand-mark"><Headphones size={18} strokeWidth={2.2} /></span>
          <span>relay<span className="marketing-brand-period">.</span></span>
        </Link>
        <button
          className="marketing-menu-toggle"
          type="button"
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? <X size={21} /> : <Menu size={21} />}
        </button>
        <nav className={`marketing-nav ${menuOpen ? "marketing-nav-open" : ""}`} aria-label="Main navigation">
          <a href="/#features" onClick={closeMenu}>Features</a>
          <Link
            className={activePage === "pricing" ? "marketing-nav-active" : ""}
            to="/pricing"
            onClick={closeMenu}
          >
            Pricing
          </Link>
          <a href="/#how-it-works" onClick={closeMenu}>How it works</a>
          <div className="marketing-nav-actions">
            {user ? (
              <Link className="marketing-login-link" to="/dashboard" onClick={closeMenu}>Dashboard</Link>
            ) : (
              <>
                <Link className="marketing-login-link" to="/login" onClick={closeMenu}>Log in</Link>
                <Link className="marketing-button marketing-button-small" to="/register" onClick={closeMenu}>
                  Get started <ArrowUpRight size={15} />
                </Link>
              </>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}

export function MarketingFooter({ user }) {
  return (
    <footer className="marketing-footer">
      <div className="marketing-footer-main">
        <div className="marketing-footer-brand">
          <Link className="marketing-brand" to="/">
            <span className="marketing-brand-mark"><Headphones size={17} strokeWidth={2.2} /></span>
            <span>relay<span className="marketing-brand-period">.</span></span>
          </Link>
          <p>A more thoughtful first hello for every caller.</p>
        </div>
        <div className="marketing-footer-links">
          <div>
            <strong>Explore</strong>
            <a href="/#features">Features</a>
            <Link to="/pricing">Pricing</Link>
            <a href="/#how-it-works">How it works</a>
          </div>
          <div>
            <strong>Your account</strong>
            {user ? <Link to="/dashboard">Dashboard</Link> : <Link to="/login">Log in</Link>}
            <Link to="/register">Register</Link>
          </div>
          <div>
            <strong>Legal</strong>
            <span className="marketing-footer-unavailable">Privacy policy not published</span>
            <span className="marketing-footer-unavailable">Terms not published</span>
          </div>
        </div>
      </div>
      <div className="marketing-footer-bottom">
        <span>© {new Date().getFullYear()} Relay</span>
        <span>Built for better business conversations.</span>
      </div>
    </footer>
  );
}

export function MarketingLayout({ children, user, activePage }) {
  return (
    <div className="marketing-site">
      <MarketingHeader user={user} activePage={activePage} />
      <main>{children}</main>
      <MarketingFooter user={user} />
    </div>
  );
}
