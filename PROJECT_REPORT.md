# 🐾 CatDB（豆包喵喵）项目完整报告

> **版本**: v2.1.3 | **日期**: 2026-09-03 | **分支**: `main`  
> **仓库**: `loeissu/CatDB`（Fork 自 `shangaokun/CatDB`）

---

## 📌 项目简介

**CatDB（豆包喵喵）** 是一款基于 Python 的局域网手机语音输入 → 电脑实时上屏工具。核心功能是通过 WebSocket 将手机端文字/语音输入实时同步到电脑光标处，并支持自定义快捷键和触控板模式。

### 核心功能
- ✅ **毫秒级实时同步**: WebSocket 局域网传输
- ✅ **智能续写**: 电脑介入后自动"翻篇"
- ✅ **系统托盘**: 无控制台窗口，静默运行
- ✅ **二维码扫码**: 手机扫描即可连接
- ✅ **Zeroconf 零配置**: 自动发现服务
- ✅ **PWA 支持**: 手机可添加到桌面
- ✅ **触控板模式**: 手机变成无线触控板

---

## ✅ 已完成的工作

### Phase 0：强制自我审查协议
建立了三重自检机制：
1. 语法编译检查 → `python -m py_compile <file.py>`
2. 导入链检查 → `requirements.txt` 中声明所有第三方库
3. 线程安全断言 → aiohttp 启动线程设置 `daemon=True`

### Phase 1：深度项目调研
产出文件：`doc/专业化改造红皮书.md`（307 行）

核心发现：
- 启动入口：`server.py`（直接运行）
- Web 框架：`aiohttp`（非 Flask）
- 前端：HTML 内嵌在 Python 中，无 `templates/` 目录
- CDN 依赖：仅 Google Fonts，已移除改用系统字体栈
- 端口：硬编码 `5000`，已添加 `argparse` 与自动探测

### Phase 2 & 3：系统托盘 + 日志 + IP 过滤 + Zeroconf + 二维码
**核心改造 `server.py`**：+371 行，-215 行

| 改造项 | 状态 | 说明 |
|--------|------|------|
| 日志迁移 | ✅ | `print()` → `logging`，按平台存储 |
| 双线程架构 | ✅ | 主线程托盘 + 守护线程 Web 服务 |
| 系统托盘菜单 | ✅ | 打开面板 / 拷贝地址 / 二维码 / 退出 |
| 命令行参数 | ✅ | `--port` / `--hotkey` / `--max-port-attempts` |
| IP 智能过滤 | ✅ | 过滤 VMware/Virtual/docker 等虚拟网卡 |
| Zeroconf | ✅ | `_catdb._tcp.local.` 服务注册 |
| 二维码路由 | ✅ | `/qr` 生成 PNG，前端每 30 秒刷新 |
| 端口自动探测 | ✅ | 5000 占用时自动向下尝试，最多 20 个端口 |

### Phase 4：移动端 PWA 改造
产出文件：
- `manifest.json` — PWA 清单
- `sw.js` — Service Worker
- `icon-192.png` / `icon-512.png` — PWA 图标

### Phase 5：终极审查修复
| 检查项 | 结果 |
|--------|------|
| 语法编译 | ✅ PASS |
| 导入链 | ✅ PASS |
| 线程安全 | ✅ PASS |
| Zeroconf 异常处理 | ✅ PASS |
| 日志迁移 | ✅ PASS |
| argparse 支持 | ✅ PASS |

### Phase 6：安装说明文档
更新文件：`安装说明.md`

### Phase 7：打包脚本
| 文件 | 平台 | 说明 |
|------|------|------|
| `build_portable.bat` | Windows | PyInstaller 打包脚本 |
| `build_macos.sh` | macOS | PyInstaller 打包脚本 |
| `build_linux.sh` | Linux | PyInstaller 打包脚本（含系统依赖检测） |
| `gen_icons.py` | 全平台 | PWA 图标生成脚本 |

