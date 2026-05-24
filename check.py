lines = open('app.py', encoding='utf-8').readlines()
# Find admin and seller pdf export routes
for i, l in enumerate(lines):
    if 'send_file' in l and 2800 < i < 5000:
        print(i+1, l.rstrip())
    if 'as_attachment' in l and 2800 < i < 5000:
        print(i+1, l.rstrip())
