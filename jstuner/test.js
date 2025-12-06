//收集时间，Performance.getMetrics+ScriptDuration中精度版本
const puppeteer = require('puppeteer');

async function main() {
  const browser = await puppeteer.launch({
    headless: false
  });

  const page = await browser.newPage();

  const client = await page.createCDPSession(); // ✅ 现在合法了
  await client.send('Performance.enable');
  await client.send('Page.enable');

  await page.goto('https://www.jd.com', { waitUntil: 'load' });

  const { metrics } = await client.send('Performance.getMetrics');

  const scripting = metrics.find(m => m.name === 'ScriptDuration');
  console.log('✅ ScriptDuration =', scripting?.value);

  //await browser.close();
}

main(); // ✅ 必须调用
