import py_compile, sys
files = [
    r'C:\Users\princ\Desktop\Ardhanarishwar\backend\app\main.py',
    r'C:\Users\princ\Desktop\Ardhanarishwar\backend\app\services\orchestrator.py',
    r'C:\Users\princ\Desktop\Ardhanarishwar\backend\app\services\llm.py',
]
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"{f.split('\\')[-1]}: OK")
    except py_compile.PyCompileError as e:
        print(f"{f.split('\\')[-1]}: ERROR - {e}")
        sys.exit(1)
