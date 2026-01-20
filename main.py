from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI()

# ---------- DB (SQLite) ----------
DB_PATH = os.getenv("DB_PATH", "app.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Assistant(Base):
    __tablename__ = "assistants"
    id = Column(Integer, primary_key=True, index=True)
    tg_username = Column(String(64), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    city = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)
    exp = Column(String(20), nullable=False, default="0")
    rate = Column(String(20), nullable=True)
    availability = Column(String(200), nullable=True)
    about = Column(Text, nullable=True)
    rating = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


class Employer(Base):
    __tablename__ = "employers"
    id = Column(Integer, primary_key=True, index=True)
    tg_username = Column(String(64), nullable=True, index=True)
    clinic = Column(String(160), nullable=False)
    city = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)
    about = Column(Text, nullable=True)
    rating = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ---------- Schemas ----------
def normalize_phone(phone: str) -> str:
    # keep digits and +
    p = phone.strip()
    # Allow formats like +7..., 8..., 7..., with spaces/()- removed
    p = re.sub(r"[^\d+]", "", p)
    # basic sanity: at least 10 digits
    digits = re.sub(r"\D", "", p)
    if len(digits) < 10:
        raise ValueError("phone_too_short")
    return p


class AssistantIn(BaseModel):
    tg_username: Optional[str] = None
    name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)
    exp: str = "0"
    rate: Optional[str] = None
    availability: Optional[str] = None
    about: Optional[str] = None


class EmployerIn(BaseModel):
    tg_username: Optional[str] = None
    clinic: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)
    about: Optional[str] = None


