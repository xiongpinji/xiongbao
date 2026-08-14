// 长任务用户实测：登录 → 发送多步开发任务 → 观察执行过程 → 验证产物
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const WEB = 'http://127.0.0.1:3000';
const SHOT = 'D:/AI编程库/项目库/进行中的项目/xiong bao/uitest-shots';
fs.mkdirSync(SHOT, { recursive: true });
const t0 = Date.now();
const ts = () => ((Date.now() - t0) / 1000).toFixed(0) + 's';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

try {
  await page.goto(WEB, { waitUntil: 'networkidle', timeout: 30000 });
  const u = page.locator('input[placeholder*="用户"]').first();
  if (await u.isVisible({ timeout: 3000 }).catch(() => false)) {
    await u.fill('admin');
    await p_fill(page);
    await page.locator('button:has-text("登录")').first().click();
    await page.waitForURL('**/chat**', { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
  }
  async function p_fill(p) { await p.locator('input[type="password"]').first().fill('admin'); }

  // 新建干净会话
  const nc = page.locator('text=新建对话').first();
  if (await nc.isVisible().catch(() => false)) { await nc.click(); await page.waitForTimeout(1200); }

  // 发送长任务（多步、需工具、产出文件）
  const task = '创建一个 Python 项目骨架：1) 用 file_write 创建 hello.py（打印 1 到 5 的平方）2) 创建 README.md 说明用法 3) 最后用 file_read 读回 hello.py 确认内容正确';
  const input = page.locator('textarea[placeholder*="描述"], textarea').first();
  await input.waitFor({ state: 'visible', timeout: 15000 });
  await input.fill(task);
  const sendBtn = page.locator('button[aria-label*="send" i], button:has-text("发送")').first();
  if (await sendBtn.isVisible().catch(() => false)) await sendBtn.click();
  else await input.press('Enter');
  console.log(`[${ts()}] 长任务已发送`);

  // 观察执行过程：周期性截图 + 检测步骤/工具事件
  let sawSteps = false, sawTools = false, done = false;
  for (let i = 0; i < 100; i++) {
    await page.waitForTimeout(5000);
    const txt = await page.locator('body').innerText();
    if (/步骤|step/i.test(txt)) sawSteps = true;
    if (/file_write|file_read|工具|tool/i.test(txt)) sawTools = true;
    if (/连接已中断/.test(txt)) { console.log(`[${ts()}] [FAIL] 连接中断`); break; }
    // 正确的完成判据：思考/生成指示器消失（而不是文本长度稳定）
    const busy = /正在思考|生成中|执行中|思考中/.test(txt);
    if (i % 3 === 1) await page.screenshot({ path: `${SHOT}/lt-${String(i).padStart(2, '0')}.png` });
    if (!busy && i > 2) { done = true; console.log(`[${ts()}] 执行指示器消失，判定完成`); break; }
    if (i % 6 === 0) console.log(`[${ts()}] 执行中… 文本 ${txt.length} 字符`);
  }
  if (!done) console.log(`[${ts()}] [WARN] 超过等待上限仍未完成`);
  await page.screenshot({ path: `${SHOT}/lt-final.png` });
  const finalTxt = await page.locator('body').innerText();
  console.log(`[${ts()}] 步骤事件可见=${sawSteps} 工具事件可见=${sawTools}`);
  console.log(`[${ts()}] 最终页面含完成标记=${/完成|成功|已创建|确认/.test(finalTxt)}`);

  // 查看运行详情页
  const runLink = page.locator('text=查看运行详情, a[href*="/runs/"]').first();
  if (await runLink.isVisible({ timeout: 3000 }).catch(() => false)) {
    await runLink.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${SHOT}/lt-run-detail.png` });
    console.log(`[${ts()}] 运行详情页已打开: ${page.url()}`);
  } else {
    console.log(`[${ts()}] [INFO] 未找到运行详情入口`);
  }
} finally {
  await browser.close();
}
console.log(`[${ts()}] 长任务实测脚本结束`);