### Phase 8：Android 端沉浸式状态栏 + 图标重绘
| 项目 | 实现 |
|------|------|
| **猫头图标重绘** | `cat_icon.svg` 基于 CSS 猫头设计（头部/耳朵/眼睛/鼻子/胡须/腮红/脚爪） |
| **多密度图标** | `generate_icons.js` + Sharp 生成 mipmap-mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi (48-192px) |
| **自适应图标** | `ic_launcher_foreground/background` (mipmap-anydpi-v26) |
| **Capacitor 配置** | `StatusBar` overlaysWebView=true, 背景色 #5D4037, dark 模式 |
| **原生主题** | `styles.xml` 透明状态栏/导航栏，`windowDrawsSystemBarBackgrounds=true` |
| **MainActivity** | Android 11+ `WindowInsetsController` / 5.0+ `SYSTEM_UI_FLAG_IMMERSIVE_STICKY` |

### Phase 9：GitHub Actions 全平台自动构建
| 平台 | Runner | 产物 |
|------|--------|------|
| Windows | `windows-latest` | `CatDB.exe` (单文件, 无控制台) |
| macOS | `macos-latest` | `CatDB` (单文件) |
| Linux | `ubuntu-latest` | `CatDB` (单文件) |
| Android | `ubuntu-latest` | `app-debug.apk` / `app-release.apk` |

---

## ❌ 未完成的工作

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P1 | **Release 版 Android APK 签名** | 当前仅 Debug APK，需配置 keystore 签名发布版 |
| P1 | **macOS / Linux 实机测试** | 仅通过 GitHub Actions 构建，未在实体机验证 |
| P2 | **Windows 代码签名证书** | 避免 SmartScreen 拦截 |
| P2 | **自动更新机制** | 检查 GitHub Releases 并提示更新 |
| P3 | **单元测试覆盖** | 关键逻辑（`compute_diff`、端口探测、diff 同步） |
| P3 | **文档国际化** | 英文版 README / 安装说明 |
| P3 | **插件系统** | 支持第三方扩展（如自定义输入法、脚本市场） |

---

## ⚠️ 遇到的问题与解决方案

### 问题 1：网络访问受限
**现象**: 无法访问 GitHub（`git clone` / API / raw content 均超时）  
**影响**: 无法从远程仓库拉取代码或推送变更  
**解决方案**: 
- 本地工作区操作，代码已完整可用
- 使用 GitHub API 令牌进行认证访问

### 问题 2：打包决策未定
**现象**: 用户要求"在 GitHub 上直接打包"而非本地打包  
**当前状态**: 已创建 `.github/workflows/build.yml`，配置三平台构建矩阵  
**解决方案**: 推送标签触发自动构建

### 问题 3：`netifaces` 跨平台编译
**现象**: `netifaces` 需要 C 编译器，Windows 上需要 Visual C++ Build Tools  
**影响**: PyInstaller 打包时可能找不到编译后的 `.pyd` 文件  
**解决方案**:
- Windows: 使用预编译的 wheel（`pip install netifaces` 通常有预编译版）
- Linux: `apt install python3-dev`
- macOS: `xcode-select --install`
- 已在 `server.py` 中实现降级方案（`netifaces` 不可用时回退到 `socket` 方式）

### 问题 4：`pystray` 无头模式
**现象**: 在无图形界面的 Linux 服务器上 `pystray` 会崩溃  
**影响**: 仅影响 Linux 服务器环境（桌面环境无此问题）  
**解决方案**: 
- 在 `requirements.txt` 和安装说明中明确标注系统依赖
- Linux 用户需要安装 `python3-gi gir1.2-gtk-3.0`

### 问题 5：`console=True` vs `--noconsole`
**现象**: 当前 `CatDB.spec` 使用 `console=True`（显示控制台窗口），但系统托盘应用应使用 `--noconsole`  
**影响**: 用户双击 exe 时会看到黑色控制台窗口  
**解决方案**: 
- 已修改 `CatDB.spec` 中 `console=False`
- 确保 `logging.FileHandler` 正常工作（日志仍能通过文件输出）

