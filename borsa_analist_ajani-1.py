import os
import threading
import time
import json
import requests
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import datetime as dt
from http.server import SimpleHTTPRequestHandler, HTTPServer
from supabase import create_client, Client
def bist_veri_cek(sembol):
    try:
        ticker = yf.Ticker(sembol)
        data = ticker.history(period="1d")
        if not data.empty:
            guncel_fiyat = float(data['Close'].iloc[-1])
            return {"fiyat": f"{guncel_fiyat:.2f}", "fk": "N/A", "pddd": "N/A"}
    except:
        pass
    return {"fiyat": "0.00", "fk": "N/A", "pddd": "N/A"}

def yabanci_veri_cek(sembol):
    ticker = yf.Ticker(sembol)
    for i in range(3):  # 3 kez deneme yap
        try:
            data = ticker.history(period="5d")
            if not data.empty:
                fiyat = float(data['Close'].iloc[-1])
                info = ticker.info
                # Hata ihtimaline karşı .get() kullanıyoruz
                fk = info.get("trailingPE", "N/A")
                pddd = info.get("priceToBook", "N/A")
                return {"fiyat": f"{fiyat:.2f}", "fk": str(fk), "pddd": str(pddd)}
        except:
            time.sleep(1) # Hata olursa 1 saniye bekle ve tekrar dene
    return {"fiyat": "0.00", "fk": "N/A", "pddd": "N/A"}
    
def veri_yonlendirici(sembol):
    return bist_veri_cek(sembol) if ".IS" in sembol else yabanci_veri_cek(sembol)
    
    

# 🛑 MANUEL GÜNCEL VERİ İSTASYONU
# ==========================================
VERI_KUTUSU = {
    "THYAO.IS": {"fk": "3.47", "pddd": "0.47"},
    "TUPRS.IS": {"fk": "11.99", "pddd": "1.22"},
    "SASA.IS":  {"fk": "20.10", "pddd": "3.80"},
    "ASTOR.IS": {"fk": "26.40", "pddd": "5.90"},
    "KCHOL.IS": {"fk": "18.63", "pddd": "0.69"},
    "MRGYO.IS": {"fk": "12.50", "pddd": "0.75"},
    "KRDMB.IS": {"fk": "11.80", "pddd": "1.55"},
    "KONTR.IS": {"fk": "0", "pddd": "0,81"}
}


PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 19, "maliyet": 3.65},   
    "KRDMB.IS": {"lot": 13, "maliyet": 96.35}   
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS", "ASTOR.IS", "KCHOL.IS", "MRGYO.IS", "BTC-USD"]
TEMEL_VERILER_YEDEK = {s: {"fk": "0.00", "pddd": "0.00"} for s in TAKIP_YEDEK}
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AQ.Ab8RN6K_..."

SUPABASE_URL = os.environ.get("SUPABASE_URL") # Girintiyi en sola çek
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # Girintiyi en sola çek
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET_NAME = "ajan_hafizasi"
FILE_NAME = "ajan_hafizasi.json"
genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

def hafizayi_yukle():
    global HAFIZA
    try:
        response = supabase.storage.from_(BUCKET_NAME).download(FILE_NAME)
        HAFIZA = json.loads(response)
        print("✅ Hafıza buluttan yüklendi.")
    except:
        print("⚠️ Bulut hafıza boş, varsayılanlar yükleniyor.")
        HAFIZA = {
            "takip_listesi": TAKIP_YEDEK,
            "portfoy": PORTFOY_YEDEK,
            "temel_veriler": TEMEL_VERILER_YEDEK,
            "tahmin_gunlugu": {},
            "ogrenilen_dersler": [],
            "last_update_id": 0
        }

def hafizayi_kaydet():
    try:
        file_content = json.dumps(HAFIZA, indent=4).encode('utf-8')
        supabase.storage.from_(BUCKET_NAME).upload(
            path=FILE_NAME,
            file=file_content,
            file_options={"content-type": "application/json", "upsert": "true"}
        )
    except Exception as e:
        print(f"⚠️ Supabase kayıt hatası: {e}")

