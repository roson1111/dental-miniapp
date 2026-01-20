from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Dental Assistant Finder</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto; padding: 20px; }
    h1 { font-size: 24px; margin-bottom: 10px; }
    button { padding: 12px 14px; margin-right: 10px; margin-top: 10px; cursor: pointer; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 14px; margin-top: 16px; }
  </style>
</head>
<body>
  <h1>Dental Assistant Finder</h1>
  <div class="card">
    <div id="hello">Загрузка…</div>
    <button onclick="choose('assistant')">Я ассистент</button>
    <button onclick="choose('employer')">Я работодатель</button>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      const u = tg.initDataUnsafe?.user;
      document.getElementById('hello').innerText =
        u ? `Привет, ${u.first_name}!` : 'Привет! (Открыто не из Telegram)';
    } else {
      document.getElementById('hello').innerText = 'Открыто не из Telegram';
    }

    function choose(role) {
      alert("Вы выбрали роль: " + role);
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
