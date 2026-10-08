# TikTok 内容采集器

一个用于面试演示的轻量级项目：输入 TikTok 搜索关键词，采集主要视频及其评论，并在本地网页中展示视频与评论的关联。

## 功能

- 创建关键词采集任务
- TikTok 游客实时采集，无需登录账号
- 优先解析浏览器捕获的 TikTok JSON 响应，DOM 作为备用
- 保存视频、主评论、评论回复以及搜索任务关联
- 使用平台 ID 去重，任务可以重复运行
- 查看任务、视频详情和评论
- 导出任务视频 CSV
- SQLite 本地存储，无需额外数据库

## 项目结构

```text
app/
├── crawler/                  # 采集适配器
│   ├── network_capture.py
│   └── playwright_collector.py
├── templates/                # 管理页面
├── static/
├── database.py
├── models.py
├── services.py
└── main.py
tests/
```

数据关系：

```text
采集任务 --< task_videos >-- 视频 --< 评论
```

使用 `task_videos` 关联表的原因是：同一个视频可以被多个关键词或多次搜索命中。

## Windows 一键安装与启动

解压项目后，双击 `setup.bat`。脚本会检查 Python 3.12；如果没有安装，会尝试通过 Windows 的 WinGet 为当前用户安装。随后在项目目录创建 `.venv`、安装固定版本的 Python 依赖、下载 Playwright Chromium，并验证应用和浏览器。首次安装需要联网，浏览器下载通常占用数百 MB。

安装完成后双击 `start.bat`，访问 <http://127.0.0.1:8000>。以后只需双击 `start.bat`；如果环境或浏览器组件缺失，启动脚本会重新运行安装程序。

如果电脑没有 WinGet，先从 Python 官网安装 Python 3.12，再双击 `setup.bat`。如果公司网络阻止 PyPI 或 Playwright 浏览器下载，需要允许这些下载后重试。窗口会停留并显示具体失败步骤。

发送给其他人时，双击 `make-share-package.bat`，直接发送生成的 `TikTok-Collector-share.zip`。压缩包只包含源码、测试、安装脚本和说明，不包含 `.venv/`、`tiktok.db`、`output/`、`.playwright-guest-profile/` 或缓存目录。对方解压后双击 `setup.bat`，安装完成再双击 `start.bat`。

## 手动安装

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 运行

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

也可以在终端运行：

```powershell
.\start.bat
```

浏览器访问：<http://127.0.0.1:8000>

## 游客实时采集

在网页中输入关键词、视频数量、主评论数量和单条评论回复数量后直接创建任务。系统会打开可见浏览器，并使用独立的 `.playwright-guest-profile` 保存 TikTok 分配给游客的 Cookie 和页面设置，不包含登录账号。首次测试建议只采集 1 个视频、5 条主评论和每条 3 个回复。

默认优先使用系统安装的 Microsoft Edge 或 Google Chrome；如果没有找到，则使用 Playwright Chromium。也可以指定浏览器：

```powershell
$env:TIKTOK_BROWSER_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

不建议使用无头模式，因为 TikTok 可能向无头浏览器返回不同的搜索结果。仅在当前环境已经验证可用时启用：

```powershell
$env:TIKTOK_HEADLESS = "1"
python -m uvicorn app.main:app
```

游客实时采集只读取未登录浏览器能够正常查看的公开搜索结果和评论。TikTok 页面结构会变化，相关选择器集中在 `app/crawler/playwright_collector.py` 中。

视频页通常默认显示“猜你喜欢”。采集器会主动切换到“评论”标签，并等待首批评论节点或评论接口响应后再读取数据。

采集器会滚动评论区并自动点击可见的“查看其他回复”或 `View more replies` 按钮。主评论与回复分别限流，回复不会占用主评论数量；游客模式无法展开的回复会被跳过，不影响任务保存已经获得的数据。

每次实时任务捕获到的搜索、视频和评论原始 JSON 会保存到：

```text
output/raw/<执行时间-关键词>/
```

保存的请求地址只保留视频 ID、游标等必要参数，不保存 Cookie 或完整动态令牌。实时采集失败时，同一目录还会生成诊断截图。

## 测试

```powershell
python -m pytest
```

## 面试演示建议

1. 使用“牙科根管治疗”创建真实采集任务。
2. 展示任务、视频、评论三级数据。
3. 重复运行任务，说明视频和评论不会重复插入。
4. 创建第二个关键词任务，说明同一视频可以关联多个任务。
5. 导出 CSV。
6. 说明网络响应解析、DOM 兜底和评论延迟加载处理。

## 项目限制

- 这是单机面试项目，后台任务由 FastAPI 进程执行，服务重启后不会自动恢复。
- 回复完整度取决于 TikTok 对当前游客会话开放的数据以及页面结构。
- 游客实时模式依赖 TikTok 页面结构、地区和网络环境，不要求登录。
- 不包含验证码绕过、访问控制绕过或大规模并发采集。
