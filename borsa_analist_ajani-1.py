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

# ==========================================
# 🧠 YEDEK HAFIZA AYARLARI
# ==========================================
PORTFOY_YEDEK = {"SASA.IS": {"lot": 19, "maliyet": 3.65}}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "SASA.IS", "KCHOL.IS"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

try:
    genai.configure(api_key=str(GEMINI_API_KEY).strip())
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = None

# Ana hafıza yapısı (Her ihtimale karşı içi dolu başlar)
HAFIZA = {
    "takip_listesi": TAKIP_YEDEK,
    "portfoy": PORTFOY_YEDEK,
    "temel_veriler": {},
    "hisse_tarihcesi": {},
    "last_update_id": 0
}

# ==========================================
# ☁️ SUPABASE BULUT HAFIZA MOTORU (ZIRHLI)
# ==========================================
def bulut_hafiza_yukle():
    global HAFIZA
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200: 
            yuklenen = res.json()
            # Eğer buluttaki dosya doluysa, yerel hafızayı onunla güncelle
            for anahtar in ["takip_listesi", "portfoy", "temel_veriler", "hisse_tarihcesi", "last_update_id"]:
                if anahtar in yuklenen:
                    HAFIZA[anahtar] = yuklenen[anahtar]
            print("✅ Bulut hafızası başarıyla yüklendi.")
        else:
            print("ℹ️ Bulutta dosya bulunamadı, yerel hafıza kullanılacak.")
    except Exception as e:
        print(f"⚠️ Bulut hafızası yüklenirken hata oluştu ama sistem devam ediyor: {e}")

def bulut_hafiza_kaydet():
    if not SUPABASE_URL or not SUPABASE_KEY: return
    url = f"{SUPABASE_URL}/storage/v1/object/ajan_hafizasi/hafiza.json"
    headers = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY, "Content-Type": "application/json", "x-upsert": "true"}
    try: 
        requests.post(url, headers=headers, data=json.dumps(HAFIZA, indent=4), timeout=5)
    except: 
        pass

# Kod başlarken hafızayı çekmeyi dener, klasör boşsa veya hata verirse çökmez!
try:
    bulut_hafiza_yukle()
except:
    print("Hafıza yükleme adımı pas geçildi.")

# ==========================================
# 📊 VERİ TOPLAMA VE ANALİZ MOTORU
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}, timeout=5)
    except: pass

def finansal_veri_topla(sembol):
    try:
        # Tıkanmayı önlemek için sadece son 1 ayı indiriyoruz
        df = yf.download(sembol, period="1mo", progress=False, timeout=5)
        if df.empty:
            return f"{sembol}: Canlı fiyat çekilemedi."
        
        if isinstance(df.columns, pd.MultiIndex): 
            df.columns = df.columns.droplevel(1)
            
        guncel_fiyat = float(df['Close'].iloc[-1])
        rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1] if len(df) >= 14 else 50.0
        
        return f"{sembol} (Fiyat: {guncel_fiyat:.2f}, RSI: {rsi:.1f})"
    except Exception as e:
        return f"{sembol} (Bağlantı Hatası: {str(e)[:20]})"

def ajani_calistir():
    veriler = []
    # Hafızada liste varsa onu kullanır, yoksa yedek listeyi devreye sokar
    hisseler = HAFIZA.get("takip_listesi", TAKIP_YEDEK)
    
    for s in hisseler:
        res = finansal_veri_topla(s)
        if res: veriler.append(res)
        time.sleep(0.5)
        
    try:
        prompt = f"Sen profesyonel bir borsa analistisin. Şu hisse verilerini yorumla ve hap gibi kısa bir özet çıkar: {veriler}"
        if model:
            rapor = model.generate_content(prompt).text
        else:
            rapor = f"Sistem aktif. Güncel Teknik Verileriniz:\n{veriler}"
        telegram_mesaj_gonder(f"📊 *PİYASA RAPORU*\n\n{rapor}")
    except Exception as e:
        telegram_mesaj_gonder(f"📊 *ANLIK DURUM*\n\nVeriler alındı ancak rapor üretilemedi: {veriler}")

# ==========================================
# ⚙️ TELEGRAM KOMUT DİNLEYİCİSİ
# ==========================================
def telegram_komutlari_dinle():
    global HAFIZA
    offset = HAFIZA.get("last_update_id", 0) + 1
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=10"
    try:
        res = requests.get(url, timeout=12).json()
        for u in res.get("result", []):
            HAFIZA["last_update_id"] = u["update_id"]
            if "message" in u and "text" in u["message"]:
                txt = u["message"]["text"]
                
                if txt.startswith("/analiz"):
                    telegram_mesaj_gonder("⏳ Komut alındı reis! Veriler toplanıyor, lütfen bekleyin...")
                    threading.Thread(target=ajani_calistir).start()
    except:
        pass

def run_dummy_server(): 
    try: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 10000))), SimpleHTTPRequestHandler).serve_forever()
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("Bot sorunsuzca başlatıldı reis, Telegram dinleniyor...")
    while True:
        telegram_komutlari_dinle()
        time.sleep(2)
        
