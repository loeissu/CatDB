with open('server.py', 'rb') as f:
    content = f.read()

idx = content.index(b'HTML_PAGE = ')
start_quote = content.index(b"'''", idx) + 3
end_quote = content.index(b"'''", start_quote)
html_bytes = content[start_quote:end_quote]
for line in html_bytes.split(b'\n'):
    if b'<title>' in line:
        print('标题行(bytes):', line)
        print('标题行(decoded):', line.decode('utf-8'))
        break