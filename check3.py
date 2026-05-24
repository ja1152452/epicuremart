lines = open('templates/base.html', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'bootstrap' in l.lower() or 'block content' in l or '</body>' in l or 'block scripts' in l:
        print(i+1, l.rstrip())
