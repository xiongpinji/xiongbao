import { useEffect, useState } from "react";
import { listMediaModels, type MediaModel } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function ModelSettings() {
  const [models, setModels] = useState<MediaModel[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    listMediaModels()
      .then((items) => setModels(items))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl space-y-6">
      <SectionTitle title="模型设置" description="可用的图像 / 视频 / 音频媒体生成模型。" />
      {loading && <div className="text-sm text-neutral-500">加载中…</div>}
      {error && <div className="text-sm text-red-400">{error}</div>}
      <div className="grid gap-3">
        {models.map((m) => (
          <div key={m.model_id} className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-white">{m.name}</div>
              <div className="font-mono text-xs text-neutral-500">{m.kind}</div>
            </div>
            <div className="mt-1 text-xs text-neutral-500">provider: {m.provider} · modes: {m.modes.join(", ")}</div>
            <div className="mt-2 text-xs text-neutral-400">{m.description}</div>
          </div>
        ))}
        {!loading && !models.length && <div className="rounded-2xl border border-dashed border-neutral-700 p-4 text-sm text-neutral-500">尚未配置媒体模型。</div>}
      </div>
    </div>
  );
}
