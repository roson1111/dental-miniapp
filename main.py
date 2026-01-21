from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI()

# -------------------- DB (SQLite) --------------------
# New DB file name to avoid schema mismatch with older versions.
DB_PATH = os.getenv("DB_PATH", "app_v3.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

ALLOWED_CITIES = ["Москва", "Санкт-Петербург"]


def normalize_phone(phone: str) -> str:
    p = phone.strip()
    p = re.sub(r"[^\d+]", "", p)
    digits = re.sub(r"\D", "", p)
    if len(digits) < 10:
        raise ValueError("phone_too_short")
    return p


def validate_city(city: str) -> str:
    c = (city or "").strip()
    if c not in ALLOWED_CITIES:
        raise ValueError("bad_city")
    return c


class Assistant(Base):
    __tablename__ = "assistants"
    id = Column(Integer, primary_key=True, index=True)
    tg_username = Column(String(64), nullable=True, index=True)

    name = Column(String(120), nullable=False)
    city = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)

    exp = Column(String(20), nullable=False, default="0")
    rate = Column(String(20), nullable=True)
    about = Column(Text, nullable=True)

    availability_dates = Column(Text, nullable=True)  # JSON string list

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


# -------------------- Schemas --------------------
class AssistantIn(BaseModel):
    tg_username: Optional[str] = None
    name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)

    exp: str = "0"
    rate: Optional[str] = None
    about: Optional[str] = None

    availability_dates: Optional[List[str]] = None


class EmployerIn(BaseModel):
    tg_username: Optional[str] = None
    clinic: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)
    about: Optional[str] = None


def assistant_to_dict(a: Assistant) -> Dict[str, Any]:
    return {
        "id": a.id,
        "tg_username": a.tg_username,
        "name": a.name,
        "city": a.city,
        "phone": a.phone,
        "exp": a.exp,
        "rate": a.rate,
        "about": a.about,
        "availability_dates": json.loads(a.availability_dates or "[]"),
        "rating": a.rating,
    }


def employer_to_dict(e: Employer) -> Dict[str, Any]:
    return {
        "id": e.id,
        "tg_username": e.tg_username,
        "clinic": e.clinic,
        "city": e.city,
        "phone": e.phone,
        "about": e.about,
        "rating": e.rating,
    }


