import sqlite3
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import secrets

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("7980889794:AAFwFN07AYjgtBLmlRdTt4QDHZwt4lZ5pP0")
ADMIN_SECRET = os.getenv("chlen")

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('garant_bot.db', check_same_thread=False)
        self.create_tables()
        logger.info("База данных SQLite подключена")
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                created_at TEXT
            )
        ''')
        
        # Таблица сделок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deals (
                deal_id TEXT PRIMARY KEY,
                buyer_id INTEGER,
                seller_id INTEGER,
                amount REAL,
                description TEXT,
                status TEXT DEFAULT 'created',
                created_at TEXT
            )
        ''')
        
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
    
    def create_user(self, user_id, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, created_at) 
            VALUES (?, ?, ?)
        ''', (user_id, username, datetime.now().isoformat()))
        self.conn.commit()
    
    def update_balance(self, user_id, amount):
        cursor = self.conn.cursor()
        # Сначала создаем пользователя если его нет
        self.create_user(user_id, "")
        
        cursor.execute('''
            UPDATE users SET balance = balance + ? WHERE user_id = ?
        ''', (amount, user_id))
        self.conn.commit()
        
        return cursor.rowcount > 0
    
    def get_balance(self, user_id):
        user = self.get_user(user_id)
        return user[2] if user else 0.0
    
    def create_deal(self, deal_id, buyer_id, amount, description):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO deals (deal_id, buyer_id, amount, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (deal_id, buyer_id, amount, description, 'created', datetime.now().isoformat()))
        self.conn.commit()
        return True
    
    def get_deal(self, deal_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM deals WHERE deal_id = ?', (deal_id,))
        return cursor.fetchone()
    
    def update_deal_status(self, deal_id, status, seller_id=None):
        cursor = self.conn.cursor()
        if seller_id:
            cursor.execute('''
                UPDATE deals SET status = ?, seller_id = ? WHERE deal_id = ?
            ''', (status, seller_id, deal_id))
        else:
            cursor.execute('''
                UPDATE deals SET status = ? WHERE deal_id = ?
            ''', (status, deal_id))
        self.conn.commit()
        return cursor.rowcount > 0

# Инициализация базы
db = Database()

class GarantBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        # Команды
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("balance", self.balance))
        self.application.add_handler(CommandHandler("deal", self.create_deal))
        self.application.add_handler(CommandHandler("many", self.admin_add_balance))
        self.application.add_handler(CommandHandler("deals", self.list_deals))
        
        # Кнопки
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # Сообщения
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db.create_user(user.id, user.username)
        
        keyboard = [
            [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton("🤝 Новая сделка", callback_data="new_deal")],
            [InlineKeyboardButton("📋 Мои сделки", callback_data="my_deals")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Я - гарант-бот для безопасных сделок.\n\n"
            "💡 Возможности:\n"
            "• Создание гарантийных сделок\n"
            "• Система баланса\n"
            "• Безопасное проведение операций\n\n"
            "Используйте кнопки ниже или команды:",
            reply_markup=reply_markup
        )
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        balance = db.get_balance(user_id)
        
        await update.message.reply_text(
            f"💰 Ваш баланс: {balance} ₽\n\n"
            "Для пополнения баланса обратитесь к администратору."
        )
    
    async def create_deal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_balance = db.get_balance(user_id)
        
        if len(context.args) < 2:
            await update.message.reply_text(
                "📝 Формат команды:\n"
                "/deal <сумма> <описание>\n\n"
                "Пример:\n"
                "/deal 1000 Продажа аккаунта Steam\n\n"
                f"💳 Ваш текущий баланс: {user_balance} ₽"
            )
            return
        
        try:
            amount = float(context.args[0])
            description = " ".join(context.args[1:])
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше 0")
                return
            
            if amount > user_balance:
                await update.message.reply_text(
                    f"❌ Недостаточно средств на балансе\n"
                    f"💳 Ваш баланс: {user_balance} ₽\n"
                    f"💸 Требуется: {amount} ₽"
                )
                return
            
            # Создание сделки
            deal_id = secrets.token_hex(6).upper()
            db.create_deal(deal_id, user_id, amount, description)
            
            # Резервирование средств
            db.update_balance(user_id, -amount)
            
            keyboard = [
                [InlineKeyboardButton("✅ Принять сделку", callback_data=f"accept_{deal_id}")],
                [InlineKeyboardButton("❌ Отменить сделку", callback_data=f"cancel_{deal_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🆕 Сделка создана!\n\n"
                f"📋 ID сделки: `{deal_id}`\n"
                f"💸 Сумма: {amount} ₽\n"
                f"📝 Описание: {description}\n"
                f"👤 Покупатель: {update.effective_user.first_name}\n\n"
                f"🔗 Поделитесь ID сделки с продавцом\n"
                f"💡 Продавец должен нажать 'Принять сделку'",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы. Используйте числа.")
    
    async def admin_add_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Проверка секретного ключа
        if len(context.args) < 2 or context.args[0] != ADMIN_SECRET:
            await update.message.reply_text("❌ Команда не найдена")
            return
        
        try:
            target_user_id = int(context.args[1])
            amount = float(context.args[2]) if len(context.args) > 2 else 1000.0
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше 0")
                return
            
            # Обновление баланса
            success = db.update_balance(target_user_id, amount)
            
            if success:
                await update.message.reply_text(
                    f"✅ Баланс пользователя {target_user_id} пополнен на {amount} ₽\n\n"
                    f"💳 Новый баланс: {db.get_balance(target_user_id)} ₽"
                )
                
                # Уведомление пользователю (если бот имеет доступ)
                try:
                    await context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"🎉 Ваш баланс пополнен на {amount} ₽!\n\n"
                             f"💳 Текущий баланс: {db.get_balance(target_user_id)} ₽"
                    )
                except:
                    logger.warning(f"Не удалось отправить уведомление пользователю {target_user_id}")
            else:
                await update.message.reply_text("❌ Ошибка при пополнении баланса")
            
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Неверный формат команды\n\n"
                "📝 Правильный формат:\n"
                "/many <секретный_ключ> <user_id> <сумма>\n\n"
                "Пример:\n"
                "/many secret123 123456789 1000"
            )
    
    async def list_deals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT deal_id, amount, description, status, created_at 
            FROM deals WHERE buyer_id = ? OR seller_id = ?
            ORDER BY created_at DESC LIMIT 10
        ''', (user_id, user_id))
        
        deals = cursor.fetchall()
        
        if not deals:
            await update.message.reply_text("📭 У вас пока нет сделок")
            return
        
        deals_text = "📋 Ваши последние сделки:\n\n"
        for deal in deals:
            deal_id, amount, description, status, created_at = deal
            status_emoji = {
                'created': '🆕',
                'in_progress': '🔄', 
                'completed': '✅',
                'cancelled': '❌'
            }.get(status, '❓')
            
            deals_text += f"{status_emoji} Сделка `{deal_id}`\n"
            deals_text += f"💸 Сумма: {amount} ₽\n"
            deals_text += f"📝 {description}\n"
            deals_text += f"📊 Статус: {status}\n"
            deals_text += "─" * 20 + "\n"
        
        await update.message.reply_text(deals_text, parse_mode='Markdown')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        if data == "balance":
            balance = db.get_balance(user_id)
            await query.edit_message_text(f"💰 Ваш баланс: {balance} ₽")
        
        elif data == "new_deal":
            await query.edit_message_text(
                "📝 Для создания сделки используйте команду:\n"
                "/deal <сумма> <описание>\n\n"
                "Пример:\n"
                "/deal 1500 Покупка игры Steam"
            )
        
        elif data == "my_deals":
            await self.list_deals_for_query(query)
        
        elif data.startswith("accept_"):
            deal_id = data.split("_")[1]
            await self.accept_deal(deal_id, user_id, query)
        
        elif data.startswith("cancel_"):
            deal_id = data.split("_")[1]
            await self.cancel_deal(deal_id, user_id, query)
    
    async def list_deals_for_query(self, query):
        user_id = query.from_user.id
        cursor = db.conn.cursor()
        cursor.execute('''
            SELECT deal_id, amount, description, status 
            FROM deals WHERE buyer_id = ? 
            ORDER BY created_at DESC LIMIT 5
        ''', (user_id,))
        
        deals = cursor.fetchall()
        
        if not deals:
            await query.edit_message_text("📭 У вас пока нет созданных сделок")
            return
        
        deals_text = "📋 Ваши сделки:\n\n"
        for deal in deals:
            deal_id, amount, description, status = deal
            status_emoji = {'created': '🆕', 'in_progress': '🔄', 'completed': '✅', 'cancelled': '❌'}.get(status, '❓')
            deals_text += f"{status_emoji} `{deal_id}` - {amount} ₽ - {status}\n"
        
        await query.edit_message_text(deals_text, parse_mode='Markdown')
    
    async def accept_deal(self, deal_id: str, seller_id: int, query):
        deal = db.get_deal(deal_id)
        
        if not deal:
            await query.edit_message_text("❌ Сделка не найдена")
            return
        
        if deal[5] != 'created':  # status
            await query.edit_message_text("❌ Сделка уже занята или завершена")
            return
        
        if deal[1] == seller_id:  # buyer_id
            await query.edit_message_text("❌ Вы не можете принять свою собственную сделку")
            return
        
        # Обновление сделки
        db.update_deal_status(deal_id, 'in_progress', seller_id)
        
        await query.edit_message_text(
            f"✅ Вы приняли сделку!\n\n"
            f"📋 ID: `{deal_id}`\n"
            f"💸 Сумма: {deal[3]} ₽\n"
            f"📝 Описание: {deal[4]}\n\n"
            f"⚠️ После выполнения условий сделки, попросите покупателя подтвердить выполнение."
        )
        
        # Уведомление покупателю
        try:
            await query.bot.send_message(
                chat_id=deal[1],  # buyer_id
                text=f"🎯 Ваша сделка `{deal_id}` принята продавцом!\n\n"
                     f"👤 Продавец: {query.from_user.first_name}\n"
                     f"💸 Сумма: {deal[3]} ₽\n\n"
                     f"Ожидайте выполнения условий сделки.",
                parse_mode='Markdown'
            )
        except:
            logger.warning(f"Не удалось уведомить покупателя {deal[1]}")
    
    async def cancel_deal(self, deal_id: str, user_id: int, query):
        deal = db.get_deal(deal_id)
        
        if not deal:
            await query.edit_message_text("❌ Сделка не найдена")
            return
        
        if deal[1] != user_id:  # Только создатель может отменить
            await query.edit_message_text("❌ Вы можете отменять только свои сделки")
            return
        
        if deal[5] != 'created':  # Можно отменять только созданные
            await query.edit_message_text("❌ Нельзя отменить сделку в процессе")
            return
        
        # Возврат средств
        db.update_balance(user_id, deal[3])  # amount
        db.update_deal_status(deal_id, 'cancelled')
        
        await query.edit_message_text(
            f"❌ Сделка отменена\n\n"
            f"📋 ID: `{deal_id}`\n"
            f"💸 Сумма {deal[3]} ₽ возвращена на ваш баланс\n"
            f"💳 Текущий баланс: {db.get_balance(user_id)} ₽"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 Используйте команды или кнопки меню:\n\n"
            "/start - Главное меню\n"
            "/balance - Проверить баланс\n" 
            "/deal - Создать сделку\n"
            "/deals - Мои сделки"
        )
    
    def run(self):
        logger.info("Запуск бота...")
        self.application.run_polling()

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не установлен!")
        exit(1)
        
    bot = GarantBot()
    bot.run()
