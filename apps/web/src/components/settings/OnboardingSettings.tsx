import { useEffect, useState } from "react";
import { getSystemCapabilities, type SystemCapabilities } from "../../api";
import { SectionTitle } from "./GeneralSettings";

const fallback = [
  "从工作区创建任务或打开项目。",
  "在短剧工厂自由画布中右键添加流程节点。",
  "运行画布后通过节点状态和 timeline 查看执行进度。",
  "剪辑和导出通过短剧工厂中的剪辑节点、导出节点完成。",
];

export default function OnboardingSettings() {
  const [caps, setCaps] = useState<SystemCapabilities | null>(null);
  useEffect(() => {
    getSystemCapabilities().then(setCaps).catch(() => undefined);
  }, []);
  const steps = caps?.onboarding?.length ? caps.onboarding : fallback;
  return (
    <div className="max-w-3xl space-y-6">
      <SectionTitle title="引导" description="工作区与短剧工厂的快速上手步骤。" />
      <div className="space-y-3">
        {steps.map((item, index) => (
          <div key={item} className="flex gap-3 rounded-2xl border border-neutral-800 bg-neutral-900 p-4 text-sm text-neutral-300">
            <span className="font-mono text-neutral-500">{String(index + 1).padStart(2, "0")}</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
