from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI()

# -------------------- Config --------------------
ADMIN_TG_ID = 810418985
ALLOWED_CITIES = ["Москва", "Санкт-Петербург"]

# IMPORTANT: new DB file name so schema is clean (old data won't be here)
DB_PATH = os.getenv("DB_PATH", "app_prod.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# -------------------- Helpers --------------------
def normalize_phone(phone: str) -> str:
    p = (phone or "").strip()
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


def validate_dates(dates: Optional[List[str]]) -> List[str]:
    dates = dates or []
    out = []
    for d in dates:
        d = (d or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            raise ValueError("bad_date")
        out.append(d)
    # unique + sorted
    return sorted(set(out))


# -------------------- DB Models --------------------
class Assistant(Base):
    __tablename__ = "assistants"
    id = Column(Integer, primary_key=True, index=True)

    tg_user_id = Column(Integer, nullable=True, index=True)  # Telegram numeric ID
    tg_username = Column(String(64), nullable=True, index=True)

    name = Column(String(120), nullable=False)
    city = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)

    exp = Column(String(20), nullable=False, default="0")
    rate = Column(String(20), nullable=True)
    about = Column(Text, nullable=True)

    availability_dates = Column(Text, nullable=True)  # JSON array of dates

    rating = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


class Employer(Base):
    __tablename__ = "employers"
    id = Column(Integer, primary_key=True, index=True)

    tg_user_id = Column(Integer, nullable=True, index=True)
    tg_username = Column(String(64), nullable=True, index=True)

    clinic = Column(String(160), nullable=False)
    city = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=False)
    about = Column(Text, nullable=True)

    rating = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def assistant_to_dict(a: Assistant) -> Dict[str, Any]:
    return {
        "id": a.id,
        "tg_user_id": a.tg_user_id,
        "tg_username": a.tg_username,
        "name": a.name,
        "city": a.city,
        "phone": a.phone,
        "exp": a.exp,
        "rate": a.rate,
        "about": a.about,
        "availability_dates": json.loads(a.availability_dates or "[]"),
        "rating": a.rating,
        "created_at": a.created_at.isoformat(),
    }


def employer_to_dict(e: Employer) -> Dict[str, Any]:
    return {
        "id": e.id,
        "tg_user_id": e.tg_user_id,
        "tg_username": e.tg_username,
        "clinic": e.clinic,
        "city": e.city,
        "phone": e.phone,
        "about": e.about,
        "rating": e.rating,
        "created_at": e.created_at.isoformat(),
    }


# -------------------- Schemas --------------------
class AssistantIn(BaseModel):
    tg_user_id: Optional[int] = None
    tg_username: Optional[str] = None

    name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)

    exp: str = "0"
    rate: Optional[str] = None
    about: Optional[str] = None
    availability_dates: Optional[List[str]] = None


class EmployerIn(BaseModel):
    tg_user_id: Optional[int] = None
    tg_username: Optional[str] = None

    clinic: str = Field(min_length=2, max_length=160)
    city: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=40)
    about: Optional[str] = None


