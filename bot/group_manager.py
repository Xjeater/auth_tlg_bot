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
        
        if chat.type not in ['group', 'supergroup']:
            return
        
        if user.id == context.bot.id:
            return
        
        print(f"👤 User {user.id} status: {old_status} -> {new_status} in group {chat.id}")
        
        # Пользователь присоединился
        if new_status == 'member' and old_status in ['left', 'kicked']:
            await self._process_new_member(chat, user, context)
        
        # Пользователь вышел
        elif new_status in ['left', 'kicked'] and old_status == 'member':
            print(f"👋 User {user.id} left group {chat.id}")
            # УДАЛЯЕМ данные
            self.db.delete_user_from_group(chat.id, user.id)
    
    async def handle_new_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает новых участников чата"""
        if not update.message or not update.message.new_chat_members:
            return
        
        chat = update.effective_chat
        if chat.type not in ['group', 'supergroup']:
            return
        
        for new_member in update.message.new_chat_members:
            if new_member.id == context.bot.id:
                continue
            
            await self._process_new_member(chat, new_member, context)
    
    async def _process_new_member(self, chat, user, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нового участника"""
        # Проверяем, уже ли пользователь одобрен
        if self.db.is_user_approved(chat.id, user.id):
            print(f"✅ User {user.id} already approved in group {chat.id}")
            return
        
        # Создаем данные пользователя
        user_data = {
            'user_id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'joined_at': datetime.now().isoformat()
        }
        
        print(f"👤 New member {user.id} joined group {chat.id}")
        
        # Добавляем в ожидание
        self.db.add_pending_user(chat.id, user.id, user_data)
        
        # Ограничиваем права
        try:
            await self._restrict_member_permissions(chat.id, user.id, context)
            print(f"🔒 Restricted user {user.id}")
        except Exception as e:
            print(f"⚠️ Restriction error: {e}")
        
        # Уведомляем администратора
        await self._notify_admin_about_new_user(chat.id, user_data, context)
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"👋 Привет, {user.first_name}! Ты присоединился к группе '{chat.title}'.\n\n"
                     f"📝 Твоя заявка отправлена администратору. Ожидай одобрения."
            )
        except:
            pass
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback от кнопок"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        admin_id = query.from_user.id
        
        print(f"🔔 Callback: {data} from admin {admin_id}")
        
        # Проверяем администратора
        from my_secrets import ADMIN_IDS
        if admin_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Нет прав")
            return
        
        if data.startswith('approve_'):
            parts = data.split('_')
            if len(parts) == 3:
                group_id = parts[1]
                user_id = int(parts[2])
                await self._approve_user(group_id, user_id, context, query)
        
        elif data.startswith('reject_'):
            parts = data.split('_')
            if len(parts) == 3:
                group_id = parts[1]
                user_id = int(parts[2])
                await self._reject_user(group_id, user_id, context, query)
    
    async def _approve_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Разрешает пользователю писать"""
        try:
            print(f"✅ Approving user {user_id} in group {group_id}")
            
            # Получаем данные группы
            group_data = self.db.get_group(group_id)
            if not group_data:
                await query.edit_message_text("❌ Группа не найдена")
                return
            
            user_id_str = str(user_id)
            
            # Проверяем, есть ли пользователь в ожидании
            if user_id_str not in group_data.get('pending_users', {}):
                await query.edit_message_text("❌ Пользователь не найден в ожидании")
                return
            
            # Получаем данные пользователя
            user_data = group_data['pending_users'][user_id_str]
            
            # Перемещаем в участники
            group_data['members'][user_id_str] = {
                **user_data,
                'approved_at': datetime.now().isoformat(),
                'approved_by': query.from_user.id
            }
            
            # Удаляем из ожидания
            del group_data['pending_users'][user_id_str]
            
            # СОХРАНЯЕМ изменения
            if self.db.save_group(group_id, group_data):
                # Даем права
                await self._grant_member_permissions(group_id, user_id, context)
                
                # Уведомляем пользователя
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ Администратор одобрил вашу заявку! Теперь вы можете писать в группе."
                    )
                except:
                    pass
                
                # Обновляем сообщение админу
                await query.edit_message_text(f"✅ Пользователь {user_data['first_name']} одобрен")
                print(f"✅ User {user_id} approved")
            else:
                await query.edit_message_text("❌ Ошибка сохранения")
                
        except Exception as e:
            print(f"❌ Approval error: {e}")
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _reject_user(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE, query):
        """Запрещает доступ и УДАЛЯЕТ пользователя"""
        try:
            print(f"❌ Rejecting user {user_id} from group {group_id}")
            
            # Получаем имя пользователя перед удалением
            group_data = self.db.get_group(group_id)
            user_name = "Пользователь"
            if group_data:
                pending = group_data.get('pending_users', {})
                if str(user_id) in pending:
                    user_name = pending[str(user_id)].get('first_name', 'Пользователь')
            
            # 1. УДАЛЯЕМ пользователя из файла группы
            self.db.delete_user_from_group(group_id, user_id)
            
            # 2. Удаляем из группы
            try:
                await context.bot.ban_chat_member(group_id, user_id)
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(group_id, user_id)
            except Exception as e:
                print(f"⚠️ Ban error: {e}")
            
            # 3. Уведомляем админа
            await query.edit_message_text(f"❌ Пользователь {user_name} удален")
            
            print(f"✅ User {user_id} rejected and deleted")
            
        except Exception as e:
            print(f"❌ Rejection error: {e}")
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")
    
    async def _restrict_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Ограничивает права"""
        try:
            permissions = {
                'can_send_messages': False,
                'can_send_media_messages': False,
                'can_send_other_messages': False,
                'can_add_web_page_previews': False,
                'can_send_polls': False,
                'can_invite_users': False,
                'can_pin_messages': False,
                'can_change_info': False
            }
            
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=permissions
            )
        except Exception as e:
            print(f"❌ Restrict error: {e}")
            raise
    
    async def _grant_member_permissions(self, group_id, user_id, context: ContextTypes.DEFAULT_TYPE):
        """Дает права"""
        try:
            permissions = {
                'can_send_messages': True,
                'can_send_media_messages': True,
                'can_send_other_messages': True,
                'can_add_web_page_previews': True,
                'can_send_polls': True,
                'can_invite_users': True,
                'can_pin_messages': False,
                'can_change_info': False
            }
            
            await context.bot.restrict_chat_member(
                chat_id=group_id,
                user_id=user_id,
                permissions=permissions
            )
        except Exception as e:
            print(f"❌ Grant permissions error: {e}")
    
    async def _notify_admin_about_new_user(self, group_id, user_data, context: ContextTypes.DEFAULT_TYPE):
        """Уведомляет администратора"""
        from my_secrets import ADMIN_IDS
        
        group_data = self.db.get_group(group_id)
        if not group_data:
            return
        
        message = (
            f"👤 **Новый пользователь**\n\n"
            f"**Имя:** {user_data['first_name']} {user_data.get('last_name', '')}\n"
            f"**Username:** @{user_data.get('username', 'нет')}\n"
            f"**Группа:** {group_data.get('title', group_id)}\n"
            f"**ID:** {user_data['user_id']}"
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
            except Exception as e:
                print(f"❌ Admin notification error: {e}")