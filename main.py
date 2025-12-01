#!/usr/bin/env python3
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.core import TelegramAuthBot
from my_secrets import BOT_TOKEN

def main():
    """Основная функция запуска"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Ошибка: Установите токен бота в файле my_secrets.py")
        sys.exit(1)
    
    try:
        # Запускаем бота
        bot = TelegramAuthBot(BOT_TOKEN)
        print("🤖 Бот запущен...")
        print("✅ Система работает в упрощенном режиме:")
        print("   1. Пользователь присоединяется к группе")
        print("   2. Бот ограничивает права на отправку сообщений")
        print("   3. Админ получает уведомление с кнопками")
        print("   4. Админ нажимает '✅ Разрешить' или '❌ Запретить'")
        bot.run()
        
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен")
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()