# -------------------- API: Assistants --------------------
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

    try:
        dates = validate_dates(payload.availability_dates)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверная дата. Выбирайте календарём.")

    db = SessionLocal()
    try:
        obj = None
        # Prefer tg_user_id for uniqueness, fallback to username
        if payload.tg_user_id:
            obj = db.query(Assistant).filter(Assistant.tg_user_id == payload.tg_user_id).first()
        if obj is None and payload.tg_username:
            obj = db.query(Assistant).filter(Assistant.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Assistant(
                tg_user_id=payload.tg_user_id,
                tg_username=payload.tg_username,
                name=payload.name.strip(),
                city=city,
                phone=phone,
                exp=str(payload.exp).strip(),
                rate=(payload.rate or "").strip() or None,
                about=(payload.about or "").strip() or None,
                availability_dates=json.dumps(dates, ensure_ascii=False),
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
        else:
            obj.tg_user_id = payload.tg_user_id or obj.tg_user_id
            obj.tg_username = payload.tg_username or obj.tg_username
            obj.name = payload.name.strip()
            obj.city = city
            obj.phone = phone
            obj.exp = str(payload.exp).strip()
            obj.rate = (payload.rate or "").strip() or None
            obj.about = (payload.about or "").strip() or None
            obj.availability_dates = json.dumps(dates, ensure_ascii=False)
            db.commit()
            db.refresh(obj)

        return {"ok": True, "assistant": assistant_to_dict(obj)}
    finally:
        db.close()


@app.get("/api/assistant")
def get_my_assistant(
    tg_user_id: Optional[int] = None,
    tg_username: Optional[str] = None,
):
    db = SessionLocal()
    try:
        obj = None
        if tg_user_id:
            obj = db.query(Assistant).filter(Assistant.tg_user_id == tg_user_id).first()
        if obj is None and tg_username:
            obj = db.query(Assistant).filter(Assistant.tg_username == tg_username).first()
        return {"ok": True, "assistant": assistant_to_dict(obj) if obj else None}
    finally:
        db.close()


@app.get("/api/assistants")
def list_assistants(
    city: Optional[str] = None,
    date: Optional[str] = None,  # YYYY-MM-DD
):
    db = SessionLocal()
    try:
        q = db.query(Assistant)
        if city:
            city = city.strip()
            if city not in ALLOWED_CITIES:
                return []
            q = q.filter(Assistant.city == city)

        items = [assistant_to_dict(a) for a in q.order_by(Assistant.rating.desc(), Assistant.created_at.desc()).limit(300).all()]

        if date:
            date = date.strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                return []
            # filter by availability_dates contains date
            filtered = []
            for a in items:
                dates = a.get("availability_dates") or []
                if date in dates:
                    filtered.append(a)
            return filtered

        return items
    finally:
        db.close()


# -------------------- API: Employers --------------------
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
        if payload.tg_user_id:
            obj = db.query(Employer).filter(Employer.tg_user_id == payload.tg_user_id).first()
        if obj is None and payload.tg_username:
            obj = db.query(Employer).filter(Employer.tg_username == payload.tg_username).first()

        if obj is None:
            obj = Employer(
                tg_user_id=payload.tg_user_id,
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
            obj.tg_user_id = payload.tg_user_id or obj.tg_user_id
            obj.tg_username = payload.tg_username or obj.tg_username
            obj.clinic = payload.clinic.strip()
            obj.city = city
            obj.phone = phone
            obj.about = (payload.about or "").strip() or None
            db.commit()
            db.refresh(obj)

        return {"ok": True, "employer": employer_to_dict(obj)}
    finally:
        db.close()


@app.get("/api/employer")
def get_my_employer(
    tg_user_id: Optional[int] = None,
    tg_username: Optional[str] = None,
):
    db = SessionLocal()
    try:
        obj = None
        if tg_user_id:
            obj = db.query(Employer).filter(Employer.tg_user_id == tg_user_id).first()
        if obj is None and tg_username:
            obj = db.query(Employer).filter(Employer.tg_username == tg_username).first()
        return {"ok": True, "employer": employer_to_dict(obj) if obj else None}
    finally:
        db.close()


# -------------------- Admin API (MVP) --------------------
def require_admin(tg_user_id: Optional[int]):
    if tg_user_id != ADMIN_TG_ID:
        raise HTTPException(status_code=403, detail="Admin only")


@app.get("/api/admin/summary")
def admin_summary(tg_user_id: int = Query(...)):
    require_admin(tg_user_id)
    db = SessionLocal()
    try:
        a_count = db.query(Assistant).count()
        e_count = db.query(Employer).count()
        return {"ok": True, "assistants": a_count, "employers": e_count}
    finally:
        db.close()


@app.get("/api/admin/assistants")
def admin_list_assistants(tg_user_id: int = Query(...)):
    require_admin(tg_user_id)
    db = SessionLocal()
    try:
        items = db.query(Assistant).order_by(Assistant.created_at.desc()).limit(500).all()
        return {"ok": True, "items": [assistant_to_dict(x) for x in items]}
    finally:
        db.close()


@app.get("/api/admin/employers")
def admin_list_employers(tg_user_id: int = Query(...)):
    require_admin(tg_user_id)
    db = SessionLocal()
    try:
        items = db.query(Employer).order_by(Employer.created_at.desc()).limit(500).all()
        return {"ok": True, "items": [employer_to_dict(x) for x in items]}
    finally:
        db.close()


@app.post("/api/admin/delete")
def admin_delete(kind: str, item_id: int, tg_user_id: int):
    require_admin(tg_user_id)
    db = SessionLocal()
    try:
        if kind == "assistant":
            obj = db.query(Assistant).filter(Assistant.id == item_id).first()
        elif kind == "employer":
            obj = db.query(Employer).filter(Employer.id == item_id).first()
        else:
            raise HTTPException(status_code=400, detail="bad kind")

        if not obj:
            raise HTTPException(status_code=404, detail="not found")

        db.delete(obj)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


# -------------------- UI --------------------
HTML = r'''
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Dental Assistant Finder</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root{
      --bg:#0b1220;
      --card:rgba(255,255,255,.06);
      --card2:rgba(255,255,255,.08);
      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.65);
      --line:rgba(255,255,255,.12);
      --accent:#6aa9ff;
      --accent2:#7c5cff;
      --good:rgba(60,255,180,.10);
      --goodLine:rgba(60,255,180,.25);
      --bad:rgba(255,80,120,.10);
      --badLine:rgba(255,80,120,.25);
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:
        radial-gradient(1200px 700px at 10% -10%, rgba(124,92,255,.35), transparent 60%),
        radial-gradient(900px 500px at 110% 10%, rgba(106,169,255,.28), transparent 55%),
        var(--bg);
      color:var(--text);
      padding:18px 16px 28px;
    }
    .wrap{max-width:920px;margin:0 auto}
    .top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}
    .brand h1{margin:0;font-size:20px;letter-spacing:.2px}
    .brand p{margin:4px 0 0;color:var(--muted);font-size:13px}
    .pill{
      padding:8px 10px;border:1px solid var(--line);border-radius:999px;
      font-size:12px;color:var(--muted);
      background:linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22));
      white-space:nowrap;
    }
    .tabs{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
    .tab{
      padding:10px 12px;border-radius:999px;border:1px solid var(--line);
      background:rgba(255,255,255,.06);color:var(--text);
      font-weight:800;font-size:13px;cursor:pointer;
    }
    .tabActive{background:linear-gradient(135deg, rgba(106,169,255,.25), rgba(124,92,255,.22))}
    .card{
      background:linear-gradient(180deg, var(--card), rgba(255,255,255,.04));
      border:1px solid var(--line);border-radius:16px;padding:14px;
      box-shadow:0 10px 30px rgba(0,0,0,.25);
      margin-bottom:12px;
    }
    .sectionTitle{margin:0 0 10px;font-size:14px;color:rgba(255,255,255,.86);letter-spacing:.2px}
    .grid{display:grid;grid-template-columns:1fr;gap:10px}
    @media (min-width:640px){.grid.two{grid-template-columns:1fr 1fr}}
    label{display:block;font-size:12px;color:var(--muted);margin:0 0 6px}
    input,select,textarea{
      width:100%;padding:12px;border-radius:12px;border:1px solid var(--line);
      background:rgba(0,0,0,.18);color:var(--text);outline:none;
    }
    textarea{min-height:92px;resize:vertical}
    .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
    .btn{
      border:1px solid var(--line);background:rgba(255,255,255,.06);
      color:var(--text);padding:12px 14px;border-radius:14px;cursor:pointer;
      font-weight:800;font-size:14px;flex:1 1 170px;text-align:center;
    }
    .btnPrimary{
      border:none;background:linear-gradient(135deg, var(--accent), var(--accent2));
      color:#081022;
    }
    .btn:active{transform:translateY(1px)}
    .note{display:none;margin-top:10px;padding:10px 12px;border-radius:12px;font-size:13px}
    .ok{border:1px solid var(--goodLine);background:var(--good)}
    .err{border:1px solid var(--badLine);background:var(--bad)}
    .small{font-size:12px;color:var(--muted);line-height:1.4;margin-top:8px}
    .rowPills{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
    .miniPill{
      border:1px solid var(--line);background:rgba(255,255,255,.04);
      border-radius:999px;padding:6px 10px;font-size:12px;color:var(--muted);
    }
    .miniPill a{color:rgba(255,255,255,.88);text-decoration:none;margin-left:8px}
    .list{display:grid;gap:10px;margin-top:10px}
    .item{border:1px solid var(--line);border-radius:14px;padding:12px;background:rgba(0,0,0,.15)}
    .itemTop{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
    .itemName{font-weight:900}
    .itemMeta{color:var(--muted);font-size:12px;margin-top:3px}
    .linkBtn{
      display:inline-block;padding:10px 12px;border-radius:12px;
      background:linear-gradient(135deg, var(--accent), var(--accent2));
      color:#081022;font-weight:900;text-decoration:none;
    }
    .ghost{opacity:.85}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1>Dental Assistant Finder</h1>
        <p id="subtitle">Заполни профиль один раз — дальше будет кабинет.</p>
      </div>
      <div class="pill" id="tgBadge">Telegram: не подключён</div>
    </div>

    <div class="tabs">
      <button class="tab tabActive" id="tabAssistant" onclick="setRole('assistant')">Ассистент</button>
      <button class="tab" id="tabEmployer" onclick="setRole('employer')">Работодатель</button>
      <button class="tab" id="tabAdmin" onclick="setRole('admin')" style="display:none;">Админ</button>
    </div>

    <!-- Assistant Dashboard -->
    <div class="card" id="assistantDash" style="display:none;">
      <h2 class="sectionTitle">Кабинет ассистента</h2>
      <div class="small" id="assistantSummary">Загрузка…</div>
      <div class="rowPills" id="assistantDatesPills" style="display:none;"></div>
      <div class="actions">
        <button class="btn btnPrimary" onclick="openAssistantForm()">Редактировать анкету</button>
        <button class="btn" onclick="setRole('employer')">Переключиться на работодателя</button>
      </div>
      <div class="small">Дальше можно добавить: подтверждения, рейтинг, жалобы, фильтры по опыту/ставке.</div>
    </div>

    <!-- Assistant Form -->
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
            <div><input id="a_date" type="date" /></div>
            <div><button class="btn" type="button" onclick="addDate()">Добавить дату</button></div>
          </div>
          <div class="rowPills" id="a_dates_view">Пока не выбрано</div>
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
      <div class="small">После сохранения при следующем входе откроется кабинет.</div>
    </div>

    <!-- Employer Dashboard -->
    <div class="card" id="employerDash" style="display:none;">
      <h2 class="sectionTitle">Кабинет работодателя</h2>
      <div class="small" id="employerSummary">Загрузка…</div>

      <div class="grid two" style="margin-top:10px;">
        <div>
          <label>Фильтр по дате</label>
          <input id="e_filter_date" type="date" />
          <div class="small ghost">Если выбрана дата — покажет только свободных в этот день.</div>
        </div>
        <div>
          <label>&nbsp;</label>
          <button class="btn btnPrimary" onclick="searchAssistants()">Найти ассистента</button>
        </div>
      </div>

      <div class="actions">
        <button class="btn" onclick="openEmployerForm()">Редактировать профиль</button>
      </div>

      <div id="listWrap" style="margin-top:12px; display:none;">
        <h2 class="sectionTitle">Ассистенты</h2>
        <div class="list" id="list"></div>
      </div>

      <div class="note err" id="e_err">❌ Ошибка</div>
    </div>

    <!-- Employer Form -->
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
      <div class="note err" id="e_err2">❌ Ошибка</div>
      <div class="small">После сохранения при следующем входе откроется кабинет.</div>
    </div>

    <!-- Admin Panel -->
    <div class="card" id="adminPanel" style="display:none;">
      <h2 class="sectionTitle">Админ-панель</h2>
      <div class="small" id="adminSummary">Загрузка…</div>
      <div class="actions">
        <button class="btn btnPrimary" onclick="adminLoadAssistants()">Ассистенты</button>
        <button class="btn" onclick="adminLoadEmployers()">Работодатели</button>
      </div>
      <div class="list" id="adminList"></div>
      <div class="note err" id="adminErr">❌ Ошибка</div>
      <div class="small ghost">MVP-админка: просмотр и удаление. Позже можно добавить блокировки, жалобы, рейтинг.</div>
    </div>

    <div class="small" style="margin-top:12px;">
      MVP-версия. Следующее улучшение: жалобы/рейтинг, подтверждение сделки, скрытие телефона до согласия.
    </div>
  </div>

<script>
  const tg = window.Telegram?.WebApp;
  let tgUserId = null;
  let username = null;

  let selectedDates = [];
  let assistantLoaded = null;
  let employerLoaded = null;

  function esc(s){
    return (s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function showNote(id, msg){
    const el = document.getElementById(id);
    if (!el) return;
    el.innerText = msg;
    el.style.display = 'block';
    setTimeout(()=> el.style.display = 'none', 2600);
  }

  function hideAll(){
    document.getElementById('assistantDash').style.display='none';
    document.getElementById('assistantForm').style.display='none';
    document.getElementById('employerDash').style.display='none';
    document.getElementById('employerForm').style.display='none';
    document.getElementById('adminPanel').style.display='none';
  }

  function setTabs(role){
    document.getElementById('tabAssistant').classList.toggle('tabActive', role==='assistant');
    document.getElementById('tabEmployer').classList.toggle('tabActive', role==='employer');
    document.getElementById('tabAdmin').classList.toggle('tabActive', role==='admin');
  }

  function setRole(role){
    localStorage.setItem('role', role);
    setTabs(role);
    hideAll();

    if (role==='assistant'){
      document.getElementById('subtitle').innerText = 'Заполни анкету один раз — дальше будет кабинет.';
      if (tg){ tg.MainButton.setText("Сохранить анкету"); tg.MainButton.onClick(saveAssistant); tg.MainButton.show(); }
      loadAssistant(true);
      return;
    }

    if (role==='employer'){
      document.getElementById('subtitle').innerText = 'Создай профиль один раз — дальше кабинет + поиск по дате.';
      if (tg){ tg.MainButton.setText("Найти ассистента"); tg.MainButton.onClick(searchAssistants); tg.MainButton.show(); }
      loadEmployer(true);
      return;
    }

    if (role==='admin'){
      document.getElementById('subtitle').innerText = 'Админ-панель.';
      if (tg){ tg.MainButton.hide(); }
      document.getElementById('adminPanel').style.display='block';
      adminLoadSummary();
      return;
    }
  }

  // -------- Dates UI (assistant) --------
  function renderDates(){
    const el = document.getElementById('a_dates_view');
    if (!selectedDates.length){
      el.innerHTML = 'Пока не выбрано';
      return;
    }
    el.innerHTML = selectedDates.map(d =>
      `<span class="miniPill">${esc(d)}<a href="#" onclick="removeDate('${d}');return false;">✕</a></span>`
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

  // -------- Assistant --------
  function openAssistantForm(){
    hideAll();
    document.getElementById('assistantForm').style.display='block';
  }

  function showAssistantDash(a){
    assistantLoaded = a;
    hideAll();
    document.getElementById('assistantDash').style.display='block';

    const summary = [
      `<b>${esc(a.name)}</b> • ${esc(a.city)}`,
      `Тел: ${esc(a.phone)}`,
      `Опыт: ${esc(a.exp)} • ₽/час: ${esc(a.rate || '—')} • Рейтинг: ${esc(String(a.rating||5))}`
    ].join('<br/>');
    document.getElementById('assistantSummary').innerHTML = summary;

    const pills = document.getElementById('assistantDatesPills');
    const dates = Array.isArray(a.availability_dates) ? a.availability_dates : [];
    if (dates.length){
      pills.style.display='flex';
      pills.innerHTML = dates.map(d => `<span class="miniPill">${esc(d)}</span>`).join('');
    } else {
      pills.style.display='none';
      pills.innerHTML='';
    }
  }

  async function loadAssistant(showUI){
    if (!tgUserId && !username){
      if (showUI) openAssistantForm();
      return;
    }
    try{
      const qs = new URLSearchParams();
      if (tgUserId) qs.set('tg_user_id', String(tgUserId));
      if (username) qs.set('tg_username', username);
      const r = await fetch('/api/assistant?' + qs.toString());
      const data = await r.json();
      if (!data.assistant){
        assistantLoaded = null;
        if (showUI) openAssistantForm();
        return;
      }
      const a = data.assistant;

      document.getElementById('a_name').value = a.name || '';
      document.getElementById('a_city').value = a.city || '';
      document.getElementById('a_phone').value = a.phone || '';
      document.getElementById('a_exp').value = a.exp || '0';
      document.getElementById('a_rate').value = a.rate || '';
      document.getElementById('a_about').value = a.about || '';

      selectedDates = Array.isArray(a.availability_dates) ? a.availability_dates.slice() : [];
      selectedDates.sort();
      renderDates();

      if (showUI) showAssistantDash(a);
    }catch(e){
      assistantLoaded = null;
      if (showUI) openAssistantForm();
    }
  }

  async function saveAssistant(){
    const payload = {
      tg_user_id: tgUserId,
      tg_username: username,
      name: document.getElementById('a_name').value.trim(),
      city: document.getElementById('a_city').value,
      phone: document.getElementById('a_phone').value.trim(),
      exp: document.getElementById('a_exp').value,
      rate: document.getElementById('a_rate').value ? String(document.getElementById('a_rate').value) : null,
      about: document.getElementById('a_about').value.trim(),
      availability_dates: selectedDates
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
      showAssistantDash(data.assistant);
    }catch(e){
      showNote('a_err', 'Сеть/сервер недоступны.');
    }
  }

  function cancelAssistant(){
    if (assistantLoaded) showAssistantDash(assistantLoaded);
    else openAssistantForm();
  }

  // -------- Employer --------
  function openEmployerForm(){
    hideAll();
    document.getElementById('employerForm').style.display='block';
  }

  function showEmployerDash(e){
    employerLoaded = e;
    hideAll();
    document.getElementById('employerDash').style.display='block';
    document.getElementById('listWrap').style.display='none';
    document.getElementById('list').innerHTML='';

    const summary = [
      `<b>${esc(e.clinic)}</b> • ${esc(e.city)}`,
      `Тел: ${esc(e.phone)}`,
      `Комментарий: ${esc(e.about || '—')} • Рейтинг: ${esc(String(e.rating||5))}`
    ].join('<br/>');
    document.getElementById('employerSummary').innerHTML = summary;
  }

  async function loadEmployer(showUI){
    if (!tgUserId && !username){
      if (showUI) openEmployerForm();
      return;
    }
    try{
      const qs = new URLSearchParams();
      if (tgUserId) qs.set('tg_user_id', String(tgUserId));
      if (username) qs.set('tg_username', username);
      const r = await fetch('/api/employer?' + qs.toString());
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
      if (showUI) showEmployerDash(e);
    }catch(e){
      employerLoaded = null;
      if (showUI) openEmployerForm();
    }
  }

  async function saveEmployer(){
    const payload = {
      tg_user_id: tgUserId,
      tg_username: username,
      clinic: document.getElementById('e_clinic').value.trim(),
      city: document.getElementById('e_city').value,
      phone: document.getElementById('e_phone').value.trim(),
      about: document.getElementById('e_about').value.trim()
    };

    if (!payload.clinic || !payload.city || !payload.phone){
      showNote('e_err2', 'Заполни обязательные поля: клиника/имя, город, телефон.');
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
        showNote('e_err2', data.detail || 'Ошибка сохранения.');
        return;
      }
      showNote('e_ok', '✅ Сохранено!');
      showEmployerDash(data.employer);
    }catch(e){
      showNote('e_err2', 'Сеть/сервер недоступны.');
    }
  }

  function cancelEmployer(){
    if (employerLoaded) showEmployerDash(employerLoaded);
    else openEmployerForm();
  }

  function tgLink(u){
    if (!u) return null;
    u = u.replace(/^@/, '');
    return 'https://t.me/' + encodeURIComponent(u);
  }

  async function searchAssistants(){
    const city = employerLoaded?.city || document.getElementById('e_city').value;
    const date = document.getElementById('e_filter_date').value;

    if (!city){
      showNote('e_err', 'Сначала выбери город в профиле работодателя.');
      return;
    }

    const qs = new URLSearchParams();
    qs.set('city', city);
    if (date) qs.set('date', date);

    try{
      const r = await fetch('/api/assistants?' + qs.toString());
      const list = await r.json();

      const wrap = document.getElementById('listWrap');
      const box = document.getElementById('list');
      box.innerHTML = '';
      wrap.style.display = 'block';

      if (!Array.isArray(list) || list.length === 0){
        box.innerHTML = '<div class="item">Никого не найдено по этому фильтру.</div>';
        if (tg) tg.HapticFeedback.notificationOccurred('warning');
        return;
      }

      for (const a of list){
        const link = tgLink(a.tg_username);
        const right = link ? `<a class="linkBtn" target="_blank" href="${link}">Написать</a>` : `<span class="pill">нет username</span>`;
        const meta = [a.city, `опыт: ${a.exp}`, a.rate ? `₽/час: ${a.rate}` : null].filter(Boolean).join(' • ');
        const dates = Array.isArray(a.availability_dates) ? a.availability_dates : [];
        const datesLine = dates.length ? ('Даты: ' + dates.join(', ')) : 'Даты: —';
        const about = (a.about || '').slice(0, 160);

        box.innerHTML += `
          <div class="item">
            <div class="itemTop">
              <div>
                <div class="itemName">${esc(a.name || 'Ассистент')}</div>
                <div class="itemMeta">${esc(meta)}</div>
              </div>
              <div>${right}</div>
            </div>
            <div class="small">${esc(datesLine)}</div>
            <div class="small">${esc(about)}</div>
            <div class="small">Тел: ${esc(a.phone || '')} • Рейтинг: ${esc(String(a.rating||5))}</div>
          </div>
        `;
      }

      if (tg) tg.HapticFeedback.notificationOccurred('success');
    }catch(e){
      showNote('e_err', 'Не удалось загрузить список.');
      if (tg) tg.HapticFeedback.notificationOccurred('error');
    }
  }

  // -------- Admin --------
  async function adminLoadSummary(){
    try{
      const r = await fetch('/api/admin/summary?tg_user_id=' + encodeURIComponent(String(tgUserId||0)));
      const data = await r.json();
      if (!r.ok){
        document.getElementById('adminSummary').innerText = 'Нет доступа.';
        return;
      }
      document.getElementById('adminSummary').innerHTML =
        `Ассистенты: <b>${esc(String(data.assistants))}</b><br/>Работодатели: <b>${esc(String(data.employers))}</b>`;
    }catch(e){
      showNote('adminErr', 'Ошибка админки.');
    }
  }

  async function adminLoadAssistants(){
    try{
      const r = await fetch('/api/admin/assistants?tg_user_id=' + encodeURIComponent(String(tgUserId||0)));
      const data = await r.json();
      if (!r.ok){ showNote('adminErr', data.detail || 'Нет доступа'); return; }
      renderAdminList('assistant', data.items || []);
    }catch(e){ showNote('adminErr', 'Ошибка загрузки'); }
  }

  async function adminLoadEmployers(){
    try{
      const r = await fetch('/api/admin/employers?tg_user_id=' + encodeURIComponent(String(tgUserId||0)));
      const data = await r.json();
      if (!r.ok){ showNote('adminErr', data.detail || 'Нет доступа'); return; }
      renderAdminList('employer', data.items || []);
    }catch(e){ showNote('adminErr', 'Ошибка загрузки'); }
  }

  function renderAdminList(kind, items){
    const box = document.getElementById('adminList');
    box.innerHTML = '';
    if (!items.length){
      box.innerHTML = '<div class="item">Пусто</div>';
      return;
    }
    for (const x of items){
      const title = kind === 'assistant'
        ? `${esc(x.name)} • ${esc(x.city)}`
        : `${esc(x.clinic)} • ${esc(x.city)}`;
      const sub = kind === 'assistant'
        ? `Тел: ${esc(x.phone)} • tg: ${esc(x.tg_username||'—')} • id: ${esc(String(x.id))}`
        : `Тел: ${esc(x.phone)} • tg: ${esc(x.tg_username||'—')} • id: ${esc(String(x.id))}`;

      box.innerHTML += `
        <div class="item">
          <div class="itemTop">
            <div>
              <div class="itemName">${title}</div>
              <div class="itemMeta">${sub}</div>
              <div class="small">Создано: ${esc(String(x.created_at||''))}</div>
            </div>
            <div>
              <a class="linkBtn" href="#" onclick="adminDelete('${kind}', ${x.id}); return false;">Удалить</a>
            </div>
          </div>
        </div>
      `;
    }
  }

  async function adminDelete(kind, id){
    if (!confirm('Точно удалить?')) return;
    try{
      const qs = new URLSearchParams();
      qs.set('kind', kind);
      qs.set('item_id', String(id));
      qs.set('tg_user_id', String(tgUserId||0));
      const r = await fetch('/api/admin/delete?' + qs.toString(), {method:'POST'});
      const data = await r.json();
      if (!r.ok){ showNote('adminErr', data.detail || 'Ошибка'); return; }
      // refresh
      if (kind==='assistant') adminLoadAssistants(); else adminLoadEmployers();
    }catch(e){ showNote('adminErr', 'Ошибка'); }
  }

  // -------- Init --------
  (function init(){
    if (tg){
      tg.ready();
      const u = tg.initDataUnsafe?.user;
      tgUserId = u?.id || null;
      username = u?.username ? ('@' + u.username) : null;

      document.getElementById('tgBadge').innerText = tgUserId
        ? ('Telegram: ' + (username || 'без username'))
        : 'Telegram: без данных';

      // show admin tab only for your ID
      if (tgUserId === 810418985){
        document.getElementById('tabAdmin').style.display = 'inline-block';
      }

      // Nice: show main button always
      tg.MainButton.show();
    } else {
      document.getElementById('tgBadge').innerText = 'Открыто не из Telegram';
      // Hide admin tab if outside tg
      document.getElementById('tabAdmin').style.display = 'none';
    }

    const role = localStorage.getItem('role') || 'assistant';
    setRole(role);
  })();
</script>
</body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
