import { useEffect, useState } from "react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function CodePreviewSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemCapabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const preview = caps?.code_preview;

  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="代码预览" description="工作台代码预览的当前默认行为。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="grid gap-3 md:grid-cols-3">
        <KV label="主题" value={preview?.default_theme} />
        <KV label="缩进" value={preview ? `${preview.tab_size} spaces` : undefined} />
        <KV label="Diff 模式" value={preview?.diff_mode} />
      </div>
    </div>
  );
}

function KV({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-2xl border border-neutral-800 bg-neutral-900 p-4">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-2 font-mono text-sm text-white">{value ?? "—"}</div>
    </div>
  );
}
