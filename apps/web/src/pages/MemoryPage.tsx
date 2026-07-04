import { Link } from "react-router-dom";

const previewMessage = "辅助模式：当前入口主要用于整理检索意图与跳转索引配置，不直接展示真实知识库命中结果。";
const assistantMessage = "真实结果仍需进入索引库或后端检索链路查看。";

export default function MemoryPage() {
  return (
    <div className="flex min-h-full items-center justify-center bg-neutral-950 p-8 text-neutral-100">
      <div className="max-w-xl rounded-3xl border border-neutral-800 bg-neutral-900 p-8 shadow-2xl shadow-black/20">
        <div className="text-sm font-medium text-neutral-500">入口已迁移</div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">知识库已移入索引库</h1>
        <p className="mt-3 text-sm leading-6 text-neutral-400">
          知识库和记忆检索现在统一放在设置页的索引库中管理，便于和开源发现、文档索引一起配置。
        </p>
        <div className="mt-4 rounded-2xl border border-sky-500/20 bg-sky-500/10 px-4 py-3 text-sm leading-6 text-sky-100">
          {previewMessage}
        </div>
        <p className="mt-4 text-sm leading-6 text-neutral-300">{assistantMessage}</p>
        <Link
          to="/settings?section=index&tab=knowledge"
          className="mt-6 inline-flex rounded-xl bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-white active:scale-[0.98]"
        >
          打开设置中的知识库
        </Link>
      </div>
    </div>
  );
}
