const fs = require("fs");
const puppeteer = require("puppeteer");
const path = require("path");

const baseConfig = JSON.parse(fs.readFileSync("./config.json", "utf-8"));
const dataset = JSON.parse(fs.readFileSync("./dataset.json", "utf-8"));
const paramGroups = JSON.parse(fs.readFileSync("./param_groups.json", "utf-8"));


async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ✅ 防死锁版 waitForPageIdle
async function waitForPageIdleSafe(page, hardTimeout = 20000) {
  return Promise.race([
    (async () => {
      // 网络 idle
      await page.waitForNetworkIdle({ idleTime: 500, timeout: 15000 });

      // 渲染 idle（原逻辑保留）
      await page.evaluate(() => {
        return new Promise(resolve => {
          let last = performance.now();
          let idleCount = 0;

          function checkIdle(now) {
            const diff = now - last;
            last = now;

            if (diff < 17.5) idleCount++;
            else idleCount = 0;

            if (idleCount >= 3) resolve();
            else requestAnimationFrame(checkIdle);
          }

          requestAnimationFrame(checkIdle);
        });
      });
    })(),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("waitForPageIdle-hard-timeout")), hardTimeout)
    )
  ]);
}


//监听LCP
async function waitForLCP(page, timeout = 20000) {
  return page.evaluate(async (timeout) => {
    return new Promise((resolve, reject) => {
      let timer = setTimeout(() => {
        reject(new Error("LCP-timeout"));
      }, timeout);

      const observer = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        if (entries.length > 0) {
          const lcpEntry = entries[entries.length - 1];
          observer.disconnect();
          clearTimeout(timer);
          resolve({
            startTime: lcpEntry.startTime,
            size: lcpEntry.size,
            element: lcpEntry.element ? lcpEntry.element.tagName : null
          });
        }
      });

      observer.observe({ type: "largest-contentful-paint", buffered: true });
    });
  }, timeout);
}

//Idle总控：调用PageIdle和LCP
async function waitForAnyIdle(page, totalTimeout = 30000) {
  return Promise.race([
    // 1️⃣ 原有 network + rAF idle
    waitForPageIdleSafe(page, totalTimeout),

    // 2️⃣ LCP 判据
    waitForLCP(page, totalTimeout)
  ]);
}


//跑单次实验
async function runSingleExperiment(paramGroup, targetUrl) {
  console.log(`\n----------`);
  console.log(`开始实验: 参数组=${paramGroup.name}, 页面=${targetUrl}`);

  const launchArgs = baseConfig.args.concat(paramGroup.args);
  const execPath = baseConfig.executablePath;

  let browser;
  let page;
  let traceEvents = [];
  const t0 = Date.now();

  try {
    // ✅ 加入 protocolTimeout
    browser = await puppeteer.launch({
      headless: baseConfig.headless,
      userDataDir: baseConfig.userDataDir,
      defaultViewport: null,
      executablePath: execPath,
      args: launchArgs,
      protocolTimeout: 120000,
      timeout: 120000
    });

    page = await browser.newPage();


    // ✅ 统一 60s 超时
    page.setDefaultTimeout(60000);
    page.setDefaultNavigationTimeout(60000);

    // ✅ 防死锁 goto
    await Promise.race([
      page.goto(targetUrl, {
        waitUntil: "domcontentloaded",
        timeout: 60000
      }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("goto-hard-timeout")), 70000)
      )
    ]);

    // ✅ 防死锁 idle 等待
    //await waitForPageIdleSafe(page, 20000);
    //判断页面是否空闲,"idle"
    //anyIdle包含三种，networkIdle+渲染Idle+LCP判断
    await waitForAnyIdle(page, 30000);

   
    const t1 = Date.now();
    const timeUsed = t1 - t0;

    console.log(`✔ 页面加载完成: ${targetUrl}`);
    console.log(`✔ 参数组: ${paramGroup.name}`);
    console.log(`✔ 加载时间: ${timeUsed} ms`);

    // ✅ M5（临时版）：保存为 JSON 文件，记录json文件模拟数据库
    const outDir = path.join(__dirname, "results");
    if (!fs.existsSync(outDir)) fs.mkdirSync(outDir);

    const safeName = targetUrl.replace(/https?:\/\//, "").replace(/[\/:?]/g, "_");

    const outPath = path.join(
      outDir,
      `${paramGroup.name}_${safeName}.json`
    );

    const finalResult = {
      experiment: {
        url: targetUrl,
        param_group: paramGroup.name,
        load_time_ms: timeUsed,
        success: true
      },
      //script_performance: scriptPerf
    };

    fs.writeFileSync(outPath, JSON.stringify(finalResult, null, 2));



    return {
      success: true,
      timeUsed
    };

  } catch (err) {
    console.log(`❌ 实验失败: ${err.message || err}`);
    return {
      success: false,
      timeUsed: null
    };

  } finally {
    // ✅ 防止 browser.close() 自身卡死
    if (page) {
      try { await page.close(); } catch {}
    }
    if (browser) {
      try {
        await Promise.race([
          browser.close(),
          new Promise(r => setTimeout(r, 3000))
        ]);
      } catch {}
    }
  }
}

async function main() {
  console.log(`将运行 ${paramGroups.length} 组参数 x ${dataset.length} 个页面\n`);

  for (const pg of paramGroups) {
    console.log(`\n=== 参数组：${pg.name} ===`);

    for (const url of dataset) {
      await runSingleExperiment(pg, url);

      // ✅ 保留你的冷却时间
      await sleep(500);
    }
  }

  console.log("\n✅ 全部实验完成！");
}

main();
