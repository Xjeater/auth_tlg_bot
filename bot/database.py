import json
import os
from datetime import datetime
from config import BOT_SETTINGS

class JSONDatabase:
    def __init__(self):
        self.data_dir = BOT_SETTINGS['data_directory']
        self.groups_dir = BOT_SETTINGS['groups_directory']
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Создает необходимые директории"""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.groups_dir, exist_ok=True)
    
    def _get_group_file(self, group_id):
        return os.path.join(self.groups_dir, f"{group_id}.json")
    
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
        filepath = self._get_group_file(group_id)
        print(f"💾 Saving group {group_id} to {filepath}")
        print(f"   Members: {len(group_data.get('members', {}))}")
        print(f"   Pending: {len(group_data.get('pending_users', {}))}")
        
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
            'pending_users': {}
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
        group_data['pending_users'][user_id_str] = user_data
        
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

    def delete_user_file(self, user_id):
        """Удаляет файл пользователя"""
        try:
            user_file = os.path.join(self.users_dir, f"{user_id}.json")
            if os.path.exists(user_file):
                os.remove(user_file)
                print(f"🗑️ User file {user_id}.json deleted from database")
                return True
            return False
        except Exception as e:
            print(f"❌ Error deleting user file {user_id}: {e}")
            return False