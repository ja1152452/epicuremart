lines = open('app.py', encoding='utf-8').readlines()
# Show admin_sales_report_export_pdf route
for i, l in enumerate(lines):
    if 'admin_sales_report_export_pdf' in l:
        print(i+1, l.rstrip())
        for j in range(i, min(i+15, len(lines))):
            print(j+1, lines[j].rstrip())
        break
