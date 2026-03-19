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
              首页
            </NavLink>
            <NavLink to="/workspace" className="nav__link">
              工作台
            </NavLink>
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
