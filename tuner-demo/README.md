# 使用OpenTuner+Puppeteer实现简单的浏览器调优

> [OpenTuner - An extensible framework for program autotuning](https://opentuner.org/): 自动化调优框架
>
> [Puppeteer | Puppeteer 中文网](https://pptr.nodejs.cn/): 通过 [开发工具协议](https://chromedevtools.github.io/devtools-protocol/) 或 [WebDriver 双向](https://pptr.nodejs.cn/webdriver-bidi) 控制 Chrome 或 Firefox的JavaScript库

**总览**：本demo尝试针对excel调整字体的测试场景（测试页面：https://docs.qq.com/sheet/DSWhFdkhOZEFBcm5y?tab=BB08J2）进行简单调优，以验证利用调优是否能够对指定页面的特定操作产生收益。

**测试上述场景加载性能的方式**：

1. 打开目标页面https://docs.qq.com/sheet/DSWhFdkhOZEFBcm5y?tab=BB08J2
2. 全选所有表格中的内容
3. 点击字号下拉选单
4. 将字体设置为48号（默认是10号）。从点击“48”开始作为加载的起点
5. 等待页面完成加载和渲染。在页面稳定后作为加载的终点
6. 上述起点和终点之间的时间作为一次加载的耗时

**调优配置的选择**：在进行调优之前需要明确调优的目标配置集合。作为demo，选择了文章[JavaScript Performance Tuning as a Crowdsourced Service | IEEE Journals & Magazine | IEEE Xplore](https://ieeexplore.ieee.org/abstract/document/10254365/?casa_token=2sAahfccB_UAAAAA:XkYQlSO2vHUnEvop8JLyLGZGnkyyZ-qYicO7TqZupNqitKA3HyqFakXMTKoGtby2dSn4JIuZLWVH_g)中筛选出的15个对于js性能最有影响的v8的参数进行调优。由于版本问题，本demo从中去掉了当前已经不可用的部分参数，并加入了`invocation-count-for-maglev`和`invocation-count-for-turbofan`（分别控制热点函数进入maglev和turbofan优化所需要的执行次数）。

**脚本实现说明**：本脚本主要包含以下三个文件：

* `web_page_driver.js`：负责启动chrome浏览器，打开目标页面，执行特定操作并记录该操作的加载耗时
* `tuner.py`：负责使用OpenTuner进行调优，并将每轮调优搜索得到的参数传递给`web_page_driver.js`并记录在该参数下执行特定操作的耗时
* `config.json`：包含用于启动chrome的参数

**性能记录的说明**：由于网页加载性能波动较强，有时候可能会出现极端数据影响调优搜索方向，因此在每次测试一个配置下的执行性能时，会进行五次执行，并在这五次中排除掉明显的离群极端数据，最后将剩下的数据的平均值作为该配置下的性能表现

## 环境准备与执行

安装Node.js和Python

安装OpenTuner：[OpenTuner - Getting Started](https://opentuner.org/tutorial/setup/)

安装Puppeteer：[Puppeteer | Puppeteer 中文网](https://pptr.nodejs.cn/#installation)

登录腾讯文档：因为操作腾讯文档之前需要登录才能进行编辑，所以需要预先完成登录。在这一步中，可以通过[config.json](./config.json)先设置一个本地的`userDataDir`，然后执行`node web_page_driver.js`打开目标页面并登录。

执行调优脚本：

```bash
python tuner.py
```

## 测试结果

使用调优器进行了45min的调优，共计56轮搜索，使用搜索得到的最佳配置和baseline的对比结果如下，端到端时延提升8.46%：

| 测试轮次 | 测试结果-baseline(ms) | 测试结果-tuning(ms) |       |
| -------- | --------------------- | ------------------- | ----- |
| 1        | 402.40                | 390.7               |       |
| 2        | 418.40                | 373.40              |       |
| 3        | 393.70                | 371.20              |       |
| 4        | 405.80                | 371.20              |       |
| 5        | 431.60                | 371.70              |       |
| 平均     | 410.38                | 375.64              | 8.46% |

