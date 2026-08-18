# Dharamshala Accounts Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simple Flask + Supabase PostgreSQL web application for managing Dharamshala financial accounts with credit/debit transactions.

**Architecture:** Flask REST API backend (deployed to Render) serves JSON to a pure static HTML/CSS/JS frontend (deployed to Netlify). All data is persisted in Supabase PostgreSQL. Flask sessions (cookie-based) protect all API endpoints behind a single admin password.

**Tech Stack:** Python 3.11, Flask 3.x, SQLAlchemy 2.x, psycopg2-binary, flask-cors, python-dotenv, gunicorn; HTML5 + CSS3 + Vanilla JS (no frameworks).

## Global Constraints

- No SQLite, no localStorage as primary DB, no local data files — Supabase PostgreSQL only
- Currency: Indian Rupee (₹), Indian numbering system (1,00,000 not 100,000)
- Balance = Total Credit − Total Debit (calculated from transactions, never stored)
- Amount stored as NUMERIC(12,2) in DB
- Auth: single admin password from env var ADMIN_PASSWORD (never hardcoded)
- No React/Vue/Angular — Vanilla JS only
- No stack traces exposed to frontend — friendly error messages only
- All amounts validated: must be positive numbers
- CORS: allow frontend origin from env var ALLOWED_ORIGIN (default localhost in dev)
- `type` column in transactions: exactly "credit" or "debit"
- Date stored and displayed as YYYY-MM-DD, shown to user as DD Month YYYY

---

## File Map

```
dharamshala-accounts/
├── backend/
│   ├── app.py              # Flask app: config, models, auth, all routes
│   ├── requirements.txt
│   └── Procfile
├── frontend/
│   ├── login.html          # Login page
│   ├── index.html          # Dashboard: accounts list
│   ├── account.html        # Account detail: transactions
│   ├── css/
│   │   └── style.css       # All styles: layout, cards, modals, responsive
│   └── js/
│       ├── config.js       # API_BASE_URL (the only configurable file for deployment)
│       ├── auth.js         # Login/logout, session guard
│       ├── dashboard.js    # Dashboard: load accounts, add/delete account
│       └── account.js      # Account detail: load transactions, add/delete
├── .env.example
├── .gitignore
└── README.md
```

---

### Task 1: Project Scaffolding & Environment

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/Procfile`
- Create: `.env.example`
- Create: `.gitignore`

**Interfaces:**
- Produces: dependency list, env var names used by all other tasks

- [ ] **Step 1: Create `backend/requirements.txt`**

```
Flask==3.1.0
Flask-Cors==5.0.0
SQLAlchemy==2.0.41
psycopg2-binary==2.9.10
python-dotenv==1.0.1
gunicorn==23.0.0
```

- [ ] **Step 2: Create `backend/Procfile`**

```
web: gunicorn app:app
```

- [ ] **Step 3: Create `.env.example`**

```
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres
SECRET_KEY=change-me-to-a-long-random-string
ADMIN_PASSWORD=change-me-to-your-admin-password
ALLOWED_ORIGIN=http://localhost:3000
```

- [ ] **Step 4: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/
.DS_Store
Thumbs.db
```

- [ ] **Step 5: Install dependencies locally**

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 6: Create `.env` from example (local dev only, never committed)**

```bash
cp ../.env.example ../.env
# Then edit .env with real Supabase credentials
```

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/Procfile .env.example .gitignore
git commit -m "chore: project scaffolding and environment setup"
```

---

### Task 2: Flask App — Models, Auth & Database Init

**Files:**
- Create: `backend/app.py`

**Interfaces:**
- Produces:
  - `Account` SQLAlchemy model with fields: `id` (UUID), `name` (str), `created_at` (datetime)
  - `Transaction` SQLAlchemy model with fields: `id` (UUID), `account_id` (UUID FK), `type` ("credit"|"debit"), `amount` (Decimal), `description` (str), `notes` (str|None), `transaction_date` (date), `created_at` (datetime)
  - Flask `app` object (used by gunicorn in Procfile as `app:app`)
  - `require_auth` decorator that returns 401 JSON if not logged in
  - `POST /api/login` → `{"message": "ok"}` (200) or `{"error": "..."}` (401)
  - `POST /api/logout` → `{"message": "ok"}` (200)
  - `GET /api/init-db` → `{"message": "Database initialized"}` (200) — creates tables

- [ ] **Step 1: Write test for auth endpoint**

Create `backend/test_app.py`:

```python
import os
os.environ['DATABASE_URL'] = 'postgresql://test'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['ADMIN_PASSWORD'] = 'testpass'

import pytest
from unittest.mock import patch, MagicMock


def test_login_wrong_password(client):
    resp = client.post('/api/login', json={'password': 'wrong'})
    assert resp.status_code == 401
    assert 'error' in resp.get_json()


def test_login_correct_password(client):
    resp = client.post('/api/login', json={'password': 'testpass'})
    assert resp.status_code == 200
    assert resp.get_json()['message'] == 'ok'


def test_protected_endpoint_without_auth(client):
    resp = client.get('/api/accounts')
    assert resp.status_code == 401


@pytest.fixture
def client():
    with patch('sqlalchemy.create_engine') as mock_engine:
        mock_engine.return_value = MagicMock()
        import app as flask_app
        flask_app.app.config['TESTING'] = True
        with flask_app.app.test_client() as c:
            yield c
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
pytest test_app.py -v
```

Expected: ImportError or ModuleNotFoundError (app.py doesn't exist yet)

- [ ] **Step 3: Create `backend/app.py`**

```python
import os
import uuid
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from sqlalchemy import create_engine, Column, String, Numeric, Date, DateTime, Text, ForeignKey, text
from sqlalchemy.orm import DeclarativeBase, Session, relationship
from sqlalchemy.dialects.postgresql import UUID

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

ALLOWED_ORIGIN = os.getenv('ALLOWED_ORIGIN', 'http://localhost:3000')
CORS(app, supports_credentials=True, origins=[ALLOWED_ORIGIN])

DATABASE_URL = os.environ['DATABASE_URL']
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    transactions = relationship('Transaction', back_populates='account',
                                cascade='all, delete-orphan')


class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.id', ondelete='CASCADE'),
                        nullable=False)
    type = Column(String(6), nullable=False)   # 'credit' or 'debit'
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String(500), nullable=False)
    notes = Column(Text, nullable=True)
    transaction_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    account = relationship('Account', back_populates='transactions')


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    if data.get('password') == os.environ['ADMIN_PASSWORD']:
        session['authenticated'] = True
        return jsonify({'message': 'ok'})
    return jsonify({'error': 'Incorrect password'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'ok'})


