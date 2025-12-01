import os

# Основные настройки бота
BOT_SETTINGS = {
    'data_directory': 'data',
    'groups_directory': 'data/groups',
    'admin_notification': True,
    'debug': True
}

# Настройки сообщений
MESSAGES = {
    'admin_request': "Новый пользователь хочет присоединиться к группе:\n\n👤 Имя: {}\n🆔 ID группы: {}\n\nПодтвердить регистрацию?",
    'user_added': "Пользователь {} успешно добавлен в группу.",
    'user_rejected': "Пользователь {} удален из группы."
}

# Создаем необходимые директории
os.makedirs(BOT_SETTINGS['data_directory'], exist_ok=True)
os.makedirs(BOT_SETTINGS['groups_directory'], exist_ok=True)