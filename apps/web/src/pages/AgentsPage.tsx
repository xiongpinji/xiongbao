import { useQuery } from "@tanstack/react-query";
import { listRoles, type AgentRole } from "../api";

export default function AgentsPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["roles"], queryFn: listRoles });

  if (isLoading) return <div className="p-6">加载中...</div>;
  if (error) return <div className="p-6 text-red-600">加载失败</div>;

  const roles: AgentRole[] = data ?? [];
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">智能体角色</h1>
      <div className="grid grid-cols-2 gap-3">
        {roles.map((r) => (
          <div key={r.name} className="bg-white border rounded-md p-4">
            <div className="font-medium">{r.name}</div>
            <div className="text-sm text-slate-600 mt-1">{r.description}</div>
            <div className="flex gap-1 mt-2 flex-wrap">
              {r.capabilities.map((c) => (
                <span key={c} className="text-xs bg-slate-100 px-2 py-0.5 rounded">
                  {c}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
