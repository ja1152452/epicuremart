lines = open('app.py', encoding='utf-8').readlines()

# Find the summary_table = Table(summary_data line
start = None
end = None
for i, l in enumerate(lines):
    if 'summary_table = Table(summary_data' in l and start is None:
        start = i
    if start is not None and 'elements.append(summary_table)' in l:
        end = i
        break

print(f'Found block: lines {start+1} to {end+1}')

if start is not None and end is not None:
    # Get current indentation
    indent = '    '
    inner = '        '
    
    new_block = [
        indent + 'if user_role != "seller":\n',
        inner + 'summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])\n',
        inner + 'summary_table.setStyle(TableStyle([\n',
        inner + "    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2ecc71')),\n",
        inner + "    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),\n",
        inner + "    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),\n",
        inner + "    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),\n",
        inner + "    ('FONTSIZE', (0, 0), (-1, 0), 14),\n",
        inner + "    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),\n",
        inner + "    ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),\n",
        inner + "    ('GRID', (0, 0), (-1, -1), 1, colors.black)\n",
        inner + ']))\n',
        inner + 'elements.append(summary_table)\n',
    ]
    
    new_lines = lines[:start] + new_block + lines[end+1:]
    open('app.py', 'w', encoding='utf-8').writelines(new_lines)
    print('Fixed successfully')
else:
    print('Block not found')
