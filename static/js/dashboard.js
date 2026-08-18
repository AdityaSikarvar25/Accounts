async function loadAccounts() {
  const grid = document.getElementById('accountsGrid');
  const empty = document.getElementById('emptyState');
  grid.innerHTML = '<p class="loading-text">Loading accounts...</p>';

  try {
    const res = await apiFetch('/api/accounts');
    if (!res) return;
    const data = await res.json();
    if (!res.ok) {
      grid.innerHTML = `<p class="error-msg">${escHtml(data.error || 'Failed to load accounts')}</p>`;
      return;
    }

    grid.innerHTML = '';
    if (data.length === 0) {
      grid.style.display = 'none';
      empty.style.display = 'block';
    } else {
      empty.style.display = 'none';
      grid.style.display = '';
      data.forEach(a => grid.appendChild(makeCard(a)));
    }
  } catch (e) {
    grid.innerHTML = `<p class="error-msg">${escHtml(e.message)}</p>`;
  }
}

function makeCard(a) {
  const card = document.createElement('div');
  card.className = 'account-card';
  card.innerHTML = `
    <div class="account-card-name">${escHtml(a.name)}</div>
    <div class="account-card-stats">
      <div class="stat-item">
        <span class="stat-label">Credit</span>
        <span class="stat-value text-credit">${formatINR(a.total_credit)}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">Debit</span>
        <span class="stat-value text-debit">${formatINR(a.total_debit)}</span>
      </div>
    </div>
    <div class="account-card-balance">
      <span class="stat-label">Balance</span>
      <span class="balance-value ${a.balance < 0 ? 'text-debit' : 'text-credit'}">${formatINR(a.balance)}</span>
    </div>
    <div class="account-card-actions">
      <a href="/account?id=${encodeURIComponent(a.id)}" class="btn btn-primary">View Account</a>
      <button class="btn btn-ghost btn-delete-acct">Delete</button>
    </div>`;
  card.querySelector('.btn-delete-acct').addEventListener('click', () => promptDeleteAccount(a.id, a.name));
  return card;
}

function promptDeleteAccount(id, name) {
  document.getElementById('deleteMsg').textContent =
    `Delete "${name}"? This will permanently delete all its transactions.`;
  openModal('deleteModal');
  document.getElementById('confirmDeleteBtn').onclick = async () => {
    closeModal('deleteModal');
    try {
      await apiFetch(`/api/accounts/${id}`, { method: 'DELETE' });
      loadAccounts();
    } catch (e) {
      alert(e.message);
    }
  };
}

function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

document.addEventListener('DOMContentLoaded', async () => {
  await guardAuth();
  loadAccounts();

  document.getElementById('logoutBtn').addEventListener('click', logout);

  // Add account
  document.getElementById('addAccountBtn').addEventListener('click', () => {
    document.getElementById('accountNameInput').value = '';
    document.getElementById('addAccountError').style.display = 'none';
    openModal('addAccountModal');
    document.getElementById('accountNameInput').focus();
  });

  document.getElementById('addAccountForm').addEventListener('submit', async e => {
    e.preventDefault();
    const name = document.getElementById('accountNameInput').value.trim();
    const errEl = document.getElementById('addAccountError');
    errEl.style.display = 'none';
    try {
      const res = await apiFetch('/api/accounts', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      if (!res) return;
      const data = await res.json();
      if (!res.ok) {
        errEl.textContent = data.error || 'Failed to create account';
        errEl.style.display = 'block';
        return;
      }
      closeModal('addAccountModal');
      loadAccounts();
    } catch (e) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
    }
  });

  document.getElementById('cancelAdd').addEventListener('click', () => closeModal('addAccountModal'));
  document.getElementById('cancelDelete').addEventListener('click', () => closeModal('deleteModal'));

  // Close modals on backdrop click
  ['addAccountModal', 'deleteModal'].forEach(id => {
    document.getElementById(id).addEventListener('click', e => {
      if (e.target.id === id) closeModal(id);
    });
  });
});
