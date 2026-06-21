import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  hasError: boolean;
  message: string;
}

/** 全局错误边界：捕获子树渲染异常，显示友好错误态。 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 max-w-md mx-auto text-center">
          <div className="text-red-600 font-medium mb-2">页面出错了</div>
          <div className="text-sm text-slate-500 mb-4">{this.state.message}</div>
          <button
            className="px-4 py-2 bg-brand-600 text-white rounded text-sm"
            onClick={() => this.setState({ hasError: false, message: "" })}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