@app.route('/api/auth-check', methods=['GET'])
def auth_check():
    return jsonify({'authenticated': bool(session.get('authenticated'))})


@app.route('/api/init-db', methods=['GET'])
def init_db():
    Base.metadata.create_all(engine)
    return jsonify({'message': 'Database initialized'})


if __name__ == '__main__':
    app.run(debug=True)
```

- [ ] **Step 4: Run auth tests**

```bash
cd backend
pytest test_app.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Verify DB connection manually**

```bash
cd backend
# Set DATABASE_URL in .env first, then:
python -c "from app import engine; engine.connect().close(); print('DB OK')"
```

Expected: "DB OK" (or connection error if Supabase creds not set yet)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/test_app.py
git commit -m "feat: Flask app with models, auth, and DB init endpoint"
```

---

### Task 3: Flask API — Account Routes

**Files:**
- Modify: `backend/app.py` (add account routes after `init_db`)

**Interfaces:**
- Consumes: `Account`, `Transaction`, `Session`, `engine`, `require_auth` from Task 2
- Produces:
  - `GET /api/accounts` → `[{id, name, created_at, total_credit, total_debit, balance}, ...]` (200)
  - `POST /api/accounts` body `{name: str}` → `{id, name, created_at, total_credit:0, total_debit:0, balance:0}` (201) or `{error}` (400/409)
  - `GET /api/accounts/<id>` → same as account item above (200) or `{error}` (404)
  - `DELETE /api/accounts/<id>` → `{message: "deleted"}` (200) or `{error}` (404)

- [ ] **Step 1: Add account summary helper + routes to `app.py`**

Add after `init_db` route in `backend/app.py`:

```python
def account_summary(account):
    credits = sum(t.amount for t in account.transactions if t.type == 'credit')
    debits = sum(t.amount for t in account.transactions if t.type == 'debit')
    return {
        'id': str(account.id),
        'name': account.name,
        'created_at': account.created_at.isoformat(),
        'total_credit': float(credits),
        'total_debit': float(debits),
        'balance': float(credits - debits),
    }


@app.route('/api/accounts', methods=['GET'])
@require_auth
def list_accounts():
    with Session(engine) as db:
        accounts = db.query(Account).order_by(Account.created_at).all()
        return jsonify([account_summary(a) for a in accounts])


@app.route('/api/accounts', methods=['POST'])
@require_auth
def create_account():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Account name is required'}), 400
    if len(name) > 200:
        return jsonify({'error': 'Account name is too long'}), 400
    with Session(engine) as db:
        existing = db.query(Account).filter_by(name=name).first()
        if existing:
            return jsonify({'error': 'An account with this name already exists'}), 409
        account = Account(name=name)
        db.add(account)
        db.commit()
        db.refresh(account)
        return jsonify(account_summary(account)), 201


