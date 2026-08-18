// Shared utilities loaded on every page.

async function apiFetch(path, options = {}) {
  try {
    const res = await fetch(API_BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    // Auto-redirect to login on session expiry (except on the login/auth endpoints)
    if (res.status === 401 && path !== '/api/login' && path !== '/api/auth-check') {
      window.location.href = '/login';
      return null;
    }
    return res;
  } catch {
    throw new Error('Network error. Please check your connection.');
  }
}

async function guardAuth() {
  const res = await apiFetch('/api/auth-check');
  if (!res) return;
  const data = await res.json();
  if (!data.authenticated) window.location.href = '/login';
}

async function logout() {
  await apiFetch('/api/logout', { method: 'POST' });
  window.location.href = '/login';
}

// Indian Rupee formatting: 1,00,000 style
function formatINR(amount) {
  const negative = amount < 0;
  const num = Math.abs(amount);
  const str = num.toFixed(2).replace(/\.00$/, '');
  const [integer, decimal] = str.split('.');

  let result;
  if (integer.length <= 3) {
    result = integer;
  } else {
    result = integer.slice(-3);
    let rest = integer.slice(0, integer.length - 3);
    while (rest.length > 2) {
      result = rest.slice(-2) + ',' + result;
      rest = rest.slice(0, rest.length - 2);
    }
    result = rest + ',' + result;
  }

  return (negative ? '-₹' : '₹') + (decimal ? result + '.' + decimal : result);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Returns "17 Aug 2026" from "2026-08-17"
function formatDate(isoDate) {
  const months = ['Jan','Feb','Mar','Apr','May','Jun',
                  'Jul','Aug','Sep','Oct','Nov','Dec'];
  const [y, m, d] = isoDate.split('-');
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}
