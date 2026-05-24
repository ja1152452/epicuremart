lines = open('templates/base.html', encoding='utf-8').readlines()
for i in range(len(lines)):
    if 'extra_js' in lines[i] or 'block extra' in lines[i]:
        print(i+1, lines[i].rstrip())
