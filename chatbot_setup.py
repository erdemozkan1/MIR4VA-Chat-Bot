# chatbot_setup.py (Ana Flask API Uygulaması)

from dotenv import load_dotenv
import google.generativeai as genai
import os
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS

# RAG (Retrieval Augmented Generation) için gerekli kütüphaneler
import chromadb

# Flask ile web sunucusu başlatılıyor
load_dotenv() # Railway'de çalışsa bile, lokalde çalışması için bırakılabilir.
# chatbot_setup.py dosyasındaki mevcut api_key satırını değiştirin:

# Önce GOOGLE_API_KEY'i dene, yoksa GEMINI_API_KEY'i dene.
api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
# *** RAG VERİTABANI YOLU ***
# data.py ile aynı mutlak yolu kullanıyoruz.
CHROMA_PATH = os.path.abspath("./chroma_db_files")
COLLECTION_NAME = "oop_bootcamp_dokumanlari"
print("Railway GEMINI_API_KEY:", os.getenv("GEMINI_API_KEY"))

# API Anahtarı Kontrolü ve Yapılandırma
if api_key:
    # API anahtarı varsa, Gemini SDK'yı yapılandır
    genai.configure(api_key=api_key)
    print("INFO: Gemini API anahtarı başarıyla yüklendi ve kullanıma hazır.")
#else:
    # Anahtar yoksa, sadece uyarı veriyoruz (çöküşü engellemek için)
    print("UYARI: GEMINI_API_KEY ortam değişkeni Railway'den alınamadı.")
    print("Uygulama genel sorgular için başlatılıyor (Gemini API gerektiren kısımlar hata verebilir).")


# ChromaDB istemcisini başlat ve koleksiyonu yükle
try:
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # Collection'ı alırken Embedding fonksiyonu belirtmiyoruz, çünkü sorguyu manuel yapacağız.
    rag_collection = client.get_collection(name=COLLECTION_NAME)
    print("Vektör Veritabanı başarıyla yüklendi. RAG aktif.")
except Exception as e:
    # Bu genellikle dosya yolu hatası veya dosya bulunamadı hatasıdır.
    print(f"HATA: RAG veritabanı yüklenemedi: {e}. Lütfen 'python data.py' dosyasını kontrol edin.")
    rag_collection = None


app = Flask(__name__)
CORS(app)

# Yapay Zeka Modelini Başlatma Fonksiyonu
def get_gemini_model(temperature_value):
    # ... (Model konfigürasyonu ve Sistem Prompt'u aynı kalır) ...
    try:
        temp = max(0.0, min(1.0, float(temperature_value)))
    except (ValueError, TypeError):
        temp = 0.35

    MODEL_CONFIG = {
        'temperature': temp,
        'max_output_tokens': 1000,
        'top_p': 0.82,
        'top_k': 40,
    }
    SYSTEM_PROMPT = """Sen bir OOP (Nesne Tabanlı Programlama) öğreticisisin. 
Kullanıcının sorularına cevap verirken, sana ek olarak sağlanan BAĞLAM (özel ders notları) varsa, öncelikle bu bilgiyi kullan. 
Eğer bağlamda yeterli bilgi yoksa, genel OOP bilginle cevap ver. 
Kullanıcılar kod dili belirtmezse Java dilinden örnek kod blokları ver. 
Sohbet etmek isterlerse samimi bir şekilde sohbet et. """

    model = genai.GenerativeModel(
        model_name='gemini-2.0-flash',
        generation_config=MODEL_CONFIG,
        system_instruction=SYSTEM_PROMPT
    )
    return model


# 1. Ana Sayfa Rotası (Frontend'i gösterecek)
@app.route('/')
def index():
    return render_template('index.html')


# 2. API Rotası (Sohbetin gerçekleştiği yer)
@app.route('/chat', methods=['POST'])
def chat_endpoint():
    global api_key, rag_collection

    data = request.get_json()
    mesaj = data.get('mesaj', '')
    gecmis = data.get('gecmis', [])
    kullanici_temp = data.get('temperature', 0.35)

    if not mesaj or mesaj.strip() == "":
        return jsonify({"cevap": "Mesaj Giriniz"}), 400

    # API Anahtarı yoksa (Railway'den gelmediyse), hemen hata döndür
    if not api_key:
        print("KRİTİK HATA: API Anahtarı eksik, Gemini çağrılamaz.")
        # Bu, chatbot'un verdiği "Bir hata oluştu" cevabının kaynağıdır.
        return jsonify({"cevap": "API Anahtarı eksik. Lütfen proje yöneticinize başvurun."}), 500

    model = get_gemini_model(kullanici_temp)

    # ----------------------------------------------------
    # RAG İŞ AKIŞI: İLGİLİ BAĞLAMI BULMA
    # ----------------------------------------------------
    ek_baglam = ""
    if rag_collection:
        try:
            # 1. Kullanıcı Mesajını Vektöre Çevir (API Key'i manuel iletiyoruz)
            sorgu_vektoru_result = genai.embed_content(
                model='text-embedding-004',
                content=mesaj.strip(),
                task_type="RETRIEVAL_QUERY",
                # API KEY'i burada manuel olarak iletiyoruz!
                api_key=api_key
            )
            sorgu_vektoru = sorgu_vektoru_result['embedding']

            # 2. Vektör DB'de Arama Yap
            sonuclar = rag_collection.query(
                query_embeddings=[sorgu_vektoru],
                n_results=3
            )

            # 3. Çekilen Bilgileri Prompt'a Eklemek İçin Hazırla
            ilgili_dokumanlar = sonuclar.get('documents', [[]])[0]
            if ilgili_dokumanlar:
                ek_baglam = "\n\n### BAĞLAM BAŞLANGIÇ (Özel Dokümanlardan Alınmıştır) ###\n"
                for doc in ilgili_dokumanlar:
                    ek_baglam += f"- {doc}\n"
                ek_baglam += "### BAĞLAM BİTİŞ ###\n"

        except Exception as e:
            # Bu hata genellikle API kotası veya ağ sorunudur
            print(f"RAG Arama İşleminde KRİTİK HATA: {e}. Bağlam eklenmiyor.")
            ek_baglam = ""

    # ----------------------------------------------------
    # SON PROMPT VE GÖNDERİM
    # ----------------------------------------------------

    yeni_mesaj = f"{ek_baglam}Kullanıcının sorusu: {mesaj.strip()}"

    chat_gecmisi = []
    for kulanici, bot in gecmis:
        if kulanici and bot:
            chat_gecmisi.append({"role": "user", "parts": [{"text": kulanici}]})
            chat_gecmisi.append({"role": "model", "parts": [{"text": bot}]})

    try:
        chat = model.start_chat(history=chat_gecmisi)
        response = chat.send_message(yeni_mesaj)

        # Cevabı JSON olarak döndür
        return jsonify({"cevap": response.text})
    except Exception as e:
        # API anahtarı eksikliği veya kota aşımı gibi nihai hatalar buraya düşer.
        print(f"Hata: {e}")
        # Uygulamanın çökmeyen, genel hata mesajı
        return jsonify({"cevap": "Bir hata oluştu. Lütfen Railway loglarını kontrol edin."}), 500


if __name__ == '__main__':
    # Web uygulamasını başlat
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)
