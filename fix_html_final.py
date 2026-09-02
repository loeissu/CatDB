# 读取当前 HTML 并修复字体栈
with open('www/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. 移除 Google Fonts 链接
html = html.replace(
    '<link href="https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&display=swap" rel="stylesheet">',
    ''
)

# 2. 修复 font-family：使用系统中文字体栈，ZCOOL KuaiLe 作为首选但不可用时自动回退
# 原: font-family: 'ZCOOL KuaiLe', cursive, sans-serif;
# 新: 完整中文字体回退栈
html = html.replace(
    "font-family: 'ZCOOL KuaiLe', cursive, sans-serif;",
    "font-family: 'ZCOOL KuaiLe', 'Microsoft YaHei', 'PingFang SC', 'Hiragino Sans GB', 'Heiti SC', 'WenQuanYi Micro Hei', sans-serif;"
)

# 3. 修复 Windows 换行符
html = html.replace('\r\n', '\n').replace('\r', '\n')

# 4. 添加离线字体预加载提示（可选）
preload_hint = '''    <!-- 预连接字体 CDN（可选，国内可能不通） -->
    <link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'''

# 写入修复后的 HTML
with open('www/index.html', 'w', encoding='utf-8', newline='\n') as f:
    f.write(html)

print('HTML 修复完成')
print('字体栈已更新为完整中文回退栈')
print('已移除 Google Fonts 硬依赖')
print('已修复换行符为 LF')