# Sistemi başlat
hafizayi_yukle()

# ==========================================
# 📊 TEK BİR HİSSE İÇİN ANLIK RESMİ VERİ ÇEKİCİ
# ==========================================

def tek_hisse_resmi_veri_cek(sembol):
    try:
        time.sleep(4) # Biraz daha sabır, veri çekme kalitesi artar
        ticker = yf.Ticker(sembol)
        
        # 1. Fiyatı al
        hist = ticker.history(period="1d")
        fiyat = hist['Close'].iloc[-1] if not hist.empty else 0.0
        
        # 2. info kısmına yüklen
        info = ticker.info
        
        # 3. PD/DD için en güncel olanı yakala: 
        # Önce trailingPE/priceToBook, olmazsa bilançodan (balance_sheet) çek
        fk = info.get("trailingPE")
        pddd = info.get("priceToBook")
        
        if pddd is None or pddd == "N/A":
            # Yahoo'nun bazen 'bookValue' verisini info'da tuttuğunu biliyoruz
            book_value = info.get("bookValue")
            if book_value and fiyat > 0:
                pddd = round(fiyat / book_value, 2)
        
        # 4. Hala yoksa, yedek kutudan al (Eskisi bile olsa en güvenli veri bu)
        if pddd is None:
            pddd = VERI_KUTUSU.get(sembol, {}).get("pddd", "N/A")
            
        HAFIZA["temel_veriler"][sembol] = {
            "fiyat": f"{fiyat:.2f}",
            "fk": str(fk) if fk else "N/A",
            "pddd": str(pddd)
        }
        return True
    except Exception as e:
        print(f"HATA ({sembol}): {e}")
        return False
        
def resmi_kaynaktan_temel_veri_guncelle():
    print("🔄 Güvenilir kaynaktan resmi temel rasyolar çekiliyor...")
    guncellenenler = []
    
    # FOR döngüsü 4 boşluk içeride
    for sembol in HAFIZA.get("takip_listesi", []):
        if tek_hisse_resmi_veri_cek(sembol):
            hisse_kodu = sembol.split(".")[0]
            guncellenenler.append(hisse_kodu)
        time.sleep(2)
            
    # IF bloğu FOR ile aynı hizada (4 boşluk)
    if guncellenenler:
        hafizayi_kaydet()
        telegram_mesaj_gonder(f"🔄 *Resmi Temel Veri Güncellemesi Tamamlandı!*\nGece Kontrolü Yapılan Hisseler: {', '.join(guncellenenler)}\nYapay zeka rasyoları %100 güvenli finans havuzundan tazeledi.")
        
    
