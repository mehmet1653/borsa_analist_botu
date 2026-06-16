import os
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import time
import json
import requests
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai
import datetime as dt

# ==========================================
# 🧠 FABRİKA AYARLARI (Yedek Hafıza)
# ==========================================
SABIT_GECHMIS_DERSLER = [
    {"tarih": "2026-06-15", "ders": "ÖĞRENİLEN DERS: Jeopolitik spekülasyonlar yerine tamamen matematiksel rasyolara ve teknik indikatörlere odaklanılmalıdır."},
    {"tarih": "2026-06-16", "ders": "ÖĞRENİLEN DERS: Canlı veri kısıtlıysa temel analiz rasyoları elle girilip bulutta saklanmalıdır."}
]

PORTFOY_YEDEK = {"SASA.IS": {"lot": 19, "maliyet": 3.65}}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KCHOL.IS", "NVDA", "INTC"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Gemini Kurulumu
genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

HAFIZA = {}

# ==========================================
# ☁️ SUPABASE BULUT HAFIZA MOTORU
# ==========================================
def bulut_hafiza_yukle():
    global HAFIZA
    if not SUPABASE_URL or not SUPABASE_KEY:
        HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER}
        return

    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200: 
            HAFIZA = res.json()
        else: 
            HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER}
    except: 
        HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK, "temel_veriler": {}, "ogrenilen_dersler": SABIT_GECHMIS_DERSLER}

def bulut_hafiza_kaydet():
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json", "x-upsert": "true"}
    try:
        requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=10)
    except: 
        pass

# İlk açılışta bulut hafızasını çek
bulut_hafiza_yukle()

# ==========================================
# 📡 EN GÜNCEL KÜRESEL HABER MOTORU
# ==========================================
def son_dakika_haberleri_al():
    """Botun anlık küresel piyasa manşetlerini internetten topladığı alan"""
    try:
        # Finans dünyasının en dinamik RSS/Haber kaynaklarından birini tarıyoruz
        res = requests.get("https://news.google.com/rss/search?q=finance+economy+markets&hl=en-US&gl=US&ceid=US:en", timeout=8)
        if res.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(res.content, 'xml')
            titles = [item.title.text for item in soup.find_all('item')[:5]]
            return " | ".join(titles)
    except:
        pass
    return "Küresel piyasalar hareketli, makroekonomik veriler takip ediliyor."

# ==========================================
# 📊 ANALİZ VE RAPORLAMA MOTORU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: 
        requests.post(url, json=payload, timeout=10)
    except: 
        pass

def finansal_veri_topla(sembol):
    try:
        df = yf.download(sembol, period="1y", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.droplevel(1)
        close_series = df['Close'].astype(float)
        guncel_fiyat = float(close_series.iloc[-1])
        rsi = ta.momentum.rsi(close_series, window=14).iloc[-1]
        macd = ta.trend.macd(close_series).iloc[-1]
        signal = ta.trend.macd_signal(close_series).iloc[-1]
        
        temel = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-"})
        portfoy_notu = ""
        if sembol in HAFIZA["portfoy"]:
            p = HAFIZA["portfoy"][sembol]
            kz = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
            portfoy_notu = f"| Pozisyon: %{kz:.1f} Kâr"

        return f"{sembol} (Fiyat: {guncel_fiyat:.2f}, RSI: {rsi:.1f}, MACD: {'AL' if macd > signal else 'SAT'}, F/K: {temel['fk']}, PD/DD: {temel['pddd']} {portfoy_notu})"
    except: 
        return None

def ajani_calistir(rapor_tipi="PİYASA ANALİZİ"):
    # 1. Teknik verileri topla
    veriler = [finansal_veri_topla(s) for s in HAFIZA["takip_listesi"] if finansal_veri_topla(s)]
    
    # 2. Anlık canlı haberleri çek
    guncel_haberler = son_dakika_haberleri_al()
    
    # 3. Yapay Zekaya hem teknik verileri hem de en güncel haberleri verip analiz ettir
    prompt = f"""
    Sen üst düzey bir borsa analistisin. 
    Aşağıdaki anlık teknik verileri ve internetten gelen en güncel piyasa haberlerini sentezleyerek profesyonel bir rapor hazırla.

    🔴 ANLIK GÜNCEL KÜRESEL HABERLER:
    {guncel_haberler}

    📊 HİSSE TEKNİK VE TEMEL VERİLERİ:
    {veriler}

    İstenen Format:
    - Girişe güncel haberlere göre çok kısa (1 cümle) genel piyasa havası yaz.
    - Takip listesindeki her hisse için sadece 2 cümle nokta atışı yorum ve 1 haftalık net beklenti yaz. 
    - Telegram karakter sınırını aşmamak için gereksiz uzatmalardan kaçın.
    """
    
    rapor = model.generate_content(prompt).text
    telegram_mesaj_gonder(f"📊 *{rapor_tipi}*\n\n{rapor}")

# ==========================================
# ⚙️ TELEGRAM KOMUT DİNLEYİCİSİ
# ==========================================
def telegram_komutlari_dinle():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={HAFIZA.get('last_update_id', 0) + 1}"
    try:
        res = requests.get(url, timeout=10).json()
        for u in res.get("result", []):
            HAFIZA["last_update_id"] = u["update_id"]
            if "message" in u and "text" in u["message"]:
                txt = u["message"]["text"]
                
                if txt.startswith("/analiz"):
                    telegram_mesaj_gonder("⏳ Veriler toplanıyor ve güncel haberler taranıyor, lütfen bekleyin...")
                    ajani_calistir()
                    
                elif txt.startswith("/rasyo_ekle"):
                    try:
                        _, s, fk, pddd = txt.split()
                        if "temel_veriler" not in HAFIZA: HAFIZA["temel_veriler"] = {}
                        HAFIZA["temel_veriler"][s.upper()] = {"fk": fk, "pddd": pddd}
                        bulut_hafiza_kaydet()
                        telegram_mesaj_gonder(f"✅ {s.upper()} rasyoları bulut hafızasına ölümsüz olarak kaydedildi.")
                    except:
                        telegram_mesaj_gonder("❌ Hatalı komut. Örnek kullanım: `/rasyo_ekle THYAO.IS 3.20 1.15`")
    except: 
        pass

def run_dummy_server(): 
    HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()

if __name__ == "__main__":
    # Render'ın kapanmaması için sahte web sunucusu
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # Sonsuz dinleme döngüsü
    while True:
        telegram_komutlari_dinle()
        time.sleep(4)
        
