const accountId = new URLSearchParams(window.location.search).get('id');

async function loadAccountSummary() {
  const res = await apiFetch(`/api/accounts/${accountId}`);
  if (!res || res.status === 404) { window.location.href = '/dashboard'; return null; }
  const a = await res.json();
  document.getElementById('accountName').textContent = a.name;
  document.title = a.name + ' — Accounts';
  renderSummary(a);
  return a;
}

function renderSummary(a) {
  document.getElementById('totalCredit').textContent = formatINR(a.total_credit);
  document.getElementById('totalDebit').textContent = formatINR(a.total_debit);
  const balEl = document.getElementById('balance');
  balEl.textContent = formatINR(a.balance);
  balEl.className = 'summary-value ' + (a.balance < 0 ? 'text-debit' : 'text-credit');
}

async function loadTransactions() {
  const res = await apiFetch(`/api/accounts/${accountId}/transactions`);
  if (!res) return;
  const txns = await res.json();
  renderList('creditList', 'creditEmpty', txns.filter(t => t.type === 'credit'), 'credit');
  renderList('debitList', 'debitEmpty', txns.filter(t => t.type === 'debit'), 'debit');
}

function renderList(listId, emptyId, txns, type) {
  const list = document.getElementById(listId);
  const empty = document.getElementById(emptyId);
  list.innerHTML = '';
  if (txns.length === 0) {
    empty.style.display = 'block';
  } else {
    empty.style.display = 'none';
    txns.forEach(t => list.appendChild(makeTxnCard(t, type)));
  }
}

function makeTxnCard(t, type) {
  const card = document.createElement('div');
  card.className = `txn-card txn-${type}`;
  card.innerHTML = `
    <div class="txn-amount ${type === 'credit' ? 'text-credit' : 'text-debit'}">
      ${type === 'credit' ? '+' : '-'}${formatINR(t.amount)}
    </div>
    <div class="txn-desc">${escHtml(t.description)}</div>
    <div class="txn-date">${formatDate(t.transaction_date)}</div>
    ${t.notes ? `<div class="txn-notes">${escHtml(t.notes)}</div>` : ''}
    <button class="btn btn-ghost btn-sm btn-del-txn">Delete</button>`;
  card.querySelector('.btn-del-txn').addEventListener('click', () => promptDeleteTxn(t.id));
  return card;
}

function promptDeleteTxn(id) {
  openModal('deleteTxnModal');
  document.getElementById('confirmDeleteTxn').onclick = async () => {
    closeModal('deleteTxnModal');
    await apiFetch(`/api/transactions/${id}`, { method: 'DELETE' });
    await refresh();
  };
}

async function refresh() {
  const res = await apiFetch(`/api/accounts/${accountId}`);
  if (!res) return;
  renderSummary(await res.json());
  await loadTransactions();
}

function openAddModal(type) {
  document.getElementById('txnTypeInput').value = type;
  document.getElementById('addTxnTitle').textContent = type === 'credit' ? '+ Add Credit' : '+ Add Debit';
  document.getElementById('addTxnForm').reset();
  document.getElementById('txnDate').value = new Date().toISOString().split('T')[0];
  document.getElementById('addTxnError').style.display = 'none';
  openModal('addTxnModal');
  document.getElementById('txnAmount').focus();
}

function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

document.addEventListener('DOMContentLoaded', async () => {
  if (!accountId) { window.location.href = '/dashboard'; return; }
  await guardAuth();
  await loadAccountSummary();
  await loadTransactions();

  document.getElementById('logoutBtn').addEventListener('click', logout);
  document.getElementById('addCreditBtn').addEventListener('click', () => openAddModal('credit'));
  document.getElementById('addDebitBtn').addEventListener('click', () => openAddModal('debit'));
  document.getElementById('printStatementBtn').addEventListener('click', () => {
    window.open(API_BASE + `/api/accounts/${accountId}/statement`, '_blank');
  });
  document.getElementById('cancelAddTxn').addEventListener('click', () => closeModal('addTxnModal'));
  document.getElementById('cancelDeleteTxn').addEventListener('click', () => closeModal('deleteTxnModal'));

  document.getElementById('addTxnForm').addEventListener('submit', async e => {
    e.preventDefault();
    const errEl = document.getElementById('addTxnError');
    errEl.style.display = 'none';
    const body = {
      type: document.getElementById('txnTypeInput').value,
      amount: parseFloat(document.getElementById('txnAmount').value),
      description: document.getElementById('txnDesc').value.trim(),
      notes: document.getElementById('txnNotes').value.trim(),
      transaction_date: document.getElementById('txnDate').value,
    };
    try {
      const res = await apiFetch(`/api/accounts/${accountId}/transactions`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        errEl.textContent = data.error || 'Failed to add transaction';
        errEl.style.display = 'block';
        return;
      }
      closeModal('addTxnModal');
      await refresh();
    } catch (e) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  });

  ['addTxnModal', 'deleteTxnModal'].forEach(id => {
    document.getElementById(id).addEventListener('click', e => {
      if (e.target.id === id) closeModal(id);
    });
  });
});
