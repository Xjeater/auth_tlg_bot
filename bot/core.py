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

        # Обработчик изменения названия группы
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_TITLE,
            self.group_manager.handle_group_title_update
        ))

        # Обработчик для ручного удаления пользователя администратором
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.LEFT_CHAT_MEMBER,
            self.group_manager.handle_admin_removal
        ))

        # Обработчик для отслеживания самостоятельного присоединения по ссылке И выхода из группы
        self.application.add_handler(ChatMemberHandler(
            self.group_manager.handle_chat_member_update,
            ChatMemberHandler.CHAT_MEMBER
        ))
        
        # Обработчик сообщений от пользователей - удаляет сообщения от неодобренных
        self.application.add_handler(MessageHandler(
            filters.ALL & filters.ChatType.GROUPS,
            self._handle_group_message
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
        # Проверяем что ADMIN_IDS это список или кортеж
        if isinstance(ADMIN_IDS, (list, tuple)):
            return user_id in ADMIN_IDS
        # Если это одно число (int)
        elif isinstance(ADMIN_IDS, int):
            return user_id == ADMIN_IDS
        else:
            print(f"⚠️ Warning: ADMIN_IDS has unexpected type: {type(ADMIN_IDS)}")
            return False
    
    async def _handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает сообщения в группах - удаляет от неодобренных пользователей"""
        if not update.message:
            return
        
        chat = update.effective_chat
        user = update.effective_user
        
        # Пропускаем сообщения от бота
        if user.id == context.bot.id:
            return
        
        # Пропускаем сообщения не из групп
        if chat.type not in ['group', 'supergroup']:
            return
        
        # Проверяем, одобрен ли пользователь
        is_approved = self.db.is_user_approved(chat.id, user.id)
        
        if not is_approved:
            # Пользователь не одобрен - удаляем сообщение
            try:
                await update.message.delete()
                print(f"🗑️ Deleted message from unapproved user {user.id} in group {chat.id}")
                
                # Предупреждаем пользователя (если возможно)
                try:
                    await context.bot.send_message(
                        chat_id=user.id,
                        text=f"⛔ Ваше сообщение в группе '{chat.title}' было удалено.\n"
                             f"Вы еще не получили доступ к отправке сообщений.\n"
                             f"Ожидайте одобрения администратора."
                    )
                except:
                    pass  # Не можем отправить ЛС - пропускаем
                    
            except Exception as e:
                print(f"❌ Could not delete message from user {user.id}: {e}")
    
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

📋 Ваши группы покажутся по команде /status

⚠️ Важно:
• Пока администратор не одобрит вас - вы не сможете отправлять сообщения
• Все ваши сообщения будут автоматически удаляться
• Ожидайте уведомления от бота об одобрении
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
• Сообщения неодобренных пользователей автоматически удаляются

⚙️ Требуемые права бота в группах:
✅ Ban users (банить пользователей)
✅ Delete messages (удалять сообщения)  
✅ Restrict members (ограничивать участников)
✅ Invite users via link (приглашать по ссылке)

📊 Мониторинг:
• Все новые участники автоматически ограничиваются
• Админы получают уведомления в реальном времени
• История решений сохраняется в базе данных
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
            f"   • /stats - эта статистика\n\n"
            
            f"💡 Система работает:\n"
            f"   • Автоограничение новых участников\n"
            f"   • Удаление сообщений неодобренных\n"
            f"   • Уведомления админам в реальном времени"
        )
        
        await update.message.reply_text(stats_text)
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        print(f"Exception while handling an update: {context.error}")
        import traceback
        traceback.print_exc()  # Добавляем трейсбек для отладки
    
    def run(self):
        """Запускает бота"""
        self.application.run_polling()