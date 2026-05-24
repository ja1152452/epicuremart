lines = open('app.py', encoding='utf-8').readlines()
for i in range(4688, 4700):
    print(i+1, lines[i].rstrip())
