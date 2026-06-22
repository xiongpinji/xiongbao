import { useEffect, useState } from "react";
import { Film, Plus, Scissors, Download, Play } from "lucide-react";
import {
  createTimeline,
  addClip,
  removeClip,
  renderTimeline,
  exportDraft,
  getTimeline,
  listTimelines,
  type EditorTimeline,
} from "../api";

const TRACK_COLORS: Record<string, string> = {
  video: "bg-blue-500",
  audio: "bg-green-500",
  text: "bg-amber-500",
};

export default function EditorPage() {
  const [timeline, setTimeline] = useState<EditorTimeline | null>(null);
  const [timelines, setTimelines] = useState<EditorTimeline[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [renderUrl, setRenderUrl] = useState<string | null>(null);
  // 添加片段表单
  const [clipType, setClipType] = useState("video");
  const [clipUrl, setClipUrl] = useState("");
  const [clipText, setClipText] = useState("");
  const [clipStart, setClipStart] = useState(0);
  const [clipEnd, setClipEnd] = useState(4);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const timelineId = params.get("timeline_id");
    if (!timelineId) return;
    (async () => {
      try {
        const tl = await getTimeline(timelineId);
        setTimeline(tl);
        setMsg(`已加载短剧工厂时间线：${tl.id.slice(0, 8)}`);
      } catch (e: unknown) {
        setMsg(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  async function handleCreate() {
    setLoading(true);
    setMsg(null);
    try {
      const tl = await createTimeline({ name: "短剧剪辑", width: 1080, height: 1920 });
      setTimeline(tl);
      setMsg(`已创建时间线：${tl.id.slice(0, 8)}`);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleList() {
    const items = await listTimelines();
    setTimelines(items);
    if (items.length > 0 && !timeline) {
      setTimeline(items[0]);
    }
  }

  async function handleAddClip() {
    if (!timeline) return;
    setLoading(true);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        track_type: clipType,
        timeline_start: clipStart,
        timeline_end: clipEnd,
      };
      if (clipType === "video" || clipType === "audio") body.source_url = clipUrl;
      if (clipType === "text") body.text = clipText;
      const tl = await addClip(timeline.id, body);
      setTimeline(tl);
      setMsg(`已添加 ${clipType} 片段`);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleRender() {
    if (!timeline) return;
    setLoading(true);
    setMsg("渲染中...");
    try {
      const result = await renderTimeline(timeline.id);
      if (result.ok) {
        setRenderUrl(result.output_url || result.output_path || null);
        setMsg("渲染完成");
      } else {
        setMsg(`渲染：${result.error}`);
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleRemoveClip(clipId: string) {
    if (!timeline) return;
    try {
      const tl = await removeClip(timeline.id, clipId);
      setTimeline(tl);
      setMsg("已删除片段");
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleExportDraft() {
    if (!timeline) return;
    setLoading(true);
    setMsg("导出草稿中...");
    try {
      const result = await exportDraft(timeline.id);
      setMsg(result.ok ? `草稿已导出：${result.draft_path}` : `导出失败`);
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Film size={20} /> 视频剪辑工作台
        </h1>
        <div className="flex gap-2">
          <button onClick={handleCreate} disabled={loading}
            className="px-3 py-1.5 bg-brand-600 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
            <Plus size={14} /> 新建时间线
          </button>
          <button onClick={handleList}
            className="px-3 py-1.5 border rounded text-sm">
            列出时间线
          </button>
        </div>
      </div>

      {msg && <div className="text-sm text-slate-600 mb-3">{msg}</div>}

      {/* 渲染结果视频预览 */}
      {renderUrl && (
        <div className="mb-4 bg-white border rounded-md p-3">
          <div className="text-xs text-slate-500 mb-2">渲染结果预览</div>
          <video
            src={renderUrl.startsWith("local://") ? undefined : renderUrl}
            controls
            className="max-h-64 rounded"
            style={{ width: "100%" }}
          >
            您的浏览器不支持视频播放。渲染文件：{renderUrl}
          </video>
        </div>
      )}

      {timelines.length > 0 && (
        <div className="mb-3 flex gap-2 flex-wrap">
          {timelines.map((t) => (
            <button key={t.id} onClick={async () => setTimeline(await getTimeline(t.id))}
              className={`text-xs px-2 py-1 rounded ${timeline?.id === t.id ? "bg-brand-100 text-brand-700" : "bg-slate-100"}`}>
              {t.name} ({t.clips.length}片段)
            </button>
          ))}
        </div>
      )}

      {/* 添加片段 */}
      {timeline && (
        <div className="bg-white border rounded-md p-3 mb-3 flex gap-2 items-end flex-wrap">
          <select value={clipType} onChange={(e) => setClipType(e.target.value)}
            className="border rounded px-2 py-1 text-sm">
            <option value="video">视频</option>
            <option value="audio">音频</option>
            <option value="text">字幕</option>
          </select>
          {clipType === "text" ? (
            <input placeholder="字幕文本" value={clipText} onChange={(e) => setClipText(e.target.value)}
              className="border rounded px-2 py-1 text-sm w-40" />
          ) : (
            <input placeholder="素材URL" value={clipUrl} onChange={(e) => setClipUrl(e.target.value)}
              className="border rounded px-2 py-1 text-sm w-40" />
          )}
          <label className="text-xs text-slate-500">起 <input type="number" value={clipStart}
            onChange={(e) => setClipStart(+e.target.value)} className="border rounded px-1 py-1 text-sm w-16" /></label>
          <label className="text-xs text-slate-500">止 <input type="number" value={clipEnd}
            onChange={(e) => setClipEnd(+e.target.value)} className="border rounded px-1 py-1 text-sm w-16" /></label>
          <button onClick={handleAddClip} disabled={loading}
            className="px-3 py-1.5 bg-slate-700 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
            <Scissors size={14} /> 添加片段
          </button>
        </div>
      )}

      {/* 时间线预览 */}
      {timeline && (
        <div className="flex-1 bg-white border rounded-md p-4 overflow-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm">
              <span className="font-medium">{timeline.name}</span>
              <span className="text-slate-400 ml-2">
                {timeline.width}×{timeline.height} · {timeline.fps}fps · {timeline.total_duration}s
              </span>
            </div>
            <div className="flex gap-2">
              <button onClick={handleRender} disabled={loading}
                className="px-3 py-1.5 bg-purple-600 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
                <Play size={14} /> 渲染导出
              </button>
              <button onClick={handleExportDraft} disabled={loading}
                className="px-3 py-1.5 bg-green-600 text-white rounded text-sm flex items-center gap-1 disabled:opacity-50">
                <Download size={14} /> 导出剪映草稿
              </button>
            </div>
          </div>

          {/* 轨道可视化 */}
          <div className="space-y-2">
            {(["video", "audio", "text"] as const).map((trackType) => {
              const clips = timeline.clips.filter((c) => c.track_type === trackType);
              if (clips.length === 0) return null;
              const maxEnd = timeline.total_duration || 1;
              return (
                <div key={trackType} className="flex items-center gap-2">
                  <div className="text-xs text-slate-400 w-12">{trackType === "video" ? "视频" : trackType === "audio" ? "音频" : "字幕"}</div>
                  <div className="flex-1 relative h-8 bg-slate-50 rounded">
                    {clips.map((clip) => {
                      const left = (clip.timeline_start / maxEnd) * 100;
                      const width = (clip.duration / maxEnd) * 100;
                      return (
                        <div key={clip.id}
                          className={`absolute h-7 ${TRACK_COLORS[trackType]} opacity-80 rounded text-white text-xs flex items-center px-1 overflow-hidden cursor-pointer hover:opacity-100 hover:ring-2 hover:ring-red-400`}
                          style={{ left: `${left}%`, width: `${Math.max(width, 3)}%` }}
                          title={`${clip.text || clip.source_url?.split("/").pop() || "片段"} — 点击删除`}
                          onClick={() => handleRemoveClip(clip.id)}>
                          {clip.text || clip.source_url?.split("/").pop() || "片段"}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
            {timeline.clips.length === 0 && (
              <div className="text-sm text-slate-400 text-center py-8">
                添加片段后在此显示时间线轨道
              </div>
            )}
          </div>

          {/* 转场 */}
          {timeline.transitions.length > 0 && (
            <div className="mt-4">
              <div className="text-xs text-slate-400 mb-1">转场</div>
              {timeline.transitions.map((t) => (
                <div key={t.id} className="text-xs text-slate-600">
                  {t.type} · {t.duration}s → clip {t.clip_id.slice(0, 6)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!timeline && (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
          点击"新建时间线"开始剪辑
        </div>
      )}
    </div>
  );
}
