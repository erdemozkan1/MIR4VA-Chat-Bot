# data.py - RAG (Embedding) Veritabanı Oluşturma Scripti

import os
from dotenv import load_dotenv
import google.generativeai as genai
from pypdf import PdfReader
from docx import Document
import chromadb

# embedding_functions'ı doğrudan kullanmıyoruz, manuel embedding için genai'yi kullanacağız.

# ----------------------------------------------------
# 1. TEMEL YAPILANDIRMA
# ----------------------------------------------------
load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')
if not API_KEY:
    raise ValueError("GEMINI_API_KEY ortam değişkeni ayarlanmadı. Lütfen .env dosyasını kontrol edin.")

# Gemini'ı yapılandır
genai.configure(api_key=API_KEY)
EMBEDDING_MODEL_NAME = 'text-embedding-004'
COLLECTION_NAME = "oop_bootcamp_dokumanlari"

# *** ÖNEMLİ DÜZELTME: ChromaDB yolu tanımlanıyor ***
# Veritabanı dosyalarının tutulacağı klasör. chatbot_setup.py ile AYNI OLMALIDIR!
CHROMA_PATH = "./chroma_db_files"

# ChromaDB istemcisini PersistentClient ile başlatıyoruz
client = chromadb.PersistentClient(path=CHROMA_PATH)


# ----------------------------------------------------
# 2. PARÇALAMA (CHUNK) VE AYRIŞTIRMA (PARSE) FONKSİYONLARI
# ----------------------------------------------------

def parse_docx(file_path):
    """DOCX dosyasından metni çıkarır."""
    try:
        doc = Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        print(f"HATA: DOCX dosyası ayrıştırılamadı ({file_path}): {e}")
        return ""


def parse_pdf(file_path):
    """PDF dosyasından tüm metni çıkarır."""
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() if page.extract_text() else ""
        return text
    except Exception as e:
        print(f"HATA: PDF dosyası ayrıştırılamadı ({file_path}): {e}")
        return ""


def chunk_text(text, chunk_size=1000, overlap=100):
    """Uzun metni RAG için küçük, anlamlı parçalara (chunk) ayırır."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunks.append(text[i:i + chunk_size])
    return chunks


# ----------------------------------------------------
# 3. ANA İŞ AKIŞI: PARS ETME, EMBED ETME VE KAYDETME
# ----------------------------------------------------

def prepare_and_save_data(data_dir="data"):
    """Belirtilen klasördeki tüm dosyaları işler ve ChromaDB'ye kaydeder."""
    global client

    # 1. Koleksiyonu temiz bir başlangıç için sil
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Mevcut koleksiyon '{COLLECTION_NAME}' silindi.")
    except Exception:
        pass

        # 2. Embedding fonksiyonunu manuel olarak devre dışı bırakıyoruz.
    # Bu, CollectionCommon.py hatasını atlatmak için kritik.
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        # Embedding fonksiyonunu burada belirtmiyoruz!
    )

    all_chunks = []
    all_metadatas = []
    all_ids = []
    chunk_counter = 0

    print(f"'{data_dir}' klasöründeki dosyalar aranıyor...")

    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)
        raw_text = None

        if filename.endswith(".pdf"):
            print(f"-> PDF dosyası işleniyor: {filename}")
            raw_text = parse_pdf(file_path)
        elif filename.endswith((".doc", ".docx")):
            print(f"-> DOCX dosyası işleniyor: {filename}")
            raw_text = parse_docx(file_path)
        else:
            continue

        if raw_text:
            chunks = chunk_text(raw_text)

            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadatas.append({"source": filename})
                all_ids.append(f"{filename}_{chunk_counter}")
                chunk_counter += 1

            print(f"   {len(chunks)} parça oluşturuldu.")

    if all_chunks:
        print(f"\nToplam {len(all_chunks)} parça Embed ediliyor ve veritabanına kaydediliyor...")

        # 3. Embedding işlemini MANUEL OLARAK yapıyoruz (Gemini SDK ile)
        # Bu, önceki "generate_embeddings" hatasını kesin olarak atlar.
        all_embeddings = []

        # Batch (toplu) embedding için chunks'ı kullan
        result = genai.embed_content(
            model=EMBEDDING_MODEL_NAME,
            content=all_chunks,
            task_type="RETRIEVAL_DOCUMENT"
        )
        all_embeddings = result['embedding']

        collection.add(
            embeddings=all_embeddings,  # Manuel oluşturulan embedding'leri ver!
            documents=all_chunks,
            metadatas=all_metadatas,
            ids=all_ids
        )

        print("\n✅ Vektör Veritabanı başarıyla oluşturuldu!")
        print(f"Veritabanı adı: {COLLECTION_NAME}")
        print(f"Toplam kayıt sayısı: {collection.count()}")
    else:
        print("\n⚠️ İşlenecek bir metin dosyası (PDF/DOCX) bulunamadı. Lütfen 'data' klasörünü kontrol edin.")


if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
        print("⚠️ 'data' klasörü oluşturuldu. Lütfen PDF/DOCX dosyalarınızı içine yerleştirin.")

    prepare_and_save_data(data_dir="data")
