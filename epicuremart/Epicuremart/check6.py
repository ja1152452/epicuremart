lines = open('templates/base.html', encoding='utf-8').readlines()
for i in range(910, 920):
    print(i+1, lines[i].rstrip())
