# Dharamshala Accounts

A simple web application for managing Dharamshala financial accounts and transactions.

Track **Credit** and **Debit** entries across multiple independent accounts. Each account shows Total Credit, Total Debit, and Balance (Credit − Debit) — calculated live from transactions, never stored separately.

---

## Tech Stack

- **Backend:** Python, Flask, SQLAlchemy, Gunicorn
- **Database:** Supabase PostgreSQL
- **Frontend:** HTML, CSS, Vanilla JavaScript (no frameworks)
- **Deployment:** Render (backend + frontend on one service — simplest option)

---

## Local Setup

### Step 1: Set up Supabase (free)

1. Go to [supabase.com](https://supabase.com) and create a free account.
2. Click **New Project** — choose a name and set a database password.
3. Once the project is ready, go to **Project Settings → Database**.
4. Scroll to **Connection string → URI**.
5. Copy the connection string. It looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-REF].supabase.co:5432/postgres
   ```
   Replace `[YOUR-PASSWORD]` with your actual database password.

### Step 2: Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
DATABASE_URL=postgresql://postgres:YOUR_PASS@db.YOUR_REF.supabase.co:5432/postgres
SECRET_KEY=some-long-random-string-here
ADMIN_PASSWORD=your-chosen-login-password
```

### Step 3: Install dependencies

```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 4: Create database tables

Start the server:

```bash
python app.py
```

Then in a browser (or with curl), visit:

```
http://localhost:5000/api/init-db
```

You should see: `{"message": "Database initialized successfully"}`

This creates the `accounts` and `transactions` tables in your Supabase database. You only need to do this **once**.

### Step 5: Use the app

Visit `http://localhost:5000` — you'll be redirected to the login page.

---

## Environment Variables

| Variable         | Required | Description                                            |
|-----------------|----------|--------------------------------------------------------|
| `DATABASE_URL`  | Yes      | Supabase PostgreSQL connection string                  |
| `SECRET_KEY`    | Yes      | Flask session secret — use a long random string        |
| `ADMIN_PASSWORD`| Yes      | The login password for the application                |
| `FLASK_ENV`     | No       | Set to `production` on Render for secure session cookies |
| `ALLOWED_ORIGIN`| No       | Only needed for Netlify + Render split deployment      |

---

## Deployment on Render (recommended — everything in one place)

1. Push your project to GitHub (make sure `.env` is in `.gitignore`).

2. Go to [render.com](https://render.com) and create a free account.

3. Click **New → Web Service** and connect your GitHub repository.

4. Configure the service:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Environment:** Python 3

5. Under **Environment Variables**, add:
   - `DATABASE_URL` — your Supabase connection string
   - `SECRET_KEY` — a long random string
   - `ADMIN_PASSWORD` — your chosen password
   - `FLASK_ENV` — `production`

6. Click **Deploy**.

7. Once deployed, visit `https://your-app.onrender.com/api/init-db` **once** to create the database tables.

8. Visit `https://your-app.onrender.com` — done!

> **Note:** On Render's free tier, the service sleeps after 15 minutes of inactivity. The first request after sleeping takes ~30–60 seconds to wake up. This is normal.

---

## Troubleshooting

**Can't connect to database:**
- Check `DATABASE_URL` in your environment variables.
- Make sure you replaced `[YOUR-PASSWORD]` in the Supabase connection string.
- Supabase free tier may pause a project after inactivity — check your Supabase dashboard.

**"Server not configured" error on login:**
- Make sure `ADMIN_PASSWORD` is set in your environment variables.

**Tables don't exist error:**
- Visit `/api/init-db` on your deployed URL to create the tables.

**Session not persisting (keeps logging out):**
- Make sure `SECRET_KEY` is set and consistent between restarts.
- On Render, ensure `FLASK_ENV=production` is set.

**Changes not showing after add/delete:**
- The page updates automatically without refresh. If it doesn't, check the browser console for JavaScript errors.

---

## Project Structure

```
dharamshala-accounts/
├── app.py              ← Flask backend: all models, routes, auth
├── requirements.txt
├── Procfile            ← For Render deployment
├── .env.example        ← Copy to .env and fill in your values
├── .gitignore
├── templates/
│   ├── login.html      ← Login page
│   ├── index.html      ← Accounts dashboard
│   └── account.html    ← Account detail with transactions
└── static/
    ├── css/
    │   └── style.css   ← All styles
    └── js/
        ├── config.js   ← API_BASE_URL (only file to change for split deployment)
        ├── auth.js     ← Shared: apiFetch, guardAuth, formatINR, formatDate
        ├── dashboard.js← Dashboard logic
        └── account.js  ← Account detail logic
```
