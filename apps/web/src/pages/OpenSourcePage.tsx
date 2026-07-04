import { Link } from "react-router-dom";

const previewMessage = "预览态：当前入口优先整理开源比选目标与接入策略，不直接返回实时仓库搜索结果。";
const assistantMessage = "真实候选仓库仍需进入开源发现链路进一步检索。";

export default function OpenSourcePage() {
  return (
    <div className="flex min-h-full items-center justify-center bg-neutral-950 p-8 text-neutral-100">
      <div className="max-w-xl rounded-3xl border border-neutral-800 bg-neutral-900 p-8 shadow-2xl shadow-black/20">
        <div className="text-sm font-medium text-neutral-500">入口已迁移</div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">开源发现已移入索引库</h1>
        <p className="mt-3 text-sm leading-6 text-neutral-400">
          开源发现现在作为工作台能力配置的一部分，统一放在设置页的索引库中管理。
        </p>
        <div className="mt-4 rounded-2xl border border-violet-500/20 bg-violet-500/10 px-4 py-3 text-sm leading-6 text-violet-100">
          {previewMessage}
        </div>
        <p className="mt-4 text-sm leading-6 text-neutral-300">{assistantMessage}</p>
        <Link
          to="/settings?section=index&tab=open-source"
          className="mt-6 inline-flex rounded-xl bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-950 hover:bg-white active:scale-[0.98]"
        >
          打开设置中的开源发现
        </Link>
      </div>
    </div>
  );
}
