from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import random
import string
from datetime import datetime
from .database import JSONDatabase

class AuthManager:
    def __init__(self):
        self.db = JSONDatabase()
        self.verification_codes = {}  # временное хранение кодов
    
    async def start_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает процесс аутентификации"""
        user = update.effective_user
        
        print(f"🔐 Start auth requested by user {user.id} ({user.first_name})")
        
        # Проверяем, не авторизован ли уже пользователь
        if self.db.user_has_phone_verification(user.id):
            await update.message.reply_text("✅ Вы уже авторизованы! Ожидайте подтверждения от администратора группы.")
            return ConversationHandler.END
        
        # Запрашиваем номер телефона с кнопкой
        keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        message_text = (
            "🔐 **Авторизация**\n\n"
            "Для доступа к защищенным группам необходимо подтвердить номер телефона.\n\n"
            "Нажмите кнопку ниже 👇 чтобы поделиться номером телефона:"
        )
        
        try:
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            print(f"📱 Sent phone request with button to user {user.id}")
            return 'WAITING_PHONE'
        except Exception as e:
            print(f"❌ Error sending phone request to user {user.id}: {e}")
            await update.message.reply_text(
                "Произошла ошибка. Пожалуйста, попробуйте еще раз.",
                reply_markup=None
            )
            return ConversationHandler.END
    
    async def process_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает полученный номер телефона"""
        print(f"📞 Processing phone for user {update.effective_user.id}")
        
        if not update.message.contact:
            # Если пользователь отправил текст вместо контакта, просим использовать кнопку
            keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                "Пожалуйста, используйте кнопку '📱 Поделиться номером' для отправки номера телефона.",
                reply_markup=reply_markup
            )
            return 'WAITING_PHONE'
        
        contact = update.message.contact
        user = update.effective_user
        
        print(f"📞 Contact received from user {user.id}: {contact.phone_number}")
        
        # Проверяем, что контакт принадлежит пользователю
        if contact.user_id != user.id:
            keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            await update.message.reply_text(
                "Пожалуйста, поделитесь своим номером телефона, а не чужим.",
                reply_markup=reply_markup
            )
            return 'WAITING_PHONE'
        
        # Генерируем код подтверждения используя random вместо secrets
        code = ''.join(random.choice(string.digits) for _ in range(6))
        
        # Сохраняем код
        self.verification_codes[user.id] = {
            'code': code,
            'phone': contact.phone_number,
            'attempts': 0
        }
        
        # В реальном приложении здесь отправляется SMS
        message_text = (
            f"📲 **Подтверждение номера**\n\n"
            f"На номер *{contact.phone_number}* отправлен код подтверждения.\n\n"
            f"💡 *Для демонстрации:* код подтверждения: `{code}`\n\n"
            f"Введите полученный код:"
        )
        
        try:
            await update.message.reply_text(
                message_text,
                parse_mode='Markdown',
                reply_markup=None  # Убираем клавиатуру
            )
            print(f"📨 Sent verification code to user {user.id}")
            return 'WAITING_CODE'
        except Exception as e:
            print(f"❌ Error sending verification code to user {user.id}: {e}")
            await update.message.reply_text(
                "Произошла ошибка при отправке кода. Пожалуйста, попробуйте еще раз.",
                reply_markup=None
            )
            return ConversationHandler.END
    
    async def verify_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверяет введенный код"""
        user = update.effective_user
        entered_code = update.message.text.strip()
        
        print(f"🔢 Code verification for user {user.id}: {entered_code}")
        
        if user.id not in self.verification_codes:
            await update.message.reply_text("❌ Сессия устарела. Начните авторизацию заново: /start")
            return ConversationHandler.END
        
        verification = self.verification_codes[user.id]
        verification['attempts'] += 1
        
        if verification['attempts'] > 3:
            del self.verification_codes[user.id]
            await update.message.reply_text("❌ Слишком много попыток. Начните заново: /start")
            return ConversationHandler.END
        
        if entered_code == verification['code']:
            # Успешная верификация
            user_data = {
                'user_id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'phone_number': verification['phone'],
                'phone_verified': True,
                'verified_at': datetime.now().isoformat()
            }
            
            # Сохраняем пользователя
            self.db.save_user(user_data)
            
            # Обрабатываем ожидающие группы (теперь только уведомляем администратора)
            await self._notify_admins_about_verified_user(user_data, context)
            
            del self.verification_codes[user.id]
            
            success_message = (
                "✅ **Телефон успешно подтвержден!**\n\n"
                "Теперь администратор группы получил уведомление о вашей регистрации. "
                "После подтверждения администратора вы получите доступ к группе."
            )
            
            await update.message.reply_text(success_message, parse_mode='Markdown')
            print(f"✅ User {user.id} successfully verified phone")
            return ConversationHandler.END
        else:
            remaining_attempts = 3 - verification['attempts']
            error_message = f"❌ Неверный код. Осталось попыток: {remaining_attempts}"
            await update.message.reply_text(error_message)
            print(f"❌ User {user.id} entered wrong code, attempts left: {remaining_attempts}")
            return 'WAITING_CODE'
    
    async def _notify_admins_about_verified_user(self, user_data, context: ContextTypes.DEFAULT_TYPE):
        """Уведомляет администраторов о верифицированном пользователе"""
        from my_secrets import ADMIN_IDS
        
        # Получаем все группы, где пользователь ожидает
        all_groups = self.db.get_all_groups()
        pending_groups = []
        
        for group_id, group_data in all_groups.items():
            if str(user_data['user_id']) in group_data.get('pending_users', {}):
                pending_groups.append((group_id, group_data))
        
        print(f"📢 Notifying admins about verified user {user_data['user_id']} in {len(pending_groups)} groups")
        
        for group_id, group_data in pending_groups:
            message = (
                f"👤 **Новый пользователь прошел верификацию**\n\n"
                f"**Имя:** {user_data['first_name']} {user_data.get('last_name', '')}\n"
                f"**Username:** @{user_data.get('username', 'нет')}\n"
                f"**Телефон:** {user_data['phone_number']}\n"
                f"**Группа:** {group_data.get('title', group_id)}\n"
                f"**ID группы:** {group_id}"
            )
            
            # Обновляем статус пользователя в группе - теперь ожидает подтверждения админа
            group_data = self.db.get_group(group_id)
            if group_data and str(user_data['user_id']) in group_data.get('pending_users', {}):
                group_data['pending_users'][str(user_data['user_id'])]['phone_verified'] = True
                group_data['pending_users'][str(user_data['user_id'])]['awaiting_admin_approval'] = True
                self.db.save_group(group_id, group_data)
            
            for admin_id in ADMIN_IDS:
                try:
                    # Создаем клавиатуру с кнопками подтверждения
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{group_id}_{user_data['user_id']}"),
                            InlineKeyboardButton("❌ Отказать", callback_data=f"reject_{group_id}_{user_data['user_id']}")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await context.bot.send_message(
                        admin_id, 
                        message, 
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                    print(f"📨 Sent admin notification to {admin_id}")
                    
                    # Дополнительно отправляем подсказку про команды админа
                    help_message = (
                        "💡 *Подсказка для админа:*\n"
                        "Используйте /admin_help для просмотра всех команд администратора"
                    )
                    await context.bot.send_message(admin_id, help_message, parse_mode='Markdown')
                    
                except Exception as e:
                    print(f"❌ Error notifying admin {admin_id}: {e}")
    
    async def cancel_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменяет авторизацию"""
        user = update.effective_user
        if user.id in self.verification_codes:
            del self.verification_codes[user.id]
        
        await update.message.reply_text("❌ Авторизация отменена.")
        print(f"❌ Auth cancelled by user {user.id}")
        return ConversationHandler.END