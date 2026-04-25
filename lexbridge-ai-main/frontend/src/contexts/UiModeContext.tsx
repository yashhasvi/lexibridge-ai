import { createContext, useContext, useLayoutEffect, useState } from "react";
import type { ReactNode } from "react";

const STORAGE_KEY = "pebble-dev-ui";

interface UiModeContextValue {
  devMode: boolean;
  setDevMode: (value: boolean) => void;
}

const UiModeContext = createContext<UiModeContextValue | undefined>(undefined);

const readStored = (): boolean => {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "true";
};

export const UiModeProvider = ({ children }: { children: ReactNode }) => {
  const [devMode, setDevModeState] = useState(readStored);

  const setDevMode = (value: boolean) => {
    setDevModeState(value);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, value ? "true" : "false");
    }
  };

  useLayoutEffect(() => {
    document.documentElement.dataset.devUi = devMode ? "true" : "false";
  }, [devMode]);

  return (
    <UiModeContext.Provider value={{ devMode, setDevMode }}>
      {children}
    </UiModeContext.Provider>
  );
};

export const useUiMode = () => {
  const ctx = useContext(UiModeContext);
  if (!ctx) throw new Error("useUiMode must be used inside UiModeProvider");
  return ctx;
};
