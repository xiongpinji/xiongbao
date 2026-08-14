// 工作流模板执行实测：专业模式 → 顺序执行模板 → 运行 → 观察步骤流
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const WEB = 'http://127.0.0.1:3000';
const SHOT = 'D:/AI编程库/项目库/进行中的项目/xiong bao/uitest-shots';
const t0 = Date.now();
const ts = () => ((Date.now() - t0) / 1000).toFixed(0) + 's';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(WEB, { waitUntil: 'networkidle', timeout: 30000 });
  const u = page.locator('input[placeholder*="用户"]').first();
  if (await u.isVisible({ timeout: 3000 }).catch(() => false)) {
    await u.fill('admin');
    await page.locator('input[type="password"]').first().fill('admin');
    await page.locator('button:has-text("登录")').first().click();
    await page.waitForURL('**/chat**', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
  }

  await page.goto(WEB + '/professional', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // 使用快速模板：顺序执行
  const tpl = page.locator('text=+ 顺序执行').first();
  if (await tpl.isVisible({ timeout: 5000 }).catch(() => false)) {
    await tpl.click();
    await page.waitForTimeout(1500);
    console.log(`[${ts()}] 已应用「顺序执行」模板`);
    await page.screenshot({ path: `${SHOT}/wf-template.png` });
  } else {
    console.log(`[${ts()}] [FAIL] 未找到快速模板`);
  }

  // 执行
  const runBtn = page.locator('button:has-text("执 行"), button:has-text("执行")').first();
  await runBtn.click();
  console.log(`[${ts()}] 已点击执行`);

  // 观察执行：步骤状态变化
  let prev = '';
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(5000);
    const txt = await page.locator('body').innerText();
    const m = txt.match(/(运行中|执行中|已完成|失败|成功|succeeded|failed|running)/g);
    if (i % 4 === 1) await page.screenshot({ path: `${SHOT}/wf-run-${String(i).padStart(2, '0')}.png` });
    const sig = (m || []).join(',');
    if (sig !== prev) { console.log(`[${ts()}] 状态: ${sig || '(无状态词)'}`); prev = sig; }
    if (/已完成|全部成功|succeeded/i.test(txt) && !/运行中|执行中/.test(txt)) {
      console.log(`[${ts()}] 工作流执行完成`);
      break;
    }
    if (/失败|failed/i.test(txt) && /工作流|步骤/.test(txt)) {
      console.log(`[${ts()}] [WARN] 出现失败标记`);
      break;
    }
  }
  await page.screenshot({ path: `${SHOT}/wf-final.png` });
} finally {
  await browser.close();
}
console.log(`[${ts()}] 工作流实测脚本结束`);
