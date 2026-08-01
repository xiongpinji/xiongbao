import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import { Check, Copy, ChevronDown, ChevronRight } from "lucide-react";

/* ---------- 代码块（带语言标签 + 复制按钮）---------- */

function CodeBlock({ className, children }: { className?: string; children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const lang = className?.replace("language-", "") || "code";
  const text = String(children).replace(/\n$/, "");

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="group relative my-3 overflow-hidden rounded-xl border border-white/[0.08] bg-[#0d1117]">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-1.5">
        <span className="text-[11px] font-medium text-neutral-500">{lang}</span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-neutral-500 opacity-0 transition hover:text-neutral-200 group-hover:opacity-100"
        >
          {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-[13px] leading-6">
        <code className={className}>{children}</code>
      </pre>
    </div>
  );
}

/* ---------- 图片渲染 ---------- */

function ImageRenderer({ src, alt }: { src?: string; alt?: string }) {
  const [loaded, setLoaded] = useState(false);
  if (!src) return null;
  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/[0.08]">
      {!loaded && <div className="h-48 animate-pulse bg-white/[0.03]" />}
      <img
        src={src}
        alt={alt || "生成图片"}
        className={`max-w-full transition-opacity ${loaded ? "opacity-100" : "opacity-0"}`}
        onLoad={() => setLoaded(true)}
        loading="lazy"
      />
    </div>
  );
}

/* ---------- 主渲染器 ---------- */

export const MarkdownRenderer = memo(function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose-agent text-sm leading-7 text-neutral-300">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className && !String(children).includes("\n");
            if (isInline) {
              return (
                <code
                  className="rounded bg-white/[0.07] px-1.5 py-0.5 text-[13px] text-amber-300/90"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return <CodeBlock className={className}>{children}</CodeBlock>;
          },
          pre({ children }) {
            return <>{children}</>;
          },
          img({ src, alt }) {
            return <ImageRenderer src={src} alt={alt} />;
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 underline decoration-blue-400/30 underline-offset-2 transition hover:text-blue-300"
              >
                {children}
              </a>
            );
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto rounded-lg border border-white/[0.08]">
                <table className="w-full text-left text-[13px]">{children}</table>
              </div>
            );
          },
          th({ children }) {
            return (
              <th className="border-b border-white/[0.08] bg-white/[0.03] px-3 py-2 font-medium text-neutral-400">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="border-b border-white/[0.04] px-3 py-2">{children}</td>;
          },
          ul({ children }) {
            return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>;
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-3 border-l-2 border-white/[0.12] pl-4 text-neutral-500 italic">
                {children}
              </blockquote>
            );
          },
          h1({ children }) {
            return <h1 className="mb-3 mt-4 text-lg font-semibold text-white">{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="mb-2 mt-4 text-base font-semibold text-white">{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="mb-2 mt-3 text-sm font-semibold text-neutral-200">{children}</h3>;
          },
          hr() {
            return <hr className="my-4 border-white/[0.06]" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});

/* ---------- 可折叠区块 ---------- */

export function CollapsibleSection({
  title,
  icon,
  children,
  defaultOpen = false,
  badge,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badge?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="my-2 overflow-hidden rounded-xl border border-white/[0.06] bg-white/[0.015]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-medium text-neutral-400 transition hover:bg-white/[0.02] hover:text-neutral-300"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {icon}
        <span className="flex-1">{title}</span>
        {badge && (
          <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-500">
            {badge}
          </span>
        )}
      </button>
      {open && <div className="border-t border-white/[0.04] px-4 py-3">{children}</div>}
    </div>
  );
}
