import os
from cryptography.fernet import Fernet

# Берём ключ из .env
key = os.getenv("FILE_ID_KEY")
if not key:
    raise ValueError("❌ FILE_ID_KEY не найден в .env")

fernet = Fernet(key.encode())

def encrypt_file_id(file_id: str) -> str:
    """Шифрует file_id перед сохранением в БД"""
    return fernet.encrypt(file_id.encode()).decode()

def decrypt_file_id(encrypted_file_id: str) -> str:
    """Расшифровывает file_id перед отправкой в Telegram"""
    try:
        return fernet.decrypt(encrypted_file_id.encode()).decode()
    except Exception:
        # Если данные не были зашифрованы — возвращаем как есть
        return encrypted_file_id