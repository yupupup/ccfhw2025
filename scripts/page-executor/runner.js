const fs = require("fs");
const puppeteer = require("puppeteer");

// ---- 加载基础配置 ----
const baseConfig = JSON.parse(fs.readFileSync("./config.json", "utf-8"));
const dataset = JSON.parse(fs.readFileSync("./dataset.json", "utf-8"));
const paramGroups = JSON.parse(fs.readFileSync("./param_groups.json", "utf-8"));

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// 页面 idle 判定（渲染 idle + 网络 idle）
async function waitForPageIdle(page) {
  // 等待网络 idle
  await page.waitForNetworkIdle({ idleTime: 500, timeout: 15000 });

  // 等待渲染（使用 requestAnimationFrame）
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
}

async function runSingleExperiment(paramGroup, targetUrl) {
  console.log(`\n----------`);
  console.log(`开始实验: 参数组=${paramGroup.name}, 页面=${targetUrl}`);

  // 启动参数 = 基础 args + paramGroup.args
  const launchArgs = baseConfig.args.concat(paramGroup.args);

  // 启动浏览器
const browser = await puppeteer.launch({
  headless: baseConfig.headless,
  userDataDir: baseConfig.userDataDir,
  defaultViewport: null,

  executablePath: "/home/rmy/chromium/src/out/Default/chrome",

  args: launchArgs
});


  const page = await browser.newPage();

  const t0 = Date.now();

  try {
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 20000 });
    await waitForPageIdle(page);

    const t1 = Date.now();
    const timeUsed = t1 - t0;

    console.log(`✔ 页面加载完成: ${targetUrl}`);
    console.log(`✔ 参数组: ${paramGroup.name}`);
    console.log(`✔ 加载时间: ${timeUsed} ms`);

    await browser.close();

    return {
      success: true,
      timeUsed
    };
  } catch (err) {
    console.log(`❌ 实验失败: ${err}`);

    await browser.close();

    return {
      success: false,
      timeUsed: null
    };
  }
}

async function main() {
  console.log(`========== Phase1 + Phase2 ==========`);
  console.log(`将运行 ${paramGroups.length} 组参数 x ${dataset.length} 个页面\n`);

  for (const pg of paramGroups) {
    console.log(`\n=== 参数组：${pg.name} ===`);

    for (const url of dataset) {
      await runSingleExperiment(pg, url);
      await sleep(500); // 两次实验之间稍微休息避免干扰
    }
  }

  console.log("\n全部实验完成！");
}

main();
