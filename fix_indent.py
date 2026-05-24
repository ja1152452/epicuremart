with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if i >= 5118 and i <= 5130:
        print(f'{i+1}: {repr(line)}')
