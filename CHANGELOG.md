# Changelog

## [2.2.0] - 2026-09-03

### Added
- 桌面 GUI 主窗口（pywebview），920×660 三栏布局
- 触控板模式开关（左侧控制面板，对接上游已有后端）
- 开机自启控制（齿轮菜单，状态持久化）
- Android 纯色状态栏（与页面背景一致，不覆盖内容）
- GitHub Actions 自动构建 Windows EXE + Android Release APK
- HTTP JSON API（/api/status、/api/logs、/api/action），供浏览器版桌面页使用

### Fixed
- **EXE 打开 404 / 页面打不开**：GUI 改为加载本地打包的 desktop.html（不再猜测端口访问 127.0.0.1:5000），并新增端口自动探测；彻底移除协程内阻塞式 Event.wait（实测会饿死 Windows Proactor 事件循环导致全部 HTTP 超时）
- **APK 未签名无法安装**：release 构建类型固定使用 debug 签名（signingConfig signingConfigs.debug），CI 增加 apksigner 校验步骤
- **安卓 App 连不上电脑**：原 App 内置页面把 localhost 当成电脑地址；新增「电脑地址」手动填写（设置弹窗），并放行明文流量（usesCleartextTraffic）
- 移除 server.py 内嵌重复手机页（HTML_PAGE），统一以 www/index.html 为唯一事实来源

### Changed
- 主程序支持 `--minimized` 静默启动模式
- 桌面页重写：flex 流式三栏布局（25%/自适应/30%），状态灯、二维码 5s 自刷新、IP 标签切换、深色终端日志面板、齿轮菜单（开机自启/最小化/退出）
- 触控板开关真实生效（后端过滤手机触控指令）并持久化到 %APPDATA%/CatDB/config.json
- 快捷键可在桌面端修改（F1–F12/Home/End 等），运行中即时重建监听

### Removed
- 无（完整保留上游所有功能）