@app.route('/api/accounts/<account_id>', methods=['GET'])
@require_auth
def get_account(account_id):
    with Session(engine) as db:
        account = db.get(Account, account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        return jsonify(account_summary(account))


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
@require_auth
def delete_account(account_id):
    with Session(engine) as db:
        account = db.get(Account, account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        db.delete(account)
        db.commit()
        return jsonify({'message': 'deleted'})
```

- [ ] **Step 2: Add account route tests to `test_app.py`**

```python
def test_create_account(authed_client):
    resp = authed_client.post('/api/accounts', json={'name': 'Food Account'})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['name'] == 'Food Account'
    assert data['total_credit'] == 0.0
    assert data['balance'] == 0.0


def test_create_account_no_name(authed_client):
    resp = authed_client.post('/api/accounts', json={'name': ''})
    assert resp.status_code == 400


def test_list_accounts(authed_client):
    authed_client.post('/api/accounts', json={'name': 'Test'})
    resp = authed_client.get('/api/accounts')
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


@pytest.fixture
def authed_client(client):
    client.post('/api/login', json={'password': 'testpass'})
    return client
```

Note: These tests use SQLite in-memory for isolation. Add to the fixture:
```python
@pytest.fixture
def client():
    with patch.dict(os.environ, {
        'DATABASE_URL': 'sqlite:///:memory:',  # ponytail: sqlite for tests only
        'SECRET_KEY': 'test-secret',
        'ADMIN_PASSWORD': 'testpass',
    }):
        # reimport fresh app for each test
        import importlib
        import app as flask_app
        importlib.reload(flask_app)
        flask_app.Base.metadata.create_all(flask_app.engine)
        flask_app.app.config['TESTING'] = True
        with flask_app.app.test_client() as c:
            yield c
```

- [ ] **Step 3: Run tests**

```bash
cd backend
pip install pytest
pytest test_app.py -v
```

Expected: All account tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/test_app.py
git commit -m "feat: account CRUD API endpoints"
```

---

### Task 4: Flask API — Transaction Routes

**Files:**
- Modify: `backend/app.py` (add transaction routes)

**Interfaces:**
- Consumes: `Transaction`, `Account`, `Session`, `engine`, `require_auth`, `account_summary` from Tasks 2-3
- Produces:
  - `GET /api/accounts/<id>/transactions` → `[{id, account_id, type, amount, description, notes, transaction_date, created_at}, ...]` (200)
  - `POST /api/accounts/<id>/transactions` body `{type, amount, description, notes?, transaction_date}` → transaction object (201) or `{error}` (400/404)
  - `DELETE /api/transactions/<id>` → `{message: "deleted"}` (200) or `{error}` (404)

- [ ] **Step 1: Add transaction routes to `app.py`**

Add after account routes in `backend/app.py`:

```python
def transaction_dict(t):
    return {
        'id': str(t.id),
        'account_id': str(t.account_id),
        'type': t.type,
        'amount': float(t.amount),
        'description': t.description,
        'notes': t.notes,
        'transaction_date': t.transaction_date.isoformat(),
        'created_at': t.created_at.isoformat(),
    }


@app.route('/api/accounts/<account_id>/transactions', methods=['GET'])
@require_auth
def list_transactions(account_id):
    with Session(engine) as db:
        account = db.get(Account, account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        txns = (db.query(Transaction)
                .filter_by(account_id=account_id)
                .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
                .all())
        return jsonify([transaction_dict(t) for t in txns])


@app.route('/api/accounts/<account_id>/transactions', methods=['POST'])
@require_auth
def create_transaction(account_id):
    with Session(engine) as db:
        account = db.get(Account, account_id)
        if not account:
            return jsonify({'error': 'Account not found'}), 404

    data = request.get_json() or {}
    txn_type = data.get('type', '').strip().lower()
    if txn_type not in ('credit', 'debit'):
        return jsonify({'error': 'Type must be credit or debit'}), 400

    try:
        amount = Decimal(str(data.get('amount', 0)))
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        return jsonify({'error': 'Amount must be a positive number'}), 400

    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({'error': 'Description is required'}), 400

    try:
        txn_date = date.fromisoformat(data.get('transaction_date', ''))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date'}), 400

    notes = (data.get('notes') or '').strip() or None

    with Session(engine) as db:
        txn = Transaction(
            account_id=account_id,
            type=txn_type,
            amount=amount,
            description=description,
            notes=notes,
            transaction_date=txn_date,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        return jsonify(transaction_dict(txn)), 201


@app.route('/api/transactions/<transaction_id>', methods=['DELETE'])
@require_auth
def delete_transaction(transaction_id):
    with Session(engine) as db:
        txn = db.get(Transaction, transaction_id)
        if not txn:
            return jsonify({'error': 'Transaction not found'}), 404
        db.delete(txn)
        db.commit()
        return jsonify({'message': 'deleted'})
```

- [ ] **Step 2: Add transaction tests to `test_app.py`**

```python
def test_add_credit_transaction(authed_client):
    acc = authed_client.post('/api/accounts', json={'name': 'Txn Test'}).get_json()
    resp = authed_client.post(f'/api/accounts/{acc["id"]}/transactions', json={
        'type': 'credit', 'amount': 5000, 'description': 'Donation', 'transaction_date': '2026-08-17'
    })
    assert resp.status_code == 201
    assert resp.get_json()['type'] == 'credit'


def test_balance_calculation(authed_client):
    acc = authed_client.post('/api/accounts', json={'name': 'Bal Test'}).get_json()
    aid = acc['id']
    authed_client.post(f'/api/accounts/{aid}/transactions', json={
        'type': 'credit', 'amount': 10000, 'description': 'In', 'transaction_date': '2026-08-17'
    })
    authed_client.post(f'/api/accounts/{aid}/transactions', json={
        'type': 'debit', 'amount': 4000, 'description': 'Out', 'transaction_date': '2026-08-17'
    })
    summary = authed_client.get(f'/api/accounts/{aid}').get_json()
    assert summary['total_credit'] == 10000.0
    assert summary['total_debit'] == 4000.0
    assert summary['balance'] == 6000.0


def test_negative_balance(authed_client):
    acc = authed_client.post('/api/accounts', json={'name': 'Neg Test'}).get_json()
    aid = acc['id']
    authed_client.post(f'/api/accounts/{aid}/transactions', json={
        'type': 'debit', 'amount': 5000, 'description': 'Out', 'transaction_date': '2026-08-17'
    })
    summary = authed_client.get(f'/api/accounts/{aid}').get_json()
    assert summary['balance'] == -5000.0


def test_transactions_dont_cross_accounts(authed_client):
    a1 = authed_client.post('/api/accounts', json={'name': 'Acct A'}).get_json()
    a2 = authed_client.post('/api/accounts', json={'name': 'Acct B'}).get_json()
    authed_client.post(f'/api/accounts/{a1["id"]}/transactions', json={
        'type': 'credit', 'amount': 10000, 'description': 'In A', 'transaction_date': '2026-08-17'
    })
    s2 = authed_client.get(f'/api/accounts/{a2["id"]}').get_json()
    assert s2['total_credit'] == 0.0


def test_invalid_amount(authed_client):
    acc = authed_client.post('/api/accounts', json={'name': 'Amt Test'}).get_json()
    resp = authed_client.post(f'/api/accounts/{acc["id"]}/transactions', json={
        'type': 'credit', 'amount': -100, 'description': 'Bad', 'transaction_date': '2026-08-17'
    })
    assert resp.status_code == 400
```

- [ ] **Step 3: Run all tests**

```bash
cd backend
pytest test_app.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/test_app.py
git commit -m "feat: transaction CRUD API with balance calculation"
```

---

### Task 5: Frontend — Config & Auth (Login Page)

**Files:**
- Create: `frontend/js/config.js`
- Create: `frontend/js/auth.js`
- Create: `frontend/login.html`
- Create: `frontend/css/style.css` (starter — extended in Task 8)

**Interfaces:**
- Produces:
  - `API_BASE` constant (from config.js) used by all other JS files
  - `apiFetch(path, options)` helper that auto-includes credentials
  - `guardAuth()` function: redirects to login.html if not authenticated
  - `logout()` function

- [ ] **Step 1: Create `frontend/js/config.js`**

```js
// Change API_BASE to your Render backend URL for production
const API_BASE = 'http://localhost:5000';
```

- [ ] **Step 2: Create `frontend/js/auth.js`**

```js
async function apiFetch(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  return res;
}

async function guardAuth() {
  const res = await apiFetch('/api/auth-check');
  const data = await res.json();
  if (!data.authenticated) {
    window.location.href = 'login.html';
  }
}

async function logout() {
  await apiFetch('/api/logout', { method: 'POST' });
  window.location.href = 'login.html';
}
```

- [ ] **Step 3: Create `frontend/login.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dharamshala Accounts</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body class="login-page">
  <div class="login-card">
    <div class="login-logo">🏛️</div>
    <h1 class="login-title">Dharamshala Accounts</h1>
    <p class="login-subtitle">Manage your accounts and daily transactions</p>
    <form id="loginForm" class="login-form">
      <div class="form-group">
        <label for="password">Password</label>
        <input type="password" id="password" placeholder="Enter password" required autofocus>
      </div>
      <div id="loginError" class="error-msg hidden"></div>
      <button type="submit" class="btn btn-primary btn-full">Login</button>
    </form>
  </div>

  <script src="js/config.js"></script>
  <script src="js/auth.js"></script>
  <script>
    // Redirect if already logged in
    apiFetch('/api/auth-check').then(r => r.json()).then(d => {
      if (d.authenticated) window.location.href = 'index.html';
    });

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const password = document.getElementById('password').value;
      const errEl = document.getElementById('loginError');
      errEl.classList.add('hidden');

      const res = await apiFetch('/api/login', {
        method: 'POST',
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        window.location.href = 'index.html';
      } else {
        const data = await res.json();
        errEl.textContent = data.error || 'Login failed. Please try again.';
        errEl.classList.remove('hidden');
      }
    });
  </script>
</body>
</html>
```

- [ ] **Step 4: Create starter `frontend/css/style.css`** (login styles + base; full styles added in Task 8)

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #f5f5f5;
  --surface: #ffffff;
  --border: #e0e0e0;
  --text: #1a1a1a;
  --text-secondary: #666;
  --primary: #2563eb;
  --primary-hover: #1d4ed8;
  --danger: #dc2626;
  --danger-hover: #b91c1c;
  --credit: #16a34a;
  --debit: #dc2626;
  --radius: 12px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04);
}

