from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes, CallbackQueryHandler
from .auth import AuthManager
from .group_manager import GroupManager
from .database import JSONDatabase
from config import MESSAGES
from my_secrets import ADMIN_IDS

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
        
        # Обработчики команд для всех пользователей
        self.application.add_handler(auth_conversation)
        self.application.add_handler(CommandHandler('help', self._help_command))
        self.application.add_handler(CommandHandler('status', self._status_command))
        
        # Обработчики команд только для администраторов
        self.application.add_handler(CommandHandler('admin_help', self._admin_help_command))
        self.application.add_handler(CommandHandler('admin_status', self._admin_status_command))
        self.application.add_handler(CommandHandler('stats', self._admin_stats_command))
        
        # Обработчик ошибок
        self.application.add_error_handler(self._error_handler)
    
    def _is_admin(self, user_id):
        """Проверяет, является ли пользователь администратором"""
        return user_id in ADMIN_IDS
    
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
        """Обработчик команды /help для всех пользователей"""
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
        """Обработчик команды /status для всех пользователей"""
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
    
    async def _admin_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /admin_help для администраторов"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        admin_help_text = """
🛠️ **Панель администратора**

**Основные команды:**
/admin_help - Показать эту справку
/admin_status - Статус всех групп
/stats - Статистика по пользователям

**Управление пользователями:**
• Автоматически получаете уведомления о новых пользователях
• Используйте кнопки "✅ Подтвердить" и "❌ Отказать"
• Пользователи удаляются автоматически через 2 минуты без авторизации

**Права бота в группах:**
• Ban users
• Delete messages  
• Restrict members
• Invite users via link
        """
        
        await update.message.reply_text(admin_help_text, parse_mode='Markdown')
    
    async def _admin_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /admin_status для администраторов"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        all_groups = self.db.get_all_groups()
        
        if not all_groups:
            await update.message.reply_text("📊 Бот еще не добавлен ни в одну группу.")
            return
        
        status_text = "📊 **Статус всех групп**\n\n"
        
        for group_id, group_data in all_groups.items():
            group_title = group_data.get('title', 'Без названия')
            members_count = len(group_data.get('members', {}))
            pending_count = len(group_data.get('pending_users', {}))
            
            # Считаем ожидающих подтверждения админа
            awaiting_admin = 0
            for user_data in group_data.get('pending_users', {}).values():
                if user_data.get('awaiting_admin_approval'):
                    awaiting_admin += 1
            
            status_text += f"**{group_title}**\n"
            status_text += f"├ ID: `{group_id}`\n"
            status_text += f"├ Участников: {members_count}\n"
            status_text += f"├ Ожидают авторизации: {pending_count - awaiting_admin}\n"
            status_text += f"└ Ожидают подтверждения: {awaiting_admin}\n\n"
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def _admin_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats для администраторов"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        all_groups = self.db.get_all_groups()
        
        # Собираем статистику
        total_groups = len(all_groups)
        total_members = 0
        total_pending = 0
        total_awaiting_admin = 0
        
        # Получаем всех пользователей
        users_dir = self.db.users_dir
        total_users = 0
        verified_users = 0
        
        import os
        if os.path.exists(users_dir):
            for filename in os.listdir(users_dir):
                if filename.endswith('.json'):
                    total_users += 1
                    user_id = filename[:-5]  # удаляем .json
                    user_data = self.db.get_user(user_id)
                    if user_data and user_data.get('phone_verified'):
                        verified_users += 1
        
        for group_data in all_groups.values():
            total_members += len(group_data.get('members', {}))
            total_pending += len(group_data.get('pending_users', {}))
            
            for user_data in group_data.get('pending_users', {}).values():
                if user_data.get('awaiting_admin_approval'):
                    total_awaiting_admin += 1
        
        stats_text = (
            "📈 **Статистика системы**\n\n"
            f"**Группы:**\n"
            f"• Всего групп: {total_groups}\n"
            f"• Участников: {total_members}\n"
            f"• Ожидают авторизации: {total_pending - total_awaiting_admin}\n"
            f"• Ожидают подтверждения: {total_awaiting_admin}\n\n"
            
            f"**Пользователи:**\n"
            f"• Всего в системе: {total_users}\n"
            f"• С подтвержденным телефоном: {verified_users}\n"
            f"• Не подтвержденных: {total_users - verified_users}\n\n"
            
            f"**Команды админа:**\n"
            f"• `/admin_status` - статус групп\n"
            f"• `/admin_help` - справка\n"
            f"• `/stats` - эта статистика"
        )
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        print(f"Exception while handling an update: {context.error}")
    
    def run(self):
        """Запускает бота"""
        self.application.run_polling()