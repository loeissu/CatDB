# CatDB（豆包喵喵）项目构建任务书（完整版）

> **适用对象**：AI 编程助手 / 开发者  
> **项目基线**：基于 `shangaokun/CatDB` 原仓库代码，在此之上增量开发  
> **交付目标**：Windows 桌面客户端（含 GUI 窗口）+ Android 手机客户端（APK）  
> **版本号**：v2.2.0


## 一、项目背景与核心目标

CatDB 是一款基于 WebSocket 的局域网文字/语音输入上屏工具。手机端输入文字，电脑端光标处实时输出。

本次构建目标：

1. **保留现有能力**：WebSocket 实时同步、系统托盘静默运行、二维码扫码连接、Zeroconf 自动发现。
2. **新增桌面 GUI**：为 Windows 客户端增加可视化主窗口（pywebview），替代纯托盘操作模式。
3. **优化 Android 状态栏**：使手机状态栏背景色与网页背景色一致（纯色，不透明，不覆盖内容）。
4. **自动化打包**：通过 GitHub Actions 自动构建 Windows EXE 和 Android APK。


## 二、明确实施范围（本期做与不做）

### ✅ 本期实施
- Python 后端（aiohttp WebSocket 服务）
- 系统托盘（pystray）
- 桌面 GUI 窗口（pywebview，尺寸 920×660）
- 二维码扫码接入（居中展示）
- Zeroconf 自动发现
- 开机自启开关（可配置，状态持久化）
- Windows 单文件 EXE 打包（PyInstaller，无控制台）
- Android Debug APK 打包（Capacitor）
- Android 纯色状态栏（不透明，不覆盖 WebView 内容）
- GitHub Actions 自动构建（仅 Windows + Android）

### ❌ 本期不涉及
- 触控板模式（无后端实现，入口暂不添加）
- macOS / Linux 构建产物
- Android 沉浸式透明状态栏
- 应用内自动更新机制
- 单元测试与国际化


## 三、技术栈锁定

| 层级 | 选型 | 版本 |
|------|------|------|
| 后端语言 | Python | 3.12 |
| Web 框架 | aiohttp | 3.9+ |
| 桌面 GUI | pywebview | 5.0+ |
| 系统托盘 | pystray | 0.19+ |
| 二维码生成 | qrcode + Pillow | 7.4+ / 9.0+ |
| 键盘模拟 | pyautogui + pynput | 最新稳定版 |
| 打包工具 | PyInstaller | 6.0+ |
| Android 容器 | Capacitor | 6.0+ |
| CI 平台 | GitHub Actions | 最新版 |


## 四、实施阶段与子任务（按顺序执行）

### Phase 1：Python 后端改造（server.py）

| # | 操作 | 说明 |
|---|------|------|
| 1.1 | 顶部导入 `webview` | 增加 `import webview` |
| 1.2 | 定义版本号变量 | `__version__ = "2.2.0"` |
| 1.3 | 新增命令行参数 `--minimized` | 用于开机自启时仅托盘运行，不弹出窗口 |
| 1.4 | 创建 `WebviewAPI` 类 | 提供 JS 桥接方法：`start_service()`、`stop_service()`、`get_ip_list()`、`toggle_autostart()`、`get_autostart_status()` |
| 1.5 | 修改主入口逻辑 | 若 `--minimized` 为 False，则创建 pywebview 窗口，加载 `http://127.0.0.1:5000`（或本地 `desktop.html`） |
| 1.6 | 日志系统接入 `logging` | 保留文件输出，增加内存队列供 GUI 日志面板读取 |

### Phase 2：桌面 GUI 前端（www/desktop.html）

