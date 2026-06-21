import { createContext, useContext, useState, type ReactNode } from "react";

type Lang = "zh" | "en";

const dict = {
  zh: {
    "nav.chat": "对话",
    "nav.agents": "智能体",
    "nav.workflows": "工作流",
    "nav.creative": "短剧工厂",
    "nav.openSource": "开源发现",
    "nav.memory": "知识库",
    "nav.settings": "设置",
    "common.run": "运行",
    "common.loading": "加载中...",
    "common.error": "出错了",
    "common.retry": "重试",
    "chat.placeholder": "输入任务目标，例如：用一句话介绍 X-Agent",
    "chat.running": "运行中...",
    "chat.runAgent": "运行 Agent",
    "chat.finalAnswer": "最终回答",
    "chat.streamOutput": "流式输出",
    "chat.events": "事件序列",
  },
  en: {
    "nav.chat": "Chat",
    "nav.agents": "Agents",
    "nav.workflows": "Workflows",
    "nav.creative": "Creative Studio",
    "nav.openSource": "Open Source",
    "nav.memory": "Knowledge",
    "nav.settings": "Settings",
    "common.run": "Run",
    "common.loading": "Loading...",
    "common.error": "Error",
    "common.retry": "Retry",
    "chat.placeholder": "Enter a task goal, e.g. introduce X-Agent",
    "chat.running": "Running...",
    "chat.runAgent": "Run Agent",
    "chat.finalAnswer": "Final Answer",
    "chat.streamOutput": "Stream Output",
    "chat.events": "Events",
  },
};

interface I18nCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}

const Ctx = createContext<I18nCtx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(
    (localStorage.getItem("xagent_lang") as Lang) || "zh"
  );
  const t = (key: string) => dict[lang][key as keyof (typeof dict)["zh"]] || key;
  const setLangPersist = (l: Lang) => {
    setLang(l);
    localStorage.setItem("xagent_lang", l);
  };
  return (
    <Ctx.Provider value={{ lang, setLang: setLangPersist, t }}>{children}</Ctx.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(Ctx);
  if (!ctx) return { lang: "zh" as Lang, setLang: () => {}, t: (k: string) => k };
  return ctx;
}
