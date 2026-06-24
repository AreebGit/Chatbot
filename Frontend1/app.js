/* ──────────────────────────────────────────
   CONFIG – point this at your FastAPI server
   ────────────────────────────────────────── */
const API_BASE = 'http://localhost:8000';

/* ── State ── */
let currentUser = null;
let sessionId = null;
let lastAssistantBubble = null;

/*
  currentToken stores the JWT token we get after login.
  We also save it to localStorage so it survives a page refresh.
  Next time the user visits, we read it back and they're already logged in.
*/
let currentToken = localStorage.getItem('ht_token') || null;

/* ── Utility ── */
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2); }
function toast(msg, dur=2500) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), dur);
}

/*
  authHeaders() returns the headers object we attach to every
  protected API request. The server reads the Authorization header,
  extracts the token, and verifies it before doing anything.
*/
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${currentToken}`
  };
}

/*
  handleAuthError() is called whenever the server returns 401.
  It clears the saved token and asks the user to log in again.
*/
function handleAuthError() {
  localStorage.removeItem('ht_token');
  currentToken = null;
  currentUser = null;
  document.getElementById('login-section').style.display = 'block';
  document.getElementById('query-section').style.display = 'none';
  document.getElementById('chat-card-title').textContent = 'Ask your nutrition & fitness question';
  toast('Session expired. Please log in again.');
}

/* ── Auto-restore session on page load ── */
/*
  JWT tokens are made of 3 parts separated by dots:
    header.payload.signature
  The payload part is just base64-encoded JSON — we can
  decode it directly in the browser without asking the server.
  We read the "exp" (expiry) field and check it against now.
  If it's expired, clear it. If it's still valid, restore the session.
*/
function decodeTokenLocally(token) {
  try {
    /* Grab the middle part (payload) and decode it */
    const base64 = token.split('.')[1];
    /* atob() decodes base64. The replace() fixes URL-safe base64 characters */
    const json = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(json);
  } catch(e) {
    return null;
  }
}

function tryRestoreSession() {
  if (!currentToken) return;

  const payload = decodeTokenLocally(currentToken);

  /* payload.exp is Unix timestamp in seconds */
  const isExpired = !payload || (payload.exp * 1000 < Date.now());

  if (isExpired) {
    /* Token is expired — clear it and show login */
    localStorage.removeItem('ht_token');
    currentToken = null;
    return;
  }

  /* Token is valid — restore the session without a server call */
  currentUser = { userId: payload.user_id, name: 'there', phone: null };
  sessionId = localStorage.getItem('ht_session') || uid();
  localStorage.setItem('ht_session', sessionId);
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('query-section').style.display = 'block';
  document.getElementById('chat-card-title').textContent = 'Welcome back! What\'s on your mind?';
}

/* ── Login / upsert-user ── */
async function handleLogin() {
  const name  = document.getElementById('inp-name').value.trim();
  const phone = document.getElementById('inp-phone').value.trim();
  const email = document.getElementById('inp-email').value.trim();

  if (!name || !phone) { toast('Please enter your name and phone number.'); return; }

  let userId;

  /* Step 1: check if user already exists by phone number */
  try {
    const loginRes = await fetch(`${API_BASE}/login/${encodeURIComponent(phone)}`);
    const loginData = await loginRes.json();
    if (loginData.exists) {
      userId = loginData.user[1];
      /* Save the token — this is the wristband */
      currentToken = loginData.token;
      localStorage.setItem('ht_token', currentToken);
      toast('Welcome back! Loading your history…');
      loadHistory(loginData.history);
    }
  } catch(e) { console.warn('Login check failed', e); }

  if (!userId) {
    /* Step 2: new user — first get a token, then register */
    userId = uid();
    try {
      /* Get a token first (upsert-user is locked, so we need this) */
      const tokenRes = await fetch(`${API_BASE}/generate-bearer-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });
      const tokenData = await tokenRes.json();
      currentToken = tokenData.access_token;
      localStorage.setItem('ht_token', currentToken);

      /* Now register the user using that token */
      await fetch(`${API_BASE}/upsert-user`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ user_id: userId, name, email: email || '', phone_number: phone })
      });
    } catch(e) { console.warn('Registration failed', e); }
  }

  currentUser = { userId, name, phone };
  sessionId = uid();
  localStorage.setItem('ht_session', sessionId);

  document.getElementById('login-section').style.display = 'none';
  document.getElementById('query-section').style.display = 'block';
  document.getElementById('chat-card-title').textContent = `Hi ${name}! What's on your mind?`;
}

