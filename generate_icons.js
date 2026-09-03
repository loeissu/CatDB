// 生成 Android mipmap 图标
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const svgPath = path.join(__dirname, 'cat_icon.svg');
const svgBuffer = fs.readFileSync(svgPath);

// 图标尺寸配置
const icons = [
  { dir: 'mipmap-mdpi', size: 48 },
  { dir: 'mipmap-hdpi', size: 72 },
  { dir: 'mipmap-xhdpi', size: 96 },
  { dir: 'mipmap-xxhdpi', size: 144 },
  { dir: 'mipmap-xxxhdpi', size: 192 },
];

async function generateIcons() {
  for (const icon of icons) {
    const outputDir = path.join(__dirname, 'android', 'app', 'src', 'main', 'res', icon.dir);
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    
    // 生成 ic_launcher.png
    await sharp(svgBuffer, { density: 300 })
      .resize(icon.size, icon.size)
      .png()
      .toFile(path.join(outputDir, 'ic_launcher.png'));
    
    // 生成 ic_launcher_round.png (圆形裁剪)
    await sharp(svgBuffer, { density: 300 })
      .resize(icon.size, icon.size)
      .composite([{
        input: Buffer.from(`<svg><circle cx="${icon.size/2}" cy="${icon.size/2}" r="${icon.size/2}" fill="white"/></svg>`),
        blend: 'dest-in'
      }])
      .png()
      .toFile(path.join(outputDir, 'ic_launcher_round.png'));
    
    console.log(`Generated ${icon.dir}: ${icon.size}x${icon.size}`);
  }
  
  // 生成自适应图标前景
  const adaptiveDir = path.join(__dirname, 'android', 'app', 'src', 'main', 'res', 'mipmap-anydpi-v26');
  if (!fs.existsSync(adaptiveDir)) {
    fs.mkdirSync(adaptiveDir, { recursive: true });
  }
  
  await sharp(svgBuffer, { density: 300 })
    .resize(432, 432)
    .png()
    .toFile(path.join(adaptiveDir, 'ic_launcher_foreground.png'));
  
  // 背景色
  const bgSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108"><rect width="108" height="108" fill="#FFF9F0"/></svg>`;
  await sharp(Buffer.from(bgSvg))
    .resize(108, 108)
    .png()
    .toFile(path.join(adaptiveDir, 'ic_launcher_background.png'));
  
  console.log('Generated adaptive icons');
}

generateIcons().catch(console.error);