body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); line-height: 1.5; }

/* Login */
.login-page { display: flex; align-items: center; justify-content: center;
              min-height: 100vh; padding: 1rem; }
.login-card { background: var(--surface); border-radius: var(--radius);
              box-shadow: var(--shadow-md); padding: 2.5rem 2rem;
              width: 100%; max-width: 380px; text-align: center; }
.login-logo { font-size: 2.5rem; margin-bottom: 0.75rem; }
.login-title { font-size: 1.5rem; font-weight: 700; color: var(--text); }
.login-subtitle { color: var(--text-secondary); margin: 0.5rem 0 1.5rem; font-size: 0.9rem; }
.login-form { text-align: left; }

/* Forms */
.form-group { margin-bottom: 1rem; }
.form-group label { display: block; font-size: 0.875rem; font-weight: 500;
                    margin-bottom: 0.375rem; color: var(--text); }
.form-group input, .form-group textarea, .form-group select {
  width: 100%; padding: 0.625rem 0.75rem; border: 1px solid var(--border);
  border-radius: 8px; font-size: 0.95rem; color: var(--text);
  background: var(--surface); transition: border-color 0.15s; outline: none; }
.form-group input:focus, .form-group textarea:focus {
  border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.form-group textarea { resize: vertical; min-height: 72px; }

/* Buttons */
.btn { padding: 0.625rem 1.25rem; border: none; border-radius: 8px; font-size: 0.9rem;
       font-weight: 500; cursor: pointer; transition: all 0.15s; display: inline-flex;
       align-items: center; gap: 0.375rem; white-space: nowrap; }
.btn-primary { background: var(--primary); color: white; }
.btn-primary:hover { background: var(--primary-hover); }
.btn-danger { background: var(--danger); color: white; }
.btn-danger:hover { background: var(--danger-hover); }
.btn-ghost { background: transparent; color: var(--text-secondary);
             border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--bg); }
.btn-full { width: 100%; justify-content: center; }

/* Utilities */
.hidden { display: none !important; }
.error-msg { color: var(--danger); font-size: 0.875rem; padding: 0.5rem; background: #fef2f2;
             border-radius: 6px; margin-bottom: 0.75rem; }
```

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: login page and auth helpers"
```

---

### Task 6: Frontend — Dashboard (Accounts List)

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/js/dashboard.js`
- Modify: `frontend/css/style.css` (add dashboard styles)

**Interfaces:**
- Consumes: `API_BASE` (config.js), `apiFetch`, `guardAuth`, `logout` (auth.js)
- Produces: Working accounts dashboard page

- [ ] **Step 1: Create `frontend/js/dashboard.js`**

```js
// Indian number formatting: 1,00,000 style
function formatINR(amount) {
  const num = Math.abs(amount);
  const str = num.toFixed(2).replace(/\.00$/, '');
  const [integer, decimal] = str.split('.');
  let result = '';
  const len = integer.length;
  if (len <= 3) {
    result = integer;
  } else {
    result = integer.slice(-3);
    let rest = integer.slice(0, len - 3);
    while (rest.length > 2) {
      result = rest.slice(-2) + ',' + result;
      rest = rest.slice(0, rest.length - 2);
    }
    result = rest + ',' + result;
  }
  const formatted = decimal ? result + '.' + decimal : result;
  return (amount < 0 ? '-₹' : '₹') + formatted;
}

async function loadAccounts() {
  const grid = document.getElementById('accountsGrid');
  const empty = document.getElementById('emptyState');
  grid.innerHTML = '<div class="loading">Loading accounts...</div>';

  const res = await apiFetch('/api/accounts');
  if (!res.ok) { grid.innerHTML = '<div class="error-msg">Failed to load accounts.</div>'; return; }

  const accounts = await res.json();
  grid.innerHTML = '';

  if (accounts.length === 0) {
    grid.classList.add('hidden');
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  grid.classList.remove('hidden');
  accounts.forEach(a => grid.appendChild(makeAccountCard(a)));
}

function makeAccountCard(a) {
  const card = document.createElement('div');
  card.className = 'account-card';
  card.innerHTML = `
    <div class="account-card-name">${escHtml(a.name)}</div>
    <div class="account-card-stats">
      <div class="stat">
        <span class="stat-label">Credit</span>
        <span class="stat-value credit">${formatINR(a.total_credit)}</span>
      </div>
      <div class="stat">
        <span class="stat-label">Debit</span>
        <span class="stat-value debit">${formatINR(a.total_debit)}</span>
      </div>
      <div class="stat stat-balance">
        <span class="stat-label">Balance</span>
        <span class="stat-value ${a.balance < 0 ? 'debit' : 'credit'}">${formatINR(a.balance)}</span>
      </div>
    </div>
    <div class="account-card-actions">
      <a href="account.html?id=${a.id}" class="btn btn-primary">View Account</a>
      <button class="btn btn-ghost btn-delete-account" data-id="${a.id}" data-name="${escHtml(a.name)}">Delete</button>
    </div>`;
  card.querySelector('.btn-delete-account').addEventListener('click', () => confirmDeleteAccount(a.id, a.name));
  return card;
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function createAccount(name) {
  const res = await apiFetch('/api/accounts', { method: 'POST', body: JSON.stringify({ name }) });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Failed to create account');
  return data;
}

function confirmDeleteAccount(id, name) {
  const modal = document.getElementById('deleteModal');
  document.getElementById('deleteModalMsg').textContent =
    `Delete "${name}"? This will permanently delete all transactions in this account.`;
  modal.classList.remove('hidden');
  document.getElementById('confirmDeleteBtn').onclick = async () => {
    modal.classList.add('hidden');
    await apiFetch(`/api/accounts/${id}`, { method: 'DELETE' });
    loadAccounts();
  };
}

// Wire up on page load
document.addEventListener('DOMContentLoaded', async () => {
  await guardAuth();
  loadAccounts();

  document.getElementById('logoutBtn').addEventListener('click', logout);

  const addAccountModal = document.getElementById('addAccountModal');
  document.getElementById('addAccountBtn').addEventListener('click', () => {
    addAccountModal.classList.remove('hidden');
    document.getElementById('accountNameInput').value = '';
    document.getElementById('accountNameInput').focus();
  });

  document.getElementById('addAccountForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('accountNameInput').value.trim();
    const errEl = document.getElementById('addAccountError');
    errEl.classList.add('hidden');
    try {
      await createAccount(name);
      addAccountModal.classList.add('hidden');
      loadAccounts();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  });

  document.getElementById('cancelAddAccount').addEventListener('click', () =>
    addAccountModal.classList.add('hidden'));
  document.getElementById('cancelDelete').addEventListener('click', () =>
    document.getElementById('deleteModal').classList.add('hidden'));

  // Close modals on backdrop click
  [addAccountModal, document.getElementById('deleteModal')].forEach(modal => {
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });
  });
});
```

- [ ] **Step 2: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dharamshala Accounts</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <header class="app-header">
    <div class="container">
      <div class="header-inner">
        <div>
          <h1 class="app-title">🏛️ Dharamshala Accounts</h1>
          <p class="app-subtitle">Manage your accounts and daily transactions</p>
        </div>
        <button id="logoutBtn" class="btn btn-ghost">Logout</button>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="section-header">
      <h2 class="section-title">All Accounts</h2>
      <button id="addAccountBtn" class="btn btn-primary">+ Add Account</button>
    </div>

    <div id="accountsGrid" class="accounts-grid"></div>

    <div id="emptyState" class="empty-state hidden">
      <div class="empty-icon">📂</div>
      <h3>No accounts yet</h3>
      <p>Create your first account to get started.</p>
      <button id="emptyAddBtn" onclick="document.getElementById('addAccountBtn').click()"
              class="btn btn-primary">+ Add Account</button>
    </div>
  </main>

  <!-- Add Account Modal -->
  <div id="addAccountModal" class="modal-overlay hidden">
    <div class="modal">
      <h3 class="modal-title">Create New Account</h3>
      <form id="addAccountForm">
        <div class="form-group">
          <label for="accountNameInput">Account Name</label>
          <input type="text" id="accountNameInput" placeholder="e.g. Food Account" required>
        </div>
        <div id="addAccountError" class="error-msg hidden"></div>
        <div class="modal-actions">
          <button type="button" id="cancelAddAccount" class="btn btn-ghost">Cancel</button>
          <button type="submit" class="btn btn-primary">Create Account</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Delete Confirmation Modal -->
  <div id="deleteModal" class="modal-overlay hidden">
    <div class="modal">
      <h3 class="modal-title">Confirm Delete</h3>
      <p id="deleteModalMsg" class="modal-body-text"></p>
      <div class="modal-actions">
        <button id="cancelDelete" class="btn btn-ghost">Cancel</button>
        <button id="confirmDeleteBtn" class="btn btn-danger">Delete Account</button>
      </div>
    </div>
  </div>

  <script src="js/config.js"></script>
  <script src="js/auth.js"></script>
  <script src="js/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html frontend/js/dashboard.js
git commit -m "feat: accounts dashboard with add/delete"
```