# ==========================================
# ⚙️ TELEGRAM İLETİŞİM FONKSİYONLARI
# ==========================================
def telegram_mesaj_gonder(mesaj):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX_LEN = 4000  
    if len(mesaj) > MAX_LEN:
        parcalar = [mesaj[i:i+MAX_LEN] for i in range(0, len(mesaj), MAX_LEN)]
        for parca in parcalar:
            telegram_mesaj_gonder(parca)
        return

    payload = {"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "Markdown"}
    try: 
        res = requests.post(url, json=payload, timeout=10).json()
        if not res.get("ok"):
            payload_duz = {"chat_id": CHAT_ID, "text": mesaj}
            requests.post(url, json=payload_duz, timeout=10)
    except Exception as e: 
        print(f"⚠️ Telegram gönderme hatası: {e}")

def telegram_komutlari_dinle():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = HAFIZA.get("last_update_id", 0) + 1
    try:
        response = requests.get(url, params={"offset": offset, "timeout": 20}, timeout=25).json()
        if not response.get("result"): 
            return
        
        for update in response["result"]:
            HAFIZA["update_id"] = update["update_id"]
            HAFIZA["last_update_id"] = update["update_id"]
            hafizayi_kaydet()
            
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            if chat_id != CHAT_ID: 
                continue 
            
            parcalar = text.split()
            if not parcalar: 
                continue
            komut = parcalar[0].lower()
            
            if komut == "/takip_listesi":
                if HAFIZA["takip_listesi"]:
                    liste = "\n".join([f"• `{h}`" for h in HAFIZA["takip_listesi"]])
                    telegram_mesaj_gonder(f"📋 *Güncel Takip Listeniz:*\n\n{liste}")
                else:
                    telegram_mesaj_gonder("📋 Takip listeniz şu an boş.")

            elif komut == "/portfoy_goster":
                if HAFIZA["portfoy"]:
                    mesaj = "💰 *Güncel Portföy Varlıklarınız:*\n\n"
                    for hisse, bilgi in HAFIZA["portfoy"].items():
                        mesaj += f"📌 `{hisse}`\n  - Lot: {bilgi['lot']} | Maliyet: {bilgi['maliyet']:.2f} TL\n"
                    telegram_mesaj_gonder(mesaj)
                else:
                    telegram_mesaj_gonder("💰 Portföyünüzde henüz kayıtlı varlık yok.")

            elif komut == "/analiz":
                telegram_mesaj_gonder("🔄 Anlık talep alındı. Küresel gündem, indikatörler, geçmiş tecrübeler ve resmi temel veriler birleştiriliyor...")
                ajani_calistir(rapor_tipi="KULLANICI TALEBİ ANLIK FİNANSAL ANALİZ")

            elif komut == "/takip_ekle" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse not in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].append(hisse)
                    telegram_mesaj_gonder(f"⏳ `{hisse}` takip listesine alınıyor...")
                    tek_hisse_resmi_veri_cek(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{hisse}` başarıyla eklendi!")
                else:
                    telegram_mesaj_gonder(f"ℹ️ `{hisse}` zaten takip listenizde mevcut.")
                    
            elif komut == "/takip_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].remove(hisse)
                    if hisse in HAFIZA["portfoy"]: del HAFIZA["portfoy"][hisse]
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"❌ `{hisse}` takip listesinden çıkarıldı.")

            elif komut == "/hafiza_temizle":
                HAFIZA["ogrenilen_dersler"] = []
                HAFIZA["tahmin_gunlugu"] = {}
                hafizayi_kaydet()
                telegram_mesaj_gonder("🧠 Yapay zeka tecrübe hafızası sıfırlandı.")
    except Exception as e:
        print(f"Komut dinleme hatası: {e}")

# ==========================================
# 📊 BİLİMSEL VERİ ANALİZİ MOTORU
# ==========================================
def dunya_gundemini_cek():
    # URL'yi daha güvenli bir Google News arama linkiyle değiştirdik
    url = "https://news.google.com/rss/search?q=global+finance+market&hl=en-US&gl=US&ceid=US:en"
    haberler = []
    try:
        # User-Agent ekleyerek bot engellemesini aşabiliriz
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5) # Timeout'u 5 saniyeye düşürdük
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, features="xml")
            items = soup.find_all('item')
            for item in items[:5]: # Hızlıca ilk 5 haberi al
                haberler.append(f"- {item.title.text}")
        else:
            return "Piyasa haberleri şu an alınamadı (Hata kodu: " + str(response.status_code) + ")"
    except Exception as e: 
        print(f"⚠️ Haber çekme hatası: {e}")
        return "Küresel haber akışı şu an geçici olarak kapalı."
    
    return "\n".join(haberler) if haberler else "Piyasalar sakin."
    
def finansal_veri_topla(sembol):
    print(f"🔍 {sembol} verisi çekiliyor...")
def finansal_veri_topla(sembol):
    print(f"DEBUG: {sembol} analizi başlatılıyor...")
    try:
        # Ticker objesini oluştur ama henüz veri çekme
        ticker = yf.Ticker(sembol)
        
        # history verisi donuyorsa, burada timeout kontrolü yapacağız
        # yfinance'in kendi timeout'u bazen yetersiz kalır, bu yüzden basit bir deneme yapıyoruz
        df = ticker.history(period="3mo", interval="1d")
        
        if df.empty:
            print(f"DEBUG: {sembol} boş veri döndü.")
            return {"fiyat": "0.00", "rsi": "N/A", "macd": "N/A", "fk": "N/A", "pddd": "N/A"}

        # HESAPLAMALAR
        close = df['Close'].iloc[-1]
        rsi = ta.momentum.rsi(df['Close'], window=14).iloc[-1]
        macd_df = ta.trend.MACD(df['Close'])
        macd = macd_df.macd().iloc[-1]
        signal = macd_df.macd_signal().iloc[-1]
        
        print(f"DEBUG: {sembol} analiz edildi.")
        return {
            "fiyat": f"{float(close):.2f}",
            "rsi": f"{float(rsi):.2f}",
            "macd": "AL" if macd > signal else "SAT",
            "fk": "N/A", "pddd": "N/A"
        }
    except Exception as e:
        print(f"DEBUG: HATA {sembol} -> {str(e)}")
        return {"fiyat": "0.00", "rsi": "N/A", "macd": "N/A", "fk": "N/A", "pddd": "N/A"}
        
# ==========================================
# 🧠 ÖZ-YANSITMALI VE ÖĞRENEN ANALİZ MOTORU (GÜNCELLENMİŞ)
# ==========================================
def ajani_calistir(rapor_tipi="GÜNLÜK_ANALİZ"):
    print(f"🔄 {rapor_tipi} başlıyor...")
    telegram_mesaj_gonder(f"🔄 *{rapor_tipi}* başlıyor. Veriler toplanıyor...")
    
    genel_haber = dunya_gundemini_cek()
    print("📰 Haberler çekildi.")
    
    toplu_metin = ""
    
    # 1. Verileri topla
    for s in HAFIZA["takip_listesi"]:
        print(f"⏳ İşleniyor: {s}")
        # Eğer bir önceki adımda 20 saniyeden uzun sürerse buraya gelmiyor bile
        v = finansal_veri_topla(s) 
        
        # Eğer fiyat 0.00 ise veri gelmemiştir, bir sonraki hisseye geç
        if v["fiyat"] == "0.00":
            print(f"⚠️ {s} verisi alınamadı, atlanıyor.")
            continue 
            
        toplu_metin += f"\n- {s}: Fiyat:{v['fiyat']}, RSI:{v['rsi']}, MACD:{v['macd']}"
            
    print("📊 Veriler toplandı, AI raporu üretiyor...")
 
    # 2. Geçmiş dersi al
    ders = HAFIZA["performans_log"][-1] if HAFIZA["performans_log"] else "Henüz ders çıkarılmadı."

    # 3. Prompt oluştur
    prompt = f"""
    Sen profesyonel bir fon yöneticisisin. 
    GEÇEN HAFTAKİ DERSİN: {ders}
    
    Piyasa verileri: {toplu_metin}
    Küresel Haber: {genel_haber}

    GÖREV:
    - Aşağıdaki formatta bir tablo oluştur:
    | HİSSE | FİYAT | RSI | MACD | KARAR | STRATEJİ |
    - KARAR sütununa sadece AL, SAT, TUT, BEKLE yaz.
    - STRATEJİ sütununa geçen haftaki dersini dikkate alarak 3-4 kelimelik not yaz.
    """
    
    # 4. Raporu üret
    cevap = model.generate_content(prompt).text
    telegram_mesaj_gonder(cevap)
    
    # 5. Gelecek hafta için ders çıkar ve hafızaya ekle
    yeni_ders_prompt = f"Bu rapordan bir sonraki hafta için stratejik bir ders çıkar: {cevap}"
    yeni_ders = model.generate_content(yeni_ders_prompt).text
    HAFIZA["performans_log"].append(yeni_ders)
    hafizayi_kaydet()
    def ajan_kendi_kendini_egit():
    # 1. Tarih hesaplamalarını netleştir
      su_an_utc = dt.datetime.utcnow()
      tr_saati = su_an_utc + dt.timedelta(hours=3)
      yedi_gun_once = (tr_saati - dt.timedelta(days=7)).strftime('%Y-%m-%d')
    
    # 2. Geçmiş verinin varlığını kontrol et
    if yedi_gun_once not in HAFIZA.get("tahmin_gunlugu", {}):
        print(f"⚠️ Eğitim için {yedi_gun_once} tarihli kayıt bulunamadı.")
        return

    gecmis_data = HAFIZA["tahmin_gunlugu"][yedi_gun_once]
    bugunku_fiyatlar = {}
    
    # 3. Güncel piyasa verisini çek
    for sembol in HAFIZA.get("takip_listesi", []):
        veri = finansal_veri_topla(sembol)
        bugunku_fiyatlar[sembol] = veri["fiyat"]
        
    # 4. Analiz için prompt'u hazırla
    prompt = f"""
    Sen kendi kararlarını denetleyen bir finansal stratejistsin.
    Geçmiş tahminlerini şu anki piyasa gerçekleriyle karşılaştır.
    
    - 7 Gün Önceki Piyasa Durumu: {gecmis_data.get('piyasa_durumu', 'Veri yok')}
    - 7 Gün Önceki Yorumun: {gecmis_data.get('ai_raporu_kesiti', 'Veri yok')}
    - Bugünün Gerçek Fiyatları: {json.dumps(bugunku_fiyatlar)}
    
    Görevin:
    1. Yönünü (Yükselecek/Düşecek) yanlış bildiğin hisseleri tespit et.
    2. Neden yanıldığını bul (İndikatörler mi hatalıydı, yoksa küresel haberler mi?)
    3. 'ÖĞRENİLEN DERS: ...' şeklinde tek bir kural cümlesi yaz.
    """
    
    try:
        # 5. Gemini'dan dersi al
        response = model.generate_content(prompt)
        ders = response.text.strip()
        
        # 6. Hafızaya kaydet
        HAFIZA["ogrenilen_dersler"].append({
            "tarih": tr_saati.strftime('%Y-%m-%d %H:%M'),
            "ders": ders
        })
        hafizayi_kaydet()
        
        telegram_mesaj_gonder(f"🧠 **AJAN ÖZ-EĞİTİM RAPORU** 🧠\n\n{ders}")
    except Exception as e:
        print(f"Eğitim döngüsü hatası: {e}")
        
# ==========================================
# 🔄 ANA DÖNGÜ (DÜZELTİLDİ VE TEK ÇATI ALTINA ALINDI)
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"==> Kukla sunucu aktif.")
    server.serve_forever()

if __name__ == "__main__":
    print("🚀 Akıllı Borsa Ajanı başlatılıyor...")
    
    # Sunucuyu başlat
    try:
        threading.Thread(target=run_dummy_server, daemon=True).start()
    except Exception as e:
        print(f"❌ Sunucu hatası: {e}")

    # Ana döngüyü if __name__ bloğunun içine aldık
    while True:
        try:
            # 1. Komutları dinle
            telegram_komutlari_dinle()
            
            # 2. Zamanı hesapla
            su_an_utc = dt.datetime.utcnow()
            tr_saati = su_an_utc + dt.timedelta(hours=3)
            saat_dakika = tr_saati.strftime("%H:%M")
            saniye = int(tr_saati.strftime("%S"))
            
            # 3. Tetikleme mekanizması
            if saniye < 15:
                if saat_dakika in ["11:00", "18:30", "23:30"]:
                    print(f"⏰ Tetiklendi: {saat_dakika}")
                    if saat_dakika == "11:00":
                        ajani_calistir("SABAH AÇILIŞ")
                    elif saat_dakika == "18:30":
                        ajani_calistir("AKŞAM KAPANIŞ")
                    elif saat_dakika == "23:30":
                        resmi_kaynaktan_temel_veri_guncelle()
                        ajan_kendi_kendini_egit()
                    time.sleep(65) 
            
            time.sleep(2) # CPU'yu yormamak için
            
        except Exception as e:
            print(f"❌ Ana döngü hatası: {e}")
            time.sleep(10) # Hata olursa 10 saniye bekle ve devam et
            


        
        
