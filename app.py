import os
from uuid import uuid4, UUID
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, render_template, redirect, Response
from flask_cors import CORS
from sqlalchemy import create_engine, Column, String, Numeric, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Session, relationship, joinedload
from sqlalchemy.dialects.postgresql import UUID as PgUUID

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'

# CORS is only needed when frontend is on a different domain (Netlify + Render split).
# For the default Render-only deployment, this is unused.
allowed_origin = os.getenv('ALLOWED_ORIGIN')
if allowed_origin:
    CORS(app, supports_credentials=True, origins=[allowed_origin])

# Normalize URL: Supabase/Render may use postgres:// or postgresql://
# pg8000 is a pure-Python driver (no system DLLs needed)
_db_url = os.environ['DATABASE_URL']
_db_url = _db_url.replace('postgres://', 'postgresql+pg8000://', 1)
_db_url = _db_url.replace('postgresql://', 'postgresql+pg8000://', 1)
engine = create_engine(_db_url, pool_pre_ping=True)


# ── Models ────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'
    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    transactions = relationship('Transaction', back_populates='account',
                                cascade='all, delete-orphan')


class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(PgUUID(as_uuid=True),
                        ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
    type = Column(String(6), nullable=False)   # 'credit' or 'debit'
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(String(500), nullable=False)
    notes = Column(Text, nullable=True)
    transaction_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    account = relationship('Account', back_populates='transactions')


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_uuid(s):
    try:
        return UUID(str(s))
    except (ValueError, AttributeError):
        return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def account_to_dict(account):
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


def txn_to_dict(t):
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


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route('/')
def root():
    return redirect('/dashboard' if session.get('authenticated') else '/login')


@app.route('/login')
def page_login():
    if session.get('authenticated'):
        return redirect('/dashboard')
    return render_template('login.html')


@app.route('/dashboard')
def page_dashboard():
    if not session.get('authenticated'):
        return redirect('/login')
    return render_template('index.html')


@app.route('/account')
def page_account():
    if not session.get('authenticated'):
        return redirect('/login')
    return render_template('account.html')


# ── Auth API ──────────────────────────────────────────────────────────────────

@app.route('/api/auth-check')
def api_auth_check():
    return jsonify({'authenticated': bool(session.get('authenticated'))})


@app.route('/api/login', methods=['POST'])
def api_login():
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if not admin_password:
        return jsonify({'error': 'Server not configured — set ADMIN_PASSWORD'}), 500
    data = request.get_json() or {}
    if data.get('password') == admin_password:
        session['authenticated'] = True
        return jsonify({'message': 'ok'})
    return jsonify({'error': 'Incorrect password'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'message': 'ok'})


# ── Accounts API ──────────────────────────────────────────────────────────────

@app.route('/api/accounts')
@require_auth
def api_list_accounts():
    with Session(engine) as db:
        accounts = (db.query(Account)
                    .options(joinedload(Account.transactions))
                    .order_by(Account.created_at)
                    .all())
        return jsonify([account_to_dict(a) for a in accounts])


@app.route('/api/accounts', methods=['POST'])
@require_auth
def api_create_account():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Account name is required'}), 400
    if len(name) > 200:
        return jsonify({'error': 'Account name is too long (max 200 characters)'}), 400
    with Session(engine) as db:
        if db.query(Account).filter_by(name=name).first():
            return jsonify({'error': 'An account with this name already exists'}), 409
        account = Account(name=name)
        db.add(account)
        db.commit()
        db.refresh(account)
        return jsonify(account_to_dict(account)), 201


@app.route('/api/accounts/<account_id>')
@require_auth
def api_get_account(account_id):
    uid = parse_uuid(account_id)
    if not uid:
        return jsonify({'error': 'Account not found'}), 404
    with Session(engine) as db:
        account = (db.query(Account)
                   .options(joinedload(Account.transactions))
                   .filter_by(id=uid)
                   .first())
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        return jsonify(account_to_dict(account))


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
@require_auth
def api_delete_account(account_id):
    uid = parse_uuid(account_id)
    if not uid:
        return jsonify({'error': 'Account not found'}), 404
    with Session(engine) as db:
        account = db.get(Account, uid)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        db.delete(account)
        db.commit()
        return jsonify({'message': 'deleted'})


# ── Transactions API ──────────────────────────────────────────────────────────

@app.route('/api/accounts/<account_id>/transactions')
@require_auth
def api_list_transactions(account_id):
    uid = parse_uuid(account_id)
    if not uid:
        return jsonify({'error': 'Account not found'}), 404
    with Session(engine) as db:
        if not db.get(Account, uid):
            return jsonify({'error': 'Account not found'}), 404
        txns = (db.query(Transaction)
                .filter_by(account_id=uid)
                .order_by(Transaction.transaction_date.desc(),
                          Transaction.created_at.desc())
                .all())
        return jsonify([txn_to_dict(t) for t in txns])


@app.route('/api/accounts/<account_id>/transactions', methods=['POST'])
@require_auth
def api_create_transaction(account_id):
    uid = parse_uuid(account_id)
    if not uid:
        return jsonify({'error': 'Account not found'}), 404
    with Session(engine) as db:
        if not db.get(Account, uid):
            return jsonify({'error': 'Account not found'}), 404

    data = request.get_json() or {}

    txn_type = (data.get('type') or '').strip().lower()
    if txn_type not in ('credit', 'debit'):
        return jsonify({'error': 'Type must be credit or debit'}), 400

    try:
        amount = Decimal(str(data.get('amount') or 0))
        if amount <= 0:
            raise ValueError
    except Exception:
        return jsonify({'error': 'Please enter a valid positive amount'}), 400

    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({'error': 'Description is required'}), 400
    if len(description) > 500:
        return jsonify({'error': 'Description is too long (max 500 characters)'}), 400

    try:
        txn_date = date.fromisoformat(str(data.get('transaction_date') or ''))
    except (ValueError, TypeError):
        return jsonify({'error': 'Please provide a valid date'}), 400

    notes = (data.get('notes') or '').strip() or None

    with Session(engine) as db:
        txn = Transaction(
            account_id=uid,
            type=txn_type,
            amount=amount,
            description=description,
            notes=notes,
            transaction_date=txn_date,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        return jsonify(txn_to_dict(txn)), 201


@app.route('/api/transactions/<transaction_id>', methods=['DELETE'])
@require_auth
def api_delete_transaction(transaction_id):
    tid = parse_uuid(transaction_id)
    if not tid:
        return jsonify({'error': 'Transaction not found'}), 404
    with Session(engine) as db:
        txn = db.get(Transaction, tid)
        if not txn:
            return jsonify({'error': 'Transaction not found'}), 404
        db.delete(txn)
        db.commit()
        return jsonify({'message': 'deleted'})


# ── Statement PDF ─────────────────────────────────────────────────────────────

def _fmt_inr(amount):
    """INR formatting for PDF (uses ASCII 'Rs.' to avoid ₹ glyph variance across fonts)."""
    amount = float(amount)
    negative = amount < 0
    amount = abs(amount)
    integer_part = int(amount)
    frac = round((amount - integer_part) * 100)
    s = str(integer_part)
    if len(s) <= 3:
        result = s
    else:
        result = s[-3:]
        s = s[:-3]
        while len(s) > 2:
            result = s[-2:] + ',' + result
            s = s[:-2]
        result = s + ',' + result
    if frac:
        result += f'.{frac:02d}'
    return ('-Rs. ' if negative else 'Rs. ') + result


def _fmt_date_short(d):
    return f"{d.day:02d}/{d.month:02d}/{str(d.year)[2:]}"


def _fmt_date_long(d):
    months = ['January','February','March','April','May','June',
              'July','August','September','October','November','December']
    return f"{d.day} {months[d.month - 1]} {d.year}"


def _generate_statement_pdf(account, transactions):
    import os
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    base = os.path.dirname(os.path.abspath(__file__))
    fonts = os.path.join(base, 'static', 'fonts')

    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    pdf.add_page()

    # NotoSans covers Latin/numbers; NotoSansGujarati is fallback for Gujarati
    pdf.add_font('NotoSans', '',  os.path.join(fonts, 'NotoSans-Regular.ttf'))
    pdf.add_font('NotoSans', 'B', os.path.join(fonts, 'NotoSans-Bold.ttf'))
    pdf.add_font('NotoGuj',  '',  os.path.join(fonts, 'NotoSansGujarati-Regular.ttf'))
    pdf.add_font('NotoGuj',  'B', os.path.join(fonts, 'NotoSansGujarati-Bold.ttf'))
    pdf.set_fallback_fonts(['NotoGuj'])

    W = 170  # usable width mm (A4 210 - 2*20 margins)

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.set_font('NotoSans', 'B', 18)
    pdf.cell(W, 10, 'ACCOUNT STATEMENT', align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font('NotoSans', 'B', 13)
    pdf.cell(W, 8, account.name, align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font('NotoSans', '', 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(W, 7, f'Generated: {_fmt_date_long(date.today())}', align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    y = pdf.get_y() + 3
    pdf.set_draw_color(30, 41, 59)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
    pdf.set_y(y + 5)

    # ── Transaction table ─────────────────────────────────────────────────────
    date_w, credit_w, debit_w = 25, 35, 35
    desc_w = W - date_w - credit_w - debit_w  # 75 mm

    total_credit = Decimal(0)
    total_debit  = Decimal(0)
    rows = []
    for t in transactions:
        if t.type == 'credit':
            total_credit += t.amount
            c_str, d_str = _fmt_inr(float(t.amount)), ''
        else:
            total_debit += t.amount
            c_str, d_str = '', _fmt_inr(float(t.amount))
        rows.append((_fmt_date_short(t.transaction_date), t.description, c_str, d_str))

    def _tbl_cell(w, h, txt, align='L', fill=False, border='B'):
        pdf.cell(w, h, txt, align=align, fill=fill, border=border,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)

    # Table header
    rh = 8
    pdf.set_font('NotoSans', 'B', 9)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    _tbl_cell(date_w,   rh, 'Date',         align='C', fill=True, border=0)
    _tbl_cell(desc_w,   rh, 'Description',  align='C', fill=True, border=0)
    _tbl_cell(credit_w, rh, 'Credit (Rs.)', align='C', fill=True, border=0)
    pdf.cell(debit_w, rh, 'Debit (Rs.)', align='C', fill=True, border=0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    # Table rows
    pdf.set_font('NotoSans', '', 9)
    rh = 7
    fill_colors = [(255, 255, 255), (248, 250, 252)]
    if not rows:
        pdf.set_fill_color(*fill_colors[0])
        pdf.set_text_color(100, 116, 139)
        pdf.cell(W, rh, 'No transactions recorded for this account.',
                 align='C', fill=True, border='B',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
    else:
        for i, (d, desc, credit, debit) in enumerate(rows):
            pdf.set_fill_color(*fill_colors[i % 2])
            _tbl_cell(date_w,   rh, d,      align='C', fill=True)
            _tbl_cell(desc_w,   rh, desc,   align='L', fill=True)
            _tbl_cell(credit_w, rh, credit, align='R', fill=True)
            pdf.cell(debit_w, rh, debit, align='R', fill=True, border='B',
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Summary ───────────────────────────────────────────────────────────────
    net = total_credit - total_debit
    pdf.ln(4)

    lbl_w = W - 45
    val_w = 45

    pdf.set_font('NotoSans', '', 10)
    for label, amt in (('Total Credit', total_credit), ('Total Debit', total_debit)):
        pdf.cell(lbl_w, 7, label, align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(val_w, 7, _fmt_inr(float(amt)), align='R',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # separator line above Net Difference
    sep_y = pdf.get_y()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin + lbl_w, sep_y, pdf.l_margin + W, sep_y)
    pdf.set_y(sep_y)

    pdf.set_font('NotoSans', 'B', 11)
    pdf.cell(lbl_w, 8, 'Net Difference', align='R', new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.cell(val_w, 8, _fmt_inr(float(net)), align='R',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


@app.route('/api/accounts/<account_id>/statement')
@require_auth
def api_account_statement(account_id):
    uid = parse_uuid(account_id)
    if not uid:
        return jsonify({'error': 'Account not found'}), 404
    with Session(engine) as db:
        account = db.get(Account, uid)
        if not account:
            return jsonify({'error': 'Account not found'}), 404
        txns = (db.query(Transaction)
                .filter_by(account_id=uid)
                .order_by(Transaction.transaction_date.desc(),
                          Transaction.created_at.desc())
                .all())
        pdf_bytes = _generate_statement_pdf(account, txns)
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'inline; filename="account_statement.pdf"'},
    )


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(Exception)
def handle_error(e):
    import traceback
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({'error': e.description}), e.code
    # Print full traceback to stdout so it appears in Flask terminal/logs
    print('\n=== UNHANDLED EXCEPTION ===')
    traceback.print_exc()
    print('===========================\n', flush=True)
    return jsonify({'error': 'An unexpected error occurred'}), 500


if __name__ == '__main__':
    app.run(debug=True)
