lines = open('app.py', encoding='utf-8').readlines()
for i in range(964, 985):
    print(f'{i+1}: {lines[i].rstrip()}')
