## Покрокова інструкція із запуску

### 1. Клонування проєкту
```bash
git clone https://github.com/hellookittyyy/schedule_backend.git
cd schedule_backend
```

### 2. Налаштування віртуального середовища (venv)

**Для Windows:**

```bash
python -m venv venv
venv\Scripts\activate.bat
```

**Для macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Встановлення залежностей

Перед встановленням бібліотек переконайтеся, що віртуальне середовище активоване (у терміналі з'явиться префікс `(venv)`)

```bash
pip install -r requirements.txt
```

### 4. Запуск додатка

```bash
python manage.py runserver
```

---

По замовчуванню, додаток буде запущений на http://127.0.0.1:8000.