| # | 操作 | 说明 |
|---|------|------|
| 2.1 | 创建 `www/desktop.html` | 固定宽 920px、高 660px，不可滚动，自定义无边框标题栏 |
| 2.2 | 顶部状态栏 | 显示运行状态指示器（绿/红点）、本机 IP、端口号 |
| 2.3 | 左侧控制面板（宽 25%） | 包含"启动/停止服务"胶囊按钮、"快捷键设置"入口（点击弹窗） |
| 2.4 | 中央扫码区（宽 45%，视觉焦点） | 二维码图片（`/qr` 路由，带时间戳防缓存）、WebSocket 地址文本、复制按钮。服务未启动时显示"请启动服务"占位图 |
| 2.5 | 右侧辅助面板（宽 30%） | 显示 Zeroconf 服务名、可用 IP 标签列表（点击切换，更新地址） |
| 2.6 | 底部日志面板（高 130px） | 深色终端风格，实时滚动显示日志（INFO/WARN/ERROR 颜色区分），带"清空"按钮 |
| 2.7 | 右上角齿轮设置菜单 | 下拉卡片内含"开机自动启动"Toggle 开关，状态读取/写入本地配置文件 |
| 2.8 | JS 交互 | 通过 `window.pywebview.api.*` 调用后端方法，所有操作反馈使用 Toast 轻提示 |

### Phase 3：Android 端状态栏配置

| # | 操作 | 说明 |
|---|------|------|
| 3.1 | 修改 `capacitor.config.json` | 添加 StatusBar 插件配置：`overlaysWebView: false`，`backgroundColor: "#F9F5F0"`（与网页背景色一致） |
| 3.2 | 修改 `android/app/src/main/res/values/styles.xml` | 使用标准 `Theme.AppCompat.Light.NoActionBar`，不添加任何透明/沉浸式属性 |
| 3.3 | 修改 `MainActivity.java` | 保持为最简继承 `BridgeActivity`，仅包含 `onCreate` 和 `load`，不引入 `WindowInsetsController` 或 `SYSTEM_UI_FLAG` |
| 3.4 | 执行资源同步 | 运行 `npx cap sync android` |

### Phase 4：GitHub Actions 自动构建配置

在 `.github/workflows/build.yml` 中创建包含两个 Job 的工作流（完整代码见第八章）：

| Job | 运行环境 | 步骤概要 |
|-----|----------|----------|
| **build-windows** | `windows-latest` | ① 检出代码 → ② 安装 Python 3.12 → ③ 安装依赖（含 pyinstaller、pywebview） → ④ 执行 `pyinstaller CatDB.spec --noconfirm` → ⑤ 上传 `CatDB.exe` 为 Artifact |
| **build-android** | `ubuntu-latest` | ① 检出代码 → ② 安装 Java 17 + Node 18 → ③ 执行 `npm install` 和 `npx cap sync android` → ④ 运行 `./gradlew assembleDebug` → ⑤ 上传 `app-debug.apk` 为 Artifact |

触发条件：推送 `v*` 标签（如 `v2.2.0`）或手动 `workflow_dispatch`。

### Phase 5：版本号与变更日志

修改以下文件中的版本号为 `2.2.0`：

| 文件 | 字段 |
|------|------|
| `server.py` | `__version__ = "2.2.0"` |
| `capacitor.config.json` | `appVersion` |
| `package.json` | `version` |
| `android/app/build.gradle` | `versionName "2.2.0"`，`versionCode` 在原有基础上 +1 |

在项目根目录创建 `CHANGELOG.md`：

```markdown
# Changelog

## [2.2.0] - 2026-09-03

### Added
- 桌面 GUI 主窗口（pywebview），920×660 三栏布局
- 开机自启开关（齿轮菜单内），状态持久化
- Android 纯色状态栏（与页面背景一致，不覆盖内容）
- GitHub Actions 自动构建 Windows EXE + Android APK

### Changed
- 主程序支持 `--minimized` 静默启动模式
- 日志系统接入 logging 模块

### Removed
- 移除未实现的触控板模式入口
```


## 五、关键文件与目录结构（最终期望）

