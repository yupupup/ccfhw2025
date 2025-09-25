const fs = require('fs');
const puppeteer = require('puppeteer');
const args = process.argv.slice(2);

// 读取 JSON 配置文件
const config = JSON.parse(fs.readFileSync('./config.json', 'utf-8'));

const excel_url = "https://www.kdocs.cn/l/cuh8SYwgFRbh";

for (let i = 1; i < args.length; i++) {
  if (args[i] === '--headless') config.headless = true;
  if (args[i].startsWith('--user-data-dir=')) {
    config.userDataDir = args[i].split('=')[1];
  }
  if (args[i].startsWith('--chrome-arg=')) {
    config.chromeArgs.push(args[i].split('=')[1]);
  }
}

(async () => {
  const browser = await puppeteer.launch({
    userDataDir: config.userDataDir,
    headless: false,
    defaultViewport: null,
    args: config.args
  });

  const page = await browser.newPage();

  const isGCExposed = await page.evaluate(() => {
    try {
      if (typeof gc === 'function') {
        gc();
        return true;
      }
      return false;
    } catch (error) {
      return false;
    }
  });

  if (isGCExposed) {
    console.log('✅ --js-flags=--expose-gc 已生效，window.gc() 可用');
  } else {
    console.log('❌ --js-flags=--expose-gc 未生效');
  }

  const docURL = excel_url;
  await page.goto(docURL, { waitUntil: 'networkidle2' });

  try {
    console.log('[1] 点击快捷框');
    await page.waitForSelector('div.shortcut_box', { visible: true, timeout: 30000 });
    await page.click('div.shortcut_box');
    
    // 全选内容
    console.log('[2] 全选内容');
    await page.keyboard.down('Control');
    await page.keyboard.press('KeyA');
    await page.keyboard.up('Control');

    // 开始性能追踪
    await page.tracing.start({
      path: 'font-c7hange-trace.json',
      categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'v8']
    });
    const t0 = await page.evaluate(() => performance.now());

    console.log('[3] 粘贴');
    await page.keyboard.down('Control');
    await page.keyboard.press('KeyV');
    await page.keyboard.up('Control');

    // 等待不再出现.selectedRect元素
    await page.evaluate(() => {
      return new Promise((resolve) => {
        const check = () => {
          if (document.querySelectorAll('div.selectedRect').length === 0) {
            resolve();
          } else {
            requestAnimationFrame(check);
          }
        };
        requestAnimationFrame(check);
      });
    });

    const t1 = await page.evaluate(() => performance.now());
    await page.tracing.stop();

    console.log('[4] 粘贴成功');
    console.log(`粘贴耗时: ${(t1 - t0).toFixed(2)} ms`);

    console.log('[5] 复原');
    await page.keyboard.down('Control');
    await page.keyboard.press('KeyZ');
    await page.keyboard.up('Control');

    // 等待页面稳定渲染后退出
    await page.evaluate(() => {
      return new Promise(resolve => {
        let last = performance.now();
        let idleCount = 0;

        function checkIdle(now) {
          const diff = now - last;
          last = now;

          if (diff < 17.5) {
            idleCount++;
          } else {
            idleCount = 0;
          }

          if (idleCount >= 3) {
            resolve();
          } else {
            requestAnimationFrame(checkIdle);
          }
        }

        requestAnimationFrame(checkIdle);
      });
    });

    console.log('[6] exit');
    await browser.close();
  } catch (e) {
    console.error('操作异常:', e);
  }
})();