import json
import os
from datetime import datetime
from config import BOT_SETTINGS

class JSONDatabase:
    def __init__(self):
        self.data_dir = BOT_SETTINGS['data_directory']
        self.groups_dir = BOT_SETTINGS['groups_directory']
        self.users_dir = BOT_SETTINGS.get('users_directory', 'data/users')
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Создает необходимые директории"""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.groups_dir, exist_ok=True)
        os.makedirs(self.users_dir, exist_ok=True)
    
    def _get_group_file(self, group_id):
        return os.path.join(self.groups_dir, f"{group_id}.json")
    
    def _get_user_file(self, user_id):
        return os.path.join(self.users_dir, f"{user_id}.json")
    
    def _read_json(self, filepath):
        """Читает JSON файл"""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"❌ Error reading JSON from {filepath}: {e}")
            return None
    
    def _write_json(self, filepath, data):
        """Записывает данные в JSON файл"""
        try:
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ Successfully wrote to {filepath}")
            return True
        except Exception as e:
            print(f"❌ Error writing to {filepath}: {e}")
            return False
    
    # Методы для работы с группами
    def get_group(self, group_id):
        """Получает данные группы"""
        filepath = self._get_group_file(group_id)
        print(f"📁 Loading group {group_id} from {filepath}")
        data = self._read_json(filepath)
        if data:
            print(f"   Members: {len(data.get('members', {}))}, Pending: {len(data.get('pending_users', {}))}")
        return data
    
    def save_group(self, group_id, group_data):
        """Сохраняет данные группы"""
        filepath = self._get_group_file(group_id)
        print(f"💾 Saving group {group_id} to {filepath}")
        print(f"   Members: {len(group_data.get('members', {}))}")
        print(f"   Pending: {len(group_data.get('pending_users', {}))}")
        
        # Проверяем структуру данных
        if 'members' not in group_data:
            group_data['members'] = {}
        if 'pending_users' not in group_data:
            group_data['pending_users'] = {}
        
        result = self._write_json(filepath, group_data)
        if result:
            print(f"✅ Group {group_id} saved successfully")
        else:
            print(f"❌ Failed to save group {group_id}")
        return result
    
    def create_group(self, group_id, group_title):
        """Создает новую группу"""
        group_data = {
            'group_id': str(group_id),
            'title': group_title,
            'created_at': datetime.now().isoformat(),
            'members': {},
            'pending_users': {},
            'settings': {
                'require_approval': True
            }
        }
        return self.save_group(group_id, group_data)
    
    def get_all_groups(self):
        """Получает все группы"""
        groups = {}
        print(f"🔍 Scanning groups directory: {self.groups_dir}")
        
        if not os.path.exists(self.groups_dir):
            print(f"⚠️ Groups directory does not exist: {self.groups_dir}")
            return groups
            
        for filename in os.listdir(self.groups_dir):
            if filename.endswith('.json'):
                group_id = filename[:-5]  # удаляем .json
                print(f"📄 Found group file: {filename}")
                group_data = self.get_group(group_id)
                if group_data:
                    groups[group_id] = group_data
        print(f"📊 Total groups loaded: {len(groups)}")
        return groups
    
    # Методы для работы с пользователями в группах
    def add_pending_user(self, group_id, user_id, user_data):
        """Добавляет пользователя в ожидание"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for adding pending user")
            return False
        
        user_id_str = str(user_id)
        
        # Инициализируем словари если их нет
        if 'pending_users' not in group_data:
            group_data['pending_users'] = {}
        
        # Обновляем данные пользователя
        group_data['pending_users'][user_id_str] = {
            **user_data,
            'added_at': datetime.now().isoformat()
        }
        
        print(f"📝 Adding user {user_id} to pending_users of group {group_id}")
        print(f"   Now pending users: {len(group_data['pending_users'])}")
        
        return self.save_group(group_id, group_data)
    
    def remove_pending_user(self, group_id, user_id):
        """Удаляет пользователя из ожидания"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for removing pending user")
            return False
        
        user_id_str = str(user_id)
        
        if 'pending_users' in group_data and user_id_str in group_data['pending_users']:
            del group_data['pending_users'][user_id_str]
            print(f"🗑️ Removed user {user_id} from pending_users of group {group_id}")
            print(f"   Remaining pending users: {len(group_data.get('pending_users', {}))}")
            return self.save_group(group_id, group_data)
        
        print(f"⚠️ User {user_id} not found in pending_users of group {group_id}")
        return False
    
    def approve_user(self, group_id, user_id, user_data, approved_by='system'):
        """Одобряет пользователя в группе"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for approving user")
            return False
        
        user_id_str = str(user_id)
        
        # Инициализируем словари если их нет
        if 'members' not in group_data:
            group_data['members'] = {}
        if 'pending_users' not in group_data:
            group_data['pending_users'] = {}
        
        # Добавляем в участники
        group_data['members'][user_id_str] = {
            **user_data,
            'approved_at': datetime.now().isoformat(),
            'approved_by': approved_by
        }
        
        # Удаляем из ожидания
        if user_id_str in group_data['pending_users']:
            del group_data['pending_users'][user_id_str]
            print(f"🔄 Moved user {user_id} from pending to members in group {group_id}")
        
        print(f"📝 Approving user {user_id} in group {group_id}")
        print(f"   Members: {len(group_data['members'])}, Pending: {len(group_data['pending_users'])}")
        
        return self.save_group(group_id, group_data)
    
    def is_user_approved(self, group_id, user_id):
        """Проверяет, одобрен ли пользователь"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for approval check")
            return False
        
        user_id_str = str(user_id)
        is_approved = user_id_str in group_data.get('members', {})
        print(f"🔍 Checking if user {user_id} is approved in group {group_id}: {is_approved}")
        return is_approved
    
    def get_pending_users(self, group_id):
        """Получает ожидающих пользователей"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for getting pending users")
            return {}
        
        pending = group_data.get('pending_users', {})
        print(f"📋 Got {len(pending)} pending users for group {group_id}")
        return pending
    
    def get_group_members(self, group_id):
        """Получает участников группы"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for getting members")
            return {}
        
        members = group_data.get('members', {})
        print(f"📋 Got {len(members)} members for group {group_id}")
        return members
    
    def remove_user_from_all_lists(self, group_id, user_id):
        """Удаляет пользователя из всех списков группы"""
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found for removing user")
            return False
        
        user_id_str = str(user_id)
        changed = False
        
        # Удаляем из ожидания
        if 'pending_users' in group_data and user_id_str in group_data['pending_users']:
            del group_data['pending_users'][user_id_str]
            changed = True
            print(f"🗑️ Removed user {user_id} from pending_users")
        
        # Удаляем из участников
        if 'members' in group_data and user_id_str in group_data['members']:
            del group_data['members'][user_id_str]
            changed = True
            print(f"🗑️ Removed user {user_id} from members")
        
        if changed:
            print(f"📝 Saving group {group_id} after removing user {user_id}")
            print(f"   Members: {len(group_data.get('members', {}))}, Pending: {len(group_data.get('pending_users', {}))}")
            return self.save_group(group_id, group_data)
        
        print(f"ℹ️ User {user_id} not found in any lists of group {group_id}")
        return True  # Возвращаем True, так как пользователя и не было
    
    def delete_user_file(self, user_id):
        """Удаляет файл пользователя"""
        try:
            user_file = self._get_user_file(user_id)
            if os.path.exists(user_file):
                os.remove(user_file)
                print(f"🗑️ User file {user_id}.json deleted from database")
                return True
            else:
                print(f"ℹ️ User file {user_id}.json not found")
                return True  # Файла нет - считаем успехом
        except Exception as e:
            print(f"❌ Error deleting user file {user_id}: {e}")
            return False