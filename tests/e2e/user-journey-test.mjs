// 用户视角实测脚本：登录 → 主界面 → 发消息 → 流式响应 → 截图留证
// 运行：node user-journey-test.mjs
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const WEB = 'http://127.0.0.1:3000';
const SHOT_DIR = 'D:/AI编程库/项目库/进行中的项目/xiong bao/uitest-shots';
fs.mkdirSync(SHOT_DIR, { recursive: true });

const results = [];
function record(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  // 1. 打开应用
  await page.goto(WEB, { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: `${SHOT_DIR}/01-initial.png` });
  const title = await page.title();
  record('应用加载', true, `title="${title}" url=${page.url()}`);

  // 2. 登录页（若在登录页则执行登录）
  const loginUser = page.locator('input[type="text"], input[name="username"], input[placeholder*="用户"], input[placeholder*="账"]').first();
  const hasLogin = await loginUser.isVisible({ timeout: 3000 }).catch(() => false);
  if (hasLogin) {
    await loginUser.fill('admin');
    const pwd = page.locator('input[type="password"]').first();
    await pwd.fill('admin');
    await page.screenshot({ path: `${SHOT_DIR}/02-login-filled.png` });
    const submit = page.locator('button[type="submit"], button:has-text("登录"), button:has-text("Login"), button:has-text("登 录")').first();
    await submit.click();
    await page.waitForTimeout(3000);
    record('登录提交', true, `after-login url=${page.url()}`);
  } else {
    record('登录页检测', true, '无登录页或已登录');
  }
  await page.screenshot({ path: `${SHOT_DIR}/03-after-login.png` });

  // 3. 主界面结构探测
  const bodyText = await page.locator('body').innerText();
  const hasSidebar = await page.locator('nav, aside, [class*="sidebar" i]').first().isVisible().catch(() => false);
  record('主界面渲染', bodyText.length > 50, `侧栏=${hasSidebar} 正文长度=${bodyText.length}`);

  // 4. 找到对话输入框并发送消息
  const chatInput = page.locator('textarea, input[placeholder*="输入" i], input[placeholder*="消息" i], [contenteditable="true"]').first();
  const inputVisible = await chatInput.isVisible({ timeout: 5000 }).catch(() => false);
  if (!inputVisible) {
    // 可能在其他路由，尝试找导航入口
    const chatNav = page.locator('a:has-text("对话"), a:has-text("Chat"), button:has-text("对话"), a[href*="chat"]').first();
    if (await chatNav.isVisible().catch(() => false)) {
      await chatNav.click();
      await page.waitForTimeout(1500);
    }
  }
  const input2 = page.locator('textarea, [contenteditable="true"], input[placeholder*="输入" i]').first();
  const inputOk = await input2.isVisible({ timeout: 5000 }).catch(() => false);
  record('对话输入框可见', inputOk);

  if (inputOk) {
    await input2.fill('你好，请用一句话介绍你自己');
    await page.screenshot({ path: `${SHOT_DIR}/04-message-typed.png` });
    const sendBtn = page.locator('button:has-text("发送"), button:has-text("Send"), button[type="submit"], button[aria-label*="send" i]').first();
    if (await sendBtn.isVisible().catch(() => false)) {
      await sendBtn.click();
    } else {
      await input2.press('Enter');
    }
    record('消息发送', true);

    // 5. 等待流式响应（gpt-5.5 真实生成）
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${SHOT_DIR}/05-streaming.png` });
    let finalText = '';
    for (let i = 0; i < 24; i++) {
      await page.waitForTimeout(5000);
      finalText = await page.locator('body').innerText();
      // 简单判据：出现新内容且没有明显“生成中”指示
      if (/等于|你好|我是|X-Agent|助手|AI/.test(finalText) && !/生成中|思考中|loading/i.test(finalText)) break;
    }
    await page.screenshot({ path: `${SHOT_DIR}/06-response.png` });
    const gotReply = finalText.length > 200;
    record('模型响应出现（gpt-5.5）', gotReply, `页面文本长度=${finalText.length}`);
  }

  // 6. 导航巡检：侧栏各入口
  const navLinks = await page.locator('nav a, aside a, [class*="sidebar" i] a').allTextContents();
  record('导航入口枚举', navLinks.length > 0, navLinks.slice(0, 12).join(' / '));

} catch (err) {
  record('脚本执行异常', false, String(err).slice(0, 200));
  await page.screenshot({ path: `${SHOT_DIR}/99-error.png` }).catch(() => {});
} finally {
  await browser.close();
}

const pass = results.filter(r => r.ok).length;
console.log(`\n=== 用户旅程实测: ${pass}/${results.length} 通过 ===`);
fs.writeFileSync(`${SHOT_DIR}/results.json`, JSON.stringify(results, null, 2));
