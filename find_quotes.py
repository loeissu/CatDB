import re

with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all triple quote positions
for m in re.finditer(r'"""', content):
    start = max(0, m.start() - 30)
    end = m.start() + 50
    print(f'Pos {m.start()}: ...{content[start:end]}...')
    print('---')