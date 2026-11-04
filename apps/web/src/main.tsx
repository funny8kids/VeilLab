import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import { AppProvider } from "./state/AppContext";
import "./styles.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("VeilPool root element is missing.");
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <AppProvider>
          <App />
        </AppProvider>
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>,
);
