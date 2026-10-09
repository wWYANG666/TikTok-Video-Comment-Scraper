# TikTok 内容采集器

一个在本地运行的 TikTok 公开内容采集工具。输入关键词后，可以查看搜索命中的视频、互动数据、主评论和回复，并导出视频结果。

默认以游客模式访问当前浏览器可以查看的公开内容。能否获得数据取决于 TikTok 的访问状态、网络环境和页面结构。

如果这个项目对你有帮助，欢迎在 GitHub 点一个 **Star**。你的支持会帮助项目继续改进。

## 快速开始

### 1. 下载并解压

下载仓库 ZIP 或分享版 ZIP，将其完整解压到有写入权限的文件夹，再打开包含 `setup.bat` 和 `start.bat` 的目录。不要直接在压缩包内运行脚本。

以下双击安装流程适用于 Windows，首次安装需要联网。

### 2. 安装环境

双击 `setup.bat`，等待窗口显示：

```text
Installation complete. Double-click start.bat to run the app.
```

安装脚本会：

1. 检查 Python 3.12；缺少时尝试通过 WinGet 为当前用户安装。
2. 在项目目录创建独立的 `.venv` 环境。
3. 安装 `requirements.txt` 中指定的依赖。
4. 安装 Playwright Chromium，并检查应用导入、依赖一致性和浏览器文件。

