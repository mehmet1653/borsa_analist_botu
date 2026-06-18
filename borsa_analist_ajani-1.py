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
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import datetime as dt
from supabase import create_client, Client

# 🛑 MANUEL GÜNCEL VERİ İSTASYONU
# ==========================================
VERI_KUTUSU = {
    "THYAO.IS": {"fk": "3.47", "pddd": "0.47"},
    "TUPRS.IS": {"fk": "6.20", "pddd": "3.40"},
    "SASA.IS":  {"fk": "22.40", "pddd": "4.10"},
    "ASTOR.IS": {"fk": "36.39", "pddd": "8.59"},
    "KCHOL.IS": {"fk": "5.50", "pddd": "1.80"},
    "MRGYO.IS": {"fk": "11.10", "pddd": "0.85"},
    "KRDMB.IS": {"fk": "14.20", "pddd": "2.15"}
}


PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 19, "maliyet": 3.65},   
    "KRDMB.IS": {"lot": 13, "maliyet": 96.35}   
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS", "ASTOR.IS", "KCHOL.IS", "MRGYO.IS", "BTC-USD"]

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
    ticker = yf.Ticker(sembol)
    info = ticker.info
    fk = info.get("trailingPE")
    
    # Eğer Yahoo PE vermezse, VERI_KUTUSU'ndakini kullan
    if not fk and sembol in VERI_KUTUSU:
        fk = VERI_KUTUSU[sembol]["fk"]
        pddd = VERI_KUTUSU[sembol]["pddd"]
    else:
        pddd = info.get("priceToBook")
    
    # Şimdi HAFIZA'ya yaz...
        
        HAFIZA["temel_veriler"][sembol] = {
            "fk": data["fk"], "pddd": data["pddd"],
            "ihracat": "-", "ozsermaye_kar": "-"
        }
        return True
    
    # 2. Öncelik: İnternetten çek ve hafızaya kaydet
    ticker = yf.Ticker(sembol)
    try:
        info = ticker.info
        fk = info.get("trailingPE")
        pddd = info.get("priceToBook")
        
        if fk and pddd:
            HAFIZA["temel_veriler"][sembol] = {
                "fk": f"{float(fk):.2f}", 
                "pddd": f"{float(pddd):.2f}",
                "ihracat": "-", "ozsermaye_kar": "-"
            }
            hafizayi_kaydet() # Artık hafızaya kalıcı yazıyor!
            return True
    except:
        return False

    
 def resmi_kaynaktan_temel_veri_guncelle():
        
    print("🔄 Güvenilir kaynaktan resmi temel rasyolar çekiliyor...")
    guncellenenler = []
    
    # Doğru girintileme burada başlıyor
    for sembol in HAFIZA.get("takip_listesi", []):
        if tek_hisse_resmi_veri_cek(sembol):
            hisse_kodu = sembol.split(".")[0]
            guncellenenler.append(hisse_kodu)
        time.sleep(1)
            
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
    url = "https://news.google.com/rss/search?q=finance+war+geopolitics+fed+inflation&hl=en-US&gl=US&ceid=US:en"
    haberler = []
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, features="xml")
        for item in soup.find_all('item')[:12]:
            haberler.append(f"- {item.title.text}")
    except: 
        return "Haber akışı alınamadı."
    return "\n".join(haberler)

def finansal_veri_topla(sembol):
    # Eğer son fiyatlar hafızası yoksa başlat
    if "son_fiyatlar" not in HAFIZA: HAFIZA["son_fiyatlar"] = {}
    
    # 3 kere deneme döngüsü
    for deneme in range(3):
        try:
            df = yf.download(sembol, period="1y", progress=False)
            if df.empty or 'Close' not in df.columns:
                time.sleep(1)
                continue
                
            # Veri düzenleme
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            df.columns = [str(col).strip() for col in df.columns]
            
            guncel_fiyat = float(df['Close'].iloc[-1])
            HAFIZA["son_fiyatlar"][sembol] = guncel_fiyat # Hafızaya kaydet
            
            # İndikatörler
            close_series = df['Close'].astype(float)
            df['RSI'] = ta.momentum.rsi(close_series, window=14)
            df['SMA_50'] = ta.trend.sma_indicator(close_series, window=50)
            df['MACD'] = ta.trend.macd(close_series)
            df['MACD_Signal'] = ta.trend.macd_signal(close_series)
            df['ADX'] = ta.trend.adx(df['High'].squeeze(), df['Low'].squeeze(), close_series, window=14)
            
            # Portföy notu
            portfoy_notu = "YOK"
            if sembol in HAFIZA["portfoy"]:
                p = HAFIZA["portfoy"][sembol]
                kar_zarar = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
                portfoy_notu = f"Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f}, Kâr/Zarar: %{kar_zarar:.2f}"

            # Analiz verileri
            temel = HAFIZA.get("temel_veriler", {}).get(sembol, {"fk": "-", "pddd": "-", "ihracat": "-", "ozsermaye_kar": "-"})
            
            return {
                "fiyat": f"{guncel_fiyat:.2f}",
                "rsi": f"{df['RSI'].iloc[-1]:.2f}",
                "sma_50": f"{df['SMA_50'].iloc[-1]:.2f}",
                "macd": "AL" if df['MACD'].iloc[-1] > df['MACD_Signal'].iloc[-1] else "SAT",
                "adx": f"{df['ADX'].iloc[-1]:.2f}",
                "fk": temel.get("fk", "-"),
                "pddd": temel.get("pddd", "-"),
                "portfoy_durumu": portfoy_notu
            }
        except:
            time.sleep(1)
            
    # Eğer internetten çekemezsek hafızadaki son fiyatı dön
    son_fiyat = HAFIZA["son_fiyatlar"].get(sembol, 0)
    return {"fiyat": f"{son_fiyat:.2f}", "rsi": "N/A", "fk": "-", "pddd": "-", "portfoy_durumu": "YOK"}
    



