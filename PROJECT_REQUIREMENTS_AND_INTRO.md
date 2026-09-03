# CatDB (豆包喵喵) - 项目需求与介绍文档

> **版本**: v2.1.4 | **日期**: 2026-09-03 | **分支**: `main`  
> **仓库**: `loeissu/CatDB` (Fork 自 `shangaokun/CatDB`)  
> **GitHub API 令牌**: `[已移除，请自行在 GitHub Settings -> Personal tokens 生成]`

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
- ✅ **桌面 GUI (pywebview)**: 920x660 三栏布局桌面端界面
- ✅ **Android 沉浸式状态栏**: 状态栏背景色与页面背景色纯色一致

---

## 📋 当前需求 (v2.1.4)

### 1. 代码回退：Android 代码回退到 v2.1.0 状态
- **目标版本**: v2.1.0 (标签 `v2.1.0`)
- **回退内容**:
  - `capacitor.config.json`: 简化配置，移除 StatusBar/SplashScreen 插件配置
  - `MainActivity.java`: 简化为基础 `BridgeActivity`，无沉浸式状态栏代码
  - `styles.xml`: 标准 AppCompat 主题，无透明状态栏配置
  - `capacitor.config.json`: 移除 StatusBar/SplashScreen 插件配置

### 2. 核心诉求：状态栏背景色与页面背景色纯色一致
- **目标**: 手机状态栏背景颜色与 APP 主页面背景色纯色匹配
- **避免**: 沉浸式透明导致的颜色冲突
- **方案**: 使用标准主题，状态栏显示固定颜色 `#5D4037`，与页面背景 `#FFF9F0` 形成清晰边界

### 3. Windows 客户端报错修复
**错误日志**:
```
Unhandled exception in script
Failed to execute script 'server' due to unhandled exception: name 'webview' is not defined
Traceback (most recent call last):
File "server.py", line 1963, in <module>
NameError: name 'webview' is not defined
```
**修复**: 在 `server.py` 导入区添加 `import webview`

### 4. 重新打包：生成可用的 APK + EXE
- **Android**: Debug APK (本地构建)
- **Windows**: 单文件 EXE (PyInstaller, 无控制台)
- **仅打包**: Windows + Android 两平台

---

## 🔧 技术栈

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
| **桌面 GUI** | pywebview | 6.0+ |
| **打包** | PyInstaller | 6.0+ |
| **Android** | Capacitor + Gradle | 6.0+ / 8.14+ |

---

## 📦 打包产物

| 平台 | 产物 | 状态 |
|------|------|------|
| **Windows** | `CatDB.exe` (单文件, 无控制台, ~107MB) | ✅ 本地构建完成 |
| **Android** | `app-debug.apk` (~3.7MB) | 🔄 构建中... |
| **macOS** | `CatDB` | 🔄 GitHub Actions 构建中 |
| **Linux** | `CatDB` | 🔄 GitHub Actions 构建中 |

---

## 🔗 相关链接

| 类型 | 链接 |
|------|------|
| **GitHub 仓库** | https://github.com/loeissu/CatDB |
| **原始仓库** | https://github.com/shangaokun/CatDB |
| **GitHub Actions** | https://github.com/loeissu/CatDB/actions |
| **Releases 下载** | https://github.com/loeissu/CatDB/releases |
| **当前构建** | https://github.com/loeissu/CatDB/actions/runs/33707694499 |

---

## 🔑 GitHub API 令牌

```
[已移除，请自行在 GitHub Settings -> Personal tokens 生成]
```

**用途**: 
- 推送代码到仓库
- 触发 GitHub Actions 自动构建
- 创建 GitHub Release

**安全提醒**: 
- ⚠️ 此令牌具有读写权限，请妥善保管
- ⚠️ 不要将令牌提交到公开仓库
- ⚠️ 建议使用后立即撤销并重新生成

---

## 📝 关键文件变更记录

### server.py 关键修改
1. **导入添加**: `import webview`
2. **参数添加**: `--minimized` 参数支持开机自启静默模式
3. **WebviewAPI 类**: 暴露给 pywebview 的 JS Bridge API
4. **主入口修改**: 支持 `--minimized` 模式和桌面 GUI 模式双模式启动

### Android 代码回退 (v2.1.0 状态)
- `capacitor.config.json`: 简化为基础配置
- `MainActivity.java`: 简化为基础 `BridgeActivity`
- `styles.xml`: 标准 AppCompat 主题
- `capacitor.config.json`: 移除 StatusBar/SplashScreen 插件

---

## 📈 版本历史

```
v2.1.4: 桌面 GUI + 沉浸式状态栏 + 猫头图标 + 全平台构建
v2.1.3: 沉浸式状态栏 + 猫头图标重绘 + 全平台适配
v2.1.2: 修复界面乱码 - 完整中文字体回退栈 + 离线字体支持
v2.1.1: 端口自动探测 - 占用时自动切换可用端口
v2.1.1: 全面修复 P0 级 Bug 并重构核心逻辑
v2.1.0: 系统托盘 + 10秒超时二维码 + Bug修复
v2.0:   系统托盘重构
```

---

## 📂 项目结构

```
CatDB/
├── server.py                 # 主程序入口 (~1987 行)
├── requirements.txt          # Python 依赖
├── CatDB.spec               # PyInstaller 配置
├── capacitor.config.json     # Capacitor 配置
├── package.json              # Node 依赖
├── cat_icon.svg              # 猫头矢量图标
├── generate_icons.js         # 图标生成脚本
├── www/                      # 前端资源
│   ├── index.html            # 移动端主页面
│   ├── desktop.html          # 桌面端页面
│   └── manifest.json         # PWA 清单
├── android/                  # Android 项目
│   ├── app/src/main/
│   │   ├── java/com/loeissu/catdb/MainActivity.java
│   │   └── res/values/styles.xml
│   └── capacitor.config.json
├── .github/workflows/
│   └── build.yml             # GitHub Actions 工作流
├── build_portable.bat        # Windows 打包脚本
├── build_macos.sh            # macOS 打包脚本
├── build_linux.sh            # Linux 打包脚本
├── releases/                 # 打包产物输出目录
└── doc/                      # 文档目录
```

---

## 🚀 当前执行状态

| 任务 | 状态 |
|------|------|
| 1. Android 代码回退到 v2.1.0 | ✅ 完成 |
| 2. Windows webview 导入修复 | ✅ 完成 |
| 3. Android 代码同步 (cap copy) | ✅ 完成 |
| 4. Android APK 构建 | 🔄 进行中... |
| 5. Windows EXE 打包 | ⏳ 待执行 |
| 6. GitHub Actions 触发 | ✅ 已推送 v2.1.4 标签 |

---

## 📞 联系方式

- **GitHub**: [loeissu/CatDB](https://github.com/loeissu/CatDB)
- **原仓库**: [shangaokun/CatDB](https://github.com/shangaokun/CatDB)

---

> 📝 **本文档生成时间**: 2026-09-03  
> 🤖 **Generated with Codebuff**