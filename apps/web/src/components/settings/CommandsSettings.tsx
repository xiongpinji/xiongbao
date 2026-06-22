import { useEffect, useState } from "react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

export default function CommandsSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSystemCapabilities()
      .then(setCaps)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="命令" description="工作区内置的 slash 命令。" />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="space-y-2">
        {(caps?.commands ?? []).map((cmd) => (
          <div key={cmd.name} className="flex items-center justify-between rounded-2xl border border-neutral-800 bg-neutral-900 px-4 py-2.5">
            <span className="font-mono text-sm text-white">{cmd.name}</span>
            <span className="text-xs text-neutral-500">{cmd.description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