# ==========================================
# 🧠 ÖZ-YANSITMALI VE ÖĞRENEN ANALİZ MOTORU (GÜNCELLENMİŞ)
# ==========================================
def ajani_calistir(rapor_tipi="GÜNLÜK DEĞERLENDİRME"):
    anlik_tahmin_verisi = {}
    bugun_str = dt.datetime.now().strftime('%Y-%m-%d')

    piyasa_ozeti = ""
    
    for sembol in HAFIZA["takip_listesi"]:
        veri = finansal_veri_topla(sembol)
        if veri:
            # Buraya 'anlik_tahmin_verisi'ni dolduracak kodları ekliyoruz
            anlik_tahmin_verisi[sembol] = veri 
            
            # Raporu oluştururken artık bu sözlüğü kullanabilirsin
            piyasa_ozeti += f"\n📌 {sembol} | Fiyat: {veri.get('fiyat')} | RSI: {veri.get('rsi')}"
        time.sleep(1)

    tecrubeler_metni = "\n🧠 ÖĞRENİLEN DERSLER (SENSEİ KURALLARI):\n"
    if HAFIZA.get("ogrenilen_dersler"):
        for d in HAFIZA["ogrenilen_dersler"][-5:]: 
            tecrubeler_metni += f"- {d['ders']}\n"
    else:
        tecrubeler_metni += "- Henüz ders çıkarılmadı, ilk analizler yapılıyor.\n"

    # Prompt'u IF bloğunun dışına çıkardım ve daha net hale getirdim
    prompt = f"""
    Sen rasyonel, geçmiş hatalarından ders çıkaran profesyonel bir finans yapay zekasısın.
    
    RAPOR TÜRÜ: {rapor_tipi}
    GÜNCEL PİYASA VERİLERİ: {piyasa_ozeti}
    {tecrubeler_metni}
    
    GÖREVİN:
    Teknik verileri (Fiyat, RSI, MACD) ve temel verileri (F/K, PD/DD) birleştirerek yorumla.
    Her hisse için tam olarak şu formatı kullan:
    
    ### [HİSSE ADI]
    * GÜNCEL FİYAT: [Fiyat]
    * TEMEL RASYOLAR: F/K: [FK], PD/DD: [PD/DD]
    * GEÇMİŞ ANALİZİM: [Önceki günlerden gelen analiz]
    * YENİ ÖNGÖRÜ: [OLUMLU/OLUMSUZ/TEMKİNLİ]
    * Yorum: [Teknik ve temel verileri harmanlayan keskin analiz]
    """
    
    try: 
        ai_raporu = model.generate_content(prompt).text
        
        HAFIZA["tahmin_gunlugu"][bugun_str] = {
            "piyasa_durumu": anlik_tahmin_verisi, 
            "ai_raporu": ai_raporu, 
            "ai_raporu_kesiti": ai_raporu[:500] 
        }

        hafizayi_kaydet()
        telegram_mesaj_gonder(f"📊 **AKILLI ANALİZ RAPORU**\n\n{ai_raporu}")
    except Exception as e: 
        telegram_mesaj_gonder(f"🤖 Yapay zeka sentez hatası: {e}")

def hisse_haber_kaziyici(sembol):
    hisse_kodu = sembol.split(".")[0].lower()
    # Investing.com'dan haber çekiyoruz
    url = f"https://tr.investing.com/equities/{hisse_kodu}-news"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Haber başlıklarını bul
        haberler = [h.text.strip() for h in soup.select('.articleItem .title')[:3]]
        if not haberler: return "Güncel haber bulunamadı."
        return ". ".join(haberler)
    except:
        return "Haber kaynağına ulaşılamadı."
        
        

# ... (Kodun geri kalanını [ajan_kendi_kendini_egit ve sonrası] aynen bırak)

