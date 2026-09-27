content = open(r'C:\Users\princ\Desktop\Ardhanarishwar\frontend\src\App.jsx').read()
lines = content.split('\n')
depth = 0
for i, line in enumerate(lines[143:], start=144):
    depth += line.count('{') - line.count('}')
    if depth < 0:
        print(f'Line {i}: Extra closing brace! depth={depth}')
        break
print(f'Final depth from line 144: {depth}')
print('BALANCED' if depth == 0 else 'UNBALANCED')
