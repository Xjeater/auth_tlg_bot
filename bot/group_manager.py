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
        
        # Пропускаем обновления, не связанные с группами
        if chat.type not in ['group', 'supergroup']:
            return
        
        # Пропускаем бота
        if user.id == context.bot.id:
            return
        
        print(f"👤 User {user.id} status changed in group {chat.id}: {old_status} -> {new_status}")
        
        # Проверяем, присоединился ли пользователь к группе
        if new_status == 'member' and old_status in ['left', 'kicked']:
            await self._process_new_member(chat, user, context)
        
        # Проверяем, вышел ли пользователь из группы
        elif new_status in ['left', 'kicked'] and old_status == 'member':
            print(f"👋 User {user.id} left/kicked from group {chat.id}")
            # Удаляем данные пользователя из этой группы
            self.db.delete_user_from_group(chat.id, user.id)
    
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
        """Обрабатывает нового участника"""
        # Создаем/получаем данные группы с правильным названием
        group_data = self.db.get_group(chat.id)
        if not group_data:
            # Создаем группу с реальным названием
            if self.db.create_group(chat.id, chat.title):
                print(f"✅ Created new group {chat.id} with title '{chat.title}'")
                group_data = self.db.get_group(chat.id)
            else:
                print(f"❌ Failed to create group {chat.id}")
                return
        
        # Проверяем, не находится ли пользователь уже в группе (одобрен)
        if self.db.is_user_approved(chat.id, user.id):
            print(f"ℹ️ User {user.id} is already approved in group {chat.id}")
            return
        
        # Проверяем, не находится ли пользователь уже в ожидании
        pending_users = self.db.get_pending_users(chat.id)
        if str(user.id) in pending_users:
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
        
        print(f"👤 New member {user.id} ({user.first_name}) joined group {chat.id} ({chat.title})")
        
        # Добавляем в ожидание
        if self.db.add_pending_user(chat.id, user.id, user_data):
            print(f"✅ User {user.id} added to pending_users")
        else:
            print(f"❌ Failed to add user {user.id} to pending_users")
            return
        
        # 1. Сразу ограничиваем права
        try:
            await self._restrict_member_permissions(chat.id, user.id, context)
            print(f"🔒 Restricted user {user.id}")
        except Exception as e:
            print(f"⚠️ Could not restrict user {user.id}: {e}")
        
        # 2. Уведомляем администратора
        await self._notify_admin_about_new_user(chat.id, user_data, context)
        
        # 3. Отправляем пользователю сообщение
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"👋 Привет, {user.first_name}! Ты присоединился к группе '{chat.title}'.\n\n"
                     f"📝 Твоя заявка отправлена администратору. Ожидай одобрения."
            )
            print(f"📨 Sent welcome message to user {user.id}")
        except Exception as e:
            print(f"⚠️ Could not send DM to user {user.id}: {e}")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback от кнопок разрешить/запретить"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        admin_id = query.from_user.id
        
        print(f"🔔 Callback received: {data} from user {admin_id}")
        
        # Проверяем, что это администратор
        from my_secrets import ADMIN_IDS
        
        # Безопасная проверка типа ADMIN_IDS
        is_admin = False
        if isinstance(ADMIN_IDS, (list, tuple)):
            is_admin = admin_id in ADMIN_IDS
        elif isinstance(ADMIN_IDS, int):
            is_admin = admin_id == ADMIN_IDS
        else:
            print(f"⚠️ ADMIN_IDS has unexpected type: {type(ADMIN_IDS)}")
        
        if not is_admin:
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
            print(f"🔄 START: Approving user {user_id} in group {group_id}")
            
            # Получаем данные группы
            group_data = self.db.get_group(group_id)
            
            if not group_data:
                await query.edit_message_text("❌ Ошибка: группа не найдена.")
                return
            
            user_id_str = str(user_id)
            
            # Проверяем, есть ли пользователь в ожидании
            pending_users = group_data.get('pending_users', {})
            if user_id_str not in pending_users:
                # Проверяем, может пользователь уже одобрен
                if user_id_str in group_data.get('members', {}):
                    await query.edit_message_text(f"ℹ️ Пользователь уже одобрен в этой группе.")
                    return
                await query.edit_message_text("❌ Ошибка: пользователь не найден в ожидании.")
                return
            
            # Получаем данные пользователя
            user_data = pending_users[user_id_str]
            
            # Перемещаем пользователя из pending в members
            group_data['members'][user_id_str] = {
                **user_data,
                'approved_at': datetime.now().isoformat(),
                'approved_by': query.from_user.id
            }
            
            # Удаляем из ожидания
            del group_data['pending_users'][user_id_str]
            
            print(f"📝 Moving user {user_id} from pending to members")
            print(f"   Before: pending={len(pending_users)}, members={len(group_data.get('members', {}))}")
            
            # СОХРАНЯЕМ изменения в файл
            if self.db.save_group(group_id, group_data):
                print(f"✅ Data saved successfully for group {group_id}")
                
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
                    print(f"⚠️ Error notifying user {user_id}: {e}")
                
                # Обновляем сообщение администратора
                user_name = user_data.get('first_name', 'Пользователь')
                group_title = group_data.get('title', group_id)
                new_text = f"✅ Пользователь {user_name} одобрен в группе '{group_title}'"
                await query.edit_message_text(new_text)
                
                print(f"✅ COMPLETE: User {user_id} approved in group {group_id}")
            else:
                await query.edit_message_text("❌ Ошибка при сохранении данных.")
                print(f"❌ Failed to save data for group {group_id}")
                
        except Exception as e:
            print(f"❌ ERROR in _approve_user: {e}")
            import traceback
            traceback.print_exc()
            await query.edit_message_text(f"❌ Ошибка при разрешении пользователя: {str(e)}")
    
    async def _reject_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Запрещает пользователю доступ к группе и УДАЛЯЕТ ВСЕ его данные"""
        try:
            print(f"🔄 START: Rejecting user {user_id} from group {group_id}")
            
            # Получаем имя пользователя перед удалением
            group_data = self.db.get_group(group_id)
            user_name = "Пользователь"
            if group_data:
                pending_users = group_data.get('pending_users', {})
                if str(user_id) in pending_users:
                    user_name = pending_users[str(user_id)].get('first_name', 'Пользователь')
            
            # 1. УДАЛЯЕМ пользователя из файла группы
            print(f"🗑️ Deleting user {user_id} from group data file")
            delete_success = self.db.delete_user_from_group(group_id, user_id)
            
            if delete_success:
                print(f"✅ User data deleted from file for group {group_id}")
            else:
                print(f"⚠️ Could not delete user data from file (maybe already deleted)")
            
            # 2. Удаляем пользователя из самой группы
            try:
                print(f"🚫 Banning user {user_id} from group {group_id}")
                await context.bot.ban_chat_member(group_id, user_id)
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(group_id, user_id)
                print(f"✅ User {user_id} banned/unbanned from group")
            except Exception as e:
                print(f"⚠️ Error banning user {user_id}: {e}")
            
            # 3. Обновляем сообщение администратора
            group_title = group_data.get('title', group_id) if group_data else group_id
            new_text = f"❌ Пользователь {user_name} удален из группы '{group_title}'"
            await query.edit_message_text(new_text)
            
            print(f"✅ COMPLETE: User {user_id} rejected and deleted from group {group_id}")
            
        except Exception as e:
            print(f"❌ ERROR in _reject_user: {e}")
            import traceback
            traceback.print_exc()
            await query.edit_message_text(f"❌ Ошибка при запрете пользователя: {str(e)}")
    
    async def _restrict_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Ограничивает права пользователя - нельзя отправлять сообщения"""
        try:
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
                permissions=permissions
            )
            print(f"🔒 Restricted user {user_id} in group {group_id}")
        except Exception as e:
            print(f"❌ Error restricting user {user_id}: {e}")
            raise
    
    async def _grant_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Дает права на отправку сообщений пользователю"""
        try:
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
        
        # Безопасная обработка ADMIN_IDS
        admin_ids = []
        if isinstance(ADMIN_IDS, (list, tuple)):
            admin_ids = ADMIN_IDS
        elif isinstance(ADMIN_IDS, int):
            admin_ids = [ADMIN_IDS]
        else:
            print(f"⚠️ ADMIN_IDS has unexpected type: {type(ADMIN_IDS)}")
            return
        
        for admin_id in admin_ids:
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

    async def handle_group_title_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает изменение названия группы"""
        if not update.message or not update.message.new_chat_title:
            return
        
        chat = update.effective_chat
        new_title = update.message.new_chat_title
        
        print(f"🏷️ Group title changed: {chat.id} -> '{new_title}'")
        
        # Обновляем название в базе данных
        self.db.update_group_title(chat.id, new_title)