import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Trash2, UserPlus, XCircle } from "lucide-react";
import { StatLine } from "./ui";
import { api } from "../../api/client";
import { useConfirm } from "../../hooks/useConfirm";

interface TenantUser {
  user_id: string;
  tenant_id: string;
  roles: string[];
  email: string;
}

interface ApiKeyView {
  key_id: string;
  name: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  revoked: boolean;
}

interface TenantInfo {
  tenant_id: string;
  user_count: number;
  api_key_count: number;
  roles_available: string[];
}

export default function TeamSettings() {
  const [info, setInfo] = useState<TenantInfo | null>(null);
  const [users, setUsers] = useState<TenantUser[]>([]);
  const [keys, setKeys] = useState<ApiKeyView[]>([]);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const errTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 创建用户表单
  const [showUserForm, setShowUserForm] = useState(false);
  const [uName, setUName] = useState("");
  const [uPass, setUPass] = useState("");
  const [uRole, setURole] = useState("member");
  // 创建 Key 表单
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [kName, setKName] = useState("");
  const [kScopes, setKScopes] = useState("*");
  const { confirm, ConfirmDialog } = useConfirm();

  const showError = (msg: string) => {
    setError(msg);
    if (errTimer.current) clearTimeout(errTimer.current);
    errTimer.current = setTimeout(() => setError(""), 6000);
  };

  const refresh = useCallback(async () => {
    try {
      const [infoR, usersR, keysR] = await Promise.all([
        api.get("/tenants/info"),
        api.get("/tenants/users"),
        api.get("/tenants/api-keys"),
      ]);
      setInfo(infoR.data);
      setUsers(usersR.data.users);
      setKeys(keysR.data.keys);
      setError("");
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const createUser = async () => {
    if (!uName.trim() || !uPass.trim()) return;
    setSubmitting(true);
    try {
      await api.post("/tenants/users", { username: uName.trim(), password: uPass, roles: [uRole] });
      setShowUserForm(false);
      setUName(""); setUPass(""); setURole("member");
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteUser = async (userId: string) => {
    const ok = await confirm({ title: "移除用户", message: "确定从团队中移除该用户？此操作不可撤销。", danger: true, confirmText: "移除" });
    if (!ok) return;
    try {
      await api.delete(`/tenants/users/${userId}`);
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "删除失败");
    }
  };

  const changeRole = async (userId: string, roles: string[]) => {
    try {
      await api.put(`/tenants/users/${userId}/roles`, { roles });
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "修改失败");
    }
  };

  const createKey = async () => {
    if (!kName.trim()) return;
    setSubmitting(true);
    try {
      const resp = await api.post("/tenants/api-keys", {
        name: kName.trim(),
        scopes: kScopes.split(",").map((s) => s.trim()),
      });
      setNewKey(resp.data.raw_key);
      setShowKeyForm(false);
      setKName(""); setKScopes("*");
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    const ok = await confirm({ title: "吊销密钥", message: "吊销后使用该密钥的集成将立即失效，确定继续？", danger: true, confirmText: "吊销" });
    if (!ok) return;
    try {
      await api.post(`/tenants/api-keys/${keyId}/revoke`);
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "吊销失败");
    }
  };

  const deleteKey = async (keyId: string) => {
    const ok = await confirm({ title: "删除密钥", message: "确定永久删除该 API Key？", danger: true, confirmText: "删除" });
    if (!ok) return;
    try {
      await api.delete(`/tenants/api-keys/${keyId}`);
      refresh();
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* 新 Key 一次性提示 */}
      {newKey && (
        <div className="border-b border-white/[0.05] py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-neutral-200">API Key 已创建（仅显示一次）</span>
            <button onClick={() => setNewKey(null)} aria-label="关闭提示" className="text-neutral-400 hover:text-white"><XCircle size={16} /></button>
          </div>
          <code className="mt-2 block break-all rounded-lg bg-black/40 px-3 py-2 text-xs text-green-300">{newKey}</code>
        </div>
      )}

      {/* 租户概览 */}
      {info && (
        <StatLine
          items={[
            { label: "租户", value: info.tenant_id },
            { label: "用户", value: info.user_count },
            { label: "API Keys", value: info.api_key_count },
          ]}
        />
      )}

      {/* 用户管理 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">用户管理</h3>
          <button
            onClick={() => setShowUserForm(!showUserForm)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100"
          >
            <UserPlus size={15} /> 添加用户
          </button>
        </div>

        {showUserForm && (
          <div className="mb-4 flex flex-wrap items-end gap-3 py-2">
            <div>
              <label className="mb-1 block text-xs text-neutral-400">用户名</label>
              <input value={uName} onChange={(e) => setUName(e.target.value)} className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]" placeholder="username" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">密码</label>
              <input type="password" value={uPass} onChange={(e) => setUPass(e.target.value)} className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]" placeholder="••••••" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">角色</label>
              <select value={uRole} onChange={(e) => setURole(e.target.value)} className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]">
                <option value="admin">admin</option>
                <option value="member">member</option>
                <option value="viewer">viewer</option>
              </select>
            </div>
            <button onClick={createUser} disabled={submitting || !uName.trim() || !uPass.trim()} className="rounded-lg bg-neutral-100 px-4 py-1.5 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40">{submitting ? "创建中…" : "创建"}</button>
          </div>
        )}

        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.user_id} className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-4 py-3">
              <div>
                <span className="text-sm font-medium text-white">{u.user_id}</span>
                {u.email && <span className="ml-2 text-xs text-neutral-500">{u.email}</span>}
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={u.roles[0] || "member"}
                  onChange={(e) => changeRole(u.user_id, [e.target.value])}
                  className="rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-xs text-white outline-none"
                >
                  <option value="admin">admin</option>
                  <option value="member">member</option>
                  <option value="viewer">viewer</option>
                </select>
                <button onClick={() => deleteUser(u.user_id)} className="text-neutral-500 transition hover:text-red-400">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* API Key 管理 */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">API Key</h3>
          <button
            onClick={() => setShowKeyForm(!showKeyForm)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-neutral-300 transition hover:border-white/20 hover:text-neutral-100"
          >
            <Plus size={15} /> 创建 Key
          </button>
        </div>

        {showKeyForm && (
          <div className="mb-4 flex flex-wrap items-end gap-3 py-2">
            <div>
              <label className="mb-1 block text-xs text-neutral-400">名称</label>
              <input value={kName} onChange={(e) => setKName(e.target.value)} className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]" placeholder="my-integration" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-neutral-400">Scopes（逗号分隔）</label>
              <input value={kScopes} onChange={(e) => setKScopes(e.target.value)} className="rounded-md border border-white/[0.08] bg-white/[0.02] px-3 py-1.5 text-[13px] text-neutral-100 outline-none transition focus:border-white/[0.2]" placeholder="*" />
            </div>
            <button onClick={createKey} disabled={submitting || !kName.trim()} className="rounded-lg bg-neutral-100 px-4 py-1.5 text-sm font-medium text-black transition hover:bg-white disabled:opacity-40">{submitting ? "创建中…" : "创建"}</button>
          </div>
        )}

        <div className="space-y-2">
          {keys.map((k) => (
            <div key={k.key_id} className={`flex items-center justify-between rounded-lg border px-4 py-3 ${k.revoked ? "border-red-500/20 bg-red-500/5 opacity-60" : "border-white/[0.06] bg-white/[0.02]"}`}>
              <div>
                <span className="text-sm font-medium text-white">{k.name}</span>
                <span className="ml-2 text-xs text-neutral-500">{k.scopes.join(", ")}</span>
                {k.revoked && <span className="ml-2 rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-300">已吊销</span>}
              </div>
              <div className="flex items-center gap-2">
                {!k.revoked && (
                  <button onClick={() => revokeKey(k.key_id)} className="text-xs text-neutral-400 transition hover:text-amber-400">吊销</button>
                )}
                <button onClick={() => deleteKey(k.key_id)} className="text-neutral-500 transition hover:text-red-400">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
          {keys.length === 0 && <p className="text-sm text-neutral-500">暂无 API Key</p>}
        </div>
      </section>
      <ConfirmDialog />
    </div>
  );
}
