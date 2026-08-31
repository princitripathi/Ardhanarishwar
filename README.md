# Ardhanarishwar

An AI-powered career and business assistance platform.

Development will be done incrementally.

## Project Structure

```
Ardhanarishwar/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── requirements.txt
│   └── .venv/
├── frontend/
│   ├── src/
│   │   ├── api.js
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── .env.example
│   └── .env.local
├── data/
├── docs/
├── .gitignore
├── README.md
└── .env.example
```

## Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate the virtual environment (already created):
   ```bash
   # Windows
   .venv\Scripts\activate
   
   # Linux/macOS
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Copy environment example:
   ```bash
   copy .env.example .env.local
   ```

## Running the Application

### Start Backend
```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at:
- Root: http://localhost:8000/
- Health: http://localhost:8000/api/health

### Start Frontend
```bash
cd frontend
npm run dev
```

Frontend will be available at:
- http://localhost:5173

## API Endpoints

### GET /
Returns basic backend identification.

### GET /api/health
Returns backend health status:
```json
{
  "status": "ok",
  "service": "ardhanarishwar-backend"
}
```

## Expected Local URLs

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Health: http://localhost:8000/api/health

## Building for Production

Frontend:
```bash
cd frontend
npm run build
```

The production build will be in `frontend/dist/`.