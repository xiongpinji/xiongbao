/**
 * 轻量级 i18n 国际化模块。
 *
 * 零依赖实现：Context + 字典 + useI18n hook。
 * 支持语言：zh（默认）、en。
 *
 * 用法：
 *   const { t, locale, setLocale } = useI18n();
 *   <span>{t("nav.chat")}</span>
 */

import { createContext, useContext } from "react";

export type Locale = "zh" | "en";

export interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, params?: Record<string, string>) => string;
}

export const I18nContext = createContext<I18nContextValue>({
  locale: "zh",
  setLocale: () => {},
  t: (key) => key,
});

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}

// ─── 字典 ───

const zh: Record<string, string> = {
  "app.name": "X-Agent",
  "app.loading": "加载中...",
  "nav.chat": "对话",
  "nav.agents": "智能体",
  "nav.supervisor": "协作",
  "nav.professional": "短剧工厂",
  "nav.workflows": "工作流",
  "nav.creative": "创意画布",
  "nav.settings": "设置",
  "nav.billing": "计费",
  "nav.audit": "审计",
  "nav.goalBoard": "目标看板",
  "nav.memory": "记忆",
  "nav.openSource": "开源发现",
  "auth.login": "登录",
  "auth.logout": "退出",
  "auth.username": "用户名",
  "auth.password": "密码",
  "auth.submit": "登录",
  "auth.error": "登录失败，请检查凭据",
  "chat.placeholder": "描述一个任务或提出一个问题...",
  "chat.send": "发送",
  "chat.run": "运行 Agent",
  "chat.viewRun": "查看运行详情",
  "agents.title": "智能体角色",
  "settings.title": "设置",
  "settings.knowledge": "知识库",
  "settings.webhook": "Webhook",
  "common.confirm": "确认",
  "common.cancel": "取消",
  "common.delete": "删除",
  "common.save": "保存",
  "common.search": "搜索",
  "common.create": "创建",
  "common.edit": "编辑",
  "common.close": "关闭",
  "common.loading": "加载中",
  "common.error": "出错了",
  "common.success": "成功",
  "billing.title": "计量计费",
  "audit.title": "审计日志",
  "market.title": "技能市场",
  "market.install": "安装",
  "market.publish": "发布",
};

const en: Record<string, string> = {
  "app.name": "X-Agent",
  "app.loading": "Loading...",
  "nav.chat": "Chat",
  "nav.agents": "Agents",
  "nav.supervisor": "Supervisor",
  "nav.professional": "Drama Factory",
  "nav.workflows": "Workflows",
  "nav.creative": "Creative Canvas",
  "nav.settings": "Settings",
  "nav.billing": "Billing",
  "nav.audit": "Audit",
  "nav.goalBoard": "Goal Board",
  "nav.memory": "Memory",
  "nav.openSource": "Open Source",
  "auth.login": "Login",
  "auth.logout": "Logout",
  "auth.username": "Username",
  "auth.password": "Password",
  "auth.submit": "Sign In",
  "auth.error": "Login failed, please check credentials",
  "chat.placeholder": "Describe a task or ask a question...",
  "chat.send": "Send",
  "chat.run": "Run Agent",
  "chat.viewRun": "View Run Details",
  "agents.title": "Agent Roles",
  "settings.title": "Settings",
  "settings.knowledge": "Knowledge Base",
  "settings.webhook": "Webhook",
  "common.confirm": "Confirm",
  "common.cancel": "Cancel",
  "common.delete": "Delete",
  "common.save": "Save",
  "common.search": "Search",
  "common.create": "Create",
  "common.edit": "Edit",
  "common.close": "Close",
  "common.loading": "Loading",
  "common.error": "Error",
  "common.success": "Success",
  "billing.title": "Billing",
  "audit.title": "Audit Log",
  "market.title": "Marketplace",
  "market.install": "Install",
  "market.publish": "Publish",
};

const dictionaries: Record<Locale, Record<string, string>> = { zh, en };

/**
 * 翻译函数工厂。
 */
export function createTranslator(locale: Locale) {
  const dict = dictionaries[locale] || zh;
  return (key: string, params?: Record<string, string>): string => {
    let text = dict[key] ?? zh[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, v);
      }
    }
    return text;
  };
}

/** 获取浏览器语言偏好 */
export function detectLocale(): Locale {
  const stored = localStorage.getItem("xagent_locale");
  if (stored === "en" || stored === "zh") return stored;
  const nav = navigator.language.toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}
