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
import ConversationalCommand from "../components/chat/ConversationalCommand";

const TRACK_COLORS: Record<string, string> = {
  video: "bg-red-500",
  audio: "bg-amber-500",
  text: "bg-violet-500",
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
    <div className="flex h-full min-h-0 flex-col px-6 py-5">
      <header className="flex shrink-0 items-start justify-between gap-4 border-b border-white/[0.07] pb-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">
            <Film size={15} />
            Studio
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white">剪辑工作台</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-500">
            管理短剧时间线、素材轨道、渲染结果与剪映草稿导出。
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={handleCreate} disabled={loading} className="gold-button flex items-center gap-2">
            <Plus size={15} /> 新建时间线
          </button>
          <button
            onClick={handleList}
            className="xagent-chip"
          >
            列出时间线
          </button>
        </div>
      </header>

      {msg && (
        <div className="mt-4 rounded-2xl border border-[#8a6a32]/25 bg-[#171208] px-4 py-3 text-sm text-[#f2d99c]">
          {msg}
        </div>
      )}

      {timelines.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {timelines.map((item) => (
            <button
              key={item.id}
              onClick={async () => setTimeline(await getTimeline(item.id))}
              className={`rounded-full border px-3 py-1.5 text-xs transition ${
                timeline?.id === item.id
                  ? "border-[#d6ad62]/50 bg-[#171208] text-[#f2d99c]"
                  : "border-white/[0.08] bg-white/[0.035] text-neutral-500 hover:text-white"
              }`}
            >
              {item.name} ({item.clips.length}片段)
            </button>
          ))}
        </div>
      )}

      <div className="mt-5 grid min-h-0 flex-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <main className="xagent-surface xagent-scrollbar min-h-0 overflow-auto p-5">
          {timeline ? (
            <div className="flex min-h-full flex-col">
              <div className="mb-5 flex items-center justify-between gap-4">
                <div>
                  <div className="text-lg font-semibold text-white">{timeline.name}</div>
                  <div className="mt-1 text-xs text-neutral-500">
                    {timeline.width}x{timeline.height} · {timeline.fps}fps · {timeline.total_duration}s
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleRender} disabled={loading} className="gold-button flex items-center gap-2">
                    <Play size={14} /> 渲染
                  </button>
                  <button
                    onClick={handleExportDraft}
                    disabled={loading}
                    className="xagent-chip disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span className="inline-flex items-center gap-2"><Download size={14} />导出草稿</span>
                  </button>
                </div>
              </div>

              <div className="mb-5 flex min-h-[260px] items-center justify-center rounded-[22px] border border-white/[0.06] bg-[radial-gradient(circle_at_center,rgba(214,173,98,0.12),rgba(255,255,255,0.025)_42%,rgba(0,0,0,0.18))]">
                {renderUrl ? (
                  <video
                    src={renderUrl.startsWith("local://") ? undefined : renderUrl}
                    controls
                    className="max-h-[420px] w-full rounded-2xl object-contain"
                  >
                    您的浏览器不支持视频播放。渲染文件：{renderUrl}
                  </video>
                ) : (
                  <div className="text-center">
                    <Film size={38} className="mx-auto text-[#d6ad62]" />
                    <div className="mt-3 text-sm font-medium text-neutral-200">预览区</div>
                    <div className="mt-1 text-xs text-neutral-600">渲染后将在这里查看成片。</div>
                  </div>
                )}
              </div>

              <div className="space-y-3">
                {(["video", "audio", "text"] as const).map((trackType) => {
                  const clips = timeline.clips.filter((clip) => clip.track_type === trackType);
                  const maxEnd = timeline.total_duration || 1;
                  return (
                    <div key={trackType} className="grid grid-cols-[56px_minmax(0,1fr)] items-center gap-3">
                      <div className="text-xs font-medium text-neutral-500">
                        {trackType === "video" ? "视频" : trackType === "audio" ? "音频" : "字幕"}
                      </div>
                      <div className="relative h-11 overflow-hidden rounded-2xl border border-white/[0.06] bg-black/25">
                        {clips.map((clip) => {
                          const left = (clip.timeline_start / maxEnd) * 100;
                          const width = (clip.duration / maxEnd) * 100;
                          return (
                            <button
                              key={clip.id}
                              type="button"
                              className={`absolute top-1 flex h-9 items-center overflow-hidden rounded-xl px-2 text-left text-xs font-medium text-white shadow-lg transition hover:ring-2 hover:ring-[#f1c96f] ${TRACK_COLORS[trackType]}`}
                              style={{ left: `${left}%`, width: `${Math.max(width, 4)}%` }}
                              title={`${clip.text || clip.source_url?.split("/").pop() || "片段"} - 点击删除`}
                              onClick={() => handleRemoveClip(clip.id)}
                            >
                              <span className="truncate">{clip.text || clip.source_url?.split("/").pop() || "片段"}</span>
                            </button>
                          );
                        })}
                        {clips.length === 0 && (
                          <div className="flex h-full items-center px-3 text-xs text-neutral-700">暂无轨道片段</div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {timeline.transitions.length > 0 && (
                <div className="mt-5 rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">Transitions</div>
                  {timeline.transitions.map((transition) => (
                    <div key={transition.id} className="text-xs leading-6 text-neutral-500">
                      {transition.type} · {transition.duration}s → clip {transition.clip_id.slice(0, 6)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-full min-h-[520px] items-center justify-center text-center">
              <div>
                <Film size={42} className="mx-auto text-[#d6ad62]" />
                <div className="mt-4 text-lg font-semibold text-white">尚未打开时间线</div>
                <div className="mt-2 text-sm text-neutral-500">新建或列出时间线后开始剪辑。</div>
              </div>
            </div>
          )}
        </main>

        <aside className="xagent-surface xagent-scrollbar min-h-0 overflow-auto p-5">
          <div className="mb-5">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[#d6ad62]">Inspector</div>
            <h2 className="mt-2 text-xl font-semibold text-white">素材与片段</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-500">为当前时间线添加视频、音频或字幕片段。</p>
          </div>

          <ConversationalCommand
            compact
            className="mb-5"
            title="剪辑助手"
            context={timeline ? timeline.name : "尚未打开时间线"}
            placeholder="例如：添加片头字幕，或把这段素材放到第 4 秒..."
            initialAssistantMessage="你可以直接描述剪辑意图，我会把它转换成当前时间线的素材输入。"
            suggestions={["添加片头字幕", "生成 3 秒转场说明", "为当前镜头补一句旁白"]}
            onSubmit={async (value) => {
              if (!timeline) {
                await handleCreate();
                setClipType("text");
                setClipText(value);
                return `已先创建一条时间线，并把「${value}」放入字幕片段输入。`;
              }
              setClipType("text");
              setClipText(value);
              setClipStart(clipStart);
              setClipEnd(Math.max(clipEnd, clipStart + 3));
              return `已把「${value}」转成字幕片段输入。确认起止时间后点击添加片段。`;
            }}
          />

          {timeline ? (
            <div className="space-y-4">
              <label className="block space-y-2">
                <span className="text-xs font-medium text-neutral-500">轨道类型</span>
                <select value={clipType} onChange={(event) => setClipType(event.target.value)} className="field">
                  <option value="video">视频</option>
                  <option value="audio">音频</option>
                  <option value="text">字幕</option>
                </select>
              </label>

              {clipType === "text" ? (
                <label className="block space-y-2">
                  <span className="text-xs font-medium text-neutral-500">字幕文本</span>
                  <input
                    placeholder="输入字幕文本"
                    value={clipText}
                    onChange={(event) => setClipText(event.target.value)}
                    className="field"
                  />
                </label>
              ) : (
                <label className="block space-y-2">
                  <span className="text-xs font-medium text-neutral-500">素材 URL</span>
                  <input
                    placeholder="https://..."
                    value={clipUrl}
                    onChange={(event) => setClipUrl(event.target.value)}
                    className="field"
                  />
                </label>
              )}

              <div className="grid grid-cols-2 gap-3">
                <label className="block space-y-2">
                  <span className="text-xs font-medium text-neutral-500">开始</span>
                  <input
                    type="number"
                    value={clipStart}
                    onChange={(event) => setClipStart(+event.target.value)}
                    className="field"
                  />
                </label>
                <label className="block space-y-2">
                  <span className="text-xs font-medium text-neutral-500">结束</span>
                  <input
                    type="number"
                    value={clipEnd}
                    onChange={(event) => setClipEnd(+event.target.value)}
                    className="field"
                  />
                </label>
              </div>

              <button onClick={handleAddClip} disabled={loading} className="gold-button flex w-full items-center justify-center gap-2">
                <Scissors size={14} /> 添加片段
              </button>

              <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-4">
                <div className="text-sm font-semibold text-white">当前时间线</div>
                <div className="mt-3 space-y-2 text-sm text-neutral-500">
                  <div>片段：{timeline.clips.length}</div>
                  <div>转场：{timeline.transitions.length}</div>
                  <div>尺寸：{timeline.width} x {timeline.height}</div>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-white/[0.08] p-4 text-sm leading-6 text-neutral-500">
              先创建时间线，再添加素材片段。
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