```
CatDB/
├── .github/workflows/build.yml   # CI 配置文件
├── android/                       # Capacitor Android 工程
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── java/.../MainActivity.java
│   │       └── res/values/styles.xml
├── www/
│   ├── index.html                # 手机端页面（原有）
│   ├── desktop.html              # 桌面端 GUI 页面（新增）
│   └── manifest.json
├── server.py                     # 主程序（含 pywebview 集成）
├── CatDB.spec                    # PyInstaller 打包配置
├── capacitor.config.json
├── package.json
├── requirements.txt
├── CHANGELOG.md                  # 变更日志（新增）
└── README.md
```


## 六、最终交付产物

| 平台 | 产物路径 | 说明 |
|------|----------|------|
| Windows | `dist/CatDB.exe` | 单文件，无控制台 |
| Android | `android/app/build/outputs/apk/debug/app-debug.apk` | Debug 版 APK |


## 七、构建触发指令（Git 操作）

完成所有代码修改后，执行以下命令推送并触发构建：

```bash
git add .
git commit -m "Release v2.2.0: desktop GUI + Android pure statusbar"
git tag v2.2.0
git push origin main --tags
```

构建完成后，从 GitHub Actions 页面下载 `CatDB-Windows` 和 `CatDB-Android` 两个 Artifact 即得最终产物。


## 八、补充文件完整源码（复制即用）

### 8.1 `CatDB.spec`（PyInstaller 配置）

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('www', 'www')],  # 打包前端静态资源
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'pystray',
        'pystray._win32',
        'aiohttp',
        'aiohttp.web',
        'qrcode',
        'PIL',
        'pyautogui',
        'pynput',
        'netifaces',
        'zeroconf'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyd = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyd,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CatDB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='cat_icon.ico' if exists('cat_icon.ico') else None,
)
```

### 8.2 `.github/workflows/build.yml`（CI 配置）

```yaml
name: Build Win + Android

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install pyinstaller pywebview
      - name: Build EXE
        run: pyinstaller CatDB.spec --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: CatDB-Windows
          path: dist/CatDB.exe

  build-android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '17'
      - uses: actions/setup-node@v4
        with:
          node-version: '18'
      - name: Install and sync Capacitor
        run: |
          npm install
          npx cap sync android
      - name: Build APK
        run: |
          cd android
          chmod +x gradlew
          ./gradlew assembleDebug
      - uses: actions/upload-artifact@v4
        with:
          name: CatDB-Android
          path: android/app/build/outputs/apk/debug/*.apk
```


## 九、补充说明（供 AI 决策参考）

- **桌面 GUI 与 Web 服务的关系**：主窗口通过 `webview.create_window` 加载本地运行的 Web 服务（`http://127.0.0.1:5000`）。若 Web 服务未启动，窗口应显示明确的等待/启动提示。
- **开机自启实现方式**：Windows 写入注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`；Android 端不涉及开机自启，该开关仅作用于 Windows 平台。
- **配置文件路径**：`%APPDATA%/CatDB/config.json`（Windows），用于保存开机自启开关状态。
- **PyInstaller 打包注意事项**：`CatDB.spec` 中需显式包含 `pywebview` 及其原生依赖，确保 EXE 可独立运行（已在上述 spec 中通过 `hiddenimports` 和 `datas` 收集）。


## 十、变更日志（CHANGELOG.md）

在项目根目录创建 `CHANGELOG.md`：

```markdown
# Changelog

## [2.2.0] - 2026-09-03

### Added
- 桌面 GUI 主窗口（pywebview），920×660 三栏布局
- 开机自启开关（齿轮菜单内），状态持久化
- Android 纯色状态栏（与页面背景一致，不覆盖内容）
- GitHub Actions 自动构建 Windows EXE + Android APK

### Changed
- 主程序支持 `--minimized` 静默启动模式
- 日志系统接入 logging 模块

### Removed
- 移除未实现的触控板模式入口
```
**GitHub API 令牌**: `[已移除，请自行在 GitHub Settings -> Personal tokens 生成]`
---

**文档版本**：v1.0  
**生成日期**：2026-09-03  
**适用项目**：CatDB（豆包喵喵）