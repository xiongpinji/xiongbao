import { Link } from "react-router-dom";

export default function ExcludedModulePage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <h1 className="text-xl font-semibold text-white">当前 Web/API 发布不包含此模块</h1>
      <p className="max-w-xl text-sm text-neutral-400">
        短剧能力由独立项目运行，稳定后再按集成规格接入 X-Agent。
      </p>
      <Link
        className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-black"
        to="/chat"
      >
        返回对话
      </Link>
    </div>
  );
}
