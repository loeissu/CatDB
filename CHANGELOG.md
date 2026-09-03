# Changelog

## [2.2.0] - 2026-09-03

### Added
- 桌面 GUI 主窗口（pywebview），920×660 三栏布局
- 触控板模式开关（左侧控制面板，对接上游已有后端）
- 开机自启控制（齿轮菜单，状态持久化）
- Android 纯色状态栏（与页面背景一致，不覆盖内容）
- GitHub Actions 自动构建 Windows EXE + Android Release APK

### Changed
- 主程序支持 `--minimized` 静默启动模式
- 前端通过 pywebview API 调用后端方法

### Removed
- 无（完整保留上游所有功能）