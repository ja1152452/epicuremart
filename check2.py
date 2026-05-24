lines = open('app.py', encoding='utf-8').readlines()
for i in range(2860, 2900):
    print(i+1, repr(lines[i].rstrip()))
