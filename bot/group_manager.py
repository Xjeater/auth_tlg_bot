from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from .database import JSONDatabase
import asyncio

class GroupManager:
    def __init__(self):
        self.db = JSONDatabase()
    
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
        
        # Создаем данные пользователя
        user_data = {
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'joined_at': datetime.now().isoformat()
        }
        
        print(f"👤 New member {user.id} ({user.first_name}) joined group {chat.id}")
        
        # Добавляем в ожидание
        self.db.add_pending_user(chat.id, user.id, user_data)
        
        # 1. Сначала сразу ограничиваем права
        try:
            await self._restrict_member_permissions(chat.id, user.id, context)
            print(f"🔒 Immediately restricted user {user.id}")
        except Exception as e:
            print(f"⚠️ Could not restrict immediately: {e}")
        
        # 2. Затем через небольшую задержку еще раз ограничиваем (на случай, если первое не сработало)
        asyncio.create_task(self._delayed_restriction(chat.id, user.id, context))
        
        # 3. Уведомляем администратора
        await self._notify_admin_about_new_user(chat.id, user_data, context)
        
        # 4. Отправляем пользователю сообщение, что нужно ждать одобрения
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"👋 Привет, {user.first_name}! Ты присоединился к группе '{chat.title}'.\n\n"
                     f"📝 Твоя заявка отправлена администратору. Пожалуйста, ожидай одобрения."
            )
        except Exception as e:
            print(f"⚠️ Could not send DM to user {user.id}: {e}")
    
    async def _delayed_restriction(self, group_id, user_id, context):
        """Повторное ограничение прав через задержку"""
        await asyncio.sleep(2)  # Ждем 2 секунды
        try:
            await self._restrict_member_permissions(group_id, user_id, context)
            print(f"🔒 Delayed restriction applied for user {user_id}")
        except Exception as e:
            print(f"❌ Failed delayed restriction for user {user_id}: {e}")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback от кнопок разрешить/запретить"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        admin_id = query.from_user.id
        
        print(f"🔔 Callback received: {data} from user {admin_id}")
        
        # Проверяем, что это администратор
        from my_secrets import ADMIN_IDS
        if admin_id not in ADMIN_IDS:
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
        """Разрешает пользователю писать в группе"""
        try:
            print(f"🔄 Approving user {user_id} in group {group_id}")
            
            group_data = self.db.get_group(group_id)
            
            if not group_data:
                await query.edit_message_text("❌ Ошибка: группа не найдена.")
                return
            
            # Получаем данные пользователя из ожидания
            pending_users = group_data.get('pending_users', {})
            if str(user_id) not in pending_users:
                # Проверяем, может пользователь уже одобрен
                if str(user_id) in group_data.get('members', {}):
                    await query.edit_message_text(f"ℹ️ Пользователь уже одобрен в этой группе.")
                    return
                await query.edit_message_text("❌ Ошибка: пользователь не найден в ожидании.")
                return
            
            user_data = pending_users[str(user_id)]
            
            # Добавляем пользователя как одобренного
            approval_data = {
                **user_data,
                'approved_by': query.from_user.id,
                'approved_at': datetime.now().isoformat()
            }
            
            # Сохраняем как одобренного
            group_data['members'][str(user_id)] = approval_data
            
            # Удаляем из ожидания
            del group_data['pending_users'][str(user_id)]
            
            # Сохраняем изменения
            if self.db.save_group(group_id, group_data):
                # Даем права на отправку сообщений
                await self._grant_member_permissions(group_id, user_id, context)
                
                # Уведомляем пользователя
                try:
                    group_title = group_data.get('title', 'группе')
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Администратор одобрил вашу заявку! Теперь вы можете писать в группе '{group_title}'."
                    )
                    print(f"📨 Notified user {user_id} about approval")
                except Exception as e:
                    print(f"Error notifying user {user_id}: {e}")
                
                # Обновляем сообщение администратора
                new_text = f"✅ Пользователь {user_data['first_name']} одобрен в группе '{group_data.get('title', group_id)}'"
                await query.edit_message_text(new_text)
                
                print(f"✅ User {user_id} approved by admin in group {group_id}")
            else:
                await query.edit_message_text("❌ Ошибка при сохранении данных.")
                
        except Exception as e:
            print(f"❌ Error approving user: {e}")
            await query.edit_message_text(f"❌ Ошибка при разрешении пользователя: {str(e)}")
    
    async def _reject_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Запрещает пользователю доступ к группе и удаляет все его данные"""
        try:
            print(f"🔄 Rejecting user {user_id} from group {group_id}")
            
            group_data = self.db.get_group(group_id)
            
            if not group_data:
                await query.edit_message_text("❌ Ошибка: группа не найдена.")
                return
            
            # Получаем данные пользователя
            pending_users = group_data.get('pending_users', {})
            user_name = "Пользователь"
            if str(user_id) in pending_users:
                user_name = pending_users[str(user_id)].get('first_name', 'Пользователь')
            
            # 1. Удаляем пользователя из группы
            await self._remove_user_from_group(group_id, user_id, context)
            
            # 2. Полностью очищаем все данные пользователя
            await self._cleanup_all_user_data(group_id, user_id)
            
            # Обновляем сообщение администратора
            new_text = f"❌ Пользователь {user_name} удален из группы '{group_data.get('title', group_id)}'"
            await query.edit_message_text(new_text)
            
            print(f"❌ User {user_id} rejected and all data cleaned up from group {group_id}")
            
        except Exception as e:
            print(f"❌ Error rejecting user: {e}")
            await query.edit_message_text(f"❌ Ошибка при запрете пользователя: {str(e)}")
    
    async def _remove_user_from_group(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет пользователя из группы"""
        try:
            print(f"🔄 Removing user {user_id} from group {group_id}")
            
            # Кикаем пользователя из группы
            await context.bot.ban_chat_member(group_id, user_id)
            await asyncio.sleep(1)
            await context.bot.unban_chat_member(group_id, user_id)
            
            print(f"✅ User {user_id} removed from group {group_id}")
            
        except Exception as e:
            print(f"❌ Error removing user {user_id} from group: {e}")
    
    async def _cleanup_all_user_data(self, group_id, user_id):
        """Полностью очищает ВСЕ данные пользователя из системы"""
        try:
            print(f"🧹 Cleaning up ALL data for user {user_id}")
            
            # 1. Удаляем пользователя из данных группы
            group_data = self.db.get_group(group_id)
            if group_data:
                # Удаляем из ожидания
                if str(user_id) in group_data.get('pending_users', {}):
                    del group_data['pending_users'][str(user_id)]
                    print(f"  🗑️ Removed from pending users of group {group_id}")
                
                # Удаляем из участников (если был одобрен)
                if str(user_id) in group_data.get('members', {}):
                    del group_data['members'][str(user_id)]
                    print(f"  🗑️ Removed from members of group {group_id}")
                
                # Сохраняем изменения в группе
                if self.db.save_group(group_id, group_data):
                    print(f"  💾 Saved updated group data for {group_id}")
            
            # 2. Удаляем файл пользователя из пользовательской базы (если существует)
            try:
                import os
                from config import BOT_SETTINGS
                
                users_dir = BOT_SETTINGS['users_directory']
                user_file = os.path.join(users_dir, f"{user_id}.json")
                
                if os.path.exists(user_file):
                    os.remove(user_file)
                    print(f"  🗑️ Deleted user file: {user_file}")
                else:
                    print(f"  ℹ️ User file not found: {user_file}")
            except Exception as e:
                print(f"  ⚠️ Could not delete user file: {e}")
            
            print(f"✅ All data for user {user_id} has been cleaned up")
            
        except Exception as e:
            print(f"❌ Error cleaning up all user data {user_id}: {e}")
    
    async def _restrict_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Ограничивает права пользователя - нельзя отправлять сообщения"""
        try:
            # Более строгое ограничение прав
            permissions = {
                'can_send_messages': False,
                'can_send_media_messages': False,
                'can_send_other_messages': False,
                'can_add_web_page_previews': False,
                'can_send_polls': False,
                'can_invite_users': False,
                'can_pin_messages': False,
                'can_change_info': False,
                'can_send_audios': False,
                'can_send_documents': False,
                'can_send_photos': False,
                'can_send_videos': False,
                'can_send_video_notes': False,
                'can_send_voice_notes': False
            }
            
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=permissions,
                until_date=int(datetime.now().timestamp()) + 86400  # на 24 часа
            )
            print(f"🔒 Restricted user {user_id} in group {group_id}")
        except Exception as e:
            print(f"❌ Error restricting user {user_id}: {e}")
            raise
    
    async def _grant_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Дает права на отправку сообщений пользователю"""
        try:
            # Полные права на отправку сообщений
            permissions = {
                'can_send_messages': True,
                'can_send_media_messages': True,
                'can_send_other_messages': True,
                'can_add_web_page_previews': True,
                'can_send_polls': True,
                'can_invite_users': True,
                'can_pin_messages': False,
                'can_change_info': False,
                'can_send_audios': True,
                'can_send_documents': True,
                'can_send_photos': True,
                'can_send_videos': True,
                'can_send_video_notes': True,
                'can_send_voice_notes': True
            }
            
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=permissions
            )
            print(f"🔓 Granted permissions to user {user_id} in group {group_id}")
        except Exception as e:
            print(f"❌ Error granting permissions to user {user_id}: {e}")
    
    async def _notify_admin_about_new_user(self, group_id, user_data, context: ContextTypes.DEFAULT_TYPE):
        """Уведомляет администратора о новом пользователе"""
        from my_secrets import ADMIN_IDS
        
        group_data = self.db.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for admin notification")
            return
        
        message = (
            f"👤 **Новый пользователь присоединился к группе**\n\n"
            f"**Имя:** {user_data['first_name']} {user_data.get('last_name', '')}\n"
            f"**Username:** @{user_data.get('username', 'нет')}\n"
            f"**Группа:** {group_data.get('title', group_id)}\n"
            f"**ID группы:** {group_id}\n"
            f"**ID пользователя:** {user_data['user_id']}\n\n"
            f"*Пользователь сейчас не может писать в группе. Разрешить доступ?*"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Разрешить", callback_data=f"approve_{group_id}_{user_data['user_id']}"),
                        InlineKeyboardButton("❌ Запретить", callback_data=f"reject_{group_id}_{user_data['user_id']}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    admin_id, 
                    message, 
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                print(f"📨 Sent notification to admin {admin_id}")
                
            except Exception as e:
                print(f"❌ Error notifying admin {admin_id}: {e}")