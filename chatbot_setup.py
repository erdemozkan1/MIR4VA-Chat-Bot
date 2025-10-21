# chatbot_setup.py (Ana Flask API Uygulaması)

from dotenv import load_dotenv
import google.generativeai as genai
import os
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS # CORS entegrasyonu (web sitesi bağlantısı için gerekli)

# RAG (Retrieval Augmented Generation) için gerekli kütüphaneler
import chromadb
# embedding_functions kullanmıyoruz, çünkü uyumsuzlukları manuel aştık.

# Flask ile web sunucusu başlatılıyor
#load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')

if not api_key:
    # API anahtarı yoksa hata fırlatmak daha iyi bir yaklaşımdır.
    raise ValueError("GEMINI_API_KEY ortam değişkeni ayarlanmadı.")

genai.configure(api_key=api_key)
app = Flask(__name__)  # Flask uygulamasını başlat
CORS(app)  # Web sitenizden gelecek istekler için CORS'u etkinleştirin

# ----------------------------------------------------
# RAG AYARLARI VE VERİTABANI BAĞLANTISI
# ----------------------------------------------------
EMBEDDING_MODEL_NAME = 'text-embedding-004' # data.py'de kullanılan model
COLLECTION_NAME = "oop_bootcamp_dokumanlari"  # data.py'de oluşturulan koleksiyon adı

# *** ÖNEMLİ DÜZELTME: RAG'a Bağlanma ***
# data.py ile veritabanı dosyaları oluşturulduğu için, burada sadece o koleksiyonu yüklüyoruz.
try:
    # ChromaDB istemcisini başlat (Veritabanı dosyaları projede yerel olarak depolanır)
    client = chromadb.PersistentClient(path="./chroma_db_files")
    # Koleksiyonu alıyoruz. (Embedding fonksiyonu tekrar belirtilmez, veritabanı onu hatırlar)
    rag_collection = client.get_collection(name=COLLECTION_NAME)
    print("Vektör Veritabanı başarıyla yüklendi. RAG aktif.")
except Exception as e:
    # Hata durumunda RAG'i devre dışı bırakır ama uygulama çökmeye devam eder
    print(f"HATA: RAG veritabanı yüklenemedi: {e}. Lütfen 'python data.py' dosyasını kontrol edin.")
    # Uygulama yine de genel sohbet için başlatılacak
    rag_collection = None


# Yapay Zeka Modelini Başlatma Fonksiyonu
def get_gemini_model(temperature_value):
    """
    Kullanıcının seçtiği temperature değeri ile model konfigürasyonunu ayarlar ve modeli döndürür.
    """
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
    # Sistem istemi (SYSTEM_PROMPT), RAG kullanımına göre güncellendi
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
    # 'templates' klasöründeki index.html dosyasını döndürür
    return render_template('index.html')


# 2. API Rotası (Sohbetin gerçekleştiği yer)
@app.route('/chat', methods=['POST'])
def chat_endpoint():
    data = request.get_json()
    mesaj = data.get('mesaj', '')
    gecmis = data.get('gecmis', [])
    kullanici_temp = data.get('temperature', 0.35)

    if not mesaj or mesaj.strip() == "":
        return jsonify({"cevap": "Mesaj Giriniz"}), 400

    model = get_gemini_model(kullanici_temp)

    # ----------------------------------------------------
    # RAG İŞ AKIŞI: İLGİLİ BAĞLAMI BULMA VE PROMPT'A EKLEME
    # ----------------------------------------------------
    ek_baglam = ""
    if rag_collection:
        try:
            # 1. Kullanıcı Mesajını Vektöre Çevir
            # Sorgu Vektörünü doğrudan Gemini API ile oluşturuyoruz
            sorgu_vektoru = genai.embed_content(
                model=EMBEDDING_MODEL_NAME,
                content=mesaj.strip(),
                task_type="RETRIEVAL_QUERY" # Sorgulama görevi için
            )['embedding']

            # 2. Vektör DB'de Arama Yap
            # ChromaDB'den vektör bazlı sorgu ile en alakalı parçaları çek
            sonuclar = rag_collection.query(
                query_embeddings=[sorgu_vektoru],
                n_results=3,  # En alakalı 3 parçayı getir
                include=['documents']
            )

            # 3. Çekilen Bilgileri Prompt'a Eklemek İçin Hazırla
            ilgili_dokumanlar = sonuclar.get('documents', [[]])[0]
            if ilgili_dokumanlar:
                ek_baglam = "\n\n### BAĞLAM BAŞLANGIÇ (Özel Dokümanlardan Alınmıştır) ###\n"
                for doc in ilgili_dokumanlar:
                    ek_baglam += f"- {doc}\n"
                ek_baglam += "### BAĞLAM BİTİŞ ###\n"

        except Exception as e:
            # Hata durumunda (örneğin API anahtarı geçersizse veya ağ hatası varsa)
            print(f"RAG Arama İşleminde Hata: {e}. Bağlam eklenmiyor.")
            ek_baglam = ""

    # ----------------------------------------------------
    # SON PROMPT VE GÖNDERİM
    # ----------------------------------------------------

    # RAG bağlamını içeren yeni mesaj oluşturulur
    yeni_mesaj = f"{ek_baglam}Kullanıcının sorusu: {mesaj.strip()}"

    # Sohbet Geçmişini Hazırla
    chat_gecmisi = []
    for kulanici, bot in gecmis:
        if kulanici and bot:
            chat_gecmisi.append({"role": "user", "parts": [{"text": kulanici}]})
            chat_gecmisi.append({"role": "model", "parts": [{"text": bot}]})

    try:
        chat = model.start_chat(history=chat_gecmisi)
        # RAG bağlamı ile zenginleştirilmiş mesajı gönder
        response = chat.send_message(yeni_mesaj)

        # Cevabı JSON olarak döndür
        return jsonify({"cevap": response.text})
    except Exception as e:
        print(f"Hata: {e}")
        return jsonify({"cevap": "Bir hata oluştu. Lütfen tekrar deneyin."}), 500


if __name__ == '__main__':
    # Web uygulamasını başlat
    app.run(debug=True)