# ---------- API ----------
@app.post("/api/assistant")
def upsert_assistant(payload: AssistantIn):
    try:
        phone = normalize_phone(payload.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный телефон (слишком короткий).")

    db = SessionLocal()
    try:
        # If we have username, update existing record for that user
        obj = None
        if payload.tg_username:
            obj = db.query(Assistant).filter(Assistant.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Assistant(
                tg_username=payload.tg_username,
                name=payload.name.strip(),
                city=payload.city.strip(),
                phone=phone,
                exp=str(payload.exp).strip(),
                rate=(payload.rate or "").strip() or None,
                availability=(payload.availability or "").strip() or None,
                about=(payload.about or "").strip() or None,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.name = payload.name.strip()
            obj.city = payload.city.strip()
            obj.phone = phone
            obj.exp = str(payload.exp).strip()
            obj.rate = (payload.rate or "").strip() or None
            obj.availability = (payload.availability or "").strip() or None
            obj.about = (payload.about or "").strip() or None
            db.commit()
            db.refresh(obj)

        return {"ok": True, "id": obj.id}
    finally:
        db.close()


@app.get("/api/assistant")
def get_my_assistant(tg_username: str):
    db = SessionLocal()
    try:
        obj = db.query(Assistant).filter(Assistant.tg_username == tg_username).first()
        if not obj:
            return JSONResponse({"ok": True, "assistant": None})
        return {
            "ok": True,
            "assistant": {
                "id": obj.id,
                "tg_username": obj.tg_username,
                "name": obj.name,
                "city": obj.city,
                "phone": obj.phone,
                "exp": obj.exp,
                "rate": obj.rate,
                "availability": obj.availability,
                "about": obj.about,
                "rating": obj.rating,
            },
        }
    finally:
        db.close()


@app.post("/api/employer")
def upsert_employer(payload: EmployerIn):
    try:
        phone = normalize_phone(payload.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный телефон (слишком короткий).")

    db = SessionLocal()
    try:
        obj = None
        if payload.tg_username:
            obj = db.query(Employer).filter(Employer.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Employer(
                tg_username=payload.tg_username,
                clinic=payload.clinic.strip(),
                city=payload.city.strip(),
                phone=phone,
                about=(payload.about or "").strip() or None,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.clinic = payload.clinic.strip()
            obj.city = payload.city.strip()
            obj.phone = phone
            obj.about = (payload.about or "").strip() or None
            db.commit()
            db.refresh(obj)

        return {"ok": True, "id": obj.id}
    finally:
        db.close()


@app.get("/api/assistants")
def list_assistants(city: Optional[str] = None) -> List[dict]:
    db = SessionLocal()
    try:
        q = db.query(Assistant)
        if city:
            q = q.filter(Assistant.city.ilike(city.strip()))
        q = q.order_by(Assistant.rating.desc(), Assistant.created_at.desc()).limit(200)
        out = []
        for a in q.all():
            out.append(
                {
                    "id": a.id,
                    "tg_username": a.tg_username,
                    "name": a.name,
                    "city": a.city,
                    "phone": a.phone,
                    "exp": a.exp,
                    "rate": a.rate,
                    "availability": a.availability,
                    "about": a.about,
                    "rating": a.rating,
                }
            )
        return out
    finally:
        db.close()


# ---------- UI ----------
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
      --text: rgba(255,255,255,.92);
      --muted: rgba(255,255,255,.65);
      --line: rgba(255,255,255,.12);
      --accent: #6aa9ff;
      --accent2: #7c5cff;
      --good: rgba(60,255,180,.10);
      --goodLine: rgba(60,255,180,.25);
      --bad: rgba(255,80,120,.10);
      --badLine: rgba(255,80,120,.25);
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
    .wrap{max-width: 760px; margin: 0 auto;}
    .top{display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom: 14px;}
    .brand{display:flex; flex-direction:column; gap:4px;}
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
    .tabs{display:flex; gap:10px; margin-bottom: 12px; flex-wrap:wrap;}
    .tab{
      padding:10px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      cursor:pointer;
      font-weight:700;
      font-size: 13px;
    }
    .tabActive{background: linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22));}
    .card{
      background: linear-gradient(180deg, var(--card), rgba(255,255,255,.04));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }
    .sectionTitle{font-size: 14px; margin: 0 0 10px; color: rgba(255,255,255,.86); letter-spacing:.2px;}
    .grid{display:grid; grid-template-columns: 1fr; gap: 10px;}
    @media (min-width: 520px){ .grid.two{grid-template-columns: 1fr 1fr;} }
    label{display:block; font-size: 12px; color: var(--muted); margin: 0 0 6px;}
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
    .actions{display:flex; gap:10px; flex-wrap: wrap; margin-top: 12px;}
    .btn{
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      padding: 12px 14px;
      border-radius: 14px;
      cursor:pointer;
      font-weight: 700;
      font-size: 14px;
      flex: 1 1 170px;
      text-align:center;
    }
    .btnPrimary{
      border: none;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #081022;
    }
    .btn:active{transform: translateY(1px);}
    .note{
      display:none;
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      font-size: 13px;
    }
    .ok{border: 1px solid var(--goodLine); background: var(--good); color: rgba(220,255,245,.95);}
    .err{border: 1px solid var(--badLine); background: var(--bad); color: rgba(255,210,225,.95);}
    .list{display:grid; gap:10px; margin-top: 10px;}
    .item{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: rgba(0,0,0,.15);
    }
    .itemTop{display:flex; justify-content:space-between; gap:10px; align-items:flex-start;}
    .itemName{font-weight:800;}
    .itemMeta{color: var(--muted); font-size: 12px; margin-top: 3px;}
    .small{font-size:12px; color: var(--muted); margin-top: 6px;}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1 id="title">Dental Assistant Finder</h1>
        <p id="subtitle">Выбери роль и заполни данные.</p>
      </div>
      <div class="pill" id="tgBadge">Telegram: не подключён</div>
    </div>

    <div class="tabs">
      <button class="tab tabActive" id="tabAssistant" onclick="setRole('assistant')">Я ассистент</button>
      <button class="tab" id="tabEmployer" onclick="setRole('employer')">Я работодатель</button>
    </div>

    <div class="card" id="assistantCard">
      <h2 class="sectionTitle">Анкета ассистента</h2>

      <div class="grid two">
        <div>
          <label>Имя *</label>
          <input id="a_name" placeholder="Например, Алина" />
        </div>
        <div>
          <label>Город *</label>
          <input id="a_city" placeholder="Например, Москва" />
        </div>
      </div>

      <div class="grid two" style="margin-top:10px;">
        <div>
          <label>Телефон *</label>
          <input id="a_phone" placeholder="+7 999 111-22-33" />
        </div>
        <div>
          <label>Опыт (лет)</label>
          <select id="a_exp">
            <option value="0">0 (стажировка)</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3+</option>
            <option value="5">5+</option>
          </select>
        </div>
      </div>

      <div class="grid two" style="margin-top:10px;">
        <div>
          <label>Ставка (₽/час)</label>
          <input id="a_rate" type="number" inputmode="numeric" placeholder="Например, 500" />
        </div>
        <div>
          <label>Когда можешь выходить</label>
          <input id="a_availability" placeholder="Пн–Пт после 16:00, Сб целый день" />
        </div>
      </div>

      <div class="grid" style="margin-top:10px;">
        <div>
          <label>Коротко о себе / навыки</label>
          <textarea id="a_about" placeholder="Ассистирование, стерилизация, снимки, 4 руки..."></textarea>
        </div>
      </div>

      <div class="actions">
        <button class="btn btnPrimary" onclick="saveAssistant()">Сохранить</button>
        <button class="btn" onclick="loadAssistant()">Загрузить из сервера</button>
      </div>

      <div class="note ok" id="a_ok">✅ Сохранено!</div>
      <div class="note err" id="a_err">❌ Ошибка</div>
    </div>

    <div class="card" id="employerCard" style="display:none;">
      <h2 class="sectionTitle">Профиль работодателя</h2>

      <div class="grid two">
        <div>
          <label>Клиника / имя работодателя *</label>
          <input id="e_clinic" placeholder="Например, Стоматология Smile" />
        </div>
        <div>
          <label>Город *</label>
          <input id="e_city" placeholder="Например, Москва" />
        </div>
      </div>

      <div class="grid two" style="margin-top:10px;">
        <div>
          <label>Телефон *</label>
          <input id="e_phone" placeholder="+7 999 111-22-33" />
        </div>
        <div>
          <label>Комментарий</label>
          <input id="e_about" placeholder="Например, ищем ассистента на завтра" />
        </div>
      </div>

      <div class="actions">
        <button class="btn btnPrimary" onclick="saveEmployer()">Сохранить профиль</button>
        <button class="btn" onclick="searchAssistants()">Найти ассистента</button>
      </div>

      <div class="note ok" id="e_ok">✅ Сохранено!</div>
      <div class="note err" id="e_err">❌ Ошибка</div>

      <div id="listWrap" style="margin-top:12px; display:none;">
        <h2 class="sectionTitle">Подходящие ассистенты</h2>
        <div class="list" id="list"></div>
      </div>
    </div>

    <div class="small" style="margin-top:12px;">
      MVP-версия. Дальше добавим рейтинг, жалобы и подтверждения.
    </div>
  </div>

  <script>
    const tg = window.Telegram?.WebApp;
    let username = null;

    function showNote(id, msg){
      const el = document.getElementById(id);
      el.innerText = msg;
      el.style.display = 'block';
      setTimeout(()=> el.style.display = 'none', 2600);
    }

    function setRole(role){
      localStorage.setItem('role', role);
      document.getElementById('tabAssistant').classList.toggle('tabActive', role==='assistant');
      document.getElementById('tabEmployer').classList.toggle('tabActive', role==='employer');
      document.getElementById('assistantCard').style.display = role==='assistant' ? 'block' : 'none';
      document.getElementById('employerCard').style.display = role==='employer' ? 'block' : 'none';
      document.getElementById('subtitle').innerText = role==='assistant'
        ? 'Заполни анкету — работодатели смогут тебя найти.'
        : 'Сохрани профиль и ищи ассистентов по городу.';
      if (tg){
        tg.MainButton.hide();
        if (role==='assistant'){
          tg.MainButton.setText("Сохранить анкету");
          tg.MainButton.onClick(saveAssistant);
          tg.MainButton.show();
        } else {
          tg.MainButton.setText("Найти ассистента");
          tg.MainButton.onClick(searchAssistants);
          tg.MainButton.show();
        }
      }
    }

    async function saveAssistant(){
      const payload = {
        tg_username: username,
        name: document.getElementById('a_name').value.trim(),
        city: document.getElementById('a_city').value.trim(),
        phone: document.getElementById('a_phone').value.trim(),
        exp: document.getElementById('a_exp').value,
        rate: document.getElementById('a_rate').value ? String(document.getElementById('a_rate').value) : null,
        availability: document.getElementById('a_availability').value.trim(),
        about: document.getElementById('a_about').value.trim(),
      };
      if (!payload.name || !payload.city || !payload.phone){
        showNote('a_err', 'Заполни обязательные поля: имя, город, телефон.');
        if (tg) tg.HapticFeedback.notificationOccurred('error');
        return;
      }
      try{
        const r = await fetch('/api/assistant', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await r.json();
        if (!r.ok){
          showNote('a_err', data.detail || 'Ошибка сохранения.');
          if (tg) tg.HapticFeedback.notificationOccurred('error');
          return;
        }
        showNote('a_ok', '✅ Сохранено!');
        if (tg) tg.HapticFeedback.notificationOccurred('success');
      }catch(e){
        showNote('a_err', 'Сеть/сервер недоступны.');
        if (tg) tg.HapticFeedback.notificationOccurred('error');
      }
    }

    async function loadAssistant(){
      if (!username){
        showNote('a_err', 'Открой через Telegram, чтобы загрузить профиль.');
        return;
      }
      try{
        const r = await fetch('/api/assistant?tg_username=' + encodeURIComponent(username));
        const data = await r.json();
        if (!data.assistant){
          showNote('a_err', 'Профиль не найден. Заполни и сохрани.');
          return;
        }
        const a = data.assistant;
        document.getElementById('a_name').value = a.name || '';
        document.getElementById('a_city').value = a.city || '';
        document.getElementById('a_phone').value = a.phone || '';
        document.getElementById('a_exp').value = a.exp || '0';
        document.getElementById('a_rate').value = a.rate || '';
        document.getElementById('a_availability').value = a.availability || '';
        document.getElementById('a_about').value = a.about || '';
        showNote('a_ok', '✅ Загружено!');
      }catch(e){
        showNote('a_err', 'Не удалось загрузить.');
      }
    }

    async function saveEmployer(){
      const payload = {
        tg_username: username,
        clinic: document.getElementById('e_clinic').value.trim(),
        city: document.getElementById('e_city').value.trim(),
        phone: document.getElementById('e_phone').value.trim(),
        about: document.getElementById('e_about').value.trim(),
      };
      if (!payload.clinic || !payload.city || !payload.phone){
        showNote('e_err', 'Заполни обязательные поля: клиника, город, телефон.');
        if (tg) tg.HapticFeedback.notificationOccurred('error');
        return;
      }
      try{
        const r = await fetch('/api/employer', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });
        const data = await r.json();
        if (!r.ok){
          showNote('e_err', data.detail || 'Ошибка сохранения.');
          if (tg) tg.HapticFeedback.notificationOccurred('error');
          return;
        }
        showNote('e_ok', '✅ Сохранено!');
        if (tg) tg.HapticFeedback.notificationOccurred('success');
      }catch(e){
        showNote('e_err', 'Сеть/сервер недоступны.');
        if (tg) tg.HapticFeedback.notificationOccurred('error');
      }
    }

    function tgLink(u){
      if (!u) return null;
      u = u.replace(/^@/, '');
      return 'https://t.me/' + encodeURIComponent(u);
    }

    async function searchAssistants(){
      const city = document.getElementById('e_city').value.trim();
      const url = city ? ('/api/assistants?city=' + encodeURIComponent(city)) : '/api/assistants';
      try{
        const r = await fetch(url);
        const list = await r.json();
        const wrap = document.getElementById('listWrap');
        const box = document.getElementById('list');
        box.innerHTML = '';
        wrap.style.display = 'block';

        if (!Array.isArray(list) || list.length === 0){
          box.innerHTML = '<div class="item">Пока нет ассистентов в этом городе.</div>';
          if (tg) tg.HapticFeedback.notificationOccurred('warning');
          return;
        }

        for (const a of list){
          const link = tgLink(a.tg_username);
          const topRight = link
            ? `<a class="btn btnPrimary" style="text-decoration:none; display:inline-block; padding:10px 12px; border-radius:12px;" href="${link}" target="_blank">Написать</a>`
            : `<div class="pill">нет username</div>`;

          const about = (a.about || '').slice(0, 180);
          const meta = [
            a.city ? a.city : '',
            a.exp ? ('опыт: ' + a.exp) : '',
            a.rate ? ('₽/час: ' + a.rate) : '',
            a.availability ? ('доступность: ' + a.availability) : '',
          ].filter(Boolean).join(' • ');

          box.innerHTML += `
            <div class="item">
              <div class="itemTop">
                <div>
                  <div class="itemName">${escapeHtml(a.name || 'Ассистент')}</div>
                  <div class="itemMeta">${escapeHtml(meta)}</div>
                </div>
                <div>${topRight}</div>
              </div>
              <div class="small">${escapeHtml(about)}</div>
              <div class="small">Тел: ${escapeHtml(a.phone || '')} • Рейтинг: ${escapeHtml(String(a.rating || 5))}</div>
            </div>
          `;
        }
        if (tg) tg.HapticFeedback.notificationOccurred('success');
      }catch(e){
        showNote('e_err', 'Не удалось загрузить список.');
        if (tg) tg.HapticFeedback.notificationOccurred('error');
      }
    }

    function escapeHtml(s){
      return (s || '').replace(/[&<>"']/g, (c)=>({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
      }[c]));
    }

    (function init(){
      const role = localStorage.getItem('role') || 'assistant';

      if (tg){
        tg.ready();
        const u = tg.initDataUnsafe?.user;
        username = u?.username ? ('@' + u.username) : null;
        document.getElementById('tgBadge').innerText =
          username ? ('Telegram: ' + username) : 'Telegram: без username';
      } else {
        document.getElementById('tgBadge').innerText = 'Открыто не из Telegram';
      }

      setRole(role);
      // If assistant and in Telegram, try to load existing profile
      if (role === 'assistant') {
        loadAssistant();
      }
    })();
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