---

### Task 7: Frontend — Account Detail Page

**Files:**
- Create: `frontend/account.html`
- Create: `frontend/js/account.js`

**Interfaces:**
- Consumes: `API_BASE` (config.js), `apiFetch`, `guardAuth`, `logout` (auth.js), `formatINR`, `escHtml` (dashboard.js — these two functions will be moved to a shared location: add them to auth.js instead so both pages can use them)
- Produces: Working account detail page with transaction management

**Note:** Move `formatINR` and `escHtml` from `dashboard.js` to `auth.js` so `account.js` can use them without duplicating code.

- [ ] **Step 1: Move `formatINR` and `escHtml` to `auth.js`** (edit `frontend/js/auth.js`, append):

```js
function formatINR(amount) {
  const num = Math.abs(amount);
  const str = num.toFixed(2).replace(/\.00$/, '');
  const [integer, decimal] = str.split('.');
  let result = '';
  const len = integer.length;
  if (len <= 3) {
    result = integer;
  } else {
    result = integer.slice(-3);
    let rest = integer.slice(0, len - 3);
    while (rest.length > 2) {
      result = rest.slice(-2) + ',' + result;
      rest = rest.slice(0, rest.length - 2);
    }
    result = rest + ',' + result;
  }
  const formatted = decimal ? result + '.' + decimal : result;
  return (amount < 0 ? '-₹' : '₹') + formatted;
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
}
```

