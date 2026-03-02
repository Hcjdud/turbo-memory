const express = require('express');
const path = require('path');
const { Pool } = require('pg');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const cron = require('node-cron');
const nodemailer = require('nodemailer');
const Imap = require('imap');
const { simpleParser } = require('mailparser');

require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ===== PostgreSQL =====
const pgPool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    max: 20
});

// ===== Инициализация таблиц =====
async function initDB() {
    const client = await pgPool.connect();
    
    // Таблица пользователей
    await client.query(`
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            real_email TEXT UNIQUE NOT NULL,
            temp_email TEXT UNIQUE NOT NULL,
            password TEXT,
            verification_code TEXT,
            code_expires TIMESTAMP,
            verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    `);
    
    // Таблица сообщений с кодами
    await client.query(`
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            user_temp_email TEXT NOT NULL,
            from_addr TEXT NOT NULL,
            subject TEXT,
            code TEXT NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_public INTEGER DEFAULT 1
        )
    `);
    
    client.release();
    console.log('✅ База данных готова');
}

// ===== Настройка почты для отправки кодов =====
const verifyTransporter = nodemailer.createTransport({
    host: process.env.SMTP_HOST,
    port: process.env.SMTP_PORT,
    secure: true,
    auth: {
        user: process.env.VERIFY_EMAIL,
        pass: process.env.VERIFY_PASSWORD
    }
});

// ===== Функции =====
function generateTempEmail() {
    const randomStr = Math.random().toString(36).substring(2, 10);
    return `${randomStr}@walle.ndjp.net`;
}

function generateVerificationCode() {
    const first = Math.floor(Math.random() * 900) + 100;
    const second = Math.floor(Math.random() * 900) + 100;
    return `${first}-${second}`;
}

function extractCode(text) {
    if (!text) return null;
    const match = text.match(/\b(\d{3}-\d{3})\b/);
    return match ? match[1] : null;
}

// ===== API: Запрос кода подтверждения =====
app.post('/api/request-code', async (req, res) => {
    try {
        const { email } = req.body;
        
        if (!email || !email.includes('@')) {
            return res.status(400).json({ error: 'Введите корректный email' });
        }
        
        // Генерируем код
        const code = generateVerificationCode();
        const expires = new Date();
        expires.setMinutes(expires.getMinutes() + 10); // код действует 10 минут
        
        // Сохраняем или обновляем пользователя
        const tempEmail = generateTempEmail();
        
        await pgPool.query(`
            INSERT INTO users (real_email, temp_email, verification_code, code_expires)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (real_email) 
            DO UPDATE SET verification_code = $3, code_expires = $4, verified = FALSE
        `, [email, tempEmail, code, expires]);
        
        // Отправляем письмо с кодом
        const mailOptions = {
            from: `"Временная почта" <${process.env.VERIFY_EMAIL}>`,
            to: email,
            subject: 'Код подтверждения',
            text: `ВАШ КОД ПОДТВЕРЖДЕНИЯ\nКОД ${code}`,
            html: `
                <div style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Подтверждение регистрации</h2>
                    <p>Ваш код подтверждения:</p>
                    <div style="font-size: 32px; font-weight: bold; color: #1e3c72; padding: 20px; background: #f0f4f8; border-radius: 10px; text-align: center; letter-spacing: 5px;">
                        ${code}
                    </div>
                    <p style="color: #666; margin-top: 20px;">Код действителен 10 минут.</p>
                </div>
            `
        };
        
        await verifyTransporter.sendMail(mailOptions);
        
        res.json({ 
            success: true, 
            message: 'Код отправлен на вашу почту',
            tempEmail: tempEmail
        });
        
    } catch (error) {
        console.error('❌ Ошибка отправки кода:', error);
        res.status(500).json({ error: 'Ошибка при отправке кода' });
    }
});

