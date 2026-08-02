/**
 * 全局错误边界组件。
 *
 * 功能：
 * - 捕获子组件树中的 JS 异常，展示友好降级 UI
 * - 提供"重试"按钮重置错误状态
 * - 开发模式下展示错误堆栈
 * - 上报错误到全局 store（可对接 Sentry 等）
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });

    // 上报（生产环境可对接 Sentry / 自建日志）
    if (import.meta.env.PROD) {
      try {
        fetch("/api/v1/system/client-errors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: error.message,
            stack: error.stack?.slice(0, 2000),
            componentStack: errorInfo.componentStack?.slice(0, 2000),
            url: window.location.href,
            timestamp: Date.now(),
          }),
        }).catch(() => {});
      } catch {
        // 静默
      }
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback;
    }

    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="text-4xl">⚠️</div>
        <h2 className="text-lg font-semibold text-neutral-200">
          页面出现异常
        </h2>
        <p className="max-w-md text-sm text-neutral-400">
          {this.state.error?.message || "未知错误"}
        </p>

        {import.meta.env.DEV && this.state.errorInfo && (
          <pre className="mt-2 max-h-48 w-full max-w-lg overflow-auto rounded-lg bg-neutral-900 p-4 text-left text-xs text-red-400">
            {this.state.error?.stack}
            {"\n\nComponent Stack:"}
            {this.state.errorInfo.componentStack}
          </pre>
        )}

        <button
          onClick={this.handleReset}
          className="mt-2 rounded-lg bg-[#d6ad62] px-4 py-2 text-sm font-medium text-black transition hover:bg-[#c49b52]"
        >
          重试
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
