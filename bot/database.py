import json
import os
from datetime import datetime, timedelta
from config import BOT_SETTINGS

class JSONDatabase:
    def __init__(self):
        self.data_dir = BOT_SETTINGS['data_directory']
        self.groups_dir = BOT_SETTINGS['groups_directory']
        self.users_dir = BOT_SETTINGS['users_directory']
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
        except (json.JSONDecodeError, FileNotFoundError):
            return None
    
    def _write_json(self, filepath, data):
        """Записывает данные в JSON файл"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error writing to {filepath}: {e}")
            return False
    
    # Методы для работы с группами
    def get_group(self, group_id):
        """Получает данные группы"""
        return self._read_json(self._get_group_file(group_id))
    
    def save_group(self, group_id, group_data):
        """Сохраняет данные группы"""
        return self._write_json(self._get_group_file(group_id), group_data)
    
    def create_group(self, group_id, group_title):
        """Создает новую группу"""
        group_data = {
            'group_id': str(group_id),
            'title': group_title,
            'created_at': datetime.now().isoformat(),
            'members': {},
            'pending_users': {},
            'settings': {
                'require_phone': True,
                'admin_approval': True,
                'welcome_message': True
            }
        }
        return self.save_group(group_id, group_data)
    
    def get_all_groups(self):
        """Получает все группы"""
        groups = {}
        for filename in os.listdir(self.groups_dir):
            if filename.endswith('.json'):
                group_id = filename[:-5]  # удаляем .json
                group_data = self.get_group(group_id)
                if group_data:
                    groups[group_id] = group_data
        return groups
    
    # Методы для работы с пользователями в группах
    def add_pending_user(self, group_id, user_id, user_data):
        """Добавляет пользователя в ожидание"""
        group_data = self.get_group(group_id)
        if not group_data:
            return False
        
        user_id_str = str(user_id)
        group_data['pending_users'][user_id_str] = {
            **user_data,
            'joined_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(seconds=BOT_SETTINGS['auth_timeout'])).isoformat()
        }
        
        return self.save_group(group_id, group_data)
    
    def remove_pending_user(self, group_id, user_id):
        """Удаляет пользователя из ожидания"""
        group_data = self.get_group(group_id)
        if not group_data:
            return False
        
        user_id_str = str(user_id)
        if user_id_str in group_data['pending_users']:
            del group_data['pending_users'][user_id_str]
            return self.save_group(group_id, group_data)
        return False
    
    def approve_user(self, group_id, user_id, user_data, approved_by='system'):
        """Одобряет пользователя в группе"""
        group_data = self.get_group(group_id)
        if not group_data:
            return False
        
        user_id_str = str(user_id)
        group_data['members'][user_id_str] = {
            **user_data,
            'approved_at': datetime.now().isoformat(),
            'approved_by': approved_by,
            'phone_verified': True
        }
        
        # Удаляем из ожидания
        if user_id_str in group_data['pending_users']:
            del group_data['pending_users'][user_id_str]
        
        return self.save_group(group_id, group_data)
    
    def is_user_approved(self, group_id, user_id):
        """Проверяет, одобрен ли пользователь"""
        group_data = self.get_group(group_id)
        if not group_data:
            return False
        return str(user_id) in group_data.get('members', {})
    
    def get_pending_users(self, group_id):
        """Получает ожидающих пользователей"""
        group_data = self.get_group(group_id)
        if not group_data:
            return {}
        return group_data.get('pending_users', {})
    
    def get_group_members(self, group_id):
        """Получает участников группы"""
        group_data = self.get_group(group_id)
        if not group_data:
            return {}
        return group_data.get('members', {})
    
    # Методы для работы с пользователями
    def save_user(self, user_data):
        """Сохраняет данные пользователя"""
        user_id = user_data.get('user_id')
        if not user_id:
            return False
        
        user_file = self._get_user_file(user_id)
        current_data = self._read_json(user_file) or {}
        
        # Обновляем данные
        current_data.update(user_data)
        current_data['updated_at'] = datetime.now().isoformat()
        
        return self._write_json(user_file, current_data)
    
    def get_user(self, user_id):
        """Получает данные пользователя"""
        return self._read_json(self._get_user_file(user_id))
    
    def delete_user(self, user_id):
        """Удаляет пользователя из базы"""
        try:
            user_file = self._get_user_file(user_id)
            if os.path.exists(user_file):
                os.remove(user_file)
                print(f"🗑️ User {user_id} deleted from database")
                return True
            return False
        except Exception as e:
            print(f"❌ Error deleting user {user_id}: {e}")
            return False
    
    def user_has_phone_verification(self, user_id):
        """Проверяет, верифицирован ли телефон пользователя"""
        user_data = self.get_user(user_id)
        return user_data and user_data.get('phone_verified', False)
    
    # Методы обслуживания
    def cleanup_expired_pending_users(self):
        """Очищает просроченных ожидающих пользователей"""
        for group_id in self.get_all_groups():
            group_data = self.get_group(group_id)
            if not group_data:
                continue
            
            pending_users = group_data.get('pending_users', {})
            current_time = datetime.now()
            expired_users = []
            
            for user_id, user_data in pending_users.items():
                expires_at = user_data.get('expires_at')
                if expires_at:
                    try:
                        expiry_time = datetime.fromisoformat(expires_at)
                        if current_time > expiry_time:
                            expired_users.append(user_id)
                    except ValueError:
                        expired_users.append(user_id)
            
            if expired_users:
                for user_id in expired_users:
                    del pending_users[user_id]
                
                group_data['pending_users'] = pending_users
                self.save_group(group_id, group_data)
                
                print(f"Cleaned up {len(expired_users)} expired users from group {group_id}")
        
        return True