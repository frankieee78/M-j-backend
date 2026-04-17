from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

# Načtení nastavení (pokud máš .env soubor)
load_dotenv()

app = FastAPI()

# Základní cesta, aby ses mohl podívat, jestli to běží
@app.get("/")
def home():
    return {"zprava": "Backend konečně funguje!", "stav": "OK"}

# Testovací cesta
@app.get("/test")
def test():
    return {"info": "Tohle je testovací cesta bez chyb."}