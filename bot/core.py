from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ChatMemberHandler
from .group_manager import GroupManager
from .database import JSONDatabase
from config import MESSAGES
from my_secrets import ADMIN_IDS

class TelegramAuthBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.db = JSONDatabase()
        self.group_manager = GroupManager()
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        
        # Обработчики групп
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS,
            self.group_manager.handle_new_chat_member
        ))
        
        # Обработчик для отслеживания самостоятельного присоединения по ссылке
        self.application.add_handler(ChatMemberHandler(
            self.group_manager.handle_chat_member_update,
            ChatMemberHandler.CHAT_MEMBER
        ))
        
        # Обработчик callback запросов (кнопки разрешить/запретить)
        self.application.add_handler(CallbackQueryHandler(
            self._handle_callback_query,
            pattern=".*"  # Обрабатываем все callback
        ))
        
        # Обработчики команд для всех пользователей
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
    
    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов"""
        await self.group_manager.handle_callback_query(update, context)
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help для всех пользователей"""
        help_text = """
🤖 Бот авторизации для Telegram групп

Процесс регистрации:
1. Присоединитесь к группе
2. Ожидайте подтверждения администратора
3. После подтверждения получите доступ к группе

Команды:
/help - Показать эту справку
/status - Проверить статус в группах
        """
        await update.message.reply_text(help_text)
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status для всех пользователей"""
        user = update.effective_user
        
        # Показываем группы, где пользователь участник
        groups = self.db.get_all_groups()
        user_groups = []
        
        for group_id, group_data in groups.items():
            if str(user.id) in group_data.get('members', {}):
                user_groups.append(f"• {group_data.get('title', group_id)} (✅ одобрен)")
            elif str(user.id) in group_data.get('pending_users', {}):
                user_groups.append(f"• {group_data.get('title', group_id)} (⏳ ожидает одобрения)")
        
        if user_groups:
            status_text = "📋 Ваши группы:\n" + "\n".join(user_groups)
        else:
            status_text = "📋 Вы не состоите ни в одной группе с этим ботом."
        
        await update.message.reply_text(status_text)
    
    async def _admin_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /admin_help для администраторов"""
        user = update.effective_user
        
        if not self._is_admin(user.id):
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
        
        admin_help_text = """
🛠️ Панель администратора

📋 Основные команды:
/admin_help - Показать эту справку
/admin_status - Статус всех групп
/stats - Статистика по пользователям

👥 Управление пользователями:
• Автоматически получаете уведомления о новых пользователях
• Используйте кнопки "✅ Разрешить" и "❌ Запретить"
• Пользователи не смогут писать пока не будут одобрены

⚙️ Права бота в группах:
• Ban users
• Delete messages  
• Restrict members
• Invite users via link
        """
        
        await update.message.reply_text(admin_help_text)
    
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
        
        status_text = "📊 Статус всех групп\n\n"
        
        for group_id, group_data in all_groups.items():
            group_title = group_data.get('title', 'Без названия')
            members_count = len(group_data.get('members', {}))
            pending_count = len(group_data.get('pending_users', {}))
            
            status_text += f"🏷️ {group_title}\n"
            status_text += f"   ID: {group_id}\n"
            status_text += f"   ✅ Одобрено: {members_count}\n"
            status_text += f"   ⏳ Ожидают: {pending_count}\n\n"
        
        await update.message.reply_text(status_text)
    
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
        
        for group_data in all_groups.values():
            total_members += len(group_data.get('members', {}))
            total_pending += len(group_data.get('pending_users', {}))
        
        stats_text = (
            "📈 Статистика системы\n\n"
            f"📊 Группы:\n"
            f"   • Всего групп: {total_groups}\n"
            f"   • Одобрено пользователей: {total_members}\n"
            f"   • Ожидают одобрения: {total_pending}\n\n"
            
            f"⚡ Команды админа:\n"
            f"   • /admin_status - статус групп\n"
            f"   • /admin_help - справка\n"
            f"   • /stats - эта статистика"
        )
        
        await update.message.reply_text(stats_text)
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        print(f"Exception while handling an update: {context.error}")
    
    def run(self):
        """Запускает бота"""
        self.application.run_polling()