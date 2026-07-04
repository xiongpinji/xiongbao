export default function ShellContextPanel() {
  const previewMessage = "辅助模式：当前为上下文助手，优先提供总结、建议与跳转，不直接执行后台任务。";
  const assistantMessage = "必要时再引导进入真实执行页面。";

  return (
    <section className="rounded-2xl border border-neutral-800 bg-neutral-950/80 p-4">
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">上下文助手</div>
      <p className="mt-3 text-sm leading-6 text-neutral-300">{previewMessage}</p>
      <p className="mt-2 text-sm leading-6 text-neutral-400">{assistantMessage}</p>
    </section>
  );
}