function loadHistory(history) {
  if (!history || !history.length) return;
  /* history rows: (id, user_id, session_id, role, content, timestamp, feedback) */
  history.slice(-20).forEach(row => {
    const role = row[3];
    const text = row[4];
    if (role === 'user') addUserMessage(text, false);
    else if (role === 'assistant') { const el = addAssistantMessage(text, false); addFeedbackRow(el); }
  });
  showNewChatBtn();
}

/* ── Guest login ── */
function continueAsGuest() {
  const guestId = 'guest_' + uid();
  currentUser = { userId: guestId, name: 'Guest', phone: null };
  sessionId = uid();
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('query-section').style.display = 'block';
  document.getElementById('chat-card-title').textContent = 'Hi! What\'s on your mind?';
  /* Note: guest messages won't be saved to DB since user isn't registered */
}

/* ── Chips (suggested questions) ── */
function chipClick(el) {
  if (!currentUser) {
    /* scroll to login */
    document.getElementById('inp-name').focus();
    toast('Please log in first to ask a question.');
    return;
  }
  document.getElementById('query-input').value = el.textContent;
  sendMessage();
}

/* ── Send message ── */
async function sendMessage() {
  const input = document.getElementById('query-input');
  const text  = input.value.trim();
  if (!text) return;
  if (!currentUser) { toast('Please log in first.'); return; }

  input.value = '';
  addUserMessage(text);

  const typingEl = addTypingIndicator();

  try {
    const res = await fetch(`${API_BASE}/send-message`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        user_id: currentUser.userId,
        session_id: sessionId,
        incoming_message: text
      })
    });

    if (res.status === 401) { typingEl.remove(); handleAuthError(); return; }

    const data = await res.json();
    typingEl.remove();
    const msgEl = addAssistantMessage(data.response);
    addFeedbackRow(msgEl);
    showNewChatBtn();
  } catch(e) {
    typingEl.remove();
    addAssistantMessage('Sorry, I couldn\'t connect to the server. Please try again.');
  }
}

/* User message — search icon + bold text + underline (matches original) */
function addUserMessage(text, scroll=true) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'msg-user';
  div.innerHTML = `
    <svg class="user-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <span>${text}</span>
  `;
  thread.appendChild(div);
  if (scroll) thread.scrollTop = thread.scrollHeight;
  return div;
}

/* Assistant message — orange spark icon + response text */
function addAssistantMessage(text, scroll=true) {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'msg-assistant';
  div.innerHTML = `
    <div class="spark-icon">
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
      </svg>
    </div>
    <div class="msg-assistant-body">
      <div class="msg-assistant-text">${text}</div>
    </div>
  `;
  thread.appendChild(div);
  if (scroll) thread.scrollTop = thread.scrollHeight;
  return div;
}

/* Typing indicator — inside the assistant layout */
function addTypingIndicator() {
  const thread = document.getElementById('chat-thread');
  const div = document.createElement('div');
  div.className = 'msg-assistant';
  div.innerHTML = `
    <div class="spark-icon">
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
      </svg>
    </div>
    <div class="msg-assistant-body">
      <div class="dot-anim"><span></span><span></span><span></span></div>
    </div>
  `;
  thread.appendChild(div);
  thread.scrollTop = thread.scrollHeight;
  return div;
}

/* Feedback — thumbs up/down icon buttons (no text, no border) */
function addFeedbackRow(msgEl) {
  const body = msgEl.querySelector('.msg-assistant-body');
  if (!body) return;
  const row = document.createElement('div');
  row.className = 'feedback-row';
  row.innerHTML = `
    <button class="fb-btn" onclick="sendFeedback(this,'helpful')" title="Helpful">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
        <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
      </svg>
    </button>
    <button class="fb-btn" onclick="sendFeedback(this,'not_helpful')" title="Not helpful">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
        <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
      </svg>
    </button>
  `;
  body.appendChild(row);
}