浏览器组件需要下载，首次安装可能耗时几分钟。如果 Python 和 WinGet 都未安装，先安装 [Python 3.12](https://www.python.org/downloads/windows/)，再重新运行 `setup.bat`。安装失败时保留窗口中的完整错误信息。

### 3. 启动程序

双击 `start.bat`，保持服务窗口打开，然后在浏览器访问：

**<http://127.0.0.1:8000>**

以后通常只需双击 `start.bat`。环境或浏览器组件缺失时，启动脚本会调用安装程序修复。首次启动会自动创建空数据库，分享版不包含历史采集结果。

停止服务时，在服务窗口按 `Ctrl+C`。建议等待当前采集任务结束后再停止。

## 创建采集任务

1. 在首页输入自己的搜索关键词。
2. 设置视频数量、单视频主评论数量和单评论回复数量。
3. 点击“开始采集”，进入任务详情页。
4. 程序会打开采集浏览器。采集期间保持服务窗口与采集浏览器打开，避免手动切换其页面。
5. 点击结果中的视频，查看主评论和嵌套回复。

首次使用建议设置为 **1 个视频、5 条主评论、每条最多 3 条回复**，确认当前网络能正常访问 TikTok 后再增加数量。

### 参数说明

| 参数 | 默认值 | 可设置范围 | 含义 |
| --- | --- | --- | --- |
| 视频数量 | 10 | 1–50 | 本次最多处理的视频数 |
| 单视频主评论 | 50 | 0–500 | 每个视频最多采集的一级评论数；设为 0 时跳过评论采集 |
| 单评论回复 | 20 | 0–100 | 本次为每条主评论最多采集的回复数；设为 0 时跳过回复补充 |

数量都是上限，不保证一定达到。公开结果不足、评论无法加载或阶段超时，都可能导致实际数量较少。回复不占用主评论名额。

程序先保存搜索结果，再采集主评论，最后补充回复，因此视频可能先出现，评论随后更新。等待中、执行中的任务详情页通常每 5 秒自动刷新；从后台切回标签页后若没有继续更新，可以手动刷新。

## 查看、导出和删除

- **任务列表**：查看状态、结果数量和北京时间；关键词搜索与状态筛选作用于当前页。
- **视频详情**：查看描述、作者、互动数据和评论线程；超过两条的回复可展开或收起，评论搜索作用于当前页。
- **导出 CSV**：在任务详情点击“导出 CSV”。当前导出包含视频信息和已采集评论数量，不包含评论正文。
- **重新采集**：对未执行中的任务再次运行，可能复用已有视频和评论数据。
- **删除任务**：点击删除并确认。等待中、执行中的任务不能删除；任务关联会从数据库移除，无其他任务引用的视频及评论也会删除。

同一个视频可以关联多个任务，评论按视频共享。重新采集得到的新数据可能影响其他任务中该视频的展示；当前没有保存每次采集的独立历史快照。

数量参数只限制本次采集，不会清空已保存的数据。视频详情和 CSV 中的评论数量是累计数据，因此可能超过本次设置的上限；设置为 0 也不会隐藏历史评论。

## 数据保存与分享

| 文件或目录 | 内容 |
| --- | --- |
| `tiktok.db` | 任务、视频、评论与关联记录 |
| `output/raw/<执行时间-关键词>/` | 捕获的原始 JSON 响应与失败诊断截图 |
| `.playwright-guest-profile/` | 独立采集浏览器的持久化会话、Cookie 和页面设置 |
| `.venv/` | 当前电脑安装的 Python 运行环境 |

删除任务只清理相关数据库记录，不会删除原始 JSON、截图或浏览器会话。备份数据库时，先停止服务，再复制 `tiktok.db`。

原始响应中保存的请求地址会限制查询参数，但响应正文保留原始字段，可能包含用户名、评论和带签名的媒体地址。浏览器配置也可能包含用户手动登录后留下的会话，不应随源码公开分享。

从源码目录重新打包时，双击 `make-share-package.bat`，发送生成的 `TikTok-Collector-share.zip`。该包只包含源码、测试、安装脚本和说明，接收者重新安装环境即可使用。邮件服务可能拦截包含安装脚本的附件，可以分享仓库或网盘下载链接。

## 常见问题

| 问题 | 处理方式 |
| --- | --- |
| 安装提示找不到 Python 或 WinGet | 安装 Python 3.12 后重试；刚安装完成仍找不到时，关闭窗口再运行 `setup.bat` |
| 下载依赖或 Chromium 失败 | 检查网络是否允许访问 PyPI 和浏览器下载服务，保留错误后重新运行 `setup.bat` |
| 提示 `.venv` 的 Python 版本不匹配 | 关闭服务，将旧 `.venv` 重命名后重新安装；不要复制其他电脑的 `.venv` |
| 提示端口被占用 | 关闭已经运行的服务，或按下方说明更换端口 |
| 页面无法打开 | 确认 `start.bat` 窗口中已出现 `Uvicorn running`，并使用窗口显示的地址 |
| 搜索不到视频、HTTP 403、评论为 0 | 检查采集浏览器能否显示 TikTok 搜索和视频页面，并查看任务错误与 `output/raw/` 中的诊断文件 |
| 实际数量少于设置值 | 设置值是采集上限；可用数据不足、加载失败或超时都可能提前结束 |
| 重新采集后数据没有变化 | 可能命中了已有评论缓存；当前缓存没有自动过期或页面上的强制刷新选项 |
| 服务重启后任务仍未完成 | 后台任务不会自动恢复。当前没有自动重置中断任务的功能，停止服务前应尽量等待任务结束 |

安装完成只表示本地环境已配置，仍需确认当前网络能够访问 TikTok。任务显示“已完成”也不代表获取到了平台全部评论，应同时核对实际结果数量。

## 高级设置

在项目目录的 PowerShell 中设置环境变量后启动。关闭该 PowerShell 窗口后，以下设置不会保留。

### 更换服务端口

```powershell
$env:TIKTOK_PORT = "8080"
.\start.bat
```

浏览器访问 <http://127.0.0.1:8080>。`TIKTOK_PORT` 由 `start.bat` 读取；直接调用 Uvicorn 时，需要自行传入 `--port`。

### 指定采集浏览器

默认优先查找系统安装的 Edge 或 Chrome，没有找到时使用 Playwright Chromium。可指定有效的浏览器可执行文件路径：

```powershell
$env:TIKTOK_BROWSER_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
.\start.bat
```

### 无头模式

默认会显示采集浏览器。如需无头模式，可设置：

```powershell
$env:TIKTOK_HEADLESS = "1"
.\start.bat
```

TikTok 在无头模式下可能返回不同内容，建议先确认该模式在当前环境可用。

## 手动安装与运行

以下命令在已安装 Python 3.12 的 Windows PowerShell 中执行。无需激活虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 开发说明

主要技术栈为 FastAPI、SQLAlchemy、SQLite、Jinja2 和 Playwright。采集优先解析浏览器的网络响应，页面 DOM 作为备用；任务之间串行执行，单任务最多同时处理两个视频页面。

```text
app/
├── crawler/       # 浏览器采集与网络响应解析
├── templates/     # 页面模板
├── static/        # 样式与交互
├── config.py      # 路径配置
├── database.py    # 数据库初始化
├── models.py      # 任务、视频与评论模型
├── services.py    # 采集调度、持久化与导出
└── main.py        # Web 路由
tests/             # 自动化测试
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

当前部分测试会触发应用数据库初始化，建议在独立项目副本中执行。

## 当前限制

- 面向本机单用户使用，默认只监听 `127.0.0.1`。
- 依赖 TikTok 的公开页面和接口，页面结构、地区策略及访问状态变化可能影响采集。
- 不保证获得全部视频、评论或回复，部分回复仅能在当前浏览器会话允许时加载。
- 后台任务随服务进程运行，暂不支持重启恢复、任务取消或独立任务队列。
- 视频与评论跨任务共享，尚无采集结果快照、缓存自动过期和逐视频阶段状态。

---

## English Documentation

### TikTok Video & Comment Scraper

A local tool for collecting publicly accessible TikTok videos, engagement data, top-level comments, and replies by keyword. Results are stored in SQLite and displayed in a local web interface.

The collector uses a guest browser session and can only read content visible in the current environment. Results depend on TikTok availability, network conditions, regional policies, and page structure.

If this project is useful to you, please consider giving it a **Star** on GitHub. Your support helps the project continue to improve.

## Quick Start on Windows

### 1. Download and extract

Download the repository ZIP or the share package, extract it completely into a writable folder, and open the folder containing `setup.bat` and `start.bat`. Do not run scripts directly from inside the ZIP archive.

The one-click setup below is for Windows and requires an internet connection the first time.

### 2. Install the environment

Double-click `setup.bat` and wait until the window shows:

```text
Installation complete. Double-click start.bat to run the app.
```

The setup script will:

1. Check for Python 3.12 and try to install it for the current user with WinGet if it is missing.
2. Create an isolated `.venv` environment in the project directory.
3. Install the pinned dependencies from `requirements.txt`.
4. Install Playwright Chromium and verify the application imports, dependencies, and browser files.

The browser download may take a few minutes. If both Python and WinGet are unavailable, install [Python 3.12](https://www.python.org/downloads/windows/) first and run `setup.bat` again. Keep the setup window open if it reports an error.

### 3. Start the application

Double-click `start.bat`, keep the server window open, and visit **<http://127.0.0.1:8000>**.

After the first setup, you normally only need to double-click `start.bat`. If dependencies or browser components are missing, the startup script runs the setup process again. A new empty database is created on first launch; the share package does not include previous collection results.

Press `Ctrl+C` in the server window to stop the application. Let an active collection task finish before stopping the service when possible.

## Create a collection task

1. Enter a keyword on the home page.
2. Set the video count, top-level comment limit, and reply limit.
3. Click **开始采集** to create a task.
4. The application opens a collection browser. Keep both the server window and collection browser open during collection.
5. Open a result video to view top-level comments and nested replies.

For the first run, use **1 video, 5 top-level comments, and up to 3 replies per comment**. Increase the limits after confirming that TikTok is accessible from the current network.

### Parameters

| Parameter | Default | Range | Description |
| --- | ---: | ---: | --- |
| Video count | 10 | 1–50 | Maximum number of videos processed in this task |
| Top-level comments per video | 50 | 0–500 | Maximum number of top-level comments collected per video; `0` skips comment collection |
| Replies per comment | 20 | 0–100 | Maximum number of replies collected for each top-level comment in this run; `0` skips reply collection |

These values are limits, not guarantees. Fewer results may be returned when public results are unavailable, comments cannot be loaded, or a stage times out. Replies do not consume the top-level comment limit.

Search results are saved first, followed by top-level comments and then replies, so videos may appear before comments finish loading. Task detail pages usually refresh every five seconds while a task is pending or running. If a background tab does not continue refreshing after you return to it, refresh the page manually.

## View, export, and delete

- **Task list**: view status, result counts, and Beijing time; keyword search and status filters apply to the current page.
- **Video details**: view descriptions, authors, engagement metrics, and comment threads. Replies beyond the first two can be expanded or collapsed.
- **CSV export**: click **导出 CSV** on a task page. The current export contains video metadata and collected comment counts, not comment text.
- **Rerun**: rerun a task that is not currently executing. Existing video and comment data may be reused.
- **Delete**: confirm deletion from the task list or task detail page. Pending and running tasks cannot be deleted. Unreferenced videos and comments are deleted with the task.

The same video can be linked from multiple tasks, and comments are shared by video. New collection data may therefore affect how that video appears in another task; independent per-run snapshots are not implemented yet.

The limits above apply only to the current collection run and do not delete stored data. Video details and CSV output use cumulative stored comments, so counts may exceed the limits of one run; setting a limit to `0` does not hide historical comments.

## Data and sharing

| File or directory | Contents |
| --- | --- |
| `tiktok.db` | Tasks, videos, comments, and relationships |
| `output/raw/<timestamp-keyword>/` | Captured raw JSON responses and failure screenshots |
| `.playwright-guest-profile/` | Persistent browser session, cookies, and page settings used by the collector |
| `.venv/` | Python environment installed on the current computer |

Deleting a task removes related database records but does not remove raw JSON, screenshots, or browser session files. Stop the service before copying `tiktok.db` for backup.

Raw response bodies may contain usernames, comments, and signed media URLs. A persistent browser profile may also contain a session left by a manual login. Do not publish these files with source code.

To create a clean share package, double-click `make-share-package.bat` and send the generated `TikTok-Collector-share.zip`. The package contains source code, tests, setup scripts, and documentation, but excludes local databases, browser profiles, raw output, and virtual environments. Some mail services block ZIP attachments containing scripts; use a repository or cloud storage link when necessary.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Python or WinGet is missing | Install Python 3.12 and run `setup.bat` again; if it was just installed, close the window and retry |
| Dependency or Chromium download fails | Check access to PyPI and the Playwright browser download service, then rerun `setup.bat` |
| `.venv` uses the wrong Python version | Stop the service, rename the old `.venv`, and run setup again; do not copy a `.venv` from another computer |
| Port is already in use | Stop the existing service, or set `TIKTOK_PORT` as described below |
| The page does not open | Confirm that the server window shows `Uvicorn running` and use the address printed there |
| No videos, HTTP 403, or zero comments | Check whether the collection browser can display TikTok search and video pages, then inspect the task error and `output/raw/` diagnostics |
| Fewer results than requested | The configured numbers are upper limits; unavailable data, loading failures, and timeouts can end a stage early |
| Rerunning produces no visible change | The task may be reusing existing comment cache; automatic cache expiry and a force-refresh control are not implemented |
| A task remains unfinished after a restart | Background tasks do not resume automatically. Try rerunning the task after starting the service again |

Successful local installation only confirms that the environment is configured. TikTok must still be reachable from the current network, and a task marked complete does not mean that all platform comments were collected.

## Advanced settings

Set environment variables in PowerShell before starting. They apply only to that PowerShell window.

### Change the server port

```powershell
$env:TIKTOK_PORT = "8080"
.\start.bat
```

Open <http://127.0.0.1:8080>. `start.bat` reads `TIKTOK_PORT`; when calling Uvicorn directly, pass `--port` yourself.

### Select the collection browser

The collector first looks for an installed Edge or Chrome and falls back to Playwright Chromium. You can provide a browser executable explicitly:

```powershell
$env:TIKTOK_BROWSER_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
.\start.bat
```

### Headless mode

The collection browser is visible by default. To use headless mode:

```powershell
$env:TIKTOK_HEADLESS = "1"
.\start.bat
```

TikTok may return different content in headless mode, so verify it in the current environment first.

## Manual installation and running

Run these commands in Windows PowerShell with Python 3.12 installed. Activating the virtual environment is optional:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Development notes

The main stack is FastAPI, SQLAlchemy, SQLite, Jinja2, and Playwright. The collector prioritizes browser network responses and uses the DOM as a fallback. Tasks run serially, with up to two video pages processed concurrently inside one task.

```text
app/
├── crawler/       # Browser collection and network response parsing
├── templates/     # HTML templates
├── static/        # Styles and browser interactions
├── config.py      # Path configuration
├── database.py    # Database initialization
├── models.py      # Task, video, and comment models
├── services.py    # Scheduling, persistence, and export
└── main.py        # Web routes
tests/             # Automated tests
```

Run tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Some tests initialize the application database, so run them in an isolated project copy when protecting an existing local database matters.

## Current limitations

- Designed for local single-user use and bound to `127.0.0.1` by default.
- Depends on TikTok public pages and APIs; page structure, regional policies, and access status can affect collection.
- Does not guarantee all videos, comments, or replies; reply visibility depends on the current guest browser session.
- Background tasks run inside the service process and currently do not support restart recovery, cancellation, or a separate job queue.
- Videos and comments are shared across tasks; per-run result snapshots, automatic cache expiry, and per-video stage status are not implemented yet.
