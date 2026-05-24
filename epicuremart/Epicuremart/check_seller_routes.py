lines = open('app.py', encoding='utf-8').readlines()
for i in range(2858, 2920):
    print(i+1, lines[i].rstrip())
