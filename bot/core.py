from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
from .auth import AuthManager
from .group_manager import GroupManager
from .database import JSONDatabase
from config import MESSAGES

class TelegramAuthBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.db = JSONDatabase()
        self.auth_manager = AuthManager()
        self.group_manager = GroupManager(self.auth_manager)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        
        # Обработчик начала авторизации
        auth_conversation = ConversationHandler(
            entry_points=[CommandHandler('start', self.auth_manager.start_auth)],
            states={
                'WAITING_PHONE': [
                    MessageHandler(filters.CONTACT, self.auth_manager.process_phone),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_during_phone)
                ],
                'WAITING_CODE': [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.auth_manager.verify_code)
                ]
            },
            fallbacks=[CommandHandler('cancel', self.auth_manager.cancel_auth)]
        )
        
        # Обработчики групп
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            self.group_manager.handle_new_chat_member
        ))
        
        # Обработчик callback запросов (кнопки подтверждения)
        self.application.add_handler(CallbackQueryHandler(
            self._handle_callback_query,
            pattern=".*"  # Обрабатываем все callback
        ))
        
        # Обработчики команд
        self.application.add_handler(auth_conversation)
        self.application.add_handler(CommandHandler('help', self._help_command))
        self.application.add_handler(CommandHandler('status', self._status_command))
        
        # Обработчик ошибок
        self.application.add_error_handler(self._error_handler)
    
    async def _handle_text_during_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текст во время ожидания номера телефона"""
        # Просим использовать кнопку для отправки номера
        from telegram import ReplyKeyboardMarkup, KeyboardButton
        
        keyboard = [[KeyboardButton("📱 Поделиться номером", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "Пожалуйста, используйте кнопку '📱 Поделиться номером' для отправки номера телефона.",
            reply_markup=reply_markup
        )
        return 'WAITING_PHONE'
    
    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов"""
        await self.group_manager.handle_callback_query(update, context)
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
🤖 Бот авторизации для Telegram групп

Основные команды:
/start - Начать процесс авторизации
/status - Проверить статус авторизации  
/cancel - Отменить текущую операцию
/help - Показать эту справку

Процесс регистрации:
1. Присоединитесь к группе
2. Авторизуйтесь через бота (/start)
3. Ожидайте подтверждения администратора
4. После подтверждения получите доступ к группе
        """
        await update.message.reply_text(help_text)
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        user = update.effective_user
        user_data = self.db.get_user(user.id)
        
        if user_data and user_data.get('phone_verified'):
            status_text = "✅ Ваш телефон подтвержден!"
            
            # Показываем группы, где пользователь участник
            groups = self.db.get_all_groups()
            user_groups = []
            
            for group_id, group_data in groups.items():
                if str(user.id) in group_data.get('members', {}):
                    user_groups.append(f"• {group_data.get('title', group_id)} (активен)")
                elif str(user.id) in group_data.get('pending_users', {}):
                    pending_data = group_data['pending_users'][str(user.id)]
                    if pending_data.get('awaiting_admin_approval'):
                        user_groups.append(f"• {group_data.get('title', group_id)} (ожидает подтверждения админа)")
                    else:
                        user_groups.append(f"• {group_data.get('title', group_id)} (требуется авторизация)")
            
            if user_groups:
                status_text += "\n\n📋 Ваши группы:\n" + "\n".join(user_groups)
            else:
                status_text += "\n\n📋 Вы не состоите ни в одной группе."
                
        else:
            status_text = "❌ Ваш телефон не подтвержден. Используйте /start для авторизации."
        
        await update.message.reply_text(status_text)
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        print(f"Exception while handling an update: {context.error}")
    
    def run(self):
        """Запускает бота"""
        print("🤖 Бот запущен...")
        self.application.run_polling()