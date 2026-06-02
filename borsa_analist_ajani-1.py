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
from datetime import datetime
import datetime as dt

# ==========================================
# 🛠️ MEHMET REİS BULUT VE HAFIZA YEDEK AYARLARI
# ==========================================
PORTFOY_YEDEK = {
    "SASA.IS": {"lot": 19, "maliyet": 3.65},   
    "KRDMB.IS": {"lot": 13, "maliyet": 96.35}   
}
TAKIP_YEDEK = ["THYAO.IS", "TUPRS.IS", "USDTRY=X", "GC=F", "SASA.IS", "KRDMB.IS", "ASTOR.IS", "KCHOL.IS", "MRGYO.IS"]

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    GEMINI_API_KEY = "AQ.Ab8RN6K_wraDxTNfR-qaqeJHO40gdpJLWp3o8jWYnR3IYgi7PA"

genai.configure(api_key=str(GEMINI_API_KEY).strip())
model = genai.GenerativeModel('gemini-2.5-flash')

DATA_FILE = "ajan_hafizasi.json"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        try:
            HAFIZA = json.load(f)
        except:
            HAFIZA = {"takip_listesi": TAKIP_YEDEK, "portfoy": PORTFOY_YEDEK}
else:
    HAFIZA = {
        "takip_listesi": TAKIP_YEDEK,
        "portfoy": PORTFOY_YEDEK
    }

def hafizayi_kaydet():
    with open(DATA_FILE, "w") as f:
        json.dump(HAFIZA, f, indent=4)

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
        if not response.get("result"): return
        
        for update in response["result"]:
            HAFIZA["last_update_id"] = update["update_id"]
            hafizayi_kaydet()
            
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            if chat_id != CHAT_ID: continue 
            
            parcalar = text.split()
            if not parcalar: continue
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
                telegram_mesaj_gonder("🔄 Anlık talep alındı. Temel istatistikler, küresel gündem ve indikatörler harmanlanıyor, lütfen bekleyin...")
                ajani_calistir(rapor_tipi="KULLANICI TALEBİ ANLIK FİNANSAL ANALİZ")

            elif komut == "/takip_ekle" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse not in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].append(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"✅ `{hisse}` takip listesine eklendi.")
                    
            elif komut == "/takip_cikar" and len(parcalar) > 1:
                hisse = parcalar[1].upper()
                if hisse in HAFIZA["takip_listesi"]:
                    HAFIZA["takip_listesi"].remove(hisse)
                    if hisse in HAFIZA["portfoy"]: del HAFIZA["portfoy"][hisse]
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"❌ `{hisse}` takip listesinden ve portföyden çıkarıldı.")
                    
            elif komut == "/portfoy_ekle" and len(parcalar) > 3:
                hisse = parcalar[1].upper()
                try:
                    lot = int(parcalar[2])
                    maliyet = float(parcalar[3])
                    HAFIZA["portfoy"][hisse] = {"lot": lot, "maliyet": maliyet}
                    if hisse not in HAFIZA["takip_listesi"]: HAFIZA["takip_listesi"].append(hisse)
                    hafizayi_kaydet()
                    telegram_mesaj_gonder(f"💰 Portföy Güncellendi:\n`{hisse}`: {lot} Lot | Maliyet: {maliyet} TL.")
                except:
                    telegram_mesaj_gonder("⚠️ Hatalı format. Örnek: `/portfoy_ekle TUPRS.IS 100 165.50`")
                    
            elif komut == "/yardim":
                telegram_mesaj_gonder("🤖 *Ajan Komutları:*\n\n"
                                      "🚀 `/analiz` - Saatleri beklemeden anlık yapay zeka raporu üretir.\n"
                                      "🔍 `/takip_listesi` - Tüm takip listenizi listeler.\n"
                                      "💰 `/portfoy_goster` - Elinizdeki varlıkları listeler.\n"
                                      "➕ `/takip_ekle HISSE.IS` - Listeye yeni hisse ekler.\n"
                                      "➖ `/takip_cikar HISSE.IS` - Listeden hisse siler.\n"
                                      "👑 `/portfoy_ekle HISSE.IS LOT MALİYET` - Portföye ekleme yapar.")
    except Exception as e:
        print(f"Komut dinleme hatası: {e}")

# ==========================================
# 📊 VERİ VE İSTATİSTİK TOPLAMA MOTORU
# ==========================================
def dunya_gundemini_cek():
    url = "https://news.google.com/rss/search?q=finance+war+geopolitics+fed+inflation&hl=en-US&gl=US&ceid=US:en"
    haberler = []
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, features="xml")
        for item in soup.find_all('item')[:12]:
            haberler.append(f"- {item.title.text}")
    except: return "Haber akışı alınamadı."
    return "\n".join(haberler)