def ajan_kendi_kendini_egit():
    print("🧠 Yapay zeka öz-yansıtma ve eğitim modülü çalışıyor...")
    su_an_utc = dt.datetime.utcnow()
    tr_saati = su_an_utc + dt.timedelta(hours=3)
    
    # 7 gün önceki tarihi bul
    gecmis_tarih = (tr_saati - timedelta(days=7)).strftime('%Y-%m-%d')
    
    if gecmis_tarih not in HAFIZA["tahmin_gunlugu"]:
        print("ℹ️ Geriye dönük değerlendirme için yeterli veri henüz yok.")
        return

    gecmis_data = HAFIZA["tahmin_gunlugu"][gecmis_tarih]
    bugunku_fiyatlar = {}
    
    for sembol in gecmis_data["piyasa_durumu"].keys():
        veri = finansal_veri_topla(sembol)
        if veri:
            bugunku_fiyatlar[sembol] = veri["fiyat"]
            
    prompt = f"""
    Sen kendi kararlarını denetleyen ve kendi kendini eğiten finansal bir yapay zekasın.
    7 Gün Önceki Tahmin Verilerin ve Fiyatların: {json.dumps(gecmis_data['piyasa_durumu'])}
    Bugün Gerçekleşen Güncel Fiyatlar: {json.dumps(bugunku_fiyatlar)}
    7 Gün Önce Yaptığın Yorum Özeti: {gecmis_data['ai_raporu_kesiti']}
    
    Görevin: Geçmiş tahminlerini gerçek piyasa sonuçlarıyla acımasızca karşılaştır. 
    Özellikle yönünü (Yükseliş/Düşüş/Yatay) yanlış bildiğin enstrümanları tespit et. 
    Hangi indikatörü (RSI, MACD, MA50) yanlış yorumladığını veya neyi ıskaladığını çöz.
    Bir sonraki analizlerinde aynı hatayı yapmamak için çıkardığın dersi 'ÖĞRENİLEN DERS: ...' şeklinde tek bir kural cümlesi olarak yaz.
    """
    
    try:
        ders = model.generate_content(prompt).text.strip()
        HAFIZA["ogrenilen_dersler"].append({
            "tarih": tr_saati.strftime('%Y-%m-%d %H:%M'),
            "ders": ders
        })
        hafizayi_kaydet()
        
        telegram_mesaj_gonder(f"🧠 **AJAN GERİ BİLDİRİM VE ÖZ-EĞİTİM RAPORU** 🧠\n\nGeçmiş tahminlerimi denetledim ve şu stratejik kuralı hafızama kazıdım:\n\n`{ders}`\n\n🤖 *Sistem Durumu:* Ajan hatalarından ders çıkararak bir basamak daha akıllandı.")
    except Exception as e:
        print(f"Eğitim döngüsü hatası: {e}")
        
def hisse_haber_analizi_yap(sembol):
    # 1. Haberleri kazı
    haber_metni = hisse_haber_kaziyici(sembol)
    if "bulunamadı" in haber_metni: return "Haber akışı yok."
    
    # 2. Gemini'ye analiz ettir
    prompt = f"{sembol} hissesi için şu haber başlıkları var: '{haber_metni}'. Bu hisse için kısa bir olumlu/olumsuz/nötr analiz yap."
    try:
        response = model.generate_content(prompt)
        return response.text.replace("\n", " ")
    except:
        return "Analiz yapılamadı."
        
# ==========================================
# 🔄 ANA DÖNGÜ (7/24 DİNLEME VE RAPORLAMA)
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"==> Kukla sunucu aktif.")
    server.serve_forever()

if __name__ == "__main__":
    # Bu satırdan itibaren her şey 4 boşluk içeride olmalı
    print("🚀 Akıllı Borsa Ajanı başlatılıyor...")
    
    try:
        threading.Thread(target=run_dummy_server, daemon=True).start()
        print("✅ Kukla sunucu başlatıldı.")
    except Exception as e:
        print(f"❌ Sunucu hatası: {e}")

    while True:
        try:
            telegram_komutlari_dinle()
            
            su_an_utc = dt.datetime.utcnow()
            tr_saati = su_an_utc + dt.timedelta(hours=3)
            saat_dakika = tr_saati.strftime("%H:%M")
            saniye = tr_saati.strftime("%S")
            
            if saniye in ["00", "01", "02"]:
                if saat_dakika == "11:00":
                    ajani_calistir(rapor_tipi="SABAH AÇILIŞ VE PORTFÖY RİSK KONTROLÜ")
                    time.sleep(5)
                elif saat_dakika == "18:30":
                    ajani_calistir(rapor_tipi="AKŞAM KAPANIŞ VE MALİYET DEĞERLENDİRMESİ")
                    time.sleep(5)
                elif saat_dakika == "23:30":
                    resmi_kaynaktan_temel_veri_guncelle()
                    ajan_kendi_kendini_egit()
                    time.sleep(5)
        except Exception as e:
            print(f"❌ Ana döngü hatası: {e}")
            time.sleep(10)
        
        time.sleep(1)
        
