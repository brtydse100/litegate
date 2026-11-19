import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}
interface State {
  failed: boolean;
}

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("LiteGate interface error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="flex min-h-screen items-center justify-center bg-card p-6 text-center">
        <div className="w-full max-w-md rounded-2xl border border-sand/40 bg-card p-6 shadow-2xl">
          <AlertTriangle size={30} className="mx-auto text-sand-ink" />
          <h1 className="mt-4 text-lg font-semibold text-ink">
            This page could not be displayed
          </h1>
          <p className="mt-2 text-sm leading-6 text-ink-3">
            Your data was not changed. Reload LiteGate to retry the request and
            restore the interface.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-blue px-4 py-2.5 text-sm font-semibold text-paper hover:brightness-110"
          >
            <RefreshCw size={15} /> Reload LiteGate
          </button>
        </div>
      </main>
    );
  }
}