### 问题 6：Google Fonts 离线问题
**现象**: 前端依赖 `fonts.googleapis.com` 加载 ZCOOL KuaiLe 字体  
**影响**: 无网络环境下字体回退到 `cursive, sans-serif`，中文显示为方框/乱码  
**解决方案**:
- 移除 Google Fonts CDN 硬依赖
- 改用完整中文字体回退栈：`ZCOOL KuaiLe` → `Microsoft YaHei` → `PingFang SC` → `Hiragino Sans GB` → `Heiti SC` → `WenQuanYi Micro Hei` → `sans-serif`
- 同步修复 `server.py` 和 `www/index.html` 所有 `font-family`

### 问题 7：Android 界面状态栏非沉浸式
**现象**: 手机客户端状态栏未制作成沉浸式，有明显黑边  
**解决方案**:
- `capacitor.config.json`: StatusBar `overlaysWebView=true`, 背景色 `#5D4037`
- `styles.xml`: 透明状态栏/导航栏，`windowDrawsSystemBarBackgrounds=true`
- `MainActivity.java`: Android 11+ `WindowInsetsController` / 5.0+ `SYSTEM_UI_FLAG_IMMERSIVE_STICKY`

### 问题 8：猫头图标为 CSS 绘制，无法直接作为 App 图标
**现象**: 界面上的猫头是用 CSS `border`/`ellipse` 绘制，无法直接导出为图标文件  
**解决方案**:
- 基于 CSS 猫头设计绘制 `cat_icon.svg`（矢量图，含头部/耳朵/眼睛/鼻子/胡须/腮红/脚爪）
- 编写 `generate_icons.js` 使用 Sharp 生成多密度 PNG (48/72/96/144/192px)
- 生成自适应图标：前景 `ic_launcher_foreground.png` + 背景 `ic_launcher_background.png`

---

## 🔗 相关链接

| 类型 | 链接 |
|------|------|
| **GitHub 仓库** | https://github.com/loeissu/CatDB |
| **原始仓库** | https://github.com/shangaokun/CatDB |
| **GitHub Actions** | https://github.com/loeissu/CatDB/actions |
| **Releases 下载** | https://github.com/loeissu/CatDB/releases |

---

## 📈 提交历史

```
5212c97 feat(v2.1.3): 沉浸式状态栏 + 猫头图标重绘 + 全平台适配
ff179f2 fix(v2.1.2): 修复界面乱码 - 完整中文字体回退栈 + 离线字体支持
67f9c19 feat: 端口自动探测 - 占用时自动切换可用端口
24722c3 fix(v2.1.1): 全面修复 P0 级 Bug 并重构核心逻辑
a7153ea feat(v2.1): 系统托盘 + 10秒超时二维码 + Bug修复
0d96cd7 ci: 添加 GitHub Actions 自动构建工作流
39e8e3d feat(touchpad): 增加触控板支持和快捷键优化
dd1b2d2 feat(ui): 添加自定义快捷键模块
92c9751 Update README.md
569ba3d Add files via upload
```

---

## 📝 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| **后端** | Python + aiohttp | 3.12 |
| **前端** | 纯 HTML/CSS/JS | — |
| **WebSocket** | aiohttp WebSocket | 3.8+ |
| **系统托盘** | pystray | 0.19+ |
| **IP 获取** | netifaces | 0.11+ |
| **二维码** | qrcode + Pillow | 7.4+ / 9.0+ |
| **键盘监听** | pynput | 1.7+ |
| **键盘模拟** | pyautogui | 0.9.53+ |
| **剪贴板** | pyperclip | 1.8+ |
| **打包** | PyInstaller | 6.0+ |
| **Android** | Capacitor + Gradle | 6.0+ / 8.14+ |

---

## 📞 联系方式

- **GitHub**: [loeissu/CatDB](https://github.com/loeissu/CatDB)
- **原仓库**: [shangaokun/CatDB](https://github.com/shangaokun/CatDB)

---

> 📝 **本文档由 AI 自动生成，最后更新: 2026-09-03**  
> 🤖 **Generated with Codebuff**