# -------------------- API --------------------
@app.post("/api/assistant")
def upsert_assistant(payload: AssistantIn):
    try:
        phone = normalize_phone(payload.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный телефон (слишком короткий).")

    try:
        city = validate_city(payload.city)
    except ValueError:
        raise HTTPException(status_code=400, detail="Выберите город: Москва или Санкт-Петербург.")

    dates = payload.availability_dates or []
    # small validation for YYYY-MM-DD strings
    for d in dates:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", (d or "").strip()):
            raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте календарь.")

    db = SessionLocal()
    try:
        obj = None
        if payload.tg_username:
            obj = db.query(Assistant).filter(Assistant.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Assistant(
                tg_username=payload.tg_username,
                name=payload.name.strip(),
                city=city,
                phone=phone,
                exp=str(payload.exp).strip(),
                rate=(payload.rate or "").strip() or None,
                about=(payload.about or "").strip() or None,
                availability_dates=json.dumps(sorted(set(dates)), ensure_ascii=False),
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.name = payload.name.strip()
            obj.city = city
            obj.phone = phone
            obj.exp = str(payload.exp).strip()
            obj.rate = (payload.rate or "").strip() or None
            obj.about = (payload.about or "").strip() or None
            obj.availability_dates = json.dumps(sorted(set(dates)), ensure_ascii=False)
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
        return {"ok": True, "assistant": assistant_to_dict(obj)}
    finally:
        db.close()


@app.post("/api/employer")
def upsert_employer(payload: EmployerIn):
    try:
        phone = normalize_phone(payload.phone)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный телефон (слишком короткий).")

    try:
        city = validate_city(payload.city)
    except ValueError:
        raise HTTPException(status_code=400, detail="Выберите город: Москва или Санкт-Петербург.")

    db = SessionLocal()
    try:
        obj = None
        if payload.tg_username:
            obj = db.query(Employer).filter(Employer.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Employer(
                tg_username=payload.tg_username,
                clinic=payload.clinic.strip(),
                city=city,
                phone=phone,
                about=(payload.about or "").strip() or None,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.clinic = payload.clinic.strip()
            obj.city = city
            obj.phone = phone
            obj.about = (payload.about or "").strip() or None
            db.commit()
            db.refresh(obj)

        return {"ok": True, "id": obj.id}
    finally:
        db.close()


@app.get("/api/employer")
def get_my_employer(tg_username: str):
    db = SessionLocal()
    try:
        obj = db.query(Employer).filter(Employer.tg_username == tg_username).first()
        if not obj:
            return JSONResponse({"ok": True, "employer": None})
        return {"ok": True, "employer": employer_to_dict(obj)}
    finally:
        db.close()


@app.get("/api/assistants")
def list_assistants(city: Optional[str] = None) -> List[dict]:
    db = SessionLocal()
    try:
        q = db.query(Assistant)
        if city:
            # strict to our allowed cities
            city = city.strip()
            if city not in ALLOWED_CITIES:
                return []
            q = q.filter(Assistant.city == city)
        q = q.order_by(Assistant.rating.desc(), Assistant.created_at.desc()).limit(200)
        return [assistant_to_dict(a) for a in q.all()]
    finally:
        db.close()


# -------------------- UI --------------------
HTML = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Dental Assistant Finder</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root{{
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
    }}
    *{{box-sizing:border-box}}
    body{{
      margin:0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:
        radial-gradient(1200px 700px at 10% -10%, rgba(124,92,255,.35), transparent 60%),
        radial-gradient(900px 500px at 110% 10%, rgba(106,169,255,.28), transparent 55%),
        var(--bg);
      color: var(--text);
      padding: 18px 16px 24px;
    }}
    .wrap{{max-width: 860px; margin: 0 auto;}}
    .top{{display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom: 14px;}}
    .brand{{display:flex; flex-direction:column; gap:4px;}}
    .brand h1{{margin:0; font-size:20px; letter-spacing:.2px;}}
    .brand p{{margin:0; font-size:13px; color: var(--muted);}}
    .pill{{
      padding:8px 10px;
      background: linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22));
      border: 1px solid var(--line);
      border-radius: 999px;
      font-size: 12px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .tabs{{display:flex; gap:10px; margin-bottom: 12px; flex-wrap:wrap;}}
    .tab{{
      padding:10px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      cursor:pointer;
      font-weight:800;
      font-size: 13px;
    }}
    .tabActive{{background: linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22));}}
    .card{{
      background: linear-gradient(180deg, var(--card), rgba(255,255,255,.04));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25);
      margin-bottom: 12px;
    }}
    .sectionTitle{{font-size: 14px; margin: 0 0 10px; color: rgba(255,255,255,.86); letter-spacing:.2px;}}
    .grid{{display:grid; grid-template-columns: 1fr; gap: 10px;}}
    @media (min-width: 620px){{ .grid.two{{grid-template-columns: 1fr 1fr;}} }}
    label{{display:block; font-size: 12px; color: var(--muted); margin: 0 0 6px;}}
    input, select, textarea{{
      width:100%;
      padding: 12px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: rgba(0,0,0,.18);
      color: var(--text);
      outline: none;
    }}
    textarea{{min-height: 92px; resize: vertical;}}
    input::placeholder, textarea::placeholder{{color: rgba(255,255,255,.38);}}
    .actions{{display:flex; gap:10px; flex-wrap: wrap; margin-top: 12px;}}
    .btn{{
      border: 1px solid var(--line);
      background: rgba(255,255,255,.06);
      color: var(--text);
      padding: 12px 14px;
      border-radius: 14px;
      cursor:pointer;
      font-weight: 800;
      font-size: 14px;
      flex: 1 1 170px;
      text-align:center;
    }}
    .btnPrimary{{
      border: none;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      color: #081022;
    }}
    .btn:active{{transform: translateY(1px);}}
    .note{{
      display:none;
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      font-size: 13px;
    }}
    .ok{{border: 1px solid var(--goodLine); background: var(--good); color: rgba(220,255,245,.95);}}
    .err{{border: 1px solid var(--badLine); background: var(--bad); color: rgba(255,210,225,.95);}}
    .small{{font-size:12px; color: var(--muted); margin-top: 6px; line-height:1.4;}}
    .list{{display:grid; gap:10px; margin-top: 10px;}}
    .item{{border: 1px solid var(--line); border-radius: 14px; padding: 12px; background: rgba(0,0,0,.15);}}
    .itemTop{{display:flex; justify-content:space-between; gap:10px; align-items:flex-start;}}
    .itemName{{font-weight:900;}}
    .itemMeta{{color: var(--muted); font-size: 12px; margin-top: 3px;}}
    .rowPills{{margin-top:8px; display:flex; flex-wrap:wrap; gap:6px;}}
    .miniPill{{border:1px solid var(--line); border-radius:999px; padding:6px 10px; font-size:12px; color: var(--muted); background: rgba(255,255,255,.04);}}
    a.link{{color: rgba(255,255,255,.9);}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1 id="title">Dental Assistant Finder</h1>
        <p id="subtitle">Выбери роль и заполни профиль один раз.</p>
      </div>
      <div class="pill" id="tgBadge">Telegram: не подключён</div>
    </div>

    <div class="tabs">
      <button class="tab tabActive" id="tabAssistant" onclick="setRole('assistant')">Ассистент</button>
      <button class="tab" id="tabEmployer" onclick="setRole('employer')">Работодатель</button>
    </div>

    <!-- Assistant: dashboard -->
    <div class="card" id="assistantDash" style="display:none;">
      <h2 class="sectionTitle">Кабинет ассистента</h2>
      <div class="small" id="assistantSummary">Загрузка…</div>
      <div class="rowPills" id="assistantDatesPills" style="display:none;"></div>
      <div class="actions">
        <button class="btn btnPrimary" onclick="openAssistantForm()">Редактировать анкету</button>
        <button class="btn" onclick="setRole('employer')">Я работодатель</button>
      </div>
      <div class="small">Дальше добавим: «Найти подработку», рейтинг и жалобы.</div>
    </div>

    <!-- Assistant: form -->
    <div class="card" id="assistantForm">
      <h2 class="sectionTitle">Анкета ассистента</h2>

      <div class="grid two">
        <div>
          <label>Имя *</label>
          <input id="a_name" placeholder="Например, Алина" />
        </div>
        <div>
          <label>Город *</label>
          <select id="a_city">
            <option value="">Выберите город</option>
            <option value="Москва">Москва</option>
            <option value="Санкт-Петербург">Санкт-Петербург</option>
          </select>
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
          <label>Даты, когда можешь выйти</label>
          <div class="grid two">
            <div>
              <input id="a_date" type="date" />
            </div>
            <div>
              <button class="btn" type="button" onclick="addDate()">Добавить дату</button>
            </div>
          </div>
          <div class="rowPills" id="a_dates_view" style="margin-top:8px;">Пока не выбрано</div>
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
        <button class="btn" onclick="cancelAssistant()">Отмена</button>
      </div>

      <div class="note ok" id="a_ok">✅ Сохранено!</div>
      <div class="note err" id="a_err">❌ Ошибка</div>
      <div class="small">Заполняешь 1 раз — при следующем входе будет кабинет.</div>
    </div>

    <!-- Employer: dashboard -->
    <div class="card" id="employerDash" style="display:none;">
      <h2 class="sectionTitle">Кабинет работодателя</h2>
      <div class="small" id="employerSummary">Загрузка…</div>
      <div class="actions">
        <button class="btn btnPrimary" onclick="searchAssistants()">Найти ассистента</button>
        <button class="btn" onclick="openEmployerForm()">Редактировать профиль</button>
      </div>
      <div id="listWrap" style="margin-top:12px; display:none;">
        <h2 class="sectionTitle">Ассистенты</h2>
        <div class="list" id="list"></div>
      </div>
    </div>

    <!-- Employer: form -->
    <div class="card" id="employerForm" style="display:none;">
      <h2 class="sectionTitle">Профиль работодателя</h2>

      <div class="grid two">
        <div>
          <label>Клиника / имя *</label>
          <input id="e_clinic" placeholder="Например, Стоматология Smile" />
        </div>
        <div>
          <label>Город *</label>
          <select id="e_city">
            <option value="">Выберите город</option>
            <option value="Москва">Москва</option>
            <option value="Санкт-Петербург">Санкт-Петербург</option>
          </select>
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
        <button class="btn btnPrimary" onclick="saveEmployer()">Сохранить</button>
        <button class="btn" onclick="cancelEmployer()">Отмена</button>
      </div>

      <div class="note ok" id="e_ok">✅ Сохранено!</div>
      <div class="note err" id="e_err">❌ Ошибка</div>
      <div class="small">Заполняешь 1 раз — при следующем входе будет кабинет.</div>
    </div>

    <div class="small" style="margin-top:12px;">
      MVP. Следующие шаги: отзывы/жалобы, рейтинг, верификация, фильтры по датам.
    </div>
  </div>

<script>
  const tg = window.Telegram?.WebApp;
  let username = null;

  // Assistant state
  let selectedDates = [];
  let assistantLoaded = null;
  let employerLoaded = null;

  function showNote(id, msg){
    const el = document.getElementById(id);
    el.innerText = msg;
    el.style.display = 'block';
    setTimeout(()=> el.style.display = 'none', 2600);
  }

  function escapeHtml(s){
    return (s || '').replace(/[&<>"']/g, (c)=>({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function setRole(role){
    localStorage.setItem('role', role);

    document.getElementById('tabAssistant').classList.toggle('tabActive', role==='assistant');
    document.getElementById('tabEmployer').classList.toggle('tabActive', role==='employer');

    // hide all cards; decide after load
    hideAssistantAll();
    hideEmployerAll();

    if (tg){
      tg.MainButton.hide();
      if (role==='assistant'){
        tg.MainButton.setText("Сохранить анкету");
        tg.MainButton.onClick(saveAssistant);
      } else {
        tg.MainButton.setText("Найти ассистента");
        tg.MainButton.onClick(searchAssistants);
      }
      tg.MainButton.show();
    }

    document.getElementById('subtitle').innerText =
      role==='assistant' ? 'Заполни анкету один раз — дальше будет кабинет.' : 'Создай профиль один раз — дальше будет кабинет.';

    // Load profile for role
    if (role === 'assistant') {
      loadAssistant(true);
    } else {
      loadEmployer(true);
    }
  }

  function hideAssistantAll(){
    document.getElementById('assistantDash').style.display = 'none';
    document.getElementById('assistantForm').style.display = 'none';
  }
  function hideEmployerAll(){
    document.getElementById('employerDash').style.display = 'none';
    document.getElementById('employerForm').style.display = 'none';
  }

  function renderDates(){
    const el = document.getElementById('a_dates_view');
    if (!selectedDates.length){
      el.innerHTML = 'Пока не выбрано';
      return;
    }
    el.innerHTML = selectedDates.map(d =>
      `<span class="miniPill">
         ${escapeHtml(d)}
         <a class="link" href="#" onclick="removeDate('${d}'); return false;" style="margin-left:8px; text-decoration:none;">✕</a>
       </span>`
    ).join('');
  }

  function addDate(){
    const inp = document.getElementById('a_date');
    const d = inp.value;
    if (!d) return;
    if (!selectedDates.includes(d)) selectedDates.push(d);
    selectedDates.sort();
    inp.value = '';
    renderDates();
  }

  function removeDate(d){
    selectedDates = selectedDates.filter(x => x !== d);
    renderDates();
  }

  function openAssistantForm(){
    hideAssistantAll();
    document.getElementById('assistantForm').style.display = 'block';
  }

  function cancelAssistant(){
    // back to dashboard if exists else stay
    if (assistantLoaded){
      showAssistantDashboard(assistantLoaded);
    } else {
      // keep form
      openAssistantForm();
    }
  }

  function showAssistantDashboard(a){
    assistantLoaded = a;
    hideAssistantAll();
    document.getElementById('assistantDash').style.display = 'block';

    const summary = [
      `<b>${escapeHtml(a.name)}</b> • ${escapeHtml(a.city)}`,
      `Тел: ${escapeHtml(a.phone)}`,
      `Опыт: ${escapeHtml(a.exp)} • ₽/час: ${escapeHtml(a.rate || '—')} • Рейтинг: ${escapeHtml(String(a.rating || 5))}`
    ].join('<br/>');
    document.getElementById('assistantSummary').innerHTML = summary;

    const pills = document.getElementById('assistantDatesPills');
    const dates = a.availability_dates || [];
    if (dates.length){
      pills.style.display = 'flex';
      pills.className = 'rowPills';
      pills.innerHTML = dates.map(d => `<span class="miniPill">${escapeHtml(d)}</span>`).join('');
    } else {
      pills.style.display = 'none';
      pills.innerHTML = '';
    }
  }

  async function loadAssistant(showUI){
    if (!username){
      // outside Telegram: show form
      if (showUI){
        openAssistantForm();
      }
      return;
    }
    try{
      const r = await fetch('/api/assistant?tg_username=' + encodeURIComponent(username));
      const data = await r.json();
      if (!data.assistant){
        assistantLoaded = null;
        if (showUI) openAssistantForm();
        return;
      }
      const a = data.assistant;
      // fill form values
      document.getElementById('a_name').value = a.name || '';
      document.getElementById('a_city').value = a.city || '';
      document.getElementById('a_phone').value = a.phone || '';
      document.getElementById('a_exp').value = a.exp || '0';
      document.getElementById('a_rate').value = a.rate || '';
      document.getElementById('a_about').value = a.about || '';

      selectedDates = Array.isArray(a.availability_dates) ? a.availability_dates.slice() : [];
      selectedDates.sort();
      renderDates();

      if (showUI) showAssistantDashboard(a);
    }catch(e){
      assistantLoaded = null;
      if (showUI) openAssistantForm();
    }
  }

  async function saveAssistant(){
    const payload = {
      tg_username: username,
      name: document.getElementById('a_name').value.trim(),
      city: document.getElementById('a_city').value,
      phone: document.getElementById('a_phone').value.trim(),
      exp: document.getElementById('a_exp').value,
      rate: document.getElementById('a_rate').value ? String(document.getElementById('a_rate').value) : null,
      about: document.getElementById('a_about').value.trim(),
      availability_dates: selectedDates,
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
      // reload and show dashboard
      await loadAssistant(true);
    }catch(e){
      showNote('a_err', 'Сеть/сервер недоступны.');
      if (tg) tg.HapticFeedback.notificationOccurred('error');
    }
  }

  function openEmployerForm(){
    hideEmployerAll();
    document.getElementById('employerForm').style.display = 'block';
  }

  function cancelEmployer(){
    if (employerLoaded){
      showEmployerDashboard(employerLoaded);
    } else {
      openEmployerForm();
    }
  }

  function showEmployerDashboard(e){
    employerLoaded = e;
    hideEmployerAll();
    document.getElementById('employerDash').style.display = 'block';
    document.getElementById('listWrap').style.display = 'none';
    document.getElementById('list').innerHTML = '';

    const summary = [
      `<b>${escapeHtml(e.clinic)}</b> • ${escapeHtml(e.city)}`,
      `Тел: ${escapeHtml(e.phone)}`,
      `Рейтинг: ${escapeHtml(String(e.rating || 5))} • Комментарий: ${escapeHtml(e.about || '—')}`
    ].join('<br/>');
    document.getElementById('employerSummary').innerHTML = summary;
  }

  async function loadEmployer(showUI){
    if (!username){
      if (showUI) openEmployerForm();
      return;
    }
    try{
      const r = await fetch('/api/employer?tg_username=' + encodeURIComponent(username));
      const data = await r.json();
      if (!data.employer){
        employerLoaded = null;
        if (showUI) openEmployerForm();
        return;
      }
      const e = data.employer;
      document.getElementById('e_clinic').value = e.clinic || '';
      document.getElementById('e_city').value = e.city || '';
      document.getElementById('e_phone').value = e.phone || '';
      document.getElementById('e_about').value = e.about || '';
      if (showUI) showEmployerDashboard(e);
    }catch(e){
      employerLoaded = null;
      if (showUI) openEmployerForm();
    }
  }

  async function saveEmployer(){
    const payload = {
      tg_username: username,
      clinic: document.getElementById('e_clinic').value.trim(),
      city: document.getElementById('e_city').value,
      phone: document.getElementById('e_phone').value.trim(),
      about: document.getElementById('e_about').value.trim(),
    };

    if (!payload.clinic || !payload.city || !payload.phone){
      showNote('e_err', 'Заполни обязательные поля: клиника/имя, город, телефон.');
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
      await loadEmployer(true);
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
    const city = employerLoaded?.city || document.getElementById('e_city').value;
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

        const meta = [
          a.city ? a.city : '',
          a.exp ? ('опыт: ' + a.exp) : '',
          a.rate ? ('₽/час: ' + a.rate) : '',
        ].filter(Boolean).join(' • ');

        const dates = Array.isArray(a.availability_dates) ? a.availability_dates : [];
        const datesLine = dates.length ? ('Даты: ' + dates.join(', ')) : 'Даты: —';
        const about = (a.about || '').slice(0, 160);

        box.innerHTML += `
          <div class="item">
            <div class="itemTop">
              <div>
                <div class="itemName">${escapeHtml(a.name || 'Ассистент')}</div>
                <div class="itemMeta">${escapeHtml(meta)}</div>
              </div>
              <div>${topRight}</div>
            </div>
            <div class="small">${escapeHtml(datesLine)}</div>
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

  (function init(){
    if (tg){
      tg.ready();
      const u = tg.initDataUnsafe?.user;
      username = u?.username ? ('@' + u.username) : null;
      document.getElementById('tgBadge').innerText = username ? ('Telegram: ' + username) : 'Telegram: без username';
    } else {
      document.getElementById('tgBadge').innerText = 'Открыто не из Telegram';
    }

    const role = localStorage.getItem('role') || 'assistant';
    setRole(role);
  })();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
