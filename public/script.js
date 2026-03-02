let token = localStorage.getItem('token');
let currentRealEmail = '';

document.addEventListener('DOMContentLoaded', () => {
    if (token) {
        verifyToken();
    }
    loadPublicMessages();
    setInterval(loadPublicMessages, 10000);
});

// Запрос кода на email
async function requestCode() {
    const email = document.getElementById('userEmail').value;
    const resultDiv = document.getElementById('emailResult');
    
    if (!email || !email.includes('@')) {
        resultDiv.className = 'result-message error';
        resultDiv.textContent = '❌ Введите корректный email';
        return;
    }
    
    resultDiv.className = 'result-message';
    resultDiv.textContent = '⏳ Отправка...';
    
    try {
        const response = await fetch('/api/request-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentRealEmail = email;
            document.getElementById('sentEmail').textContent = email;
            document.getElementById('emailStep').classList.remove('active');
            document.getElementById('codeStep').classList.add('active');
            document.getElementById('emailResult').className = 'result-message';
            document.getElementById('emailResult').textContent = '';
        } else {
            resultDiv.className = 'result-message error';
            resultDiv.textContent = '❌ ' + (data.error || 'Ошибка');
        }
    } catch (error) {
        resultDiv.className = 'result-message error';
        resultDiv.textContent = '❌ Ошибка сервера';
    }
}

// Проверка кода
async function verifyCode() {
    const code = document.getElementById('verificationCode').value;
    const resultDiv = document.getElementById('codeResult');
    
    if (!code || !/^\d{3}-\d{3}$/.test(code)) {
        resultDiv.className = 'result-message error';
        resultDiv.textContent = '❌ Введите код в формате 000-000';
        return;
    }
    
    resultDiv.className = 'result-message';
    resultDiv.textContent = '⏳ Проверка...';
    
    try {
        const response = await fetch('/api/verify-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                email: currentRealEmail,
                code: code 
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            token = data.token;
            localStorage.setItem('token', token);
            
            showUserInfo(data.tempEmail);
            resultDiv.className = 'result-message success';
            resultDiv.textContent = '✅ Код подтвержден!';
            
            loadMyMessages();
        } else {
            resultDiv.className = 'result-message error';
            resultDiv.textContent = '❌ ' + (data.error || 'Неверный код');
        }
    } catch (error) {
        resultDiv.className = 'result-message error';
        resultDiv.textContent = '❌ Ошибка сервера';
    }
}

// Проверка токена
async function verifyToken() {
    try {
        const response = await fetch('/api/verify', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const data = await response.json();
        
        if (response.ok && data.valid) {
            showUserInfo(data.tempEmail);
        } else {
            logout();
        }
    } catch (error) {
        logout();
    }
}

// Показать информацию о пользователе
function showUserInfo(tempEmail) {
    document.getElementById('authSection').style.display = 'none';
    document.getElementById('mainContent').style.display = 'grid';
    document.getElementById('myMessagesSection').style.display = 'block';
    document.getElementById('headerEmail').textContent = tempEmail;
    document.getElementById('userTempEmail').textContent = tempEmail;
}

// Выход
function logout() {
    token = null;
    localStorage.removeItem('token');
    currentRealEmail = '';
    
    document.getElementById('authSection').style.display = 'flex';
    document.getElementById('mainContent').style.display = 'none';
    document.getElementById('myMessagesSection').style.display = 'none';
    
    document.getElementById('codeStep').classList.remove('active');
    document.getElementById('emailStep').classList.add('active');
    
    document.getElementById('userEmail').value = '';
    document.getElementById('verificationCode').value = '';
    
    document.querySelectorAll('.result-message').forEach(el => {
        el.className = 'result-message';
        el.textContent = '';
    });
}

// Назад к вводу email
function backToEmail() {
    document.getElementById('codeStep').classList.remove('active');
    document.getElementById('emailStep').classList.add('active');
    document.getElementById('verificationCode').value = '';
    document.getElementById('codeResult').className = 'result-message';
    document.getElementById('codeResult').textContent = '';
}

// Загрузка публичных кодов
async function loadPublicMessages() {
    try {
        const response = await fetch('/api/public-messages');
        const messages = await response.json();
        
        const container = document.getElementById('publicMessages');
        
        if (!messages.length) {
            container.innerHTML = '<div class="loading">Пока нет кодов</div>';
            return;
        }
        
        container.innerHTML = messages.map(msg => `
            <div class="message-item has-code">
                <div class="code-value">🔢 ${msg.code}</div>
                <div class="message-meta">📧 Для: ${msg.user_temp_email}</div>
                <div class="message-meta">📨 От: ${msg.from_addr}</div>
                <div class="message-time">🕐 ${new Date(msg.received_at).toLocaleString()}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки:', error);
    }
}

// Загрузка своих кодов
async function loadMyMessages() {
    if (!token) return;
    
    try {
        const response = await fetch('/api/my-messages', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const messages = await response.json();
        const container = document.getElementById('myMessages');
        
        if (!messages.length) {
            container.innerHTML = '<div class="loading">У вас пока нет кодов</div>';
            return;
        }
        
        container.innerHTML = messages.map(msg => `
            <div class="message-item has-code">
                <div class="code-value">🔢 ${msg.code}</div>
                <div class="message-meta">📨 От: ${msg.from_addr}</div>
                <div class="message-meta">📧 Тема: ${msg.subject}</div>
                <div class="message-time">🕐 ${new Date(msg.received_at).toLocaleString()}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Ошибка загрузки:', error);
    }
}
