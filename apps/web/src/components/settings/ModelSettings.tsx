import { useCallback, useEffect, useState } from "react";
import { Brain, Check, Key, Loader2, RefreshCw, Server } from "lucide-react";
import {
  getLLMConfig,
  updateLLMConfig,
  listMediaModels,
  type LLMConfig,
  type LLMConfigUpdate,
  type MediaModel,
} from "../../api";
import { SectionTitle } from "./GeneralSettings";
import { useUnsavedChangesWarning } from "../../hooks/useUnsavedChangesWarning";

/* ---------- 通用小组件 ---------- */

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-neutral-300">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-neutral-500">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-sm text-neutral-100 placeholder-neutral-600 outline-none transition focus:border-white/[0.16]";

function KeyStatus({ has, label }: { has: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${
        has
          ? "bg-emerald-500/15 text-emerald-400"
          : "bg-neutral-700/50 text-neutral-500"
      }`}
    >
      <Key size={10} />
      {label}: {has ? "已配置" : "未设置"}
    </span>
  );
}

/* ---------- 主组件 ---------- */

export default function ModelSettings() {
  // LLM 配置
  const [cfg, setCfg] = useState<LLMConfig | null>(null);
  const [form, setForm] = useState<LLMConfigUpdate>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  // 未保存变更标记：用户编辑表单后置 true，加载/保存成功后置 false
  const [dirty, setDirty] = useState(false);

  // 媒体模型
  const [mediaModels, setMediaModels] = useState<MediaModel[]>([]);

  const load = useCallback(async () => {
    setError("");
    try {
      const [llmCfg, media] = await Promise.all([getLLMConfig(), listMediaModels()]);
      setCfg(llmCfg);
      setMediaModels(media);
      setForm({
        default_model: llmCfg.default_model,
        fallback_models: llmCfg.fallback_models,
        proxy_url: llmCfg.proxy_url,
        ollama_base_url: llmCfg.ollama_base_url,
        ollama_model: llmCfg.ollama_model,
        request_timeout_seconds: llmCfg.request_timeout_seconds,
      });
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载配置失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 有未保存配置时，拦截浏览器刷新/关闭，避免编辑内容静默丢失
  useUnsavedChangesWarning(dirty);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      // 只提交非空字段
      const payload: LLMConfigUpdate = {};
      if (form.default_model) payload.default_model = form.default_model;
      if (form.fallback_models?.length) payload.fallback_models = form.fallback_models;
      if (form.proxy_url !== undefined) payload.proxy_url = form.proxy_url;
      if (form.proxy_api_key) payload.proxy_api_key = form.proxy_api_key;
      if (form.ollama_base_url !== undefined) payload.ollama_base_url = form.ollama_base_url;
      if (form.ollama_model !== undefined) payload.ollama_model = form.ollama_model;
      if (form.request_timeout_seconds) payload.request_timeout_seconds = form.request_timeout_seconds;
      if (form.openai_api_key) payload.openai_api_key = form.openai_api_key;
      if (form.anthropic_api_key) payload.anthropic_api_key = form.anthropic_api_key;
      if (form.deepseek_api_key) payload.deepseek_api_key = form.deepseek_api_key;

      await updateLLMConfig(payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof LLMConfigUpdate, value: unknown) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  return (
    <div className="max-w-4xl space-y-8">
      {/* ===== LLM 模型配置 ===== */}
      <section className="space-y-4">
        <SectionTitle
          title="LLM 模型配置"
          description="设置默认推理模型、代理网关、本地 Ollama 及 API Key。保存后运行时立即生效。"
        />

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {error}
          </div>
        )}

        {!cfg ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Loader2 size={14} className="animate-spin" /> 加载中…
          </div>
        ) : (
          <div className="space-y-5 rounded-lg border border-white/[0.06] bg-white/[0.02] p-5">
            {/* 基本模型 */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="默认模型" hint="如 gpt-4o-mini / claude-sonnet-4-20250514 / deepseek-chat">
                <input
                  className={inputCls}
                  value={form.default_model ?? ""}
                  onChange={(e) => set("default_model", e.target.value)}
                  placeholder="gpt-4o-mini"
                />
              </Field>
              <Field label="回退模型（逗号分隔）" hint="主模型不可用时依次尝试">
                <input
                  className={inputCls}
                  value={(form.fallback_models ?? []).join(", ")}
                  onChange={(e) =>
                    set(
                      "fallback_models",
                      e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                    )
                  }
                  placeholder="gpt-4o-mini, deepseek-chat"
                />
              </Field>
            </div>

            {/* 代理 / Ollama */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="LiteLLM Proxy URL" hint="留空则不走代理">
                <div className="relative">
                  <Server size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500" />
                  <input
                    className={`${inputCls} pl-8`}
                    value={form.proxy_url ?? ""}
                    onChange={(e) => set("proxy_url", e.target.value)}
                    placeholder="http://localhost:4000"
                  />
                </div>
              </Field>
              <Field label="Proxy API Key" hint="留空不修改">
                <input
                  className={inputCls}
                  type="password"
                  value={form.proxy_api_key ?? ""}
                  onChange={(e) => set("proxy_api_key", e.target.value)}
                  placeholder={cfg.has_proxy_api_key ? "••••••（已配置）" : "sk-..."}
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Ollama Base URL" hint="本地推理，零 API 费用。留空则不启用">
                <input
                  className={inputCls}
                  value={form.ollama_base_url ?? ""}
                  onChange={(e) => set("ollama_base_url", e.target.value)}
                  placeholder="http://localhost:11434"
                />
              </Field>
              <Field label="Ollama 模型名" hint="如 qwen3:4b，留空则用默认模型">
                <input
                  className={inputCls}
                  value={form.ollama_model ?? ""}
                  onChange={(e) => set("ollama_model", e.target.value)}
                  placeholder="qwen3:4b"
                />
              </Field>
            </div>

            {/* 超时 */}
            <Field label="请求超时（秒）">
              <input
                className={`${inputCls} max-w-[140px]`}
                type="number"
                min={5}
                max={600}
                value={form.request_timeout_seconds ?? 60}
                onChange={(e) => set("request_timeout_seconds", Number(e.target.value))}
              />
            </Field>

            {/* API Keys */}
            <div className="space-y-3 border-t border-neutral-800 pt-4">
              <div className="flex items-center gap-2 text-xs font-medium text-neutral-400">
                <Brain size={13} /> Provider API Keys
                <span className="ml-auto flex gap-2">
                  <KeyStatus has={cfg.has_openai_key} label="OpenAI" />
                  <KeyStatus has={cfg.has_anthropic_key} label="Anthropic" />
                  <KeyStatus has={cfg.has_deepseek_key} label="DeepSeek" />
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <input
                  className={inputCls}
                  type="password"
                  placeholder={cfg.has_openai_key ? "OpenAI ✓" : "sk-..."}
                  value={form.openai_api_key ?? ""}
                  onChange={(e) => set("openai_api_key", e.target.value)}
                />
                <input
                  className={inputCls}
                  type="password"
                  placeholder={cfg.has_anthropic_key ? "Anthropic ✓" : "sk-ant-..."}
                  value={form.anthropic_api_key ?? ""}
                  onChange={(e) => set("anthropic_api_key", e.target.value)}
                />
                <input
                  className={inputCls}
                  type="password"
                  placeholder={cfg.has_deepseek_key ? "DeepSeek ✓" : "sk-..."}
                  value={form.deepseek_api_key ?? ""}
                  onChange={(e) => set("deepseek_api_key", e.target.value)}
                />
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-3 border-t border-neutral-800 pt-4">
              <button
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 rounded-md bg-white px-4 py-2 text-sm font-medium text-black transition hover:bg-neutral-200 disabled:opacity-50"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                保存配置
              </button>
              <button
                onClick={load}
                className="inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] px-3 py-2 text-sm text-neutral-400 transition hover:bg-white/[0.04]"
              >
                <RefreshCw size={13} /> 刷新
              </button>
              {saved && (
                <span className="text-sm text-emerald-400">✓ 已保存，运行时已生效</span>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ===== 媒体生成模型 ===== */}
      <section className="space-y-4">
        <SectionTitle
          title="媒体生成模型"
          description="可用的图像 / 视频 / 音频媒体生成模型（只读）。"
        />
        <div className="grid gap-3">
          {mediaModels.map((m) => (
            <div key={m.model_id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-white">{m.name}</div>
                <div className="font-mono text-xs text-neutral-500">{m.kind}</div>
              </div>
              <div className="mt-1 text-xs text-neutral-500">
                provider: {m.provider} · modes: {m.modes.join(", ")}
              </div>
              <div className="mt-2 text-xs text-neutral-400">{m.description}</div>
            </div>
          ))}
          {!mediaModels.length && (
            <div className="rounded-lg border border-dashed border-white/[0.08] p-4 text-sm text-neutral-500">
              尚未配置媒体模型。
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
