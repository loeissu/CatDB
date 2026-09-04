// ============================================================
// 安卓启动器图标生成（统一入口，v2.2.11+）
// ------------------------------------------------------------
// 说明：图标正式稿为「Typing」文字方案（奶油底深棕字 + 橙色笔触，
// 设计母稿见 typing_icon.svg）。唯一权威生成器是
//   tools/gen_typing_icons.py （PIL，无外部渲染依赖），
// 仓库内 android/app/src/main/res 下全套 mipmap PNG 均由它产出。
//
// 本 JS 文件是旧 cat_icon.svg 管线的后继：不再各自用 sharp 渲染
// SVG（避免 librsvg 字体回退造成与正式稿不一致），而是直接调用
// Python 生成器，保证任何入口重跑结果一致。
// ============================================================
const { spawnSync } = require('child_process');
const path = require('path');

const script = path.join(__dirname, 'tools', 'gen_typing_icons.py');
const py = process.env.PYTHON || 'python';

const r = spawnSync(py, [script], { stdio: 'inherit' });
if (r.error) {
  console.error('[generate_icons.js] failed to launch python:', r.error.message);
  process.exit(1);
}
process.exit(r.status === null ? 1 : r.status);
