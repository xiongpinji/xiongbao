import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export default function CollapsiblePanel({
  title,
  collapsed,
  onToggle,
  children,
}: {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-neutral-200 hover:text-white"
      >
        <span>{title}</span>
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
      </button>
      {!collapsed && <div className="border-t border-neutral-800 p-4">{children}</div>}
    </section>
  );
}
