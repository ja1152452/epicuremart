lines = open('app.py', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'Content-Disposition' in l or 'X-Frame-Options' in l or 'make_response' in l:
        if i < 3000:
            print(i+1, l.rstrip())
