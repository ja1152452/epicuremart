lines = open('app.py', encoding='utf-8').readlines()
print('Total lines before:', len(lines))

# Find the second occurrence of def notifications() (the duplicate)
count = 0
start_del = None
for i, l in enumerate(lines):
    if "def notifications():" in l:
        count += 1
        if count == 2:
            # Go back to find the @app.route decorator
            j = i - 1
            while j >= 0 and (lines[j].strip().startswith('@') or lines[j].strip() == ''):
                j -= 1
            start_del = j + 1
            break

if start_del is None:
    print('No duplicate found')
else:
    print(f'Duplicate starts at line {start_del+1}')
    # Delete from start_del to end of file
    new_lines = lines[:start_del]
    open('app.py', 'w', encoding='utf-8').writelines(new_lines)
    print('Total lines after:', len(new_lines))
    print('Done')
