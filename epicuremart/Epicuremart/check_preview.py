lines = open('app.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'preview_pdf' in l or 'preview-pdf' in l:
        print(i+1, l.rstrip())
