# 🐾 豆包喵喵 (CatDB)

**把手机变成电脑的语音输入键盘。** 手机上说话/打字，文字实时出现在电脑当前光标处。

> **v2.3.0 起只提供 Windows 桌面客户端 + 手机浏览器 / PWA，不再提供安卓原生 App。**
> 手机无需安装任何应用：扫二维码或打开桌面端给出的链接即可使用。

---

## ✨ 功能

- **实时同步**：WebSocket 局域网传输，手机输入即时上屏（支持中文、换行、emoji）。
- **Smart Rebase 电脑介入**：在电脑上敲键盘或点鼠标后自动切断上下文，回到手机继续输入时作为新段落发送，不会回退删改你在电脑上改过的内容。
- **触控板 / 快捷键 / 图片**：手机可当无线触控板、发送自定义快捷键、把照片直接粘贴到电脑光标处。
- **桌面常驻**：系统托盘、关闭最小化到托盘、开机自启、深浅色主题、运行日志、防火墙一键放行。
- **连接码鉴权**：首次启动自动生成连接码，二维码与地址自带连接码，手机无感连接；未授权设备无法控制键鼠。

## 🚀 使用

1. 双击 `CatDB.exe`（或源码运行 `python server.py`）。
2. 桌面窗口右侧出现二维码；也可点「复制」拿到**完整地址**（含连接码）。
3. 手机与电脑连同一 Wi-Fi，扫码或用手机浏览器打开该地址即可输入。
4. 首次使用若手机打不开网页，点托盘菜单「🛡️ 防火墙放行」（会弹一次 UAC），完成后手机立即可连。

> 手动填地址时请粘贴桌面端复制的**完整地址**。只填 `IP:端口` 会因缺少连接码被拒绝，页面会提示「连接码无效」。

## 🔧 从源码运行 / 打包

```bash
pip install -r requirements.txt
python server.py                      # 桌面 GUI
python server.py --minimized          # 仅托盘
python -m unittest discover -s tests -v    # 跑测试（CI 打包前强制通过）
pyinstaller CatDB.spec --noconfirm    # 或双击 build_portable.bat
```

GitHub Actions 在推送 `v*` tag 时自动跑测试并打包 `CatDB_Windows_<tag>.exe` 到 Release。
版本号统一用 `python tools/bump_version.py <x.y.z>` 更新。

## 🔒 安全说明

- WebSocket 与本地 HTTP 控制接口都需要连接码 / 仅允许本机访问；不再对任意来源开放 CORS。
- 手机端发送的组合键经过白名单校验，且不再允许拉起 `cmd.exe` / `powershell.exe`。
- 防火墙放行规则只覆盖 **专用/域网络** 且端口范围固定为 5000–5010（与服务端口探测范围一致）。
- 连接码保存在 `%APPDATA%/CatDB/config.json`，换码后手机需重新扫码。

## 📁 结构

```
server.py            # 服务端 + 桌面 GUI + 托盘（单文件核心）
www/index.html       # 手机浏览器页面
www/desktop.html     # 桌面窗口页面
CatDB.spec           # 唯一打包配置
tests/               # 标准库 unittest 回归测试
tools/               # 版本号工具
```

`doc/`、`PROJECT_*.md` 与「项目构建任务书」为历史设计文档，其中关于安卓客户端的内容仅作存档。

---
*Created with ❤️ by Claude & Gemini*
