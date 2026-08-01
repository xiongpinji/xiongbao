/**
 * 骨架屏组件：加载态占位动画。
 *
 * 提供多种预设布局：
 * - SkeletonLine: 单行文本
 * - SkeletonCard: 卡片
 * - SkeletonTable: 表格
 * - SkeletonChat: 对话气泡
 *
 * 用法：
 *   {loading ? <SkeletonTable rows={8} /> : <DataTable />}
 */

interface SkeletonProps {
  className?: string;
}

/** 基础骨架块 */
export function SkeletonBlock({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded bg-neutral-700/50 ${className}`}
    />
  );
}

/** 单行文本骨架 */
export function SkeletonLine({ width = "100%", className = "" }: SkeletonProps & { width?: string }) {
  return <SkeletonBlock className={`h-4 ${className}`} style={{ width } as never} />;
}

/** 多行段落骨架 */
export function SkeletonParagraph({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBlock
          key={i}
          className="h-4"
          style={{ width: i === lines - 1 ? "60%" : "100%" } as never}
        />
      ))}
    </div>
  );
}

/** 卡片骨架 */
export function SkeletonCard({ className = "" }: SkeletonProps) {
  return (
    <div className={`rounded-xl border border-neutral-700/50 p-5 ${className}`}>
      <div className="mb-4 flex items-center gap-3">
        <SkeletonBlock className="h-10 w-10 rounded-full" />
        <div className="flex-1 space-y-2">
          <SkeletonBlock className="h-4 w-1/3" />
          <SkeletonBlock className="h-3 w-1/4" />
        </div>
      </div>
      <SkeletonParagraph lines={3} />
    </div>
  );
}

/** 表格骨架 */
export function SkeletonTable({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      {/* 表头 */}
      <div className="flex gap-3">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonBlock key={i} className="h-8 flex-1" />
        ))}
      </div>
      {/* 行 */}
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <SkeletonBlock key={c} className="h-10 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** 对话气泡骨架 */
export function SkeletonChat({ messages = 4 }: { messages?: number }) {
  return (
    <div className="space-y-4 p-4">
      {Array.from({ length: messages }).map((_, i) => (
        <div key={i} className={`flex ${i % 2 === 0 ? "justify-start" : "justify-end"}`}>
          <div className={`max-w-[70%] space-y-2 ${i % 2 === 0 ? "" : "items-end"}`}>
            <SkeletonBlock className="h-8 w-8 rounded-full" />
            <SkeletonBlock className={`h-16 ${i % 2 === 0 ? "w-64" : "w-48"} rounded-xl`} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** 页面级骨架（侧边栏 + 内容区） */
export function SkeletonPage() {
  return (
    <div className="flex h-full gap-4 p-4">
      {/* 侧边栏 */}
      <div className="w-56 space-y-3">
        <SkeletonBlock className="h-8 w-full" />
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonBlock key={i} className="h-10 w-full" />
        ))}
      </div>
      {/* 内容区 */}
      <div className="flex-1 space-y-4">
        <SkeletonBlock className="h-12 w-1/2" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}
