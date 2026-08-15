import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { I18nProvider } from "./i18n";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ShellStoreProvider } from "./shell/useShellStore";
import { initializeApiClient } from "./api/client";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const rootElement = document.getElementById("root")!;

async function bootstrap() {
  await initializeApiClient();
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <ErrorBoundary>
        <I18nProvider>
          <QueryClientProvider client={queryClient}>
            <ShellStoreProvider>
              <BrowserRouter>
                <App />
              </BrowserRouter>
            </ShellStoreProvider>
          </QueryClientProvider>
        </I18nProvider>
      </ErrorBoundary>
    </React.StrictMode>
  );
}

void bootstrap().catch((error: unknown) => {
  rootElement.textContent = error instanceof Error ? error.message : "桌面后端初始化失败";
});