/* Show the + New Chat button after first exchange */
function showNewChatBtn() {
  document.getElementById('new-chat-btn').style.display = 'block';
}

/* Start a fresh chat session — clears thread, new session ID */
function startNewChat() {
  document.getElementById('chat-thread').innerHTML = '';
  sessionId = uid();
  localStorage.setItem('ht_session', sessionId);
  document.getElementById('new-chat-btn').style.display = 'none';
  document.getElementById('query-input').focus();
}

async function sendFeedback(btn, value) {
  const row = btn.closest('.feedback-row');
  row.querySelectorAll('.fb-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  try {
    const res = await fetch(`${API_BASE}/update-feedback`, {
      method: 'POST',
      headers: authHeaders(), /* ← token attached here too */
      body: JSON.stringify({ session_id: sessionId, feedback: value })
    });
    if (res.status === 401) handleAuthError();
  } catch(e) { console.warn('feedback failed', e); }
}

/* ── FAQ DATA ── */
const faqData = {
  'Dietary Fibre': [
    { q: '1. What is dietary fibre?', a: 'Dietary fibre is the indigestible part of plant foods — including fruits, vegetables, whole grains, and legumes — that passes through your digestive system mostly intact. Unlike other nutrients, fibre isn\'t digested; instead it helps regulate digestion, blood sugar, and cholesterol.' },
    { q: '2. What are the sources of dietary fibre?', a: 'Great sources include oats, barley, whole wheat, brown rice, lentils, chickpeas, kidney beans, broccoli, carrots, apples, pears, berries, flaxseeds, and nuts. Aim for a mix of soluble and insoluble sources across meals.' },
    { q: '3. What are the health benefits of dietary fibre?', a: 'Regular fibre intake supports healthy digestion and bowel regularity, lowers LDL cholesterol, helps control blood sugar spikes, promotes satiety (helping with weight management), and feeds beneficial gut bacteria linked to better immune function.' },
    { q: '4. Which fruits & vegetables are good sources of fibre?', a: 'Top fruit sources: avocado (6.7g/100g), guava, raspberries, passion fruit, and pears. Top vegetable sources: green peas, artichokes, broccoli, sweet corn, and Brussels sprouts. Eating skins where safe boosts intake significantly.' },
    { q: '5. How much dietary fibre do I need in my daily diet?', a: 'Adults need 25–38g of fibre per day — 25g for women and 38g for men according to most health bodies. Most people consume only about half this amount. Increase intake gradually and drink plenty of water to avoid discomfort.' },
    { q: '6. Is consuming too much fibre risky?', a: 'Excess fibre (>70g/day) can cause bloating, gas, cramping, and may interfere with absorption of minerals like iron and zinc. Always increase intake gradually and stay well-hydrated.' },
    { q: '7. Which are the food sources that are low in fibre?', a: 'White bread, white rice, processed cereals, juices (without pulp), most dairy products, meats, eggs, and refined snacks are low in fibre. These can still be part of a balanced diet but shouldn\'t be the staples if fibre intake is a priority.' },
    { q: '8. How to increase fibre in the diet?', a: 'Switch to whole grain bread and pasta. Add legumes (dal, rajma, chana) to meals. Snack on nuts and fruits instead of packaged snacks. Keep the skin on vegetables and fruits. Add a tablespoon of flaxseed or chia seeds to smoothies or curd.' },
    { q: '9. References', a: 'WHO Dietary Fibre Guidelines (2023) · ICMR-NIN Nutrient Requirements for Indians · Harvard T.H. Chan School of Public Health – The Nutrition Source' }
  ],
  'Multigrain': [
    { q: '1. What is multigrain?', a: 'Multigrain refers to foods made with more than one type of grain — such as wheat, oats, rye, barley, millet, and corn. Each grain contributes a different nutrient profile, making multigrain products nutritionally richer than single-grain alternatives.' },
    { q: '2. Are multigrain and whole grain the same?', a: 'No. Multigrain just means multiple grains are used, but they may still be refined. Whole grain means the entire grain kernel (bran, germ, and endosperm) is intact. Whole multigrain is the best of both worlds.' },
    { q: '3. Benefits of eating multigrain foods', a: 'Multigrain foods offer a broader spectrum of B-vitamins, minerals (iron, magnesium, zinc), and fibre. They support sustained energy, better digestion, and reduced risk of heart disease and type 2 diabetes.' },
  ],
  'Balanced Diet': [
    { q: '1. What is a balanced diet?', a: 'A balanced diet provides the right amounts of macronutrients (carbohydrates, proteins, and fats) and micronutrients (vitamins and minerals) to maintain health, energy, and well-being.' },
    { q: '2. How do I build a balanced plate?', a: 'Fill half your plate with vegetables and fruits, one quarter with whole grains, and one quarter with lean protein. Include a small portion of healthy fat (nuts, seeds, olive oil) and a dairy or dairy alternative.' },
  ],
  'Fats': [
    { q: '1. Are all fats bad for you?', a: 'No. Unsaturated fats (found in nuts, seeds, avocado, and olive oil) are beneficial for heart health. Trans fats and excessive saturated fats are harmful. The goal is to replace bad fats with good ones, not to eliminate fat entirely.' },
    { q: '2. How much fat should I eat daily?', a: 'Fats should make up 20–35% of total daily calories. For a 2000-calorie diet that\'s 44–78g of fat per day. Prioritise unsaturated sources and limit saturated fat to under 10% of calories.' },
  ],
  'BMI & IBW': [
    { q: '1. What is BMI?', a: 'Body Mass Index (BMI) is a simple calculation using your height and weight (kg/m²). It categorises weight as underweight (<18.5), normal (18.5–24.9), overweight (25–29.9), or obese (≥30). It\'s a screening tool, not a diagnostic measure.' },
    { q: '2. What is IBW?', a: 'Ideal Body Weight (IBW) is an estimated target weight based on height and sex using formulas like Devine or Robinson. It\'s used clinically to calculate medication doses and nutritional needs rather than as a strict personal goal.' },
  ],
};