def finansal_veri_topla(sembol):
    try:
        df = yf.download(sembol, period="1y", progress=False)
        if df.empty: return None
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        df.columns = [str(col).strip() for col in df.columns]
        
        if 'Close' not in df.columns or len(df) < 50: return None
        
        guncel_fiyat = float(df['Close'].iloc[-1])
        close_series = df['Close'].astype(float)
        
        # Teknik İndikatörler
        df['RSI'] = ta.momentum.rsi(close_series, window=14)
        df['SMA_50'] = ta.trend.sma_indicator(close_series, window=50)
        df['SMA_200'] = ta.trend.sma_indicator(close_series, window=200)
        df['MACD'] = ta.trend.macd(close_series)
        df['MACD_Signal'] = ta.trend.macd_signal(close_series)
        df['ADX'] = ta.trend.adx(df['High'].squeeze(), df['Low'].squeeze(), close_series, window=14)
        
        # Temel Analiz İstatisikleri (Midas Verileri)
        ticker = yf.Ticker(sembol)
        info = {}
        try: info = ticker.info
        except: pass
        
        # Ekran görüntülerindeki Midas rasyolarını güvenli şekilde çekiyoruz
        fk = info.get('trailingPE', 'Veri Yok')
        pddd = info.get('priceToBook', 'Veri Yok')
        favok = info.get('ebitda', 'Veri Yok')
        ozsermaye_karliligi = info.get('returnOnEquity', 'Veri Yok')
        cari_oran = info.get('currentRatio', 'Veri Yok')
        brut_marj = info.get('grossMargins', 'Veri Yok')
        net_marj = info.get('profitMargins', 'Veri Yok')
        
        # Temel verileri formatlayalım
        if favok != 'Veri Yok': favok = f"{favok / 1e9:.2f} Milyar TL/USD"
        if ozsermaye_karliligi != 'Veri Yok': ozsermaye_karliligi = f"%{ozsermaye_karliligi * 100:.2f}"
        if brut_marj != 'Veri Yok': brut_marj = f"%{brut_marj * 100:.2f}"
        if net_marj != 'Veri Yok': net_marj = f"%{net_marj * 100:.2f}"
        
        portfoy_notu = "YOK"
        if sembol in HAFIZA["portfoy"]:
            p = HAFIZA["portfoy"][sembol]
            kar_zarar = ((guncel_fiyat - p['maliyet']) / p['maliyet']) * 100
            portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f}, Güncel Kâr/Zarar: %{kar_zarar:.2f}"

        macd_val = df['MACD'].iloc[-1]
        macd_sig = df['MACD_Signal'].iloc[-1]
        macd_durum = "AL SİNYALİ" if macd_val > macd_sig else "SAT SİNYALİ"
        adx_val = df['ADX'].iloc[-1]
        adx_durum = "GÜÇLÜ TREND" if adx_val > 25 else "ZAYIF TREND / YATAY"

        return {
            "fiyat": guncel_fiyat,
            "rsi": f"{df['RSI'].iloc[-1]:.2f}",
            "sma_50": f"{df['SMA_50'].iloc[-1]:.2f}",
            "sma_200": f"{df['SMA_200'].iloc[-1]:.2f}",
            "macd": f"{macd_durum} (MACD: {macd_val:.2f}, Sinyal: {macd_sig:.2f})",
            "adx": f"{adx_durum} (ADX Değeri: {adx_val:.2f})",
            "fk": fk,
            "pddd": pddd,
            "favok": favok,
            "ozsermaye_karliligi": ozsermaye_karliligi,
            "cari_oran": cari_oran,
            "brut_marj": brut_marj,
            "net_marj": net_marj,
            "portfoy_durumu": portfoy_notu
        }
    except Exception as e:
        print(f"⚠️ {sembol} veri toplama hatası: {e}")
        return None

def ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi):
    prompt = f"""
    Sen finans biliminin kurallarına körü körüne bağlı, profesyonel bir kıdemli portföy yöneticisi ve finans yapay zeka ajanısın.
    
    RAPOR TÜRÜ: {rapor_tipi}
    KÜRESEL GÜNDEM HABERLERİ: {gundem}
    ŞİRKETLERİN TEMEL-TEKNİK VE PORTFÖY ÖZETLERİ: {piyasa_ozeti}
    
    ⚠️ KESİN KURALLAR (BU KURALLARA MİLİMETRİK UYULACAK):
    1. ASLA GEREKSİZ UZUN METİNLER YAZMA! Sade, askeri nizamda ve scannable (gözle taranabilir) başlıklar kullan.
    2. Her enstrümanı kendi başlığı altında incele: Güncel Fiyat, RSI, MACD ve ADX durumunu yaz.
    3. Hemen altına şirketin temel rasyolarını (F/K, PD/DD, Özsermaye Kârlılığı, FAVÖK ve Cari Oran) değerlendirerek şirketin finansal sağlığını 1 cümleyle yorumla.
    4. HİBRİT TAHMİN MODÜLÜ (1 HAFTALIK ÖNGÖRÜ): Şirketin teknik trendini, temel finansal rasyolarını (borçluluk/kârlılık) ve "KÜRESEL GÜNDEM" başlıklarını birbiriyle evlendir. Eğer teknik yön güçlüyse, temel veriler şirketi destekliyorsa ve küresel krizler sektörü vurmuyorsa rasyonel bir gerekçe sunarak "📌 1 HAFTALIK ÖNGÖRÜ: ..." şeklinde nokta atışı kısa vadeli yön projeksiyonu yap. 
    5. Kullanıcının elindeki hisselerin kâr/zarar durumlarına göre cüzdan risk analizi uyarısı ekle.
    6. Tamamen Türkçe ve profesyonel bir üslup kullan.
    """
    try: 
        return model.generate_content(prompt).text
    except Exception as e: 
        print(f"🔄 Birincil model hatası, yedek çağrılıyor... Hata: {e}")
        try:
            alternatif_model = genai.GenerativeModel('gemini-2.5-flash')
            return alternatif_model.generate_content(prompt).text
        except Exception as ex:
            return f"🤖 Yapay zeka bağlantı hatası: {ex}"

def ajani_calistir(rapor_tipi="GÜNLÜK DEĞERLENDİRME"):
    gundem = dunya_gundemini_cek()
    piyasa_ozeti = ""
    
    for sembol in HAFIZA["takip_listesi"]:
        veri = finansal_veri_topla(sembol)
        if veri:
            piyasa_ozeti += f"\n📌 {sembol}\n" \
                            f"  - Fiyat: {veri['fiyat']:.2f} | RSI: {veri['rsi']}\n" \
                            f"  - MA50: {veri['sma_50']} | MA200: {veri['sma_200']}\n" \
                            f"  - MACD: {veri['macd']} | Trend Gücü: {veri['adx']}\n" \
                            f"  - Temel İstatistikler -> F/K: {veri['fk']} | PD/DD: {veri['pddd']} | FAVÖK: {veri['favok']} | Özsermaye Kârlılığı: {veri['ozsermaye_karliligi']} | Cari Oran: {veri['cari_oran']} | Brüt/Net Marj: {veri['brut_marj']}/{veri['net_marj']}\n" \
                            f"  - [YATIRIM DURUMU]: {veri['portfoy_durumu']}\n"
        else:
            portfoy_notu = "TAKİP LİSTESİNDE"
            if sembol in HAFIZA["portfoy"]:
                p = HAFIZA["portfoy"][sembol]
                portfoy_notu = f"KULLANICININ ELİNDE VAR! Lot: {p['lot']}, Maliyet: {p['maliyet']:.2f} TL (Canlı fiyat çekilemedi)"
            
            piyasa_ozeti += f"\n📌 {sembol}\n  - Fiyat/İndikatör: Veri çekilemedi.\n  - [YATIRIM DURUMU]: {portfoy_notu}\n"
        time.sleep(2) 

    ai_raporu = ajana_sentez_yaptir(gundem, piyasa_ozeti, rapor_tipi)
    
    su_an_utc = dt.datetime.utcnow()
    tr_saati = su_an_utc + dt.timedelta(hours=3)
    simdi = tr_saati.strftime('%d/%m/%Y %H:%M')
    
    final_mesaj = f"📊 **AKILLI PORTFÖY VE ANALİZ RAPORU** 📊\n🗓️ *Saat:* {simdi}\n" \
                  f"───────────────\n{ai_raporu}"
    telegram_mesaj_gonder(final_mesaj)

# ==========================================
# 🔄 ANA DÖNGÜ (7/24 DİNLEME VE RAPORLAMA)
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    print(f"==> Render için kukla sunucu {port} portunda başlatıldı!")
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Borsa Ajanı başarıyla başlatıldı. Komutlar anlık dinleniyor...")
    
    while True:
        telegram_komutlari_dinle()
        
        su_an_utc = dt.datetime.utcnow()
        tr_saati = su_an_utc + dt.timedelta(hours=3)
        
        saat_dakika = tr_saati.strftime("%H:%M")
        saniye = tr_saati.strftime("%S")
        
        if saniye == "00":
            if saat_dakika == "11:00":
                ajani_calistir(rapor_tipi="SABAH AÇILIŞ VE PORTFÖY RİSK KONTROLÜ")
            elif saat_dakika == "18:30":
                ajani_calistir(rapor_tipi="AKŞAM KAPANIŞ VE MALİYET DEĞERLENDİRMESİ")
            
        time.sleep(2)
