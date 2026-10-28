import google.generativeai as genai
import os
from dotenv import load_dotenv

# Ładuje klucz z Twojego pliku .env
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Dostępne modele dla Twojego konta to:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)