/* ── Render FAQ ── */
function renderFAQ(category) {
  const items = faqData[category] || [];
  const acc = document.getElementById('accordion');
  acc.innerHTML = '';
  items.forEach((item, i) => {
    const el = document.createElement('div');
    el.className = 'acc-item';
    el.innerHTML = `
      <div class="acc-header" onclick="toggleAcc(this)">
        <span>${item.q}</span>
        <svg class="acc-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div class="acc-body">
        <div class="acc-body-inner">${item.a}</div>
      </div>
    `;
    acc.appendChild(el);
  });
}

function toggleAcc(header) {
  const item = header.closest('.acc-item');
  const body = item.querySelector('.acc-body');
  const isOpen = item.classList.contains('open');
  /* Close all */
  document.querySelectorAll('.acc-item.open').forEach(i => {
    i.classList.remove('open');
    i.querySelector('.acc-body').style.maxHeight = '0';
  });
  if (!isOpen) {
    item.classList.add('open');
    body.style.maxHeight = body.scrollHeight + 'px';
  }
}

function initTabs() {
  const tabsEl = document.getElementById('faq-tabs');
  Object.keys(faqData).forEach((cat, i) => {
    const btn = document.createElement('button');
    btn.className = 'faq-tab' + (i === 0 ? ' active' : '');
    btn.innerHTML = `<span class="tab-dot"></span>${cat}`;
    btn.onclick = () => {
      document.querySelectorAll('.faq-tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      renderFAQ(cat);
    };
    tabsEl.appendChild(btn);
  });
  renderFAQ(Object.keys(faqData)[0]);
}

initTabs();

/*
  When the page loads, try to restore a previous session.
  If the user has a valid saved token, skip the login screen.
  Guest users always see the login screen (no token saved).
*/
tryRestoreSession();