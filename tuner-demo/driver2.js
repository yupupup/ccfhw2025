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

    
    // 点击右侧按钮
    console.log('[3] 等待按钮出现');
    await page.waitForSelector('div.right-btn', { visible: true, timeout: 5000 });
    
    console.log('[4] 点击字号下拉按钮');
    await page.click('div.component-select-group.float-font-size > div.right-btn', {delay: 100, timeout: 5000});

    // 等待字体菜单出现

    console.log('[5] 等待字体选择菜单');
    await page.waitForSelector('div.panel-item.wpp-kdesign-panel-item', { visible: true, timeout: 5000 });
    // 开始性能追踪
    await page.tracing.start({
      path: 'font-c7hange-trace.json',
      categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'v8']
    });

    const t0 = await page.evaluate(() => performance.now());

    // 选择72号字体
    console.log('[6] 选择 72 号字体');
    await page.evaluate(() => {
      const sizeOptions = Array.from(document.querySelectorAll('div.panel-item.wpp-kdesign-panel-item'));
      const targetSize = sizeOptions.find(el => {
        // 同时匹配文本内容和自定义属性
        return el.textContent.includes('72') || 
               el.getAttribute('data-value') === '72';
      });
      
      if (targetSize) {
        targetSize.click();
      } else {
        throw new Error('未找到 72 号字体选项');
      }
    });


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

    console.log('[7] 字号已设置为 72');

    console.log(`time consumed: ${(t1 - t0).toFixed(2)} ms`);

    console.log('[8] 点击字号下拉按钮');
    await page.click('div.component-select-group.float-font-size > div.right-btn', {delay: 100, timeout: 5000});
  
    console.log('[9] 等待字体选择菜单');
    await page.waitForSelector('div.panel-item.wpp-kdesign-panel-item', { visible: true, timeout: 5000 });



    // 选择 40 号字体
    console.log('[10] 选择 40 号字体');
    await page.evaluate(() => {
      const sizeOptions = Array.from(document.querySelectorAll('div.panel-item.wpp-kdesign-panel-item'));
      const targetSize = sizeOptions.find(el => {
        // 同时匹配文本内容和自定义属性
        return el.textContent.includes('40') || 
               el.getAttribute('data-value') === '40';
      });
      
      if (targetSize) {
        targetSize.click();
      } else {
        throw new Error('未找到 40 号字体选项');
      }
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

  console.log('[11] exit');
  await browser.close();
})();