// ===== API: Проверка кода =====
app.post('/api/verify-code', async (req, res) => {
    try {
        const { email, code } = req.body;
        
        if (!email || !code) {
            return res.status(400).json({ error: 'Email и код обязательны' });
        }
        
        // Ищем пользователя
        const user = await pgPool.query(
            'SELECT * FROM users WHERE real_email = $1',
            [email]
        );
        
        if (!user.rows[0]) {
            return res.status(404).json({ error: 'Пользователь не найден' });
        }
        
        const userData = user.rows[0];
        
        // Проверяем, не истек ли код
        if (new Date() > new Date(userData.code_expires)) {
            return res.status(400).json({ error: 'Код истек, запросите новый' });
        }
        
        // Проверяем код (строгое сравнение)
        if (userData.verification_code !== code) {
            return res.status(400).json({ error: 'Неверный код' });
        }
        
        // Код верный - помечаем пользователя как верифицированного
        await pgPool.query(
            'UPDATE users SET verified = TRUE WHERE real_email = $1',
            [email]
        );
        
        // Генерируем токен
        const token = jwt.sign(
            { 
                realEmail: email,
                tempEmail: userData.temp_email 
            }, 
            process.env.JWT_SECRET, 
            { expiresIn: process.env.JWT_EXPIRES_IN }
        );
        
        res.json({ 
            success: true, 
            message: 'Код подтвержден',
            tempEmail: userData.temp_email,
            token
        });
        
    } catch (error) {
        console.error('❌ Ошибка проверки кода:', error);
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// ===== API: Вход по токену =====
app.post('/api/login', async (req, res) => {
    try {
        const { email } = req.body;
        
        const user = await pgPool.query(
            'SELECT * FROM users WHERE real_email = $1 AND verified = TRUE',
            [email]
        );
        
        if (!user.rows[0]) {
            return res.status(401).json({ error: 'Пользователь не найден или не подтвержден' });
        }
        
        const token = jwt.sign(
            { 
                realEmail: email,
                tempEmail: user.rows[0].temp_email 
            },
            process.env.JWT_SECRET,
            { expiresIn: process.env.JWT_EXPIRES_IN }
        );
        
        res.json({ 
            success: true, 
            tempEmail: user.rows[0].temp_email,
            token 
        });
        
    } catch (error) {
        console.error('❌ Ошибка входа:', error);
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// ===== API: Проверка токена =====
app.get('/api/verify', async (req, res) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        if (!token) {
            return res.status(401).json({ error: 'Не авторизован' });
        }
        
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        
        const user = await pgPool.query(
            'SELECT * FROM users WHERE real_email = $1 AND verified = TRUE',
            [decoded.realEmail]
        );
        
        if (!user.rows[0]) {
            return res.status(401).json({ error: 'Пользователь не найден' });
        }
        
        res.json({ 
            valid: true, 
            realEmail: user.rows[0].real_email,
            tempEmail: user.rows[0].temp_email 
        });
        
    } catch (error) {
        res.status(401).json({ error: 'Недействительный токен' });
    }
});

// ===== API: Получение публичных кодов =====
app.get('/api/public-messages', async (req, res) => {
    try {
        const messages = await pgPool.query(
            'SELECT * FROM messages WHERE is_public = 1 ORDER BY received_at DESC LIMIT 50'
        );
        res.json(messages.rows);
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// ===== API: Получение своих кодов =====
app.get('/api/my-messages', async (req, res) => {
    try {
        const token = req.headers.authorization?.split(' ')[1];
        if (!token) {
            return res.status(401).json({ error: 'Не авторизован' });
        }
        
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        
        const messages = await pgPool.query(
            'SELECT * FROM messages WHERE user_temp_email = $1 ORDER BY received_at DESC',
            [decoded.tempEmail]
        );
        
        res.json(messages.rows);
    } catch (error) {
        res.status(500).json({ error: 'Ошибка сервера' });
    }
});

// ===== Проверка почты для получения кодов =====
async function checkTempMail() {
    return new Promise((resolve, reject) => {
        const imap = new Imap({
            user: process.env.TEMP_EMAIL,
            password: process.env.TEMP_PASSWORD,
            host: process.env.IMAP_HOST,
            port: process.env.IMAP_PORT,
            tls: true
        });

        imap.once('ready', () => {
            imap.openBox('INBOX', false, (err) => {
                if (err) return reject(err);
                
                imap.search(['UNSEEN'], (err, results) => {
                    if (err || !results?.length) {
                        imap.end();
                        return resolve([]);
                    }

                    const fetch = imap.fetch(results, { bodies: '' });
                    const messages = [];

                    fetch.on('message', (msg) => {
                        const message = {};
                        
                        msg.on('body', (stream) => {
                            simpleParser(stream, async (err, parsed) => {
                                if (err) return;
                                
                                const text = parsed.text || '';
                                const html = parsed.html || '';
                                
                                // Ищем email получателя
                                const emailRegex = /([a-zA-Z0-9._%+-]+@walle\.ndjp\.net)/i;
                                const match = text.match(emailRegex) || html.match(emailRegex);
                                const code = extractCode(text) || extractCode(html);
                                
                                if (match && code) {
                                    message.to = match[1];
                                    message.from = parsed.from?.text || '';
                                    message.subject = parsed.subject || '';
                                    message.code = code;
                                    message.date = parsed.date || new Date();
                                }
                            });
                        });

                        msg.once('end', () => {
                            if (message.to && message.code) {
                                messages.push(message);
                            }
                        });
                    });

                    fetch.once('end', () => {
                        imap.end();
                        resolve(messages);
                    });
                });
            });
        });

        imap.once('error', reject);
        imap.connect();
    });
}

// ===== Сохранение кодов =====
async function saveTempMessages(messages) {
    if (!messages?.length) return;
    
    for (const msg of messages) {
        try {
            // Проверяем существование пользователя
            const user = await pgPool.query(
                'SELECT id FROM users WHERE temp_email = $1 AND verified = TRUE',
                [msg.to]
            );
            
            if (user.rows.length > 0) {
                await pgPool.query(
                    `INSERT INTO messages (user_temp_email, from_addr, subject, code, received_at) 
                     VALUES ($1, $2, $3, $4, $5)`,
                    [msg.to, msg.from, msg.subject, msg.code, msg.date]
                );
                console.log(`✅ Код ${msg.code} для ${msg.to}`);
            }
        } catch (error) {
            console.error('❌ Ошибка сохранения:', error);
        }
    }
}

// ===== Фоновая задача =====
if (process.env.TEMP_EMAIL && process.env.TEMP_PASSWORD) {
    cron.schedule('*/30 * * * * *', async () => {
        try {
            const messages = await checkTempMail();
            if (messages?.length) {
                await saveTempMessages(messages);
            }
        } catch (error) {
            console.error('❌ Ошибка при проверке почты:', error);
        }
    });
    console.log('📧 Проверка почты запущена (каждые 30 секунд)');
}

// ===== Health check =====
app.get('/health', (req, res) => res.send('OK'));

// ===== Запуск =====
initDB().then(() => {
    app.listen(PORT, '0.0.0.0', () => {
        console.log(`🚀 Сервер на порту ${PORT}`);
        console.log(`📧 Отправка кодов: ${process.env.VERIFY_EMAIL}`);
        console.log(`📨 Прием кодов: ${process.env.TEMP_EMAIL}`);
    });
});
