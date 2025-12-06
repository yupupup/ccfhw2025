# 1.首先配置全局代理

```
echo 'export http_proxy="http://s4plus:s4plususer@127.0.0.1:17890"' >> ~/.zshrc
echo 'export https_proxy="http://s4plus:s4plususer@127.0.0.1:17890"' >> ~/.zshrc
```

执行生效：

```
source ~/.zshrc
```

 测试代理是否生效

  curl：

```
curl https://google.com -I
```

如果返回 200 或 301，就说明代理 OK。

  下一步：测试 Git 是否真的走代理（很重要）

```
git ls-remote https://github.com/chromium/chromium.git
```

如果能列出 HEAD 信息，则 git 代理成功。

---

# 2.拉取chromium项目
**步骤1：clone源码**

可选加速：使用浅克隆（如果你不需要历史记录）

```
git clone --depth 1 https://chromium.googlesource.com/chromium/src.git chromium
```

这样只下载最新一份代码（几 GB），速度会快很多。



**步骤 2：执行 gclient config**

**方式 A：官方源（有代理即可）**（从googlesource.com克隆）

```
gclient config https://chromium.googlesource.com/chromium/src.git
```

**步骤 3：开始真正的同步**

```
gclient sync
```

gclient 会自动：

- 下载所有 DEPS 子模块
- 同步工具链
- 拉取需要的第三方依赖
- 与 main 分支对齐

> 建议tmux new -s chrome挂载在后台运行，gclient sync跑了5个小时

---

# 检验

### Step 1：检查 gclient 是否真的同步成功

进入 src：

```
cd ~/chromium/src
gclient sync
```

如果显示：

```
(sync completed successfully)
No changes.
```

说明你的 src **是完整的**。

如果同步过程中：

- 仍出现 `_bad_scm`
- 仍出现 clone 错误
- 或者需要继续下载几 GB

说明：**你的 src 目录不完整，必须修复或重来。**

------

### Step 2：检查是否包含 chromium 的关键组件

在 src 下执行：

```
ls -d chrome content v8 third_party buildtools tools
```

如果都存在，则目录结构正常。

------

### Step 3：测试 gn 是否能生成构建目录

```
gn gen out/Default
```

如果成功生成：

```
out/Default/build.ninja
```

说明你的源码完整到可以构建。

如果失败，报缺文件、缺 third_party，这说明你的 src **并不完整**。

------

### Step 4：测试 chromium 是否可构建（最关键）

```
ninja -C out/Default chrome
```

如果这里成功编译，那你已经可以进行自动页面加载测试任务。



## 问题

###  **1. GN 找不到：你没有把 depot_tools 加到 PATH**

**必须在当前 Shell 加载 depot_tools**：

```
export PATH="$HOME/depot_tools:$PATH"
```

然后确认 GN 是否能找到：

```
which gn
```

如果输出像：

```
/home/rmy/depot_tools/gn
```

就正常了。

###  **2. .gclient_entries 缺失：你的 src 不是通过 gclient sync 完整拉取的**

 解决：重新让 gclient 补全 metadata（不会重新下载全部）

在 `/home/rmy/chromium` 目录执行：

```
cd ~/chromium
gclient sync
```

它会重新生成：

```
.gclient_entries
.gclient_previous_sync_commits
```

### **3. 然后再生成构建目录**

确保在 `src/`：

```
cd ~/chromium/src/
gn gen out/Default
```

生成：

```go
➜  src git:(d1a23b9f43d07) gn gen out/Default
Done. Made 28718 targets from 4343 files in 6487ms
```

### **4.开始构建 Chrome**

在 `src/` 目录中执行：

```
ninja -C out/Default chrome
```

```go
➜  src git:(d1a23b9f43d07) ninja -C out/Default chrome
ninja: Entering directory `out/Default'
[55381/55381] LINK ./chrome
```

**恭喜！你已经完整成功编译出 Chromium（chrome 二进制）！**

现在你已经有了可用的 Chrome 浏览器

你的可执行文件在：

```
src/out/Default/chrome
```

你可以直接运行：

```
./chrome --headless
```
