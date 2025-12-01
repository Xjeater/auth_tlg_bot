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
        except Exception as e:
            print(f"❌ Error reading JSON: {e}")
            return None
    
    def _write_json(self, filepath, data):
        """Записывает данные в JSON файл"""
        try:
            # ВАЖНО: создаем временный файл, затем переименовываем
            temp_file = filepath + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Переименовываем временный файл в основной
            os.replace(temp_file, filepath)
            return True
        except Exception as e:
            print(f"❌ Error writing JSON: {e}")
            return False
    
    # Методы для работы с группами
    def get_group(self, group_id):
        """Получает данные группы"""
        return self._read_json(self._get_group_file(group_id))
    
    def save_group(self, group_id, group_data):
        """Сохраняет данные группы - ГАРАНТИРОВАННО"""
        filepath = self._get_group_file(group_id)
        print(f"💾 SAVING group {group_id}")
        print(f"   Members count: {len(group_data.get('members', {}))}")
        print(f"   Pending count: {len(group_data.get('pending_users', {}))}")
        
        # Гарантируем структуру
        if 'members' not in group_data:
            group_data['members'] = {}
        if 'pending_users' not in group_data:
            group_data['pending_users'] = {}
        
        result = self._write_json(filepath, group_data)
        if result:
            print(f"✅ Group {group_id} SAVED SUCCESSFULLY")
        else:
            print(f"❌ FAILED to save group {group_id}")
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
    
    # Удаление пользователя из группы - ГЛАВНЫЙ МЕТОД
    def delete_user_from_group(self, group_id, user_id):
        """УДАЛЯЕТ пользователя из группы - ВСЕ данные"""
        print(f"🗑️ DELETING user {user_id} from group {group_id}")
        
        # Получаем данные группы
        group_data = self.get_group(group_id)
        if not group_data:
            print(f"❌ Group {group_id} not found")
            return False
        
        user_id_str = str(user_id)
        deleted = False
        
        # Удаляем из pending_users
        if 'pending_users' in group_data:
            if user_id_str in group_data['pending_users']:
                del group_data['pending_users'][user_id_str]
                deleted = True
                print(f"   Removed from pending_users")
        
        # Удаляем из members
        if 'members' in group_data:
            if user_id_str in group_data['members']:
                del group_data['members'][user_id_str]
                deleted = True
                print(f"   Removed from members")
        
        if deleted:
            # Сохраняем изменения
            success = self.save_group(group_id, group_data)
            if success:
                print(f"✅ User {user_id} DELETED from group {group_id}")
                return True
            else:
                print(f"❌ Failed to save after deletion")
                return False
        else:
            print(f"ℹ️ User {user_id} not found in group {group_id}")
            return True  # Уже не существует
    
    # Остальные методы (упрощенные)
    def add_pending_user(self, group_id, user_id, user_data):
        """Добавляет пользователя в ожидание"""
        group_data = self.get_group(group_id) or self.create_group(group_id, "Unknown")
        
        user_id_str = str(user_id)
        if 'pending_users' not in group_data:
            group_data['pending_users'] = {}
        
        group_data['pending_users'][user_id_str] = user_data
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
    
    def get_all_groups(self):
        """Получает все группы"""
        groups = {}
        if not os.path.exists(self.groups_dir):
            return groups
            
        for filename in os.listdir(self.groups_dir):
            if filename.endswith('.json'):
                group_id = filename[:-5]
                group_data = self.get_group(group_id)
                if group_data:
                    groups[group_id] = group_data
        return groups