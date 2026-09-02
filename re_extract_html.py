with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

start = content.index('HTML_PAGE = ') + len('HTML_PAGE = ')
start_quote = content.index("'''", start) + 3
end_quote = content.index("'''", start_quote)
html = content[start_quote:end_quote]

with open('www/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('重新提取完成，长度:', len(html))
for line in html.split('\n'):
    if '<title>' in line:
        print('标题行:', line.strip())
        break