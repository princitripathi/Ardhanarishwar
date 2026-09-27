import subprocess
import sys
p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"], cwd=r"C:\Users\princ\Desktop\Ardhanarishwar\backend")
print(f"Server PID: {p.pid}")
