import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import AppErrorBoundary from "./components/AppErrorBoundary";
import { applyStoredTheme } from "./components/ThemeToggle";
import { AuthProvider } from "./hooks/useAuth";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

applyStoredTheme();

async function start() {
  if (import.meta.env.VITE_DEMO_MODE === "true") {
    const { installDemoApi } = await import("./demo/mockApi");
    installDemoApi();
  }

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <AuthProvider>
            <AppErrorBoundary>
              <App />
            </AppErrorBoundary>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}

void start();
