with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find HTML_PAGE
start = content.index('HTML_PAGE = ') + len('HTML_PAGE = ')
# Find the first triple quote after that
start_quote = content.index("'''", start) + 3
end_quote = content.index("'''", start_quote)
html = content[start_quote:end_quote]

with open('www/index.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML 重新提取完成，长度:', len(html))
print('前200字符:', html[:200])