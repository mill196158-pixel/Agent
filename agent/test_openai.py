import os
from dotenv import load_dotenv
from openai import OpenAI

# Загружаем ключи из .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
project_id = os.getenv("OPENAI_PROJECT_ID")

if not api_key:
    raise ValueError("❌ Ключ не найден в .env")
if not project_id:
    raise ValueError("❌ Project ID не найден в .env")

# Создаём клиента с проектом
client = OpenAI(api_key=api_key, project=project_id)

# Пробный запрос
resp = client.chat.completions.create(
    model="gpt-5-mini",   # дешёвая модель для тестов
    messages=[
        {"role": "system", "content": "Ты помощник, отвечай очень кратко."},
        {"role": "user", "content": "Напиши формулу воды"}
    ]
)

print("✅ Ответ:", resp.choices[0].message.content)
