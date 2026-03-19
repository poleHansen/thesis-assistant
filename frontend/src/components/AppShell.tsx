import type { PropsWithChildren } from "react";
import { Link, NavLink } from "react-router-dom";

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar__inner">
          <Link to="/" className="brand">
            <span className="brand__mark">TA</span>
            <span className="brand__text">Thesis Assistant</span>
          </Link>
          <nav className="nav">
            <NavLink to="/" className="nav__link">
              Home
            </NavLink>
            <NavLink to="/workspace" className="nav__link">
              Workspace
            </NavLink>
            <NavLink to="/settings" className="nav__link">
              Settings
            </NavLink>
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
