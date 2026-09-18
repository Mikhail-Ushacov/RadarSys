# Перейдіть у папку backend
cd surgical-ew/backend

# Створіть та активуйте віртуальне середовище Python
python3 -m venv venv
source venv/bin/activate       # Для Linux / macOS
# venv\Scripts\activate        # Для Windows

# Встановіть залежності
pip install -r requirements.txt

# Запустіть сервер FastAPI (Uvicorn)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Перейдіть у папку frontend
cd surgical-ew/frontend

# Встановіть залежності Node.js
npm install

# Запустіть локальний сервер розробки
npm run dev
