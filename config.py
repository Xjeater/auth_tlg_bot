import os

# Основные настройки бота
BOT_SETTINGS = {
    'auth_timeout': 3600,  # в секундах для неавторизованных
    'data_directory': 'data',
    'groups_directory': 'data/groups',
    'users_directory': 'data/users',
    'admin_notification': True,
    'debug': True
}

# Настройки сообщений
MESSAGES = {
    'welcome': "Добро пожаловать! Для доступа к группе необходимо авторизоваться.",
    'auth_required': "Пожалуйста, авторизуйтесь в боте в течении 60 минут @{} для получения доступа к группе. В боте нажмите кнопку ПОДЕЛИТЬСЯ КОНТАКТОМ, это необходимо чтобы исключить доступ к группе случайных пользователей.",
    'auth_success': "Авторизация успешна! Теперь у вас есть доступ к группе.",
    'auth_timeout': "Время авторизации истекло. Вы были исключены из группы. Пройдите авторизацию и попробуйте присоединиться снова.",
    'admin_request': "Новый пользователь хочет присоединиться к группе:\n\n👤 Имя: {}\n📱 Телефон: {}\n🆔 ID группы: {}\n\nПодтвердить регистрацию?",
    'user_added': "Пользователь {} успешно добавлен в группу.",
    'user_rejected': "Регистрация пользователя {} отклонена."
}

# Создаем необходимые директории
os.makedirs(BOT_SETTINGS['data_directory'], exist_ok=True)
os.makedirs(BOT_SETTINGS['groups_directory'], exist_ok=True)
os.makedirs(BOT_SETTINGS['users_directory'], exist_ok=True)