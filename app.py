# app.py
import os, sqlite3, base64
from datetime import datetime
import streamlit as st
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

DB_PATH   = os.environ.get("APP_DB_PATH", "app.db")
LOGO_PATH = os.environ.get("APP_LOGO_PATH", "logo.png")   # klasörünüzde logo.png olsun

# ------------------------ DB ------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT, email TEXT UNIQUE, full_name TEXT,
        phone TEXT, institution TEXT,
        role TEXT NOT NULL DEFAULT 'user',
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
      )
    """)
    # ⬇️ kalıcı puanlar tablosu
    c.execute("""
      CREATE TABLE IF NOT EXISTS scores(
        module TEXT PRIMARY KEY,
        value  INTEGER,
        updated_at TEXT NOT NULL
      )
    """)
    conn.commit()
    # admin yoksa ekle
    c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
    if c.fetchone()[0] == 0:
        c.execute("""INSERT INTO users(username, full_name, role, password_hash, created_at)
                     VALUES(?, ?, 'admin', ?, ?)""",
                  ("admin", "Sistem Yöneticisi",
                   generate_password_hash("admin"),
                   datetime.now().isoformat(timespec="seconds")))
        conn.commit()
    conn.close()

def ensure_admin_compat():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1")
    r = c.fetchone()
    if r:
        c.execute("UPDATE users SET username=?, password_hash=? WHERE id=?",
                  ("admin", generate_password_hash("admin"), r["id"]))
        conn.commit()
    conn.close()

def list_users():
    conn = get_db(); c = conn.cursor()
    c.execute("""SELECT id,username,email,full_name,phone,institution,role,is_active,created_at
                 FROM users ORDER BY created_at DESC""")
    rows = c.fetchall(); conn.close(); return rows

def add_user(email, full_name, phone, institution, role, password, username=None):
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO users(username,email,full_name,phone,institution,role,password_hash,created_at)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (username or (email.split("@")[0] if email else None),
               (email or None).lower().strip() if email else None,
               full_name.strip(), (phone or "").strip(), (institution or "").strip(),
               role, generate_password_hash(password),
               datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close()

def get_user_by_id(uid:int):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    r = c.fetchone(); conn.close(); return r

def update_password(uid, new_pw):
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_pw), uid))
    conn.commit(); conn.close()

def find_user_for_login(key):
    key = (key or "").strip().lower()
    conn = get_db(); c = conn.cursor()
    c.execute("""
      SELECT * FROM users
      WHERE (LOWER(IFNULL(username,''))=? OR LOWER(IFNULL(email,''))=?)
        AND is_active=1
    """, (key, key))
    r = c.fetchone(); conn.close(); return r

# ----- Scores helpers -----
def set_score(module: str, value: int | None):
    conn = get_db(); c = conn.cursor()
    c.execute("""
      INSERT INTO scores(module, value, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(module) DO UPDATE
        SET value=excluded.value, updated_at=excluded.updated_at
    """, (module, value, datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close()

def get_score(module: str):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT value FROM scores WHERE module=?", (module,))
    row = c.fetchone(); conn.close()
    return row[0] if row else None

# --------------------- AUTH / STATE ------------------
def require_state():
    st.session_state.setdefault("auth", None)
    st.session_state.setdefault("page", "home")
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("selected_hospital", None)   # seçilen hastane
    st.session_state.setdefault("selected_adsm_module", None) # ADSM modül

def nav_to(page):
    cur = st.session_state.page
    if cur != page:
        st.session_state.history.append(cur)
        st.session_state.page = page

def go_back():
    if st.session_state.history:
        st.session_state.page = st.session_state.history.pop()
    else:
        st.session_state.page = "home"

def do_login(key, pw):
    r = find_user_for_login(key)
    if r and check_password_hash(r["password_hash"], pw):
        st.session_state.auth = dict(
            id=r["id"], username=r["username"], email=r["email"],
            full_name=r["full_name"] or (r["username"] or r["email"]), role=r["role"]
        )
        st.session_state.page = "home"; st.session_state.history = []
        return True, None
    return False, "Kullanıcı adı/e-posta veya şifre hatalı."

def do_logout():
    st.session_state.auth = None
    st.session_state.page = "home"; st.session_state.history = []

# --------------------- CSS HELPERS -------------------
def load_logo_b64():
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None

def inject_login_css():
    b64 = load_logo_b64()
    bg  = f"url('data:image/png;base64,{b64}')" if b64 else "radial-gradient(circle at center, #ffffff, #f3f4f6)"

    st.markdown(f"""
    <style>
      html, body, .stApp {{ height:100%; margin:0 !important; padding:0 !important; }}
      header[data-testid="stHeader"],
      [data-testid="stToolbar"],
      [data-testid="stDecoration"] {{ display:none !important; }}
      [data-testid="stAppViewContainer"] {{ padding:0 !important; margin:0 !important; }}

      .stApp::before {{
        content:""; position:fixed; inset:0;
        background:{bg} center/70vmin no-repeat;
        filter: blur(10px) opacity(.28);
        z-index:0;
      }}

      .block-container {{
        height:100vh !important;
        display:flex !important;
        justify-content:center !important;
        align-items:center !important;
      }}

      .stForm {{
        width: 380px !important;
        background: rgba(255,255,255,0.92) !important;
        backdrop-filter: blur(12px) !important;
        border-radius: 20px !important;
        padding: 24px 20px !important;
        border: 1px solid rgba(255,255,255,0.5) !important;
        box-shadow: 0 30px 60px rgba(0,0,0,.18),
                    0 2px  0 rgba(255,255,255,.65) inset,
                    0 -2px 0 rgba(0,0,0,.04) inset !important;
      }}

      .stTextInput>div>div>input, .stPassword>div>div>input {{
        height: 42px !important; border-radius: 12px !important;
      }}
      .stButton>button {{
        width: 100%; height: 44px;
        border-radius: 12px; font-weight: 700;
        box-shadow: 0 10px 20px rgba(0,0,0,.10);
      }}
    </style>
    """, unsafe_allow_html=True)

def inject_app_css():
    """Giriş sonrasındaki genel stil + navbar + kart butonlar."""
    st.markdown("""
    <style>
      .block-container { padding-top:.8rem; padding-bottom:2rem; }
      .topbar{
        position:sticky; top:0; z-index:9; background:#fff; border-radius:12px;
        padding:10px 8px; margin-bottom:10px;
        border-bottom:1px solid rgba(0,0,0,.06);
        box-shadow:0 6px 20px rgba(0,0,0,.04);
      }
      .topbar .btn{
        width:100%; padding:10px 14px; border-radius:10px;
        border:1px solid rgba(0,0,0,.08); background:#fff; font-weight:600;
      }
      .topbar .btn:hover{ transform:translateY(-1px); box-shadow:0 8px 22px rgba(0,0,0,.08); }

      [data-testid="stAppViewContainer"] .stButton>button{
        background:#fff !important; border:1px solid rgba(0,0,0,.10) !important;
        box-shadow:0 10px 30px rgba(0,0,0,.10) !important;
        border-radius:18px !important; padding:22px !important;
        font-size:18px !important; font-weight:700 !important; min-height:110px !important;
        transition: transform .06s ease, box-shadow .2s ease;
        text-wrap: balance;
      }
      [data-testid="stAppViewContainer"] .stButton>button:hover{ transform:translateY(-2px); }
      .muted{ color:#6b7280; font-size:14px; margin-top:6px; text-align:center; }
      .footer-back{ margin-top:28px; }
      .grid-caption{ margin:.25rem 0 1rem 0; color:#6b7280; font-size:13px; }

      /* Selectbox'ta input'u gizleyip sadece dropdown gibi davranmasını sağla */
      .stSelectbox div[role="combobox"] input { display:none !important; }
      .stSelectbox div[role="combobox"] { cursor:pointer !important; }

      /* Durum sütunundaki selectbox genişliğini tam yap */
      .stSelectbox > div > div { width:100% !important; }
    </style>
    """, unsafe_allow_html=True)

# ------------------------ UI ------------------------
def ui_topbar():
    st.markdown('<div class="topbar">', unsafe_allow_html=True)
    cols = st.columns([1.3, 1, 1, 0.9])
    with cols[0]:
        if st.button("🏠 Ana Sayfa", key="nav_home", use_container_width=True):
            nav_to("home"); st.rerun()
    with cols[1]:
        if st.button("🔑 Şifre", key="nav_pwd", use_container_width=True):
            nav_to("sifre"); st.rerun()
    auth = st.session_state.auth or {}
    if auth.get("role") == "admin":
        with cols[2]:
            if st.button("⚙️ Kullanıcılar", key="nav_admin", use_container_width=True):
                nav_to("admin_users"); st.rerun()
    with cols[-1]:
        if st.button("🚪 Çıkış", key="nav_logout", use_container_width=True):
            do_logout(); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def ui_header_centered():
    st.markdown(
        '<div style="text-align:center;">'
        '<span style="display:inline-block;padding:6px 12px;border-radius:12px;'
        'background:linear-gradient(90deg,#ef4444,#f59e0b);color:#fff;font-weight:600;'
        'font-size:12px;letter-spacing:.4px">KURUM İÇİ</span></div>',
        unsafe_allow_html=True
    )
    st.markdown(
        "<h1 style='text-align:center; margin-top:10px;'>"
        "SAĞLIK TESİSİ DEĞERLENDİRME STANDARTLARI"
        "</h1>",
        unsafe_allow_html=True
    )

def ui_login():
    inject_login_css()
    with st.form("login_form", clear_on_submit=False):
        key = st.text_input("Kullanıcı adı veya E-posta", value="", autocomplete="username")
        pw  = st.text_input("Şifre", type="password", value="", autocomplete="current-password")
        ok  = st.form_submit_button("Giriş")
        if ok:
            success, err = do_login(key, pw)
            if success:
                st.success("Giriş başarılı."); st.rerun()
            else:
                st.error(err)

def ui_home_cards():
    st.subheader("Ana Sayfa")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🦷  ADSM/H", use_container_width=True):
            nav_to("adsmh"); st.rerun()
        st.markdown('<div class="muted">Ağız ve Diş Sağlığı Merkezleri / Hastaneler</div>', unsafe_allow_html=True)
    with c2:
        if st.button("🏥  Hastaneler", use_container_width=True):
            nav_to("hastaneler"); st.rerun()
        st.markdown('<div class="muted">Genel hastane yönetimi</div>', unsafe_allow_html=True)

# ---------- ADSM/H ----------
def ui_adsmh():
    st.subheader("ADSM/H Modülü")

    if st.button("🦷  Malatya Şehit Mehmet Kılınç Ağız ve Diş Sağlığı Hastanesi",
                 use_container_width=True):
        nav_to("adsm_msk_hastanesi"); st.rerun()

    st.markdown('<div class="muted">Malatya ADSM için değerlendirme ekranına ilerleyin.</div>',
                unsafe_allow_html=True)

    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# İSTENEN BUTONLAR (liste)
ADSM_MSK_MODULLER = [
    "Kurum Hedef Göstergeleri",
    "Poliklinik Hizmetleri",
    "Muayene ve Tedavi Süreleri",
    "Dental Görüntüleme Hizmetleri",
    "Protez Laboratuvar Süreçleri",
    "Nöbet, Mesai Dışı Çalışma ve Mesai Kaydırma Hizmetleri",
    "Sterilizasyon Hizmetleri",
    "Çalışan Memnuniyetini Artırma",
    "Sağlık Tesisinde Bina Turları",
    "Otelcilik Hizmetleri",
    "Tesis Güvenliği",
    "Sağlık Tesisinde Cihaz Yönetimi",
    "Sağlık Tesisinde İlaç ve Tıbbi Sarf Yönetimi",
    "Sağlık Tesisinde Medikal Depoların Yönetimi",
    "Sağlık Tesisi Gelir Analizi",
    "Sağlık Tesisi Gider Analizi",
    "Hasta Memnuniyeti ve Güvenliği",
    "Evde Sağlık Hizmetleri",
    "Kurum Hedef Göstergeleri",
    "Klinik Rehber ve Protokoller (o)",
    "Uzaktan Sağlık Hizmetler (o)",
    "Bakanlık Merkez Ekibi Yerinde Gözlem(P)",
]

def ui_adsm_msk_hastanesi():
    st.subheader("Malatya Şehit Mehmet Kılınç Ağız ve Diş Sağlığı Hastanesi")
    st.caption("Aşağıdaki modüllerden birini seçin.")

    # 3 sütunlu buton ızgarası
    cols = st.columns(3)
    for i, title in enumerate(ADSM_MSK_MODULLER):
        with cols[i % 3]:
            if st.button(title, key=f"adsm_mod_{i}", use_container_width=True):
                st.session_state.selected_adsm_module = title
                nav_to("adsm_module_detail"); st.rerun()

    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# ---------- Module Detail ----------
def ui_adsm_module_detail():
    import pandas as pd

    title = st.session_state.get("selected_adsm_module") or "Modül"

    # Başlık + REHBERLİK butonu aynı satırda (sadece Poliklinik ekranında göster)
    if title == "Poliklinik Hizmetleri":
        h1, h2 = st.columns([0.7, 0.3])
        with h1:
            st.subheader("🦷 Poliklinik Hizmetleri")
        with h2:
            if st.button("📘 REHBERLİK", use_container_width=True):
                nav_to("rehberlik"); st.rerun()
    else:
        st.subheader(f"🦷 {title}")

    # ---- sabitler
    OPTIONS = ["Karşılanıyor", "Kısmen Karşılanıyor", "Karşılanmıyor", "Değerlendirme Dışı"]
    SOFT_BG = {
        "Karşılanıyor":        "#e8f6ee",
        "Kısmen Karşılanıyor": "#fff7da",
        "Karşılanmıyor":       "#ffe7e7",
        "Değerlendirme Dışı":  "#eaf2ff",
    }
    PUAN_MAP = {"Karşılanıyor": 10, "Kısmen Karşılanıyor": 5, "Karşılanmıyor": 0, "Değerlendirme Dışı": None}
    BORDER = "#d1d5db"

    st.session_state.setdefault("poliklinik_results", {})

    # Selectbox'ı saf dropdown gibi kullan: input alanını gizle
    st.markdown("""
    <style>
      .stSelectbox div[role="combobox"] input { display:none !important; }
      .stSelectbox div[role="combobox"] { cursor:pointer !important; }
      .stSelectbox > div > div { width:100% !important; }
    </style>
    """, unsafe_allow_html=True)

    # ---------------- KURUM HEDEF GÖSTERGELERİ ----------------
    if title == "Kurum Hedef Göstergeleri":
        pol_toplam = st.session_state.get("puanlar", {}).get("Poliklinik Hizmetleri")
        try:
            if pol_toplam is None:
                pol_toplam = get_score("Poliklinik Hizmetleri")
        except Exception:
            pass

        data = [
            (1,  "Poliklinik hizmetlerinin etkinliği analiz edilmelidir(Ç).", pol_toplam if pol_toplam is not None else ""),
            (2,  "Poliklinik hizmetleri muayene ve tedavi süreleri etkinliği analiz edilmelidir. (Ç)", ""),
            (3,  "Dental görüntüleme hizmetleri etkinliği analiz edilmelidir.", ""),
            (4,  "Protez laboratuvar süreçleri etkinliği analiz edilmelidir.", ""),
            (5,  "Nöbet, mesai dışı çalışma ve mesai kaydırma hizmetleri etkinliği analiz edilmelidir.", ""),
            (6,  "Sterilizasyon hizmetlerinin etkinliği analiz edilmelidir.", ""),
            (7,  "Çalışan memnuniyetini artırmaya yönelik önlemler alınmalıdır.", ""),
            (8,  "Sağlık tesisinde bina turları yapılmalıdır.", ""),
            (9,  "Otelcilik hizmetlerinin etkinliğini artırmaya yönelik önlemler alınmalıdır.", ""),
            (10, "Tesis güvenliğini sağlamaya yönelik önlemler alınmalıdır.", ""),
            (11, "Sağlık tesisinde cihaz yönetiminin etkinliği analiz edilmelidir.", ""),
            (12, "Sağlık tesisinde ilaç ve tıbbi sarf yönetiminin etkinliği analiz edilmelidir.", ""),
            (13, "Sağlık tesisinde medikal depoların yönetiminin etkinliği analiz edilmelidir.", ""),
            (14, "Sağlık tesisi gelirlerinin analizi yapılmalıdır.", ""),
            (15, "Sağlık tesisi giderlerinin analizi yapılmalıdır.", ""),
            (16, "Hasta memnuniyeti ve güvenliğine yönelik düzenleme yapılmalıdır.", ""),
            (17, "Evde sağlık hizmetlerinin etkinliği analiz edilmelidir.", ""),
            (18, "Kurum Hedef Göstergeleri analiz edilmelidir.", ""),
            (19, "Klinik Rehber ve Protokollere uyum düzeyi analiz edilmelidir (O).", ""),
            (20, "Uzaktan sağlık hizmetlerinin güvenli ve etkin sunumu sağlanmalıdır (O).", ""),
            (21, "Bakanlık merkez ekibi tarafından sağlık tesisinde yerinde gözlem yapılır (P).", ""),
        ]
        df = pd.DataFrame(data, columns=["SORU", "STANDART", "PUAN"])
        st.table(df)  # scroll olmasın

        st.markdown(f"**TOPLAM PUAN (Poliklinik):** {pol_toplam if pol_toplam is not None else '⬜⬜⬜'}")

        st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
        if st.button("⬅️  Geri"):
            go_back(); st.rerun()
        return

    # ---------------- POLİKLİNİK HİZMETLERİ ----------------
    if title == "Poliklinik Hizmetleri":
        # AMAÇ kutusu
        st.markdown("""
        <div style='border-radius:12px; background:#f3f4f6; padding:16px; margin-bottom:18px;
                    border:1px solid #d1d5db; box-shadow:0 2px 6px rgba(0,0,0,0.06);'>
          <div style='font-weight:800; font-size:16px; color:#0369a1; margin-bottom:6px;'>⚙️ AMAÇ</div>
          <div style='font-size:14px; line-height:1.5; color:#374151;'>
            Poliklinik hizmetlerinin etkinliğini, erişilebilirliğini ve sürdürülebilirliğini artırmak;
            hasta memnuniyetini artırmak, kaynakların verimli kullanımını sağlamak ve randevu
            süreçlerinde karşılaşılabilecek aksaklıkların önüne geçerek sağlık hizmet sunumunda
            kaliteyi sürekli iyileştirmektir.
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.caption("Durum seçildiğinde satır anında renklenecek, puan otomatik atanacaktır.")

        # başlık şeridi
        head = st.columns([0.08, 0.55, 0.25, 0.12])  # Durum sütunu geniş
        with head[0]: st.markdown("<div style='font-weight:700;'>SORU</div>", unsafe_allow_html=True)
        with head[1]: st.markdown("<div style='font-weight:700;'>STANDART</div>", unsafe_allow_html=True)
        with head[2]: st.markdown("<div style='font-weight:700;'>DURUM</div>", unsafe_allow_html=True)
        with head[3]: st.markdown("<div style='font-weight:700;'>PUAN</div>", unsafe_allow_html=True)

        standards = [
            "Poliklinik hizmetlerinin etkinliği analiz edilmelidir(Ç).",
            "MHRS muayene ve devam eden MHRS muayene sayıları branş ve hekim bazlı analiz edilmelidir.",
            "MHRS dışı hasta muayene sayıları branş ve hekim bazlı analiz edilmelidir.",
            "Mesai dışı ve mesai kaydırma hizmetlerindeki muayene sayısı branş ve hekim bazlı analiz edilmelidir.",
            "MHRS ’ye esas poliklinikler için aktif çalışan tüm hekimlere cetvel tanımlanmış olmalıdır.",
            "MHRS ’de 15 günlük cetvelde %80 doluluğu olan branşlar analiz edilmeli, bekleyen randevu oluşmaması için gerekli önlemler alınmalıdır.",
            "Aktif bekleyen talep sayıları günlük analiz edilmeli, gerekli çalışmalar günlük yapılmalıdır.",
            "MHRS’ye girilen aksiyonların ve istisnaların doğruluğu kontrol edilmelidir.",
            "MHRS Kapalı cetvel tanımlanan hekim sayısı ve nedenleri analiz edilmelidir.",
            "Muayene ve tedavi bekleme süreleri branş ve hekim bazlı analiz edilmelidir.",
            "Devam eden MHRS muayene sadakat oranları branş ve hekim bazlı analiz edilmelidir.",
            "Ek ödemeye esas puanların aksiyon kodlarına uygunluğu kontrol edilmelidir.",
            "Başhekim başkanlığında ilgili yönetici ve sorumluların katılımı ile poliklinik hizmetleri randevu verme süreleri iki ayda bir, sonraki ayın ilk 7 günü içinde önceki iki aya ait veriler analiz edilerek değerlendirilmelidir. Gerekli hallerde iyileştirme çalışması başlatılmalıdır.",
        ]

        # sayaç & toplam
        count = {"Karşılanmıyor": 0, "Karşılanıyor": 0, "Kısmen Karşılanıyor": 0}
        total = 0

        for i, text in enumerate(standards, start=1):
            key = f"pol_res_{i}"
            default_val = st.session_state["poliklinik_results"].get(key, "Karşılanıyor")

            c1, c2, c3, c4 = st.columns([0.08, 0.55, 0.25, 0.12])

            sel = c3.selectbox(
                "Durum", OPTIONS,
                index=OPTIONS.index(default_val),
                key=key, label_visibility="collapsed"
            )
            st.session_state["poliklinik_results"][key] = sel

            puan = PUAN_MAP[sel]  # None olabilir
            if sel in count: count[sel] += 1
            if isinstance(puan, (int, float)): total += puan

            bg = SOFT_BG[sel]
            c1.markdown(
                f"<div style='padding:10px;border:1px solid {BORDER};border-right:none;"
                f"border-radius:10px 0 0 10px;background:{bg};text-align:center;font-weight:600'>{i}</div>",
                unsafe_allow_html=True
            )
            c2.markdown(
                f"<div style='padding:10px;border:1px solid {BORDER};border-left:none;border-right:none;"
                f"background:{bg};'>{text}</div>",
                unsafe_allow_html=True
            )
            c3.markdown(
                f"<div style='height:0;border:1px solid {BORDER};border-left:none;border-right:none;margin-top:-6px'></div>",
                unsafe_allow_html=True
            )
            c4.markdown(
                f"<div style='padding:10px;border:1px solid {BORDER};border-left:none;border-radius:0 10px 10px 0;"
                f"background:{bg};text-align:center;font-weight:700'>{'—' if puan is None else puan}</div>",
                unsafe_allow_html=True
            )

        # ---- KURAL: Toplam ve Genel Durum
        if count["Karşılanmıyor"] > 0:
            genel_durum = "Karşılanmıyor"; toplam_puan = 0
        else:
            karsi, kismen = count["Karşılanıyor"], count["Kısmen Karşılanıyor"]
            if karsi > 0 and kismen == 0:
                genel_durum, toplam_puan = "Karşılanıyor", total
            elif kismen > 0 and karsi == 0:
                genel_durum, toplam_puan = "Kısmen Karşılanıyor", total
            elif karsi > 0 and kismen > 0:
                genel_durum, toplam_puan = ("Karşılanıyor" if karsi >= kismen else "Kısmen Karşılanıyor", total)
            else:
                genel_durum, toplam_puan = "Değerlendirme Dışı", total

        DURUM_COLOR = {
            "Karşılanıyor": SOFT_BG["Karşılanıyor"],
            "Kısmen Karşılanıyor": SOFT_BG["Kısmen Karşılanıyor"],
            "Karşılanmıyor": SOFT_BG["Karşılanmıyor"],
            "Değerlendirme Dışı": SOFT_BG["Değerlendirme Dışı"],
        }

        # Toplam Puan + Genel Durum kutuları
        st.markdown(
            f"<div style='display:flex;gap:12px;margin-top:16px;'>"
            f"<div style='flex:1;padding:12px 14px;border:2px solid {BORDER};border-radius:12px;"
            f"background:#f9fafb;font-weight:800;font-size:16px;box-shadow:0 4px 14px rgba(0,0,0,.05)'>"
            f"Toplam Puan: {toplam_puan}</div>"
            f"<div style='padding:12px 14px;border:2px solid {BORDER};border-radius:12px;"
            f"background:{DURUM_COLOR[genel_durum]};font-weight:800;font-size:16px;'>"
            f"Genel Durum: {genel_durum}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

        # ---- ÖZET ROZETLER (renkli sayaçlar)
        toplam_soru = len(standards)
        deger_disi = sum(1 for v in st.session_state["poliklinik_results"].values() if v == "Değerlendirme Dışı")
        tamlanan   = count["Karşılanıyor"] + count["Kısmen Karşılanıyor"] + count["Karşılanmıyor"]
        kalan      = toplam_soru - (tamlanan + deger_disi)

        st.markdown(
            f"""
            <div style="margin-top:12px;display:flex;flex-wrap:wrap;gap:10px;">
              <div style="padding:8px 12px;border-radius:999px;background:{SOFT_BG['Karşılanıyor']};
                          border:1px solid #b7e2c6;font-weight:700;color:#065f46;">
                Karşılanıyor: {count['Karşılanıyor']}
              </div>
              <div style="padding:8px 12px;border-radius:999px;background:{SOFT_BG['Kısmen Karşılanıyor']};
                          border:1px solid #f1d48a;font-weight:700;color:#7a5a00;">
                Kısmen Karşılanıyor: {count['Kısmen Karşılanıyor']}
              </div>
              <div style="padding:8px 12px;border-radius:999px;background:{SOFT_BG['Karşılanmıyor']};
                          border:1px solid #f4b0b0;font-weight:700;color:#7f1d1d;">
                Karşılanmıyor: {count['Karşılanmıyor']}
              </div>
              <div style="padding:8px 12px;border-radius:999px;background:{SOFT_BG['Değerlendirme Dışı']};
                          border:1px solid #c8dafb;font-weight:700;color:#1e40af;">
                Değerlendirme Dışı: {deger_disi}
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Toplam puanı sakla (oturum + DB)
        st.session_state.setdefault("puanlar", {})
        st.session_state["puanlar"]["Poliklinik Hizmetleri"] = toplam_puan
        try:
            set_score("Poliklinik Hizmetleri", int(toplam_puan) if toplam_puan is not None else None)
        except Exception:
            pass

    else:
        st.info("Bu modül için içerik henüz eklenmedi.")

    # Genel geri
    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# ---------- Hastaneler ----------
HASTANELER_LISTESI = [
    "Malatya Eğitim ve Araştırma Hastanesi",
    "Battalgazi Devlet Hastanesi",
    "Darende Hulusi Efendi Devlet Hastanesi",
    "Doğanşehir Şehit Esra Köse Başaran Devlet Hastanesi",
    "Yeşilyurt Hasan Çalık Devlet Hastanesi",
    "Akçadağ Şehit Gökhan Aslan Devlet Hastanesi",
    "Arapgir Ali Özge Devlet Hastanesi",
    "Hekimhan Devlet Hastanesi",
    "Pütürge Devlet Hastanesi",
    "Doğanyol İlçe Devlet Hastanesi",
    "Kale İlçe Devlet Hastanesi",
    "Kuluncak Şehit Mehmet Ali Şekerci İlçe Devlet Hastanesi",
    "Yazıhan Şehit Eyüp Hacıoğlu İlçe Devlet Hastanesi",
]

def ui_hastaneler():
    st.subheader("Hastaneler Modülü")
    st.caption("Aşağıdan hastane seçin.")

    col1, col2 = st.columns(2)
    for i, name in enumerate(HASTANELER_LISTESI):
        col = col1 if i % 2 == 0 else col2
        with col:
            if st.button(f"🏥  {name}", use_container_width=True, key=f"hs_{i}"):
                st.session_state.selected_hospital = name
                nav_to("hastane_detail"); st.rerun()

    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

def ui_hastane_detail():
    name = st.session_state.get("selected_hospital") or "Hastane"
    st.subheader(name)
    st.info(f"“{name}” için değerlendirme ekranı burada olacak. (Formlar, kontrol listeleri, göstergeler, raporlar vb.)")
    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# ---------- Admin & Şifre ----------
def ui_admin_users():
    st.subheader("Kullanıcı Yönetimi")
    with st.form("add_user", clear_on_submit=True):
        email = st.text_input("Mail (kullanıcı adı olarak kullanılabilir)")
        full_name = st.text_input("İsim Soyisim*")
        phone = st.text_input("Telefon")
        institution = st.text_input("Kurum Adı")
        role = st.selectbox("Rol", ["user", "admin"], index=0)
        temp_pw = st.text_input("Geçici Şifre*", value="Malatya2025!")
        sub = st.form_submit_button("Kaydet")
        if sub:
            if not (full_name and temp_pw):
                st.error("İsim Soyisim ve Geçici Şifre zorunludur.")
            else:
                try:
                    add_user(email, full_name, phone, institution, role, temp_pw)
                    st.success("Kullanıcı eklendi.")
                except sqlite3.IntegrityError:
                    st.error("Bu e-posta zaten kayıtlı.")
    rows = list_users()
    if rows:
        st.dataframe([{
            "Kullanıcı Adı": r["username"] or "-",
            "E-posta": r["email"] or "-",
            "İsim": r["full_name"] or "-",
            "Telefon": r["phone"] or "-",
            "Kurum": r["institution"] or "-",
            "Rol": r["role"],
            "Durum": "Aktif" if r["is_active"] else "Pasif",
            "Kayıt": r["created_at"]
        } for r in rows], use_container_width=True, hide_index=True)
    else:
        st.info("Kayıtlı kullanıcı yok.")
    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

def ui_password_change():
    st.subheader("Şifremi Değiştir")
    with st.form("chg_pwd", clear_on_submit=True):
        old  = st.text_input("Mevcut Şifre", type="password")
        new1 = st.text_input("Yeni Şifre", type="password")
        new2 = st.text_input("Yeni Şifre (Tekrar)", type="password")
        sub  = st.form_submit_button("Güncelle")
        if sub:
            u = get_user_by_id(st.session_state.auth["id"])
            if not check_password_hash(u["password_hash"], old):
                st.error("Mevcut şifre yanlış.")
            elif len(new1) < 8:
                st.error("Yeni şifre en az 8 karakter olmalı.")
            elif new1 != new2:
                st.error("Yeni şifreler uyuşmuyor.")
            else:
                update_password(u["id"], new1); st.success("Şifre güncellendi.")
    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# ---------- Rehberlik sayfası ----------
def ui_rehberlik():
    st.subheader("📘 REHBERLİK")
    st.markdown("""
    <div style='background:#f9fafb;padding:16px;border-radius:12px;border:1px solid #d1d5db;'>
    Poliklinik çalışma düzeni, MHRS, MHRS dışı muayeneler ve mesai dışı hizmetlerle ilgili olarak 
    başhekim yardımcısı, günlük takipleri düzenli bir şekilde yürütmelidir. MHRS, çalışma cetveli 
    prensibine dayalı olarak planlanmalı ve polikliniklerden sorumlu başhekim/başhekim yardımcısı, 
    birim sorumlu hekimleri ve klinik sorumluları ile birlikte bu cetvelleri oluşturmalıdır. Cetveller, 
    zamanında ve en yüksek kapasiteyle girilmeli, belirtilen aksiyonlara uyum düzenli olarak izlenmelidir.<br><br>

    Örneğin, bir hekim MHRS üzerinden randevu açmadığı takdirde, aksiyon kodu olarak ameliyat 
    açması durumunda, ameliyat vaka sayısı ve süresi kontrol edilmelidir. Ayrıca, MHRS iptal nedenleri 
    sorgulanmalı ve analiz edilerek iyileştirme süreçleri başlatılmalıdır. Polikliniklerde yoğunluk yaşanan 
    ve randevu alınamayan branşlar için günlük aksiyonlar alınmalı, özellikle uzmanlık gerektiren 
    branşlardaki randevu ve bekleme süreleri özel olarak analiz edilmeli, sağlık personeli, poliklinik odası 
    ve tıbbi cihaz verimliliği sürekli olarak izlenmelidir.<br><br>

    Yoğun polikliniklerde yardımcı sağlık personeli desteği sağlanmalı, yeterli hekim mevcut olmasına rağmen 
    poliklinik oda sayısı yetersizse, mesai kaydırma ile hizmet verilmelidir. Poliklinik odası mevcut fakat hekim sayısı 
    eksikse, gönüllülük esasına dayalı olarak mesai dışı poliklinik hizmetleri sunulmalıdır. Geçici görevle 
    görevlendirilen diş hekimlerinin, kadrosunun bulunduğu sağlık tesisi tarafından MHRS cetvelinde aksiyon kodu 
    "geçici görevli" olarak işaretlenmelidir.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="footer-back"></div>', unsafe_allow_html=True)
    if st.button("⬅️  Geri"):
        go_back(); st.rerun()

# ------------------------ ROUTER ------------------------
def ui_router():
    auth = st.session_state.auth
    if not auth:
        ui_login(); return

    inject_app_css()
    ui_header_centered()
    ui_topbar()

    page = st.session_state.page
    if page == "home":
        ui_home_cards()
    elif page == "adsmh":
        ui_adsmh()
    elif page == "adsm_msk_hastanesi":
        ui_adsm_msk_hastanesi()
    elif page == "adsm_module_detail":
        ui_adsm_module_detail()
    elif page == "hastaneler":
        ui_hastaneler()
    elif page == "hastane_detail":
        ui_hastane_detail()
    elif page == "sifre":
        ui_password_change()
    elif page == "admin_users" and auth.get("role") == "admin":
        ui_admin_users()
    elif page == "rehberlik":
        ui_rehberlik()

# ------------------------ MAIN ----------------------
def main():
    st.set_page_config(page_title="SAĞLIK TESİSİ DEĞERLENDİRME STANDARTLARI",
                       page_icon="🏥", layout="wide",
                       initial_sidebar_state="collapsed")
    init_db(); ensure_admin_compat()
    require_state()
    ui_router()

if __name__ == "__main__":
    main()
