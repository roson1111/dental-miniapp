from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Dental Assistant Finder</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root{
      --bg: #0b1220;
      --card: rgba(255,255,255,.06);
      --card2: rgba(255,255,255,.09);
      --text: rgba(255,255,255,.92);
      --muted: rgba(255,255,255,.65);
      --line: rgba(255,255,255,.12);
      --accent: #6aa9ff;
      --accent2: #7c5cff;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:
        radial-gradient(1200px 700px at 10% -10%, rgba(124,92,255,.35), transparent 60%),
        radial-gradient(900px 500px at 110% 10%, rgba(106,169,255,.28), transparent 55%),
        var(--bg);
      color: var(--text);
      padding: 18px 16px 24px;
    }
    .wrap{max-width: 640px; margin: 0 auto;}
    .top{
      display:flex; align-items:center; justify-content:space-between;
      gap:12px; margin-bottom: 14px;
    }
    .brand{
      display:flex; flex-direction:column; gap:4px;
    }
    .brand h1{margin:0; font-size:20px; letter-spacing:.2px;}
    .brand p{margin:0; font-size:13px; color: var(--muted);}
    .pill{
      padding:8px 10px;
      background: linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22));
      border: 1px solid var(--line);
      border-radius: 999px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }
    .card{
      background: linear-gradient(180deg, var(--card), rgba(255,255,255,.04));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }
    .sectionTitle{
      font-size: 14px; margin: 0 0 10px;
      color: rgba(255,255,255,.86);
      letter-spacing:.2px;
    }
    .grid{
      display:grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }
    @media (min-width: 520px){
      .grid.two{grid-template-columns: 1fr 1fr;}
    }
    label{
      display:block;
      font-size: 12px;
      color: var(--muted);
      margin: 0 0 6px;
    }
    input, select, textarea{
      width:100%;
      padding: 12px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(0,0,0,.18);
      color: var(--text);
      outline: none;
    }
    textarea{min-height: 92px; resize: vertical;}
    input::placeholder, textarea::placeholder{color: rgba(255,255,255,.38);}
    .hint{
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
    }
    .actions{
      display:flex; gap:10px; flex-wrap: wrap;
      margin-top: 12px;
    }
    .btn{
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      padding: 12px 14px;
      border-radius: 14px;
      cursor:pointer;
      font-weight: 600;
      font-size: 14px;
      flex: 1 1 170px;
    }
    .btnPrimary{
      border: none;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #081022;
    }
    .btn:active{transform: translateY(1px);}
    .ok{
      display:none;
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(60,255,180,.25);
      background: rgba(60,255,180,.10);
      color: rgba(220,255,245,.95);
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1>Анкета ассистента</h1>
        <p>Заполни 1 раз — работодатели смогут тебя найти.</p>
      </div>
      <div class="pill" id="tgBadge">Telegram: не подключён</div>
    </div>

    <div class="card">
      <h2 class="sectionTitle">Основные данные</h2>

      <div class="grid two">
        <div>
          <label>Имя</label>
          <input id="name" placeholder="Например, Алина" />
        </div>
        <div>
          <label>Город</label>
          <input id="city" placeholder="Например, Москва" />
        </div>
      </div>

      <div class="grid two" style="margin-top:10px;">
        <div>
          <label>Опыт (лет)</label>
          <select id="exp">
            <option value="0">0 (стажировка)</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3+</option>
            <option value="5">5+</option>
          </select>
        </div>
        <div>
          <label>Ставка (₽/час)</label>
          <input id="rate" type="number" inputmode="numeric" placeholder="Например, 500" />
        </div>
      </div>

      <div class="grid" style="margin-top:10px;">
        <div>
          <label>Когда можешь выходить (пример)</label>
          <input id="availability" placeholder="Пн–Пт после 16:00, Сб целый день" />
        </div>
        <div>
          <label>Коротко о себе / навыки</label>
          <textarea id="about" placeholder="Например: ассистирование, стерилизация, снимки, работа в 4 руки..."></textarea>
        </div>
      </div>

      <div class="actions">
        <button class="btn btnPrimary" onclick="save()">Сохранить</button>
        <button class="btn" onclick="resetForm()">Очистить</button>
      </div>

      <div class="ok" id="ok">✅ Сохранено! (пока локально в телефоне/браузере)</div>
      <div class="hint">Дальше подключим базу данных и поиск работодателя.</div>
    </div>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      const u = tg.initDataUnsafe?.user;
      document.getElementById('tgBadge').innerText =
        u ? `Telegram: @${(u.username || 'без username')}` : 'Telegram: подключён';
      // сделаем главную кнопку Telegram (снизу) красивой
      tg.MainButton.setText("Сохранить анкету");
      tg.MainButton.onClick(save);
      tg.MainButton.show();
    }

    // сохраняем пока локально (чтобы сразу работало без базы)
    function save() {
      const data = {
        name: document.getElementById('name').value.trim(),
        city: document.getElementById('city').value.trim(),
        exp: document.getElementById('exp').value,
        rate: document.getElementById('rate').value,
        availability: document.getElementById('availability').value.trim(),
        about: document.getElementById('about').value.trim(),
      };
      localStorage.setItem('assistantProfile', JSON.stringify(data));
      const ok = document.getElementById('ok');
      ok.style.display = 'block';
      setTimeout(()=> ok.style.display = 'none', 2500);
      if (tg) tg.HapticFeedback.notificationOccurred('success');
    }

    function resetForm(){
      localStorage.removeItem('assistantProfile');
      document.getElementById('name').value = '';
      document.getElementById('city').value = '';
      document.getElementById('exp').value = '0';
      document.getElementById('rate').value = '';
      document.getElementById('availability').value = '';
      document.getElementById('about').value = '';
      if (tg) tg.HapticFeedback.notificationOccurred('warning');
    }

    // автозагрузка
    (function load(){
      const raw = localStorage.getItem('assistantProfile');
      if (!raw) return;
      try {
        const d = JSON.parse(raw);
        document.getElementById('name').value = d.name || '';
        document.getElementById('city').value = d.city || '';
        document.getElementById('exp').value = d.exp || '0';
        document.getElementById('rate').value = d.rate || '';
        document.getElementById('availability').value = d.availability || '';
        document.getElementById('about').value = d.about || '';
      } catch(e) {}
    })();
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
