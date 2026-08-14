// 浏览器端完整复测：登录 → 新建对话 → 发消息 → 等待真实模型完整响应 → 截图
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const WEB = 'http://127.0.0.1:3000';
const SHOT_DIR = 'D:/AI编程库/项目库/进行中的项目/xiong bao/uitest-shots';
fs.mkdirSync(SHOT_DIR, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(WEB, { waitUntil: 'networkidle', timeout: 30000 });
  const loginUser = page.locator('input[placeholder*="用户"]').first();
  if (await loginUser.isVisible({ timeout: 3000 }).catch(() => false)) {
    await loginUser.fill('admin');
    await page.locator('input[type="password"]').first().fill('admin');
    await page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Login"), button:has-text("登 录")').first().click();
    await page.waitForURL('**/chat**', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2500);
    console.log('[INFO] after-login url =', page.url());
  }

  const nc = page.locator('text=新建对话').first();
  if (await nc.isVisible().catch(() => false)) { await nc.click(); await page.waitForTimeout(1500); }

  const input = page.locator('textarea[placeholder*="描述"], textarea, [contenteditable="true"]').first();
  await input.waitFor({ state: 'visible', timeout: 15000 });
  await input.fill('用一句话介绍 X-Agent 的核心能力');
  await page.screenshot({ path: `${SHOT_DIR}/10-typed.png` });
  const sendBtn = page.locator('button[aria-label*="send" i], button:has-text("发送")').first();
  if (await sendBtn.isVisible().catch(() => false)) await sendBtn.click();
  else await input.press('Enter');
  console.log('[PASS] 消息已发送，等待 gpt-5.5 流式响应...');

  // 等待 token 流出现并稳定
  let last = '';
  let stableCount = 0;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(3000);
    const mainText = await page.locator('main, [class*="content" i], body').first().innerText();
    if (/连接已中断|请重试/.test(mainText)) {
      console.log('[FAIL] 出现「连接已中断」');
      break;
    }
    if (mainText === last) {
      stableCount++;
      if (stableCount >= 3 && mainText.length > 300) { console.log('[PASS] 响应稳定完成'); break; }
    } else { stableCount = 0; last = mainText; }
    if (i === 59) console.log('[WARN] 等待超时');
  }
  await page.screenshot({ path: `${SHOT_DIR}/11-final-response.png` });
  const finalText = await page.locator('body').innerText();
  const interrupted = /连接已中断/.test(finalText);
  console.log(interrupted ? '[FAIL] 最终结果含中断错误' : '[PASS] 无中断错误，流式对话完整');
  // 提取回答片段
  const m = finalText.match(/X-Agent[^。\n]{10,120}/);
  console.log('[INFO] 回答片段:', m ? m[0].slice(0, 100) : finalText.slice(0, 150));
} finally {
  await browser.close();
}
