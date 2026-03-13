//收集时间，tracing+scripting版本
const puppeteer = require('puppeteer');
const fs = require('fs');

const execPath = "/opt/google/chrome/google-chrome";

async function runTracing(url) {
  const browser = await puppeteer.launch({
    headless: false,
    executablePath: execPath
  });

  const page = await browser.newPage();
  const client = await page.createCDPSession();

  // 1️⃣ 启动 Tracing（等价 DevTools Performance 面板）
  await client.send('Tracing.start', {
  categories: 
    'devtools.timeline,' +
    'v8.execute,' +
    'disabled-by-default-devtools.timeline,' +
    'disabled-by-default-devtools.timeline.frame,' +
    'blink.user_timing',
  options: 'sampling-frequency=10000'
});


  // 2️⃣ 触发页面加载
  await page.goto(url, { waitUntil: 'load' });

  // 3️⃣ 收集 Trace 数据
  const traceEvents = [];
  client.on('Tracing.dataCollected', e => {
    traceEvents.push(...e.value);
  });

  // 4️⃣ 停止 Tracing
  await client.send('Tracing.end');

  // 等待 Tracing.flush 完成
  await new Promise(resolve => {
    client.once('Tracing.tracingComplete', resolve);
  });

  // 5️⃣ 保存原始 trace（可导入 Chrome DevTools 查看）
  fs.writeFileSync(
    'trace.json',
    JSON.stringify({ traceEvents }, null, 2)
  );

  // 6️⃣ 解析 DevTools 等价的四大时间
  const result = analyzeTrace(traceEvents);

  console.log('\n✅ DevTools 等价性能数据（单位 ms）');
  console.table(result);

  // await browser.close();
}

// ✅ 等价 DevTools 面板分类统计
function analyzeTrace(events) {
  let scripting = 0;
  let rendering = 0;
  let painting = 0;
  let loading = 0;

  for (const e of events) {
    if (!e.cat || !e.dur) continue;

    const dur = e.dur / 1000; // μs → ms

    if (e.cat.includes('devtools.timeline')) {
      // Scripting
      if (
        ['FunctionCall', 'EvaluateScript', 'RunMicrotasks'].includes(e.name)
      ) {
        scripting += dur;
      }

      // Rendering
      if (
        ['UpdateLayoutTree', 'Layout', 'RecalculateStyles'].includes(e.name)
      ) {
        rendering += dur;
      }

      // Painting
      if (
        ['Paint', 'CompositeLayers', 'PrePaint'].includes(e.name)
      ) {
        painting += dur;
      }
    }

    // Loading（网络 + 解析）
    if (e.cat.includes('loading')) {
      loading += dur;
    }
  }

  return {
    Scripting: scripting.toFixed(2),
    Rendering: rendering.toFixed(2),
    Painting: painting.toFixed(2),
    Loading: loading.toFixed(2)
  };
}

// ✅ 入口
runTracing('https://www.zhihu.com');
