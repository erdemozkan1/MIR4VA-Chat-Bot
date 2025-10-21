// static/script.js

const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const tempSlider = document.getElementById('temperature-slider');
const tempValueSpan = document.getElementById('temperature-value');

let chatHistory = []; // Sohbet geçmişini burada tutacağız: [ [kullanıcı_mesajı, bot_cevabı], ... ]

// Temperature değerini güncelleme fonksiyonu
tempSlider.addEventListener('input', (e) => {
    const value = parseFloat(e.target.value);
    let level = '';
    if (value <= 0.3) {
        level = ' (Düşük)';
    } else if (value <= 0.7) {
        level = ' (Orta)';
    } else {
        level = ' (Yüksek)';
    }
    tempValueSpan.textContent = value.toFixed(2) + level;
});


// Mesajı sohbet kutusuna ekleyen fonksiyon
function addMessage(sender, message) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    messageDiv.innerHTML = `<p>${message.replace(/\n/g, '<br>')}</p>`; // Satır atlamaları <br> ile göster
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight; // En alta kaydır
}

// Sohbet gönderme fonksiyonu
async function sendMessage() {
    const userMessage = userInput.value.trim();
    const temperature = parseFloat(tempSlider.value); // Seçilen temperature değerini al

    if (!userMessage) return;

    // 1. Kullanıcı mesajını ekle
    addMessage('user', userMessage);
    userInput.value = ''; // Giriş alanını temizle
    sendButton.disabled = true;

    // 2. Bir yükleme mesajı ekle
    const loadingMessage = document.createElement('div');
    loadingMessage.classList.add('message', 'model-message', 'loading');
    loadingMessage.innerHTML = '<p>MIR4VA düşünüyor...</p>';
    chatBox.appendChild(loadingMessage);
    chatBox.scrollTop = chatBox.scrollHeight;

    // 3. Backend'e isteği gönder
    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                mesaj: userMessage,
                gecmis: chatHistory,
                temperature: temperature // Temperature değerini gönder
            })
        });

        const data = await response.json();

        // 4. Yükleme mesajını kaldır
        chatBox.removeChild(loadingMessage);

        // 5. Bot cevabını ekle
        const botResponse = data.cevap;
        addMessage('model', botResponse);

        // 6. Geçmişi güncelle
        chatHistory.push([userMessage, botResponse]);

    } catch (error) {
        console.error('API Hatası:', error);
        chatBox.removeChild(loadingMessage); // Yükleme mesajını kaldır
        addMessage('model', 'Bağlantı hatası oluştu. Lütfen tekrar deneyin.');
    } finally {
        sendButton.disabled = false;
        userInput.focus();
    }
}

sendButton.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});