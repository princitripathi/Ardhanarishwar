import pathlib, re
txt=pathlib.Path('../README.md').read_text(encoding='utf-8')
pat=re.compile(r'Ardhanarishwar(?! Solver)')
for m in pat.finditer(txt):
    start=max(0,m.start()-50)
    end=min(len(txt), m.end()+50)
    snippet=txt[start:end].replace('\n',' ')
    print(snippet.encode('ascii','ignore').decode())
    print('--- line', txt[:m.start()].count('\n')+1)
