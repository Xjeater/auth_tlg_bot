from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from datetime import datetime
from .database import JSONDatabase
from config import BOT_SETTINGS, MESSAGES
import asyncio

class GroupManager:
    def __init__(self, auth_manager):
        self.db = JSONDatabase()
        self.auth_manager = auth_manager
        self.pending_tasks = {}  # Словарь для отслеживания задач таймаута
    
    async def handle_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает обновления статуса участников чата"""
        if not update.chat_member:
            return
        
        chat = update.chat_member.chat
        new_status = update.chat_member.new_chat_member.status
        old_status = update.chat_member.old_chat_member.status
        user = update.chat_member.new_chat_member.user
        
        # Пропускаем обновления, не связанные с присоединением к группе
        if chat.type not in ['group', 'supergroup']:
            return
        
        # Пропускаем бота
        if user.id == context.bot.id:
            return
        
        # Проверяем, присоединился ли пользователь к группе
        # (новый статус: 'member', старый статус: 'left' или 'kicked')
        if new_status == 'member' and old_status in ['left', 'kicked']:
            await self._process_new_member(chat, user, context)
    
    async def handle_new_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает новых участников чата (для обратной совместимости)"""
        if not update.message or not update.message.new_chat_members:
            return
        
        chat = update.effective_chat
        if chat.type not in ['group', 'supergroup']:
            return
        
        for new_member in update.message.new_chat_members:
            # Пропускаем бота
            if new_member.id == context.bot.id:
                continue
            
            await self._process_new_member(chat, new_member, context)
    
    async def _process_new_member(self, chat, user, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нового участника (общая функция для всех случаев присоединения)"""
        # Создаем/получаем данные группы
        group_data = self.db.get_group(chat.id)
        if not group_data:
            self.db.create_group(chat.id, chat.title)
        
        user_data = {
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'joined_at': datetime.now().isoformat(),
            'phone_verified': False,
            'awaiting_admin_approval': False,
            'join_method': 'unknown'  # Можно добавить логику определения метода присоединения
        }
        
        print(f"👤 New member {user.id} ({user.first_name}) joined group {chat.id}")
        
        # Проверяем, не находится ли пользователь уже в группе
        existing_members = self.db.get_group_members(chat.id)
        if str(user.id) in existing_members:
            print(f"ℹ️ User {user.id} is already a member of group {chat.id}")
            return
        
        # Проверяем, не находится ли пользователь уже в ожидании
        existing_pending = self.db.get_pending_users(chat.id)
        if str(user.id) in existing_pending:
            print(f"ℹ️ User {user.id} is already pending in group {chat.id}")
            return
        
        # Добавляем в ожидание (независимо от того, авторизован ли пользователь)
        self.db.add_pending_user(chat.id, user.id, user_data)
        await self._restrict_member_permissions(chat.id, user.id, context)
        
        # ОБЯЗАТЕЛЬНО отправляем инструкции по авторизации
        await self._send_auth_instructions(chat.id, user, context)
        
        # Если пользователь уже авторизован, сразу уведомляем администратора
        if self.db.user_has_phone_verification(user.id):
            user_full_data = self.db.get_user(user.id)
            if user_full_data:
                await self._notify_admins_about_verified_user(chat.id, user_full_data, context)
        else:
            # Запускаем таймер удаления только для неавторизованных
            task_key = f"{chat.id}_{user.id}"
            # Отменяем предыдущую задачу, если она существует
            if task_key in self.pending_tasks:
                self.pending_tasks[task_key].cancel()
            
            self.pending_tasks[task_key] = asyncio.create_task(
                self._schedule_user_removal(chat.id, user.id, context)
            )
            print(f"⏰ Started timeout task for user {user.id} in group {chat.id}")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback от кнопок подтверждения"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        print(f"🔔 Callback received: {data} from user {user_id}")
        
        # Проверяем, что это администратор
        from my_secrets import ADMIN_IDS
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ У вас нет прав для выполнения этого действия.")
            return
        
        if data.startswith('approve_'):
            # Формат: approve_groupId_userId
            parts = data.split('_')
            if len(parts) == 3:
                group_id = parts[1]
                target_user_id = int(parts[2])
                await self._approve_user(group_id, target_user_id, context, query)
            else:
                await query.edit_message_text("❌ Ошибка в формате данных.")
        
        elif data.startswith('reject_'):
            # Формат: reject_groupId_userId
            parts = data.split('_')
            if len(parts) == 3:
                group_id = parts[1]
                target_user_id = int(parts[2])
                await self._reject_user(group_id, target_user_id, context, query)
            else:
                await query.edit_message_text("❌ Ошибка в формате данных.")
        else:
            await query.edit_message_text("❌ Неизвестная команда.")
    
    async def _approve_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Подтверждает пользователя в группе"""
        try:
            print(f"🔄 Approving user {user_id} in group {group_id}")
            
            group_data = self.db.get_group(group_id)
            user_data = self.db.get_user(user_id)
            
            if not group_data:
                await query.edit_message_text("❌ Ошибка: группа не найдена.")
                return
            
            if not user_data:
                await query.edit_message_text("❌ Ошибка: пользователь не найден.")
                return
            
            # Добавляем пользователя как одобренного
            approval_data = {
                **user_data,
                'approved_by': query.from_user.id,
                'approved_at': datetime.now().isoformat()
            }
            
            if self.db.approve_user(group_id, user_id, approval_data):
                # Даем права в группе
                await self._grant_member_permissions(group_id, user_id, context)
                
                # Отменяем задачу таймаута если она есть
                await self._cancel_pending_removal(group_id, user_id)
                
                # Уведомляем пользователя
                try:
                    group_title = group_data.get('title', 'группе')
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Администратор подтвердил вашу регистрацию в группе '{group_title}'! Теперь вы можете писать сообщения."
                    )
                    print(f"📨 Notified user {user_id} about approval")
                except Exception as e:
                    print(f"Error notifying user {user_id}: {e}")
                
                # Обновляем сообщение администратора
                new_text = f"✅ Пользователь {user_data['first_name']} подтвержден в группе '{group_data.get('title', group_id)}'"
                await query.edit_message_text(new_text)
                
                print(f"✅ User {user_id} approved by admin in group {group_id}")
            else:
                await query.edit_message_text("❌ Ошибка при подтверждении пользователя.")
                
        except Exception as e:
            print(f"❌ Error approving user: {e}")
            await query.edit_message_text(f"❌ Ошибка при подтверждении пользователя: {str(e)}")
    
    async def _reject_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Отклоняет пользователя"""
        try:
            print(f"🔄 Rejecting user {user_id} from group {group_id}")
            
            group_data = self.db.get_group(group_id)
            user_data = self.db.get_user(user_id)
            
            if not group_data:
                await query.edit_message_text("❌ Ошибка: группа не найдена.")
                return
            
            # Удаляем пользователя из группы и из базы
            await self._remove_user_from_group(group_id, user_id, context)
            
            # Уведомляем пользователя
            try:
                group_title = group_data.get('title', 'группе')
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Администратор отклонил вашу регистрацию в группе '{group_title}'."
                )
                print(f"📨 Notified user {user_id} about rejection")
            except Exception as e:
                print(f"Error notifying user {user_id}: {e}")
            
            # Обновляем сообщение администратора
            user_name = user_data['first_name'] if user_data else "Пользователь"
            new_text = f"❌ Регистрация пользователя {user_name} отклонена в группе '{group_data.get('title', group_id)}'"
            await query.edit_message_text(new_text)
            
            print(f"❌ User {user_id} rejected by admin in group {group_id}")
            
        except Exception as e:
            print(f"❌ Error rejecting user: {e}")
            await query.edit_message_text(f"❌ Ошибка при отклонении пользователя: {str(e)}")
    
    async def _remove_user_from_group(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет пользователя из группы и из базы данных"""
        try:
            print(f"🔄 Removing user {user_id} from group {group_id} and database")
            
            # Кикаем пользователя из группы
            await context.bot.ban_chat_member(group_id, user_id)
            await asyncio.sleep(1)
            await context.bot.unban_chat_member(group_id, user_id)
            
            # Удаляем пользователя из всех данных
            await self._cleanup_user_data(group_id, user_id)
            
            print(f"✅ User {user_id} completely removed from group {group_id}")
            
        except Exception as e:
            print(f"❌ Error removing user {user_id}: {e}")
            raise
    
    async def _cleanup_user_data(self, group_id, user_id):
        """Полностью очищает данные пользователя"""
        try:
            # 1. Удаляем из ожидания в группе
            self.db.remove_pending_user(group_id, user_id)
            
            # 2. Удаляем из участников группы (если был одобрен)
            group_data = self.db.get_group(group_id)
            if group_data and str(user_id) in group_data.get('members', {}):
                del group_data['members'][str(user_id)]
                self.db.save_group(group_id, group_data)
                print(f"🗑️ Removed user {user_id} from members of group {group_id}")
            
            # 3. Удаляем файл пользователя (полностью из базы)
            self.db.delete_user(user_id)
            
            # 4. Отменяем задачу таймаута
            await self._cancel_pending_removal(group_id, user_id)
            
            print(f"✅ Completely cleaned up data for user {user_id}")
            
        except Exception as e:
            print(f"❌ Error cleaning up user data {user_id}: {e}")
    
    async def _cancel_pending_removal(self, group_id, user_id):
        """Отменяет задачу удаления пользователя"""
        task_key = f"{group_id}_{user_id}"
        if task_key in self.pending_tasks:
            task = self.pending_tasks[task_key]
            task.cancel()
            try:
                await task  # Ждем завершения отмены
            except asyncio.CancelledError:
                pass
            del self.pending_tasks[task_key]
            print(f"🛑 Cancelled removal task for user {user_id} in group {group_id}")
    
    async def _restrict_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Ограничивает права пользователя"""
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions={
                    'can_send_messages': False,
                    'can_send_media_messages': False,
                    'can_send_other_messages': False,
                    'can_add_web_page_previews': False,
                    'can_send_polls': False,
                    'can_invite_users': False,
                    'can_pin_messages': False,
                    'can_change_info': False
                }
            )
            print(f"🔒 Restricted user {user_id} in group {group_id}")
        except Exception as e:
            print(f"❌ Error restricting user {user_id}: {e}")
    
    async def _grant_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Дает полные права пользователю"""
        try:
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions={
                    'can_send_messages': True,
                    'can_send_media_messages': True,
                    'can_send_other_messages': True,
                    'can_add_web_page_previews': True,
                    'can_send_polls': True,
                    'can_invite_users': True,
                    'can_pin_messages': False,
                    'can_change_info': False
                }
            )
            print(f"🔓 Granted permissions to user {user_id} in group {group_id}")
        except Exception as e:
            print(f"❌ Error granting permissions to user {user_id}: {e}")
    
    async def _send_auth_instructions(self, group_id, user, context: ContextTypes.DEFAULT_TYPE):
        """Отправляет инструкции по авторизации"""
        try:
            # Создаем клавиатуру с кнопкой для начала авторизации
            start_link = f"https://t.me/{context.bot.username}?start=auth"
            
            message = (
                "🔒 **Требуется авторизация**\n\n"
                f"Привет, {user.first_name}!\n\n"
                "Для доступа к этой группе необходимо пройти авторизацию по номеру телефона.\n\n"
                "Чтобы начать авторизацию:\n"
                "1. Нажмите на эту ссылку: 👇\n"
                f"2. Или напишите боту @{context.bot.username} команду /start\n\n"
                "После авторизации ожидайте подтверждения администратора."
            )
            
            # Отправляем сообщение с инструкциями
            await context.bot.send_message(
                chat_id=user.id,
                text=message,
                parse_mode='Markdown'
            )
            print(f"📨 Sent auth instructions to user {user.id}")
            
            # Дополнительно отправляем сообщение с кнопкой для быстрого старта
            keyboard = [[KeyboardButton("🔐 Начать авторизацию", url=start_link)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            
            quick_start_message = (
                "🚀 **Быстрый старт**\n\n"
                "Нажмите кнопку ниже чтобы сразу перейти к авторизации:"
            )
            
            await context.bot.send_message(
                chat_id=user.id,
                text=quick_start_message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            print(f"📱 Sent quick start button to user {user.id}")
            
        except Exception as e:
            print(f"❌ Could not send DM to user {user.id}: {e}")
            
            # Если не удалось отправить ЛС, отправляем в группу
            try:
                message = (
                    f"{user.first_name}, для доступа к группе необходимо авторизоваться. "
                    f"Напишите мне в личные сообщения @{context.bot.username} и используйте команду /start"
                )
                await context.bot.send_message(
                    chat_id=group_id,
                    text=message
                )
                print(f"📨 Sent group auth instructions for user {user.id}")
            except Exception as e2:
                print(f"❌ Could not send group message: {e2}")
    
    async def _notify_admins_about_verified_user(self, group_id, user_data, context: ContextTypes.DEFAULT_TYPE):
        """Уведомляет администраторов о верифицированном пользователе"""
        from my_secrets import ADMIN_IDS
        
        group_data = self.db.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for admin notification")
            return
        
        message = (
            f"👤 **Новый пользователь прошел верификацию**\n\n"
            f"**Имя:** {user_data['first_name']} {user_data.get('last_name', '')}\n"
            f"**Username:** @{user_data.get('username', 'нет')}\n"
            f"**Телефон:** {user_data['phone_number']}\n"
            f"**Группа:** {group_data.get('title', group_id)}\n"
            f"**ID группы:** {group_id}"
        )
        
        # Обновляем статус пользователя в группе
        group_data = self.db.get_group(group_id)
        if group_data and str(user_data['user_id']) in group_data.get('pending_users', {}):
            group_data['pending_users'][str(user_data['user_id'])]['phone_verified'] = True
            group_data['pending_users'][str(user_data['user_id'])]['awaiting_admin_approval'] = True
            self.db.save_group(group_id, group_data)
            print(f"📝 Updated user {user_data['user_id']} status in group {group_id}")
        
        for admin_id in ADMIN_IDS:
            try:
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
                print(f"📨 Sent approval request to admin {admin_id}")
            except Exception as e:
                print(f"❌ Error notifying admin {admin_id}: {e}")
    
    async def _schedule_user_removal(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Планирует удаление пользователя по таймауту"""
        try:
            print(f"⏰ Waiting {BOT_SETTINGS['auth_timeout']} seconds for user {user_id} in group {group_id}")
            await asyncio.sleep(BOT_SETTINGS['auth_timeout'])
            
            # Проверяем, авторизовался ли пользователь
            group_data = self.db.get_group(group_id)
            if group_data and str(user_id) in group_data.get('pending_users', {}):
                user_data = group_data['pending_users'][str(user_id)]
                if not user_data.get('phone_verified', False):
                    print(f"⏰ Timeout reached for user {user_id} in group {group_id} - removing...")
                    await self._remove_user_from_group(group_id, user_id, context)
                else:
                    print(f"✅ User {user_id} in group {group_id} verified but awaiting admin approval")
            else:
                print(f"✅ User {user_id} in group {group_id} was approved before timeout")
                
        except asyncio.CancelledError:
            print(f"🛑 Removal task cancelled for user {user_id} in group {group_id}")