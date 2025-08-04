const fs = require('fs');
const puppeteer = require('puppeteer');
const args = process.argv.slice(2);

// 读取 JSON 配置文件
const config = JSON.parse(fs.readFileSync('./config.json', 'utf-8'));

const excel_url = "https://docs.qq.com/sheet/DSWhFdkhOZEFBcm5y?tab=BB08J2";

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
  // 启动浏览器并打开腾讯文档页面
  const browser = await puppeteer.launch({
    userDataDir: config.userDataDir,
    headless: false,
    defaultViewport: null,
    args: config.args
  });

  const page = await browser.newPage();

  const isGCExposed = await page.evaluate(() => {
    try {
      // 如果 gc() 存在，则参数生效
      if (typeof gc === 'function') {
        gc(); // 尝试调用垃圾回收（无报错则成功）
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

  // page.on('console', msg => console.log('PAGE LOG:', msg.text()));

  // 你需要把下面的链接换成你有权限访问的腾讯文档链接
  const docURL = excel_url; // 示例地址，请替换成真实可访问地址
  await page.goto(docURL, { waitUntil: 'networkidle2' });

  try {
    console.log('[1] 全选内容');
    await page.keyboard.down('Control');
    await page.keyboard.press('KeyA');
    await page.keyboard.up('Control');
  
    console.log('[2] 等待字号按钮出现');
    await page.waitForSelector('.buttons_icon-container__1Miuv', { visible: true, timeout: 5000 });
  
    console.log('[3] 点击字号下拉按钮');
    await page.evaluate(() => {
      const el = document.querySelector('#toolbar-button-font-size');
      if (el) el.click();
    });
  
    console.log('[4] 等待字号菜单项出现');
    await page.waitForFunction(() => {
      return Array.from(document.querySelectorAll('.dui-menu-item-text-container'))
        .some(el => el.textContent.trim() === '48');
    }, { timeout: 5000 });
  
    // 开始录制 trace，path 是保存文件名
    // await page.tracing.start({
    //   path: 'trace.json',
    //   categories: ['devtools.timeline', 'v8.execute', 'blink.user_timing']
    // });

    const t0 = await page.evaluate(() => performance.now());

    console.log('[5] 点击字号48');
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('.dui-menu-item-text-container'));
      const target = items.find(el => el.textContent.trim() === '48');
      if (target) target.click();
    });

    // // 等待字号按钮的 aria-label 变为 '48'，说明渲染完成
    // await page.waitForFunction(() => {
    //   const btn = document.querySelector('#toolbar-button-font-size');
    //   return btn && btn.getAttribute('aria-label') === '48';
    // }, { timeout: 10000 });
    // 等待页面稳定渲染后退出
  await page.evaluate(() => {
    return new Promise(resolve => {
      let last = performance.now();
      let idleCount = 0;

      function checkIdle(now) {
        const diff = now - last;
        last = now;

        // 判断帧率是否趋于稳定（即变化小）
        if (diff < 17.5) {
          idleCount++;
        } else {
          idleCount = 0; // 有跳帧，重置
        }

        if (idleCount >= 3) {
          resolve(); // 连续 3 帧稳定，认定渲染完成
        } else {
          requestAnimationFrame(checkIdle);
        }
      }

      requestAnimationFrame(checkIdle);
    });
  });

    const t1 = await page.evaluate(() => performance.now());
    // await page.tracing.stop();

    console.log('[6] 字号已设置为48');

    console.log(`time consumed: ${(t1 - t0).toFixed(2)} ms`);

    console.log('[7] 点击字号下拉按钮');
    await page.evaluate(() => {
      const el = document.querySelector('#toolbar-button-font-size');
      if (el) el.click();
    });
  
    console.log('[8] 等待字号菜单项出现');
    await page.waitForFunction(() => {
      return Array.from(document.querySelectorAll('.dui-menu-item-text-container'))
        .some(el => el.textContent.trim() === '48');
    }, { timeout: 5000 });

    console.log('[9] 点击字号10');
    await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('.dui-menu-item-text-container'));
      const target = items.find(el => el.textContent.trim() === '10');
      if (target) target.click();
    });

  } catch (e) {
    console.error('操作异常:', e);
  }

  // 等待页面稳定渲染后退出
  await page.evaluate(() => {
    return new Promise(resolve => {
      let last = performance.now();
      let idleCount = 0;

      function checkIdle(now) {
        const diff = now - last;
        last = now;

        // 判断帧率是否趋于稳定（即变化小）
        if (diff < 17.5) {
          idleCount++;
        } else {
          idleCount = 0; // 有跳帧，重置
        }

        if (idleCount >= 3) {
          resolve(); // 连续 3 帧稳定，认定渲染完成
        } else {
          requestAnimationFrame(checkIdle);
        }
      }

      requestAnimationFrame(checkIdle);
    });
  });

  console.log('[10] exit');

  await browser.close();
})();
