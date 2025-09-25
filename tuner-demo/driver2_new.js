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
    await page.waitForSelector('div.shortcut_box', { visible: true, timeout: 2000 });
    await page.click('div.shortcut_box');
    
    // 全选内容
    console.log('[2] 全选内容');
    await page.keyboard.down('Control');
    await page.keyboard.press('KeyA');
    await page.keyboard.up('Control');

    
    // 点击右侧按钮
    console.log('[3] 等待按钮出现');
    await page.waitForSelector('div.right-btn', { visible: true, timeout: 2000 });
    
    console.log('[4] 点击字号下拉按钮');
    await page.click('div.component-select-group.float-font-size > div.right-btn', {delay: 100, timeout: 2000});

    // 等待字体菜单出现
    console.log('[5] 等待字体选择菜单');
    await page.waitForSelector('div.panel-item.wpp-kdesign-panel-item', { visible: true, timeout: 2000 });
    
    // 开始性能追踪
    await page.tracing.start({
      path: 'font-change-trace.json',
      categories: ['devtools.timeline', 'disabled-by-default-devtools.timeline', 'v8']
    });

    console.log('[6] 选择72号字体并测量时间');
    
    // 修改1: 将统计起始时间移到click之前
    // 修改2: 分别计算click用时和稳定用时
    // 修改3: 将所有操作放在同一个evaluate中以避免异步问题
    const {clickDuration, stableDuration, totalDuration} = await page.evaluate(async () => {
      // 记录开始时间
      const startTime = performance.now();
      
      // 选择72号字体
      const sizeOptions = Array.from(document.querySelectorAll('div.panel-item.wpp-kdesign-panel-item'));
      const targetSize = sizeOptions.find(el => 
          el.textContent.includes('72') || el.getAttribute('data-value') === '72'
      );
      if (!targetSize) throw new Error('未找到72号字体选项');
      
      // 记录点击前时间
      const beforeClickTime = performance.now();
      
      // 执行点击
      targetSize.click();
      
      // 记录点击后时间
      const afterClickTime = performance.now();
      
      // 计算点击用时
      const clickDuration = afterClickTime - beforeClickTime;
      
      // 等待高度条件满足
      const heightThreshold = 80;
      const stableStartTime = performance.now();
      
      // 使用Promise等待高度条件满足
      await new Promise((resolve) => {
        const checkStability = () => {
          const rects = document.querySelectorAll('.selectedRect');
          if (rects.length === 0) {
            requestAnimationFrame(checkStability);
            return;
          }
          
          const isStable = Array.from(rects).some(rect => {
            const height = parseFloat(rect.style.height);
            return height > heightThreshold;
          });
          
          if (isStable) {
            resolve();
          } else {
            requestAnimationFrame(checkStability);
          }
        };
        
        requestAnimationFrame(checkStability);
      });
      
      // 记录稳定完成时间
      const stableEndTime = performance.now();
      
      // 计算稳定用时和总用时
      const stableDuration = stableEndTime - stableStartTime;
      const totalDuration = stableEndTime - startTime;
      
      return {clickDuration, stableDuration, totalDuration};
    });

    console.log(`[7] 点击用时: ${clickDuration.toFixed(2)} ms`);
    console.log(`[8] 稳定用时: ${stableDuration.toFixed(2)} ms`);
    console.log(`[9] 总耗时: ${totalDuration.toFixed(2)} ms`);

    // 停止性能追踪
    await page.tracing.stop();

    console.log('[10] 点击字号下拉按钮');
    await page.click('div.component-select-group.float-font-size > div.right-btn', {delay: 100, timeout: 2000});
  
    console.log('[11] 等待字体选择菜单');
    await page.waitForSelector('div.panel-item.wpp-kdesign-panel-item', { visible: true, timeout: 2000 });

    // 选择 40 号字体
    console.log('[12] 选择 40 号字体');
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

  console.log('[13] exit');
  await browser.close();
})();