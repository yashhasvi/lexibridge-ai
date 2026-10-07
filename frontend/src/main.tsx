import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "./bones/registry";
import App from "./App.tsx";
import { ThemeProvider } from "./contexts/ThemeContext";
import { UiModeProvider } from "./contexts/UiModeContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <UiModeProvider>
        <App />
      </UiModeProvider>
    </ThemeProvider>
  </StrictMode>
);