Remove `formatINR` and `escHtml` from `dashboard.js` (they'll now come from `auth.js` which is loaded first).

- [ ] **Step 2: Create `frontend/js/account.js`**

```js
const params = new URLSearchParams(window.location.search);
const accountId = params.get('id');
let currentAccount = null;

async function loadAccount() {
  const res = await apiFetch(`/api/accounts/${accountId}`);
  if (res.status === 404) { window.location.href = 'index.html'; return; }
  currentAccount = await res.json();
  document.getElementById('accountName').textContent = currentAccount.name;
  document.title = currentAccount.name + ' — Dharamshala Accounts';
  updateSummary(currentAccount);
}

function updateSummary(a) {
  document.getElementById('totalCredit').textContent = formatINR(a.total_credit);
  document.getElementById('totalDebit').textContent = formatINR(a.total_debit);
  const balEl = document.getElementById('balance');
  balEl.textContent = formatINR(a.balance);
  balEl.className = 'summary-amount ' + (a.balance < 0 ? 'debit' : 'credit');
}

async function loadTransactions() {
  const res = await apiFetch(`/api/accounts/${accountId}/transactions`);
  const txns = await res.json();
  const credits = txns.filter(t => t.type === 'credit');
  const debits = txns.filter(t => t.type === 'debit');
  renderTransactionList('creditList', 'creditEmpty', credits, 'credit');
  renderTransactionList('debitList', 'debitEmpty', debits, 'debit');
}

function renderTransactionList(listId, emptyId, txns, type) {
  const list = document.getElementById(listId);
  const empty = document.getElementById(emptyId);
  list.innerHTML = '';
  if (txns.length === 0) { empty.classList.remove('hidden'); return; }
  empty.classList.add('hidden');
  txns.forEach(t => list.appendChild(makeTxnCard(t, type)));
}

function makeTxnCard(t, type) {
  const card = document.createElement('div');
  card.className = `txn-card txn-${type}`;
  card.innerHTML = `
    <div class="txn-amount">${type === 'credit' ? '+' : '-'}${formatINR(t.amount)}</div>
    <div class="txn-desc">${escHtml(t.description)}</div>
    <div class="txn-date">${formatDate(t.transaction_date)}</div>
    ${t.notes ? `<div class="txn-notes">${escHtml(t.notes)}</div>` : ''}
    <button class="btn btn-ghost btn-sm btn-delete-txn" data-id="${t.id}">Delete</button>`;
  card.querySelector('.btn-delete-txn').addEventListener('click', () => confirmDeleteTxn(t.id));
  return card;
}

function confirmDeleteTxn(id) {
  const modal = document.getElementById('deleteTxnModal');
  modal.classList.remove('hidden');
  document.getElementById('confirmDeleteTxnBtn').onclick = async () => {
    modal.classList.add('hidden');
    await apiFetch(`/api/transactions/${id}`, { method: 'DELETE' });
    await refreshAll();
  };
}

async function refreshAll() {
  const res = await apiFetch(`/api/accounts/${accountId}`);
  currentAccount = await res.json();
  updateSummary(currentAccount);
  await loadTransactions();
}

function openAddModal(type) {
  const modal = document.getElementById('addTxnModal');
  document.getElementById('txnType').value = type;
  document.getElementById('addTxnTitle').textContent = type === 'credit' ? 'Add Credit' : 'Add Debit';
  document.getElementById('addTxnForm').reset();
  document.getElementById('txnDate').value = new Date().toISOString().split('T')[0];
  document.getElementById('addTxnError').classList.add('hidden');
  modal.classList.remove('hidden');
  document.getElementById('txnAmount').focus();
}

document.addEventListener('DOMContentLoaded', async () => {
  if (!accountId) { window.location.href = 'index.html'; return; }
  await guardAuth();
  await loadAccount();
  await loadTransactions();

  document.getElementById('logoutBtn').addEventListener('click', logout);
  document.getElementById('addCreditBtn').addEventListener('click', () => openAddModal('credit'));
  document.getElementById('addDebitBtn').addEventListener('click', () => openAddModal('debit'));
  document.getElementById('cancelAddTxn').addEventListener('click', () =>
    document.getElementById('addTxnModal').classList.add('hidden'));
  document.getElementById('cancelDeleteTxn').addEventListener('click', () =>
    document.getElementById('deleteTxnModal').classList.add('hidden'));

  document.getElementById('addTxnForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('addTxnError');
    errEl.classList.add('hidden');
    const body = {
      type: document.getElementById('txnType').value,
      amount: parseFloat(document.getElementById('txnAmount').value),
      description: document.getElementById('txnDesc').value.trim(),
      notes: document.getElementById('txnNotes').value.trim(),
      transaction_date: document.getElementById('txnDate').value,
    };
    const res = await apiFetch(`/api/accounts/${accountId}/transactions`, {
      method: 'POST', body: JSON.stringify(body),
    });
    if (res.ok) {
      document.getElementById('addTxnModal').classList.add('hidden');
      await refreshAll();
    } else {
      const data = await res.json();
      errEl.textContent = data.error || 'Failed to add transaction.';
      errEl.classList.remove('hidden');
    }
  });

  [document.getElementById('addTxnModal'), document.getElementById('deleteTxnModal')].forEach(modal => {
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });
  });
});
```

- [ ] **Step 3: Create `frontend/account.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Account — Dharamshala Accounts</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <header class="app-header">
    <div class="container">
      <div class="header-inner">
        <div>
          <a href="index.html" class="back-link">← Back to Accounts</a>
          <h1 class="app-title" id="accountName">Loading...</h1>
        </div>
        <button id="logoutBtn" class="btn btn-ghost">Logout</button>
      </div>
    </div>
  </header>

  <main class="container">
    <!-- Summary Cards -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Total Credit</div>
        <div class="summary-amount credit" id="totalCredit">₹0</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Debit</div>
        <div class="summary-amount debit" id="totalDebit">₹0</div>
      </div>
      <div class="summary-card summary-card-balance">
        <div class="summary-label">Balance</div>
        <div class="summary-amount credit" id="balance">₹0</div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="txn-actions">
      <button id="addCreditBtn" class="btn btn-credit">+ Add Credit</button>
      <button id="addDebitBtn" class="btn btn-debit">+ Add Debit</button>
    </div>

    <!-- Transactions -->
    <div class="txn-sections">
      <div class="txn-section">
        <h2 class="txn-section-title credit-title">Credit</h2>
        <div id="creditList"></div>
        <div id="creditEmpty" class="empty-state hidden">
          <p>No credit transactions yet.</p>
        </div>
      </div>
      <div class="txn-section">
        <h2 class="txn-section-title debit-title">Debit</h2>
        <div id="debitList"></div>
        <div id="debitEmpty" class="empty-state hidden">
          <p>No debit transactions yet.</p>
        </div>
      </div>
    </div>
  </main>

  <!-- Add Transaction Modal -->
  <div id="addTxnModal" class="modal-overlay hidden">
    <div class="modal">
      <h3 class="modal-title" id="addTxnTitle">Add Transaction</h3>
      <form id="addTxnForm">
        <input type="hidden" id="txnType" value="credit">
        <div class="form-group">
          <label>Amount (₹)</label>
          <input type="number" id="txnAmount" placeholder="e.g. 5000" min="0.01" step="0.01" required>
        </div>
        <div class="form-group">
          <label>Description</label>
          <input type="text" id="txnDesc" placeholder="e.g. Donation received" required>
        </div>
        <div class="form-group">
          <label>Date</label>
          <input type="date" id="txnDate" required>
        </div>
        <div class="form-group">
          <label>Notes (optional)</label>
          <textarea id="txnNotes" placeholder="Additional details..."></textarea>
        </div>
        <div id="addTxnError" class="error-msg hidden"></div>
        <div class="modal-actions">
          <button type="button" id="cancelAddTxn" class="btn btn-ghost">Cancel</button>
          <button type="submit" class="btn btn-primary">Add</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Delete Transaction Modal -->
  <div id="deleteTxnModal" class="modal-overlay hidden">
    <div class="modal">
      <h3 class="modal-title">Delete Transaction?</h3>
      <p class="modal-body-text">This action cannot be undone.</p>
      <div class="modal-actions">
        <button id="cancelDeleteTxn" class="btn btn-ghost">Cancel</button>
        <button id="confirmDeleteTxnBtn" class="btn btn-danger">Delete</button>
      </div>
    </div>
  </div>

  <script src="js/config.js"></script>
  <script src="js/auth.js"></script>
  <script src="js/account.js"></script>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/account.html frontend/js/account.js frontend/js/auth.js frontend/js/dashboard.js
git commit -m "feat: account detail page with transaction management"
```

---

### Task 8: CSS — Complete Styling

**Files:**
- Modify: `frontend/css/style.css` (add all remaining styles)

**Interfaces:**
- Consumes: HTML classes used in Tasks 5-7
- Produces: Fully styled, responsive, mobile-ready UI

- [ ] **Step 1: Append all remaining styles to `frontend/css/style.css`**

```css
/* ── Layout ────────────────────────────────────────────── */
.container { max-width: 1100px; margin: 0 auto; padding: 0 1rem; }

/* ── Header ─────────────────────────────────────────────── */
.app-header { background: var(--surface); border-bottom: 1px solid var(--border);
              padding: 1rem 0; position: sticky; top: 0; z-index: 10; }
.header-inner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.app-title { font-size: 1.25rem; font-weight: 700; margin: 0; }
.app-subtitle { color: var(--text-secondary); font-size: 0.85rem; margin: 0; }
.back-link { color: var(--primary); text-decoration: none; font-size: 0.875rem;
             display: inline-block; margin-bottom: 0.25rem; }
.back-link:hover { text-decoration: underline; }

/* ── Section header ─────────────────────────────────────── */
.section-header { display: flex; align-items: center; justify-content: space-between;
                  margin: 1.5rem 0 1rem; }
.section-title { font-size: 1.1rem; font-weight: 600; }

/* ── Accounts Grid ──────────────────────────────────────── */
.accounts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                 gap: 1rem; }
.account-card { background: var(--surface); border-radius: var(--radius);
                box-shadow: var(--shadow); padding: 1.25rem;
                transition: box-shadow 0.15s; border: 1px solid var(--border); }
.account-card:hover { box-shadow: var(--shadow-md); }
.account-card-name { font-size: 1.05rem; font-weight: 600; margin-bottom: 1rem; }
.account-card-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
                      margin-bottom: 1rem; }
.stat-balance { grid-column: 1 / -1; padding-top: 0.5rem;
                border-top: 1px solid var(--border); }
.stat-label { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase;
              letter-spacing: 0.04em; display: block; }
.stat-value { font-size: 1rem; font-weight: 600; display: block; margin-top: 0.1rem; }
.account-card-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.account-card-actions .btn { flex: 1; justify-content: center; font-size: 0.85rem;
                              padding: 0.5rem 0.75rem; }

/* ── Summary Cards ──────────────────────────────────────── */
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.5rem 0; }
.summary-card { background: var(--surface); border-radius: var(--radius);
                box-shadow: var(--shadow); padding: 1.25rem; text-align: center;
                border: 1px solid var(--border); }
.summary-card-balance { border: 2px solid var(--border); }
.summary-label { font-size: 0.8rem; color: var(--text-secondary); text-transform: uppercase;
                 letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.summary-amount { font-size: 1.5rem; font-weight: 700; }

/* ── Transaction Actions ────────────────────────────────── */
.txn-actions { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.btn-credit { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.btn-credit:hover { background: #bbf7d0; }
.btn-debit { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
.btn-debit:hover { background: #fecaca; }

/* ── Transaction Sections ───────────────────────────────── */
.txn-sections { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
.txn-section-title { font-size: 1rem; font-weight: 600; margin-bottom: 0.75rem;
                     padding-bottom: 0.5rem; border-bottom: 2px solid; }
.credit-title { border-color: var(--credit); color: var(--credit); }
.debit-title { border-color: var(--debit); color: var(--debit); }

/* ── Transaction Cards ──────────────────────────────────── */
.txn-card { background: var(--surface); border-radius: 8px; padding: 0.875rem;
            margin-bottom: 0.625rem; border: 1px solid var(--border);
            box-shadow: var(--shadow); }
.txn-credit { border-left: 3px solid var(--credit); }
.txn-debit { border-left: 3px solid var(--debit); }
.txn-amount { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.25rem; }
.txn-credit .txn-amount { color: var(--credit); }
.txn-debit .txn-amount { color: var(--debit); }
.txn-desc { font-size: 0.9rem; font-weight: 500; margin-bottom: 0.25rem; }
.txn-date { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.25rem; }
.txn-notes { font-size: 0.8rem; color: var(--text-secondary); font-style: italic;
             margin-bottom: 0.5rem; }
.btn-sm { padding: 0.3rem 0.625rem; font-size: 0.8rem; }
.btn-delete-txn { margin-top: 0.375rem; }

/* ── Color Utilities ────────────────────────────────────── */
.credit { color: var(--credit); }
.debit { color: var(--debit); }

/* ── Empty States ───────────────────────────────────────── */
.empty-state { text-align: center; padding: 3rem 1rem; color: var(--text-secondary); }
.empty-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
.empty-state h3 { font-size: 1.1rem; color: var(--text); margin-bottom: 0.375rem; }
.empty-state p { margin-bottom: 1rem; }
.loading { text-align: center; padding: 2rem; color: var(--text-secondary); }

/* ── Modals ─────────────────────────────────────────────── */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45);
                 display: flex; align-items: center; justify-content: center;
                 z-index: 100; padding: 1rem; }
.modal { background: var(--surface); border-radius: var(--radius);
         box-shadow: 0 20px 40px rgba(0,0,0,0.15); padding: 1.75rem;
         width: 100%; max-width: 440px; max-height: 90vh; overflow-y: auto; }
.modal-title { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
.modal-body-text { color: var(--text-secondary); margin-bottom: 1.25rem; line-height: 1.6; }
.modal-actions { display: flex; gap: 0.625rem; justify-content: flex-end; margin-top: 1rem; }

/* ── Mobile ─────────────────────────────────────────────── */
@media (max-width: 640px) {
  .app-title { font-size: 1rem; }
  .summary-grid { grid-template-columns: 1fr 1fr; }
  .summary-card:last-child { grid-column: 1 / -1; }
  .summary-amount { font-size: 1.2rem; }
  .txn-sections { grid-template-columns: 1fr; }
  .txn-actions { flex-direction: column; }
  .txn-actions .btn { width: 100%; justify-content: center; }
  .accounts-grid { grid-template-columns: 1fr; }
  .account-card-actions { flex-direction: column; }
  .modal { padding: 1.25rem; }
  .modal-actions { flex-direction: column-reverse; }
  .modal-actions .btn { width: 100%; justify-content: center; }
}

@media (max-width: 400px) {
  .summary-grid { grid-template-columns: 1fr; }
  .summary-card:last-child { grid-column: auto; }
}
```

- [ ] **Step 2: Manually open `frontend/login.html` in a browser**

Verify:
- Login card is centered
- Typography is clean
- Error state works (type wrong password → message appears)
- Mobile: open at 375px width — card fits, inputs are large enough

- [ ] **Step 3: Commit**

```bash
git add frontend/css/style.css
git commit -m "feat: complete responsive CSS styling"
```

---

### Task 9: Integration, CORS Hardening & README

**Files:**
- Modify: `backend/app.py` (add error handlers)
- Create: `README.md`

**Interfaces:**
- Produces: Production-ready app with `README.md` covering full setup

- [ ] **Step 1: Add global error handlers to `app.py`** (append before `if __name__ == '__main__':`):

```python
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'An internal error occurred'}), 500


@app.errorhandler(Exception)
def unhandled(e):
    app.logger.error(f'Unhandled error: {e}', exc_info=True)
    return jsonify({'error': 'An unexpected error occurred'}), 500
```

- [ ] **Step 2: Create `README.md`** — see full content in the README section below; write it to the file

(Full README content follows in the appendix section at the end of this plan)

- [ ] **Step 3: Run the full application end-to-end locally**

```bash
# Terminal 1: start backend
cd backend
python app.py
# Should see: Running on http://127.0.0.1:5000

# Terminal 2: serve frontend (Python built-in server)
cd frontend
python -m http.server 3000
# Open browser: http://localhost:3000/login.html
```

Verify these flows manually:
- [ ] Login with wrong password → error message shown
- [ ] Login with correct password → redirect to index.html
- [ ] Create account "Food Account"
- [ ] Create account "Maintenance Account"
- [ ] Add Credit ₹10,000 to Food Account → summary shows Credit ₹10,000, Balance ₹10,000
- [ ] Add Debit ₹4,000 to Food Account → Balance shows ₹6,000
- [ ] Debit ₹5,000 to new empty account → Balance shows -₹5,000
- [ ] Maintenance Account shows ₹0 (no cross-contamination)
- [ ] Delete a transaction → totals update immediately
- [ ] Delete account → gone from dashboard
- [ ] Mobile: open DevTools, set viewport to 375px, check all layouts
- [ ] Empty state shown when no accounts exist

- [ ] **Step 4: Final commit**

```bash
git add backend/app.py README.md
git commit -m "feat: error handlers and complete README"
```

---

## README Appendix

The README.md for this project should be written to `README.md` in the project root during Task 9. It must cover:

```markdown
# Dharamshala Accounts

Simple financial ledger for managing Dharamshala accounts and transactions.

## What It Does

Track Credit and Debit transactions across multiple independent accounts. Each account shows Total Credit, Total Debit, and Balance (Credit − Debit).

## Tech Stack

- **Backend:** Python, Flask, SQLAlchemy, Gunicorn
- **Database:** Supabase PostgreSQL
- **Frontend:** HTML, CSS, Vanilla JavaScript
- **Hosting:** Render (backend) + Netlify (frontend)

## Local Setup

### 1. Supabase Setup

1. Create a free account at https://supabase.com
2. Create a new project
3. Go to **Settings → Database → Connection string → URI**
4. Copy the connection string (format: `postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres`)

### 2. Clone and configure

git clone <your-repo>
cd dharamshala-accounts
cp .env.example .env
# Edit .env with your Supabase connection string, a random SECRET_KEY, and your ADMIN_PASSWORD

### 3. Create database tables

cd backend
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
python app.py
# In a new terminal:
curl http://localhost:5000/api/init-db
# Should return: {"message": "Database initialized"}

### 4. Run locally

# Terminal 1 (backend):
cd backend && python app.py

# Terminal 2 (frontend):
cd frontend && python -m http.server 3000
# Open http://localhost:3000/login.html

## Environment Variables

| Variable         | Description                                      | Example                          |
|-----------------|--------------------------------------------------|----------------------------------|
| DATABASE_URL    | Supabase PostgreSQL connection string            | postgresql://postgres:...        |
| SECRET_KEY      | Flask session secret (use a long random string)  | abc123xyz...                     |
| ADMIN_PASSWORD  | Login password for the application              | MySecurePass2026                 |
| ALLOWED_ORIGIN  | Frontend URL (for CORS)                         | https://your-app.netlify.app     |

## Deployment

### Backend → Render

1. Push code to GitHub
2. Create a new **Web Service** on Render (https://render.com)
3. Connect your GitHub repository
4. Set **Root directory** to `backend`
5. Set **Build command**: `pip install -r requirements.txt`
6. Set **Start command**: `gunicorn app:app`
7. Add environment variables: DATABASE_URL, SECRET_KEY, ADMIN_PASSWORD, ALLOWED_ORIGIN
8. Once deployed, note your Render URL: `https://your-app.onrender.com`
9. Initialize DB: visit `https://your-app.onrender.com/api/init-db`

### Frontend → Netlify

1. Edit `frontend/js/config.js`:
   const API_BASE = 'https://your-app.onrender.com';
2. Push changes to GitHub
3. Create a new site on Netlify (https://netlify.com)
4. Set **Publish directory** to `frontend`
5. Deploy

### Connecting Frontend to Backend

The only file that needs to change for deployment is `frontend/js/config.js`:

```js
const API_BASE = 'https://your-render-url.onrender.com';
```

## Troubleshooting

**Database connection error:** Check DATABASE_URL in .env. Supabase connection string should use port 5432.

**CORS error in browser:** Make sure ALLOWED_ORIGIN in backend env vars exactly matches your Netlify URL (no trailing slash).

**Login not working:** Verify ADMIN_PASSWORD env var is set correctly on Render.

**Tables don't exist:** Visit `/api/init-db` on your backend URL once after deployment.

**Render sleeps after inactivity (free tier):** First request may take 30–60 seconds to wake up the server.
```

---

## Self-Review Checklist

- [x] Auth (single password, env var) — Task 2
- [x] Account CRUD with cascade delete — Tasks 2, 3
- [x] Transaction CRUD — Task 4
- [x] Balance calculated from transactions, not stored — `account_summary()` in Task 3
- [x] Indian Rupee formatting — `formatINR()` in Task 5 (moved to auth.js in Task 7)
- [x] CORS configured with env var — Task 2
- [x] Error handlers (no stack traces) — Task 9
- [x] Input validation (amount > 0, description required, type in credit/debit) — Task 4
- [x] Empty states — Tasks 6, 7 HTML
- [x] Delete confirmation modals — Tasks 6, 7
- [x] Mobile responsive CSS — Task 8
- [x] Procfile for Render — Task 1
- [x] .env.example — Task 1
- [x] .gitignore — Task 1
- [x] README with Supabase, Render, Netlify instructions — Task 9
- [x] No localStorage as primary DB
- [x] No hard-coded passwords
- [x] Transactions isolated per account (foreign key constraint)
