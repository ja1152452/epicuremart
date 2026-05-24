lines = open('templates/admin_dashboard.html', encoding='utf-8').readlines()
# Find exportBtn and modal related lines
for i, l in enumerate(lines):
    if 'exportBtn' in l or 'pdfPreview' in l or 'pdfDownload' in l:
        print(i+1, l.rstrip())
