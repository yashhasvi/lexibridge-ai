// src/components/Sidebar.tsx
import { useTheme } from "../contexts/ThemeContext";
import { useUiMode } from "../contexts/UiModeContext";

export const Sidebar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const { devMode, setDevMode } = useUiMode();

  return (
    <aside className="sidebar">
      <div className="sidebar__avatar" title="Assistant">
        P
      </div>

      <div className="sidebar__spacer" />

      <button
        type="button"
        className={`sidebar__dev-toggle ${devMode ? "sidebar__dev-toggle--on" : ""}`}
        onClick={() => setDevMode(!devMode)}
        aria-pressed={devMode}
        aria-label={devMode ? "Switch to customer view" : "Switch to developer view"}
        title={devMode ? "Customer mode" : "Dev mode: timings, raw diagnostics"}
      >
        <WrenchIcon />
      </button>

      <button
        type="button"
        className="sidebar__theme-toggle"
        onClick={toggleTheme}
        aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      >
        {theme === "dark" ? <SunIcon /> : <MoonIcon />}
      </button>

      {devMode && <div className="sidebar__rail">dev · v2.4</div>}
    </aside>
  );
};

const WrenchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </svg>
);

const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);
