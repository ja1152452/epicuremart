lines = open('templates/base.html', encoding='utf-8').readlines()
for i in range(1000, 1110):
    print(i+1, lines[i].rstrip())
