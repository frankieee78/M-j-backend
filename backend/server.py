from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, BeforeValidator
from typing import List, Optional, Annotated
from bson import ObjectId
from datetime import datetime, timezone, timedelta
import os
import logging
import uuid
from pathlib import Path
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_object_id(v):
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError("Invalid ObjectId")

PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


# ============ MODELS ============

class Question(BaseModel):
    id: str
    text: str
    options: List[str]
    correct: int
    explanation: str


class UserCreate(BaseModel):
    username: str
    device_id: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    xp: int
    level: int
    streak: int
    last_activity: Optional[datetime]
    badges: List[str]
    completed_lessons: List[str]
    total_correct: int
    total_questions: int


class ProgressCreate(BaseModel):
    user_id: str
    lesson_id: str
    correct_count: int
    total_questions: int


class ChatMessageCreate(BaseModel):
    user_id: str
    message: str


class FinancialPlanCreate(BaseModel):
    user_id: str
    age: int
    monthly_income: float
    monthly_expenses: float
    savings: float
    debts: float
    goals: List[str]
    risk_tolerance: str  # 'low' | 'medium' | 'high'


# ============ SEED DATA ============

SEED_LESSONS = [
    # --- CATEGORY 1: Základy ---
    {
        "lesson_id": "cat1_l1", "category": "Základy", "category_emoji": "💰",
        "category_order": 1, "title": "Příjmy a výdaje", "order": 1,
        "description": "Pochopte základy osobních financí", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je to příjem?",
             "options": ["Peníze, které dostáváte", "Peníze, které utrácíte", "Typ bankovního účtu", "Forma pojištění"],
             "correct": 0, "explanation": "Příjem jsou veškeré peníze, které dostáváte – mzda, pronájem, dividendy, stipendium apod."},
            {"id": "q2", "text": "Co je to hrubá mzda?",
             "options": ["Mzda po odečtení daní", "Mzda před odečtením daní a pojistného", "Minimální zákonná mzda", "Mzda s bonusem"],
             "correct": 1, "explanation": "Hrubá mzda je celková domluvená odměna. Čistá mzda je to, co vám přijde na účet po odečtení daní a pojistného."},
            {"id": "q3", "text": "Které z následujících je fixní výdaj?",
             "options": ["Návštěva restaurace", "Nákup oblečení", "Měsíční nájem", "Jízdenka na výlet"],
             "correct": 2, "explanation": "Fixní výdaje se každý měsíc nemění (nájem, splátky). Variabilní výdaje kolísají (jídlo, oblečení, zábava)."},
            {"id": "q4", "text": "Co znamená pojem 'deficit v rozpočtu'?",
             "options": ["Výdaje jsou vyšší než příjmy", "Příjmy jsou vyšší než výdaje", "Rovnováha příjmů a výdajů", "Velká výše úspor"],
             "correct": 0, "explanation": "Deficit nastane, když utrácíte více, než vyděláváte. Je důležité ho identifikovat a co nejdříve napravit."},
            {"id": "q5", "text": "Proč je důležité sledovat své výdaje?",
             "options": ["Ze zákona to musíte", "Banky to vyžadují", "Abyste věděli, kam peníze jdou a mohli šetřit", "Kvůli daňovému přiznání"],
             "correct": 2, "explanation": "Sledování výdajů vám pomáhá pochopit finanční návyky a najít místa, kde lze ušetřit."}
        ]
    },
    {
        "lesson_id": "cat1_l2", "category": "Základy", "category_emoji": "💰",
        "category_order": 1, "title": "Pravidlo 50/30/20", "order": 2,
        "description": "Jednoduchý způsob, jak rozdělit příjem", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co říká pravidlo 50/30/20?",
             "options": ["50% zábava, 30% jídlo, 20% bydlení", "50% potřeby, 30% přání, 20% spoření", "50% spoření, 30% výdaje, 20% investice", "50% investice, 30% bydlení, 20% jídlo"],
             "correct": 1, "explanation": "Pravidlo 50/30/20: 50 % na životní nutnosti, 30 % na přání a zábavu, 20 % na spoření a splácení dluhů."},
            {"id": "q2", "text": "Co patří do kategorie 'potřeby' (50 %)?",
             "options": ["Netflix, restaurace, oblečení", "Nájem, jídlo, elektřina, pojištění", "Dovolená, elektronika, hobby", "Akcie, zlato, kryptoměny"],
             "correct": 1, "explanation": "Potřeby jsou výdaje nezbytné pro život – bydlení, základní jídlo, doprava do práce, zdravotní péče."},
            {"id": "q3", "text": "Váš čistý měsíční příjem je 30 000 Kč. Kolik byste měli spořit dle pravidla?",
             "options": ["3 000 Kč", "9 000 Kč", "6 000 Kč", "15 000 Kč"],
             "correct": 2, "explanation": "20 % z 30 000 Kč = 6 000 Kč. Tato částka jde na spoření a splácení dluhů."},
            {"id": "q4", "text": "Co patří do kategorie 'přání' (30 %)?",
             "options": ["Nájem a jídlo", "Netflix, dovolená, restaurace", "Splátka hypotéky", "Zdravotní pojištění"],
             "correct": 1, "explanation": "Přání jsou výdaje nad rámec nutnosti – restaurace, streaming, dovolená, nová elektronika apod."},
            {"id": "q5", "text": "Jaký je první krok při sestavování osobního rozpočtu?",
             "options": ["Investovat do akcií", "Vzít si půjčku", "Zapsat příjmy a výdaje za posledních 3 měsíce", "Otevřít si spořicí účet"],
             "correct": 2, "explanation": "Pochopení stávajících finančních návyků je základem dobrého rozpočtu."}
        ]
    },
    {
        "lesson_id": "cat1_l3", "category": "Základy", "category_emoji": "💰",
        "category_order": 1, "title": "Sestavení rozpočtu", "order": 3,
        "description": "Naučte se plánovat rodinné finance", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je 'zero-based budgeting'?",
             "options": ["Mít nulové výdaje", "Každá koruna příjmu má přiřazený účel", "Spořit pouze přebytky", "Nekupovat žádná přání"],
             "correct": 1, "explanation": "Zero-based budgeting znamená, že příjmy minus výdaje = 0. Každé koruně přiřadíte funkci – spoření, výdaje nebo investice."},
            {"id": "q2", "text": "Co je 'obálková metoda' (envelope method)?",
             "options": ["Platit vše poštovní poukázkou", "Rozdělení hotovosti do obálek dle kategorií výdajů", "Zasílání výpisů poštou", "Investice do dluhopisů"],
             "correct": 1, "explanation": "Obálková metoda je fyzický systém: rozdělíte hotovost do obálek označených kategoriemi (jídlo, zábava atd.) a z každé čerpáte jen danou částku."},
            {"id": "q3", "text": "Jak nejlépe snížit fixní výdaje?",
             "options": ["Přestat platit nájemné", "Renegociovat smlouvy, sdílet náklady, hledat levnější alternativy", "Vzít si půjčku", "Ignorovat je"],
             "correct": 1, "explanation": "Fixní výdaje lze snížit například renegociací smluv (internet, telefon), sdílením nákladů nebo přechodem na levnější variantu."},
            {"id": "q4", "text": "Co byste měli udělat s přebytkem v rozpočtu?",
             "options": ["Ihned utratit", "Uložit na spořicí účet nebo investovat", "Vrátit zaměstnavateli", "Zapomenout na něj"],
             "correct": 1, "explanation": "Přebytek je skvělá příležitost pro budování nouzového fondu, splácení dluhů nebo investice do budoucnosti."},
            {"id": "q5", "text": "Jak často byste měli revidovat svůj rozpočet?",
             "options": ["Jednou za 10 let", "Nikdy, stačí ho nastavit jednou", "Měsíčně nebo při změně životní situace", "Pouze v době krize"],
             "correct": 2, "explanation": "Pravidelná revize rozpočtu (ideálně měsíčně) umožňuje přizpůsobit plán aktuální situaci a cílům."}
        ]
    },
    # --- CATEGORY 2: Spoření ---
    {
        "lesson_id": "cat2_l1", "category": "Spoření", "category_emoji": "🐷",
        "category_order": 2, "title": "Proč a jak spořit", "order": 1,
        "description": "Základy efektivního spoření", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je princip 'zaplaťte nejdříve sobě' (pay yourself first)?",
             "options": ["Nakupujte luxusní věci první", "Ihned po výplatě odložte část na spoření", "Nejdříve splaťte všechny účty", "Investujte celý příjem"],
             "correct": 1, "explanation": "Princip 'pay yourself first' znamená, že hned po výplatě automaticky odložíte stanovenou částku na spoření – než ji stihnete utratit."},
            {"id": "q2", "text": "Kdy je nejlepší čas začít spořit?",
             "options": ["Po splacení všech dluhů", "Až budu vydělávat víc", "Co nejdříve, i malé částky jsou cenné", "Před důchodem"],
             "correct": 2, "explanation": "Díky složenému úroku platí: čím dříve začnete, tím lépe. I 500 Kč měsíčně v 25 letech je mnohem cennější než 2 000 Kč v 45."},
            {"id": "q3", "text": "Co je složený úrok (compound interest)?",
             "options": ["Úrok z více půjček najednou", "Úrok, který se přičítá k jistině a pak opět přináší úrok", "Úrok placený ročně", "Typ daňového odpočtu"],
             "correct": 1, "explanation": "Složený úrok je 'úrok z úroku'. Vaše úspory rostou exponenciálně – čím déle spoříte, tím rychleji roste váš kapitál."},
            {"id": "q4", "text": "Kolik procent příjmu doporučují finanční experti spořit?",
             "options": ["2–5 %", "Alespoň 20 %", "Přesně 50 %", "Záleží na věku, ale vždy 0 %"],
             "correct": 1, "explanation": "Finanční experti doporučují spořit alespoň 20 % čistého příjmu. I pokud to zpočátku není možné, začněte i s 5 % a postupně zvyšujte."},
            {"id": "q5", "text": "Proč je automatizace spoření výhodná?",
             "options": ["Banky za ni platí bonus", "Odstraňuje potřebu vůle a snižuje riziko utracení úspor", "Je povinná ze zákona", "Přináší vyšší úroky"],
             "correct": 1, "explanation": "Automatický převod na spořicí účet hned po výplatě eliminuje pokušení peníze utratit."}
        ]
    },
    {
        "lesson_id": "cat2_l2", "category": "Spoření", "category_emoji": "🐷",
        "category_order": 2, "title": "Nouzový fond", "order": 2,
        "description": "Vaše finanční záchranná síť", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je nouzový fond?",
             "options": ["Státní podpora v nezaměstnanosti", "Peněžní rezerva pro neočekávané výdaje", "Typ investičního fondu", "Půjčka s nízkým úrokem"],
             "correct": 1, "explanation": "Nouzový fond je vaše finanční polštář – peníze rezervované pouze pro skutečně neočekávané situace (ztráta práce, oprava auta, zdravotní problém)."},
            {"id": "q2", "text": "Jaká je doporučená výše nouzového fondu?",
             "options": ["1–2 měsíční výdaje", "3–6 měsíčních výdajů", "Přesně 100 000 Kč", "Vše, co ušetříte"],
             "correct": 1, "explanation": "3 až 6 měsíčních výdajů pokryje většinu krizí. Pokud máte nejistý příjem, doporučuje se 6–12 měsíců."},
            {"id": "q3", "text": "Kde nejlépe uchovávat nouzový fond?",
             "options": ["V hotovosti doma", "V akciích pro maximální výnos", "Na spořicím účtu s okamžitou dostupností", "V penzijním fondu"],
             "correct": 2, "explanation": "Nouzový fond musí být okamžitě dostupný bez pokut. Spořicí účet nabízí bezpečnost, dostupnost a malý úrokový výnos."},
            {"id": "q4", "text": "Na co by se nouzový fond NEMĚL používat?",
             "options": ["Ztráta zaměstnání", "Nečekaná oprava auta", "Nový telefon, který jste chtěli", "Urgentní zdravotní péče"],
             "correct": 2, "explanation": "Nouzový fond je pro skutečné krize, ne pro plánované nebo diskreční výdaje. Na přání si šetřete zvlášť."},
            {"id": "q5", "text": "Vaše měsíční výdaje jsou 25 000 Kč. Jaký je minimální doporučený nouzový fond?",
             "options": ["25 000 Kč", "50 000 Kč", "75 000 Kč", "250 000 Kč"],
             "correct": 2, "explanation": "Minimum jsou 3 měsíce výdajů: 3 × 25 000 Kč = 75 000 Kč. Ideálně 6 měsíců = 150 000 Kč."}
        ]
    },
    {
        "lesson_id": "cat2_l3", "category": "Spoření", "category_emoji": "🐷",
        "category_order": 2, "title": "Spořicí produkty v ČR", "order": 3,
        "description": "Přehled spořicích možností v České republice", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Jaký je hlavní rozdíl mezi běžným a spořicím účtem?",
             "options": ["Spořicí účet nese vyšší úrok a omezuje výběry", "Běžný účet je bezpečnější", "Spořicí účet je povinný", "Žádný rozdíl"],
             "correct": 0, "explanation": "Spořicí účet nabízí vyšší úrokové sazby než běžný účet. Může mít omezený počet výběrů, ale peníze jsou stále dostupné."},
            {"id": "q2", "text": "Co je stavební spoření v ČR?",
             "options": ["Spoření určené výhradně na nákup nábytku", "Státem podporované spoření s příspěvkem až 2 000 Kč ročně na bydlení", "Typ hypotéky", "Penzijní produkt"],
             "correct": 1, "explanation": "Stavební spoření je produkt s státní podporou (až 2 000 Kč/rok). Po 6 letech můžete získat úvěr na bydlení za výhodný úrok."},
            {"id": "q3", "text": "Co je penzijní připojištění (transformovaný fond)?",
             "options": ["Povinné pojistné placené zaměstnavatelem", "Dobrovolné důchodové spoření s možným příspěvkem zaměstnavatele a daňovým odpočtem", "Státní důchod", "Spekulativní investice"],
             "correct": 1, "explanation": "Penzijní připojištění je dobrovolné spoření na důchod. Stát přispívá, zaměstnavatel může přispívat a vy si odečtete část ze základu daně."},
            {"id": "q4", "text": "Do jaké výše jsou vklady v bankách pojištěny Fondem pojištění vkladů?",
             "options": ["100 000 Kč", "500 000 Kč", "2 500 000 Kč (100 000 EUR)", "Bez limitu"],
             "correct": 2, "explanation": "Vklady jsou pojištěny do výše 100 000 EUR (cca 2,5 mil. Kč) na osobu a banku. Pokud máte více, rozdělte je mezi více bank."},
            {"id": "q5", "text": "Co je to spořicí výzva '52 týdnů'?",
             "options": ["Investovat 52 000 Kč najednou", "Každý týden uložit o 50 Kč více než předchozí týden (1. týden 50 Kč, 2. týden 100 Kč...)", "Nekupovat nic po dobu roku", "Bankovní produkt"],
             "correct": 1, "explanation": "Výzva 52 týdnů je populární gamifikace spoření. Za rok ušetříte 68 900 Kč, přičemž každý týden jen o trochu zvyšujete úložku."}
        ]
    },
    # --- CATEGORY 3: Dluhy ---
    {
        "lesson_id": "cat3_l1", "category": "Dluhy", "category_emoji": "💳",
        "category_order": 3, "title": "Dobré a špatné dluhy", "order": 1,
        "description": "Naučte se rozlišovat prospěšné a škodlivé dluhy", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je příkladem 'dobrého dluhu'?",
             "options": ["Půjčka na dovolenou", "Spotřebitelský úvěr na nový TV", "Hypotéka na koupi nemovitosti", "Kreditní karta pro každodenní nákupy"],
             "correct": 2, "explanation": "Dobrý dluh investuje do aktiv, která se zhodnocují nebo generují příjem (vzdělání, nemovitost, podnikání). Špatný dluh financuje depreciující věci."},
            {"id": "q2", "text": "Která z uvedených RPSN (roční procentní sazba nákladů) je nejdražší?",
             "options": ["Hypotéka: 5 %", "Autoúvěr: 8 %", "Kreditní karta: 22 %", "Spotřebitelský úvěr: 12 %"],
             "correct": 2, "explanation": "RPSN zahrnuje veškeré náklady úvěru. Kreditní karty mají typicky nejvyšší sazby (15–30 %), proto je kritické splácet je vždy celé."},
            {"id": "q3", "text": "Co je metoda 'debt avalanche' (lavina dluhů)?",
             "options": ["Brát si vždy více půjček", "Nejdříve splatit dluh s nejvyšším úrokem", "Nejdříve splatit nejmenší dluh", "Ignorovat dluhy s nízkým zůstatkem"],
             "correct": 1, "explanation": "Metoda debt avalanche: nejdříve splatíte dluh s nejvyšším úrokem, čímž minimalizujete celkové náklady na dluhy."},
            {"id": "q4", "text": "Co je metoda 'debt snowball' (sněhová koule)?",
             "options": ["Refinancování všech dluhů", "Nejdříve splatit dluh s nejvyšší jistinou", "Nejdříve splatit nejmenší dluh pro psychologickou motivaci", "Platit jen minimální splátky"],
             "correct": 2, "explanation": "Metoda snowball: nejdříve splatíte nejmenší dluh. I když finančně není optimální jako avalanche, psychologicky motivuje k pokračování."},
            {"id": "q5", "text": "Jaké je nebezpečí úvěrové past?",
             "options": ["Příliš vysoké úspory", "Spirála, kde si berete půjčky na splacení jiných půjček", "Nízké úrokové sazby", "Rychlé splacení dluhu"],
             "correct": 1, "explanation": "Úvěrová past nastane, když si musíte půjčovat na splácení existujících dluhů. Náklady exponenciálně rostou a situace se stává neudržitelnou."}
        ]
    },
    {
        "lesson_id": "cat3_l2", "category": "Dluhy", "category_emoji": "💳",
        "category_order": 3, "title": "Kreditní karty a půjčky", "order": 2,
        "description": "Jak chytře používat kreditní karty a úvěry", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je 'bezúročné období' u kreditní karty?",
             "options": ["Období, kdy karta nefunguje", "Doba, po kterou neplatíte úroky, pokud splatíte celý zůstatek", "Doba, kdy je karta zdarma", "Minimální splátka"],
             "correct": 1, "explanation": "Bezúročné období (typicky 45–55 dní) umožňuje platit kreditkou bez úroků, pokud každý měsíc splatíte celý dluh. Jinak úroky jsou vysoké."},
            {"id": "q2", "text": "Co se stane, když platíte jen minimální splátku kreditní karty?",
             "options": ["Je to ideální strategie", "Splatíte dluh rychleji", "Zaplatíte mnohonásobek původní ceny kvůli úrokům", "Karta se automaticky zruší"],
             "correct": 2, "explanation": "Minimální splátka pokryje jen úroky a malou část jistiny. Dluh 50 000 Kč s 20% úrokem při minimálních splátkách může trvat 20+ let."},
            {"id": "q3", "text": "Co je refinancování půjčky?",
             "options": ["Vzít si novou, dražší půjčku", "Nahradit stávající půjčku novou s lepšími podmínkami", "Odložení splátek o rok", "Prominutí dluhu"],
             "correct": 1, "explanation": "Refinancování = záměna stávající půjčky za novou s nižším úrokem nebo lepšími podmínkami. Může ušetřit tisíce korun na úrocích."},
            {"id": "q4", "text": "Jaká je výhoda pravidelného splácení půjček na čas?",
             "options": ["Žádná výhoda", "Budujete si dobrou úvěrovou historii a skóre", "Dostanete zpět zaplacené úroky", "Snižuje se daňová zátěž"],
             "correct": 1, "explanation": "Dobrá platební historie je základem zdravého úvěrového skóre. Pomáhá při žádosti o hypotéku, autoúvěr nebo jiné produkty s nízkým úrokem."},
            {"id": "q5", "text": "Na co si dát pozor při rychlých půjčkách (SMS půjčky)?",
             "options": ["Jsou vždy výhodné", "Mají extrémně vysoké RPSN, někdy přes 1000 %", "Stát je dotuje", "Jsou bezúrokové"],
             "correct": 1, "explanation": "Rychlé půjčky a mikropůjčky mívají RPSN přes 100–1000 %. Za malou krátkodobou půjčku zaplatíte násobek původní sumy."}
        ]
    },
    {
        "lesson_id": "cat3_l3", "category": "Dluhy", "category_emoji": "💳",
        "category_order": 3, "title": "Hypotéky", "order": 3,
        "description": "Základy hypotečního financování", "xp_reward": 20,
        "questions": [
            {"id": "q1", "text": "Co je LTV (Loan-to-Value) u hypotéky?",
             "options": ["Roční úroková sazba", "Poměr výše půjčky k hodnotě nemovitosti", "Délka fixace úroku", "Měsíční splátka"],
             "correct": 1, "explanation": "LTV 80 % znamená, že si půjčujete 80 % hodnoty nemovitosti a 20 % musíte mít jako vlastní kapitál. Nižší LTV = nižší úrok."},
            {"id": "q2", "text": "Co je fixace úrokové sazby hypotéky?",
             "options": ["Změna výše splátky", "Období, po které se nemění úroková sazba", "Poplatek za předčasné splacení", "Pojištění hypotéky"],
             "correct": 1, "explanation": "Fixace (typicky 3, 5 nebo 10 let) zaručuje neměnný úrok po dané období. Po skončení fixace banka nabídne novou sazbu."},
            {"id": "q3", "text": "Jak ovlivní délka hypotéky (20 vs. 30 let) měsíční splátku?",
             "options": ["Délka splácení neovlivňuje splátku", "Delší hypotéka má nižší splátku, ale zaplatíte více na úrocích", "Kratší hypotéka má nižší splátku", "Splátka závisí pouze na úrokové sazbě"],
             "correct": 1, "explanation": "Delší hypotéka = nižší měsíční splátka, ale zaplatíte mnohem více na úrocích celkem. Kratší = vyšší splátka, ale ušetříte statisíce."},
            {"id": "q4", "text": "Co jsou dle ČNB tzv. DSTI a DTI limity?",
             "options": ["Typy bankovních poplatků", "Limity poměru splátky/příjmu a celkového dluhu/příjmu", "Daňové odpočty na hypotéku", "Pojistné produkty"],
             "correct": 1, "explanation": "ČNB stanovuje limity: DSTI (celkové splátky max. 50 % příjmu) a DTI (celkový dluh max. 8,5× ročního příjmu). Chrání před předlužením."},
            {"id": "q5", "text": "Co je předčasné splacení hypotéky a kdy je výhodné?",
             "options": ["Nevýhodné vždy", "Splacení části nebo celé hypotéky před koncem fixace, ideálně na konci fixačního období", "Automatické navýšení splátky", "Státní dotace na hypotéku"],
             "correct": 1, "explanation": "Předčasné splacení na konci fixace bývá bezpoplatkové. Výhodné při vysokém úroku nebo přebytku financí – snižuje celkové náklady."}
        ]
    },
    # --- CATEGORY 4: Investování ---
    {
        "lesson_id": "cat4_l1", "category": "Investování", "category_emoji": "📈",
        "category_order": 4, "title": "Základy investování", "order": 1,
        "description": "První kroky ve světě investic", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Proč inflace snižuje hodnotu peněz?",
             "options": ["Banky berou poplatky", "Zvyšující se ceny zboží znamenají, že za stejnou sumu koupíte méně", "Stát zdaňuje úspory", "Směnný kurz se mění"],
             "correct": 1, "explanation": "Inflace 3 % ročně snižuje kupní sílu peněz. 100 000 Kč dnes bude za 10 let mít kupní sílu asi 74 000 Kč. Investice chrání před inflací."},
            {"id": "q2", "text": "Co je diverzifikace portfolia?",
             "options": ["Investovat vše do jedné akcie", "Rozložit investice do více různých aktiv pro snížení rizika", "Pravidelně měnit investiční strategii", "Investovat pouze do zlata"],
             "correct": 1, "explanation": "Diverzifikace = 'Nedávejte všechna vejce do jednoho košíku.' Rozložením do různých aktiv snižujete riziko ztráty."},
            {"id": "q3", "text": "Jaký je vztah mezi rizikem a potenciálním výnosem?",
             "options": ["Vyšší riziko = nižší výnos", "Vyšší riziko = vyšší potenciální výnos", "Riziko a výnos spolu nesouvisí", "Nižší riziko = vždy vyšší výnos"],
             "correct": 1, "explanation": "Základní princip: za vyšší riziko se žádá vyšší potenciální odměna. Státní dluhopisy jsou bezpečné (nízký výnos), akcie rizikovější (vyšší potenciální výnos)."},
            {"id": "q4", "text": "Co je investiční horizont?",
             "options": ["Zeměpisná oblast investic", "Plánovaná délka doby, po kterou plánujete mít investici", "Roční výnos investice", "Poplatky za správu fondu"],
             "correct": 1, "explanation": "Investiční horizont určuje strategii. Krátký horizont (1–3 roky) → konzervativnější přístup. Dlouhý horizont (10+ let) → lze tolerovat vyšší riziko pro vyšší výnos."},
            {"id": "q5", "text": "Co je pravidelné investování (DCA – Dollar Cost Averaging)?",
             "options": ["Investovat celou úsporu najednou", "Pravidelně investovat fixní částku bez ohledu na cenu", "Kupovat pouze při propadu trhu", "Investovat jen do amerických akcií"],
             "correct": 1, "explanation": "DCA znamená investovat např. 2 000 Kč každý měsíc bez ohledu na cenu. Průměrujete nákupní cenu a eliminujete riziko špatného načasování."}
        ]
    },
    {
        "lesson_id": "cat4_l2", "category": "Investování", "category_emoji": "📈",
        "category_order": 4, "title": "Akcie a dluhopisy", "order": 2,
        "description": "Pochopte nejrozšířenější investiční nástroje", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Co je akcie?",
             "options": ["Půjčka společnosti", "Podíl ve vlastnictví společnosti", "Státní cenný papír", "Pojistný produkt"],
             "correct": 1, "explanation": "Akcie reprezentuje podíl v dané společnosti. Jako akcionář máte právo na dividendy a podíl na růstu hodnoty firmy."},
            {"id": "q2", "text": "Co je dluhopis?",
             "options": ["Podíl v podniku", "Půjčka poskytnutá emitentovi (státu/firmě) za pravidelný úrok", "Typ spořicího účtu", "Kryptoměna"],
             "correct": 1, "explanation": "Dluhopis je cenný papír, kterým půjčujete peníze emitentovi (stát, firma). Na oplátku dostáváte pravidelný úrok (kupon) a jistinu zpět po splatnosti."},
            {"id": "q3", "text": "Které aktivum je obecně považováno za bezpečnější?",
             "options": ["Akcie malých podniků", "Státní dluhopisy vyspělých zemí", "Kryptoměny", "Startupové investice"],
             "correct": 1, "explanation": "Státní dluhopisy vyspělých zemí (ČR, Německo, USA) jsou považovány za velmi bezpečné, ale s nižším výnosem. Akcie a krypto jsou rizikovější."},
            {"id": "q4", "text": "Co je dividenda?",
             "options": ["Burzovní poplatek", "Podíl na zisku společnosti vyplácený akcionářům", "Typ obligace", "Daňová sleva pro investory"],
             "correct": 1, "explanation": "Dividenda je část zisku, kterou firma vyplácí akcionářům. Ne všechny společnosti platí dividendy – růstové firmy (tech) raději reinvestují zisk."},
            {"id": "q5", "text": "Co je tržní kapitalizace (market cap) společnosti?",
             "options": ["Roční tržby firmy", "Celková tržní hodnota všech akcií firmy", "Hodnota nemovitostí firmy", "Výše dividend"],
             "correct": 1, "explanation": "Tržní kapitalizace = cena akcie × počet akcií. Například Apple: 180 $ × 15 mld. akcií = 2 700 mld. $. Kategorie: large-cap, mid-cap, small-cap."}
        ]
    },
    {
        "lesson_id": "cat4_l3", "category": "Investování", "category_emoji": "📈",
        "category_order": 4, "title": "ETF a podílové fondy", "order": 3,
        "description": "Nejpopulárnější způsoby kolektivního investování", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Co je ETF (Exchange Traded Fund)?",
             "options": ["Typ bankovního účtu", "Fond obchodovaný na burze, který sleduje index (např. S&P 500)", "Státní obligace", "Kryptografický token"],
             "correct": 1, "explanation": "ETF je košík cenných papírů obchodovaný na burze jako akcie. Index ETF (např. S&P 500 ETF) kopíruje výkonnost 500 největších amerických firem."},
            {"id": "q2", "text": "Jaká je hlavní výhoda ETF oproti aktivně spravovaným fondům?",
             "options": ["ETF vždy vydělají více", "Nižší poplatky (TER) a průhlednost", "ETF jsou pojištěny státem", "ETF nemají žádné riziko"],
             "correct": 1, "explanation": "ETF mají typicky velmi nízké roční poplatky (0,05–0,5 %), zatímco aktivně spravované fondy účtují 1–2 %. Zdánlivě malý rozdíl může za 30 let znamenat statisíce Kč."},
            {"id": "q3", "text": "Co je index S&P 500?",
             "options": ["500 největších německých firem", "Index 500 největších amerických společností obchodovaných na burze", "Úroková sazba FEDu", "Burzovní index ČR"],
             "correct": 1, "explanation": "S&P 500 sleduje 500 největších amerických veřejně obchodovaných firem. Historicky přinášel průměrný roční výnos ~10 % (před inflací)."},
            {"id": "q4", "text": "Co je TER (Total Expense Ratio)?",
             "options": ["Celkový zisk fondu", "Celkové roční náklady fondu vyjádřené v %", "Daň z výnosu fondu", "Minimální investice"],
             "correct": 1, "explanation": "TER je celkový roční poplatek za správu fondu. ETF mají TER kolem 0,07–0,50 %, aktivní fondy 1–2,5 %. Čím nižší TER, tím více vám zůstane."},
            {"id": "q5", "text": "Co je rebalancování portfolia?",
             "options": ["Prodej všech aktiv při poklesu trhu", "Pravidelná úprava portfolia zpět na cílové rozložení aktiv", "Přidání nových aktiv každý den", "Zdanění investičních výnosů"],
             "correct": 1, "explanation": "Rebalancování = obnovení původního rozložení aktiv. Pokud akcie vzrostly z 60 % na 75 % portfolia, část prodáte a nakoupíte jiná aktiva k udržení strategie."}
        ]
    },
    # --- CATEGORY 5: Daně ---
    {
        "lesson_id": "cat5_l1", "category": "Daně", "category_emoji": "🏛️",
        "category_order": 5, "title": "Daň z příjmu v ČR", "order": 1,
        "description": "Jak funguje zdanění příjmů v České republice", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Jaká je základní sazba daně z příjmu fyzických osob v ČR?",
             "options": ["10 %", "15 %", "20 %", "25 %"],
             "correct": 1, "explanation": "V ČR platíte 15 % daně z příjmu. Pro příjmy nad 48násobek průměrné mzdy (cca 1,9 mil. Kč ročně) platí sazba 23 %."},
            {"id": "q2", "text": "Co je daňové přiznání?",
             "options": ["Přihlášení k platbě pojistného", "Formulář, kde oznamujete příjmy a výpočet daně finančnímu úřadu", "Žádost o sociální dávku", "Smlouva s bankou"],
             "correct": 1, "explanation": "Daňové přiznání musíte podat, pokud máte příjmy z více zdrojů, OSVČ činnost nebo jiné příjmy nad 20 000 Kč mimo zaměstnání. Termín: 1. dubna (nebo 1. července s poradcem)."},
            {"id": "q3", "text": "Co je 'sleva na poplatníka' v ČR?",
             "options": ["Sleva v obchodech pro daňové poplatníky", "Základní roční daňová sleva 30 840 Kč, na kterou má každý pracující nárok", "Odpočet za děti", "Sleva za pojištění"],
             "correct": 1, "explanation": "Každý daňový rezident ČR má nárok na základní slevu na poplatníka 30 840 Kč ročně (2 570 Kč/měsíc), která přímo snižuje výši daně."},
            {"id": "q4", "text": "Co jsou zálohy na daň pro OSVČ?",
             "options": ["Dopředu placená daň na základě příjmů z minulého roku", "Dobrovolné příspěvky do státního rozpočtu", "Povinné pojistné", "Záloha na nákup majetku"],
             "correct": 0, "explanation": "OSVČ platí zálohy na daň z příjmu čtvrtletně nebo pololetně. Výše vychází z daně za předchozí rok. Po podání přiznání se vyrovná přeplatek nebo nedoplatek."},
            {"id": "q5", "text": "Co je DPH (daň z přidané hodnoty)?",
             "options": ["Daň z příjmu zaměstnanců", "Nepřímá daň zahrnutá v ceně zboží a služeb, plátcem je firma", "Daň z nemovitostí", "Sociální pojistné"],
             "correct": 1, "explanation": "DPH je nepřímá daň, kterou platíte jako zákazník v ceně produktu. Základní sazba v ČR je 21 %, snížené sazby 15 % (potraviny) a 10 % (léky, knihy)."}
        ]
    },
    {
        "lesson_id": "cat5_l2", "category": "Daně", "category_emoji": "🏛️",
        "category_order": 5, "title": "Daňové odpočty a výhody", "order": 2,
        "description": "Jak legálně snížit daňovou zátěž", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Co je odečitatelná položka od základu daně?",
             "options": ["Přímá sleva na dani", "Částka snižující základ daně, ze které se pak počítá 15%", "Vrácení přeplatku daně", "Povinný příspěvek státu"],
             "correct": 1, "explanation": "Odečitatelné položky snižují základ daně. Pokud odpočtete 12 000 Kč, ušetříte na dani 12 000 × 15 % = 1 800 Kč."},
            {"id": "q2", "text": "Co si lze odečíst od základu daně v ČR?",
             "options": ["Výdaje za jídlo a oblečení", "Penzijní připojištění (nad 12 000 Kč), životní pojištění, úroky z hypotéky, dary", "Splátky kreditní karty", "Nákup automobilu"],
             "correct": 1, "explanation": "Daňové odpočty v ČR: úroky z hypotéky (až 150 000 Kč/rok), penzijní připojištění (příspěvky nad 12 000 Kč ročně), životní pojištění (až 24 000 Kč), dary."},
            {"id": "q3", "text": "Jak funguje daňové zvýhodnění na dítě?",
             "options": ["Stát platí za vás pojistné za každé dítě", "Přímá sleva na dani (daňový bonus) za každé vyživované dítě v domácnosti", "Snížení DPH na dětské zboží", "Bezúročná půjčka na vzdělání"],
             "correct": 1, "explanation": "Za první dítě máte nárok na daňové zvýhodnění 15 204 Kč/rok. Za druhé 22 320 Kč a za třetí a další 27 840 Kč ročně (hodnoty se mohou měnit)."},
            {"id": "q4", "text": "Co je daňové přiznání za OSVČ a kdy se podává?",
             "options": ["Každý týden", "Do 1. dubna (nebo 1. července s daňovým poradcem) za předchozí rok", "Do 1. ledna za aktuální rok", "Kdykoli v roce"],
             "correct": 1, "explanation": "OSVČ podávají přiznání do 1. 4. Pokud ho zpracovává daňový poradce, termín se prodlužuje na 1. 7. Platit daň musíte ve stejném termínu."},
            {"id": "q5", "text": "Co je daň z kapitálových výnosů (z prodeje akcií)?",
             "options": ["Daň z dividend", "Daň z rozdílu mezi nákupní a prodejní cenou cenných papírů", "Poplatek za správu portfolia", "DPH na finanční produkty"],
             "correct": 1, "explanation": "V ČR: pokud držíte akcie déle než 3 roky, zisk z prodeje je od daně osvobozen. Pokud prodáte dříve, zisk se zdaňuje jako ostatní příjem (15 %)."}
        ]
    },
    {
        "lesson_id": "cat5_l3", "category": "Daně", "category_emoji": "🏛️",
        "category_order": 5, "title": "OSVČ a podnikání", "order": 3,
        "description": "Daně a odvody pro živnostníky", "xp_reward": 25,
        "questions": [
            {"id": "q1", "text": "Co jsou paušální výdaje pro OSVČ?",
             "options": ["Povinné platby státu", "Zákonem stanovené procento z příjmů jako náhrada za skutečné výdaje", "Platba za licence", "Výdaje na reklamu"],
             "correct": 1, "explanation": "Paušální výdaje umožňují odečíst % z příjmů bez nutnosti dokládat skutečné výdaje. Řemeslníci 80 %, svobodná povolání 60 %, ostatní 40 %."},
            {"id": "q2", "text": "Co je paušální daň pro OSVČ (od 2021)?",
             "options": ["Fixní měsíční platba zahrnující daň, zdravotní a sociální pojistné", "Sleva na dani pro živnostníky", "Osvobození od DPH", "Státní příspěvek OSVČ"],
             "correct": 0, "explanation": "Paušální daň je jedna fixní měsíční platba (~9 000 Kč/měsíc) zahrnující daň z příjmu + zdravotní + sociální pojistné. Vhodná pro OSVČ s příjmem do 2 mil. Kč."},
            {"id": "q3", "text": "Jaký je rozdíl mezi OSVČ a s.r.o.?",
             "options": ["Žádný rozdíl", "OSVČ ručí celým majetkem, s.r.o. pouze vkladem do firmy", "s.r.o. platí méně daní vždy", "OSVČ je pouze pro IT obory"],
             "correct": 1, "explanation": "OSVČ = fyzická osoba podnikající na živnostenský list, ručí vším. s.r.o. = právnická osoba, odděluje osobní a firemní majetek, má více administrativy ale ochranu majetku."},
            {"id": "q4", "text": "Co jsou minimální zálohy na sociální pojištění pro OSVČ v ČR?",
             "options": ["Neexistují minimální zálohy", "Jsou stanoveny státem a mění se každý rok, základní cca 3 000–4 000 Kč/měsíc", "Přesně 1 000 Kč/měsíc", "Zálohy platí stát za OSVČ"],
             "correct": 1, "explanation": "OSVČ musí platit minimální zálohy na sociální a zdravotní pojistné. Výše se každoročně mění (odvíjí od průměrné mzdy). Jsou-li příjmy vyšší, zálohy se zvyšují."},
            {"id": "q5", "text": "Co je neplátce DPH vs. plátce DPH?",
             "options": ["Rozdíl v sazbě daně z příjmu", "Pokud obrat přesáhne 2 mil. Kč ročně, stáváte se plátcem DPH a účtujete DPH zákazníkům", "Plátce DPH platí nižší daně", "DPH se týká jen firem, ne OSVČ"],
             "correct": 1, "explanation": "Dobrovolně nebo povinně (obrat nad 2 mil. Kč) se stáváte plátcem DPH. Přidáváte DPH k cenám, ale zároveň si odečítáte DPH ze svých nákupů pro podnikání."}
        ]
    },
    # --- CATEGORY 6: Pokročilé ---
    {
        "lesson_id": "cat6_l1", "category": "Pokročilé", "category_emoji": "🚀",
        "category_order": 6, "title": "Akcie – pokročilé", "order": 1,
        "description": "Hloubkový pohled na akciové investice", "xp_reward": 30,
        "questions": [
            {"id": "q1", "text": "Co je P/E ratio (Price-to-Earnings)?",
             "options": ["Podíl ceny akcie a dividendy", "Cena akcie dělená ročním ziskem na akcii – ukazuje, kolik platíte za 1 Kč zisku", "Roční výnos portfolia", "Procentuální pokles akcie"],
             "correct": 1, "explanation": "P/E = cena akcie / zisk na akcii (EPS). P/E 20 znamená, že platíte 20 Kč za každou 1 Kč ročního zisku. Nízké P/E může být levná akcie, vysoké P/E = očekávání růstu."},
            {"id": "q2", "text": "Co je short selling (krátký prodej)?",
             "options": ["Krátkodobá koupě akcií", "Spekulace na pokles ceny – půjčíte si akcie, prodáte je a doufáte v levnější zpětný nákup", "Prodej akcií pod tržní cenou", "Rychlý nákup při propadu"],
             "correct": 1, "explanation": "Short selling: půjčíte si 100 akcií, prodáte za 500 Kč. Pokud klesnou na 400 Kč, koupíte je zpět a vrátíte, zisk 100 Kč/akcie. Ale pokud cena roste, ztráta je neomezená."},
            {"id": "q3", "text": "Co je dividendový výnos?",
             "options": ["Celkový roční výnos akcie", "Roční dividenda dělená cenou akcie v %", "Daň z dividend", "Počet dividend ročně"],
             "correct": 1, "explanation": "Dividendový výnos = (roční dividenda / cena akcie) × 100. Akcie za 1000 Kč s dividendou 50 Kč = 5% dividendový výnos. Srovnatelné s úrokovým výnosem dluhopisu."},
            {"id": "q4", "text": "Co je IPO (Initial Public Offering)?",
             "options": ["Pravidelná výplata dividend", "První veřejná nabídka akcií – firma poprvé vstupuje na burzu", "Typ investičního fondu", "Mezinárodní burzovní index"],
             "correct": 1, "explanation": "IPO = vstup firmy na burzu. Firma vydá nové akcie a prodá je veřejnosti. Investoři mohou nakoupit nové akcie. IPO bývá vzrušující, ale i rizikové (neznámá tržní cena)."},
            {"id": "q5", "text": "Co je hodnotové investování (value investing)?",
             "options": ["Investování do luxusních značek", "Hledání podhodnocených akcií s vnitřní hodnotou vyšší než tržní cena (Warren Buffett)", "Spekulativní obchodování", "Investice do startupů"],
             "correct": 1, "explanation": "Value investing = nakupovat akcie, jejichž tržní cena je nižší než jejich skutečná (vnitřní) hodnota. Filosofie Warrena Buffetta a Benjamina Grahama."}
        ]
    },
    {
        "lesson_id": "cat6_l2", "category": "Pokročilé", "category_emoji": "🚀",
        "category_order": 6, "title": "Kryptoměny", "order": 2,
        "description": "Základy světa digitálních měn", "xp_reward": 30,
        "questions": [
            {"id": "q1", "text": "Co je blockchain?",
             "options": ["Typ kryptoměnné peněženky", "Decentralizovaná distribuovaná databáze záznamů (bloků) propojených kryptograficky", "Centrální banka pro krypto", "Platební karta pro kryptoměny"],
             "correct": 1, "explanation": "Blockchain je nezměnitelná veřejná databáze transakcí. Každý blok obsahuje data, hash a hash předchozího bloku. Decentralizovaný – žádná centrální autorita."},
            {"id": "q2", "text": "Jaké je hlavní riziko investic do kryptoměn?",
             "options": ["Příliš nízký výnos", "Extrémní volatilita – cena může klesnout o 50–90 % v krátkém čase", "Státní regulace zakazující zisk", "Příliš komplexní nákup"],
             "correct": 1, "explanation": "Kryptoměny jsou extrémně volatilní. Bitcoin klesl v roce 2022 z ~65 000 $ na ~16 000 $ (−75 %). Investujte jen peníze, o které si můžete dovolit přijít."},
            {"id": "q3", "text": "Co je DeFi (Decentralized Finance)?",
             "options": ["Státní digitální měna", "Finanční služby (půjčky, směna, spoření) fungující bez zprostředkovatelů na blockchainu", "Typ kreditní karty", "Systém zálohy na krypto"],
             "correct": 1, "explanation": "DeFi nahrazuje tradiční finanční instituce smart kontrakty na blockchainu. Poskytuje půjčky, úroky a obchodování bez banky – ale s vyšším rizikem."},
            {"id": "q4", "text": "Co je 'cold wallet' (studená peněženka)?",
             "options": ["Bankovní účet pro kryptoměny", "Hardware zařízení pro offline uchovávání kryptoměn, bezpečnější před hackery", "Burzovní peněženka", "Zmrazený bankovní účet"],
             "correct": 1, "explanation": "Cold wallet (hardware wallet, např. Ledger, Trezor) uchovává privátní klíče offline. Nejvyšší bezpečnost – hackeři k ní nemají přístup přes internet."},
            {"id": "q5", "text": "Jak se zdaňují příjmy z kryptoměn v ČR?",
             "options": ["Jsou zcela osvobozeny od daně", "Zisky z prodeje do 1 roku = zdanění jako ostatní příjem (15 %), po 3 letech pro fyzické osoby osvobozen", "Zdaňují se jako DPH", "Platí se fixní 5% daň"],
             "correct": 1, "explanation": "Od 2025: fyzické osoby jsou osvobozeny od daně z prodeje kryptoměn po 3 letech držení. Pro příjmy do 100 000 Kč ročně také osvobození. Jinak 15 % ze zisku."}
        ]
    },
    {
        "lesson_id": "cat6_l3", "category": "Pokročilé", "category_emoji": "🚀",
        "category_order": 6, "title": "Nemovitosti a penzijní spoření", "order": 3,
        "description": "Dlouhodobé budování majetku", "xp_reward": 30,
        "questions": [
            {"id": "q1", "text": "Co je výnosový pronájem (buy-to-let)?",
             "options": ["Státní program pronájmu", "Nákup nemovitosti za účelem pronájmu a generování pasivního příjmu", "Dočasná výpůjčka bytu", "Typ hypotéky"],
             "correct": 1, "explanation": "Buy-to-let = koupíte nemovitost, pronajmete ji a inkasujete nájemné. Ideálně nájemné pokryje hypotéku a přinese zisk. Nutno počítat s opravami a prázdninami."},
            {"id": "q2", "text": "Jaký je přibližný výnosový ukazatel nemovitosti (rental yield)?",
             "options": ["Počet pokojů / cena", "(Roční nájemné / cena nemovitosti) × 100 %", "Cena nemovitosti / inflace", "Výše hypotéky"],
             "correct": 1, "explanation": "Hrubý výnos z pronájmu = (roční nájemné / cena nemovitosti) × 100. Byt za 5 mil. Kč s nájmem 20 000 Kč/měsíc = (240 000 / 5 000 000) × 100 = 4,8 % hrubý výnos."},
            {"id": "q3", "text": "Co je DIP (Dlouhodobý investiční produkt) zavedený v ČR od 2024?",
             "options": ["Typ stavebního spoření", "Nový daňově zvýhodněný investiční produkt umožňující investice do akcií a dluhopisů se státní podporou", "Forma penzijního připojištění", "Spořicí dluhopis ČR"],
             "correct": 1, "explanation": "DIP (od 2024) umožňuje odečíst až 48 000 Kč ročně od základu daně při investicích do akcií, dluhopisů a ETF. Alternativa k penzijnímu připojištění s větší flexibilitou."},
            {"id": "q4", "text": "Co je REIT (Real Estate Investment Trust)?",
             "options": ["Registr nemovitostí", "Fond investující do nemovitostí – umožňuje investovat do realit bez přímé koupě nemovitosti", "Hypoteční pojistka", "Realitní kancelář"],
             "correct": 1, "explanation": "REIT = fond obchodovaný na burze, který vlastní nemovitosti. Umožňuje investovat do realit od malých částek, se diverzifikací a bez starostí s pronájmem."},
            {"id": "q5", "text": "Proč je důležité začít spořit na důchod co nejdříve?",
             "options": ["Stát to přikazuje zákonem", "Díky složenému úroku a dlouhému horizontu roste kapitál exponenciálně – každých 10 let prodlení snižuje výsledek o desítky %", "Penze jsou velmi nízké a nestačí na živobytí", "Kvůli inflaci je to zbytečné"],
             "correct": 1, "explanation": "Příklad: 2 000 Kč/měsíc od 25 let → ~5 mil. Kč v 65 letech (při 7 % ročně). Od 35 let → ~2,5 mil. Kč. 10 let navíc = dvojnásobný výsledek díky složenému úroku."}
        ]
    }
]

BADGES_CONFIG = {
    "prvni_lekce": {"name": "První krok", "emoji": "🌱", "description": "Dokončil/a první lekci"},
    "tyden_seria": {"name": "Týdenní série", "emoji": "🔥", "description": "7 dní v řadě"},
    "mesic_seria": {"name": "Měsíční série", "emoji": "⚡", "description": "30 dní v řadě"},
    "zaklady_master": {"name": "Básník čísel", "emoji": "💰", "description": "Dokončil/a kategorii Základy"},
    "sporeni_master": {"name": "Šetřivý", "emoji": "🐷", "description": "Dokončil/a kategorii Spoření"},
    "dluhy_master": {"name": "Bez dluhů", "emoji": "💳", "description": "Dokončil/a kategorii Dluhy"},
    "investovani_master": {"name": "Investor", "emoji": "📈", "description": "Dokončil/a kategorii Investování"},
    "dane_master": {"name": "Daňový expert", "emoji": "🏛️", "description": "Dokončil/a kategorii Daně"},
    "pokrocile_master": {"name": "Finanční guru", "emoji": "🚀", "description": "Dokončil/a kategorii Pokročilé"},
    "vsechny_lekce": {"name": "Mistr financí", "emoji": "👑", "description": "Dokončil/a všechny lekce"},
}


# ============ STARTUP ============

@app.on_event("startup")
async def seed_data():
    count = await db.lessons.count_documents({})
    if count == 0:
        for lesson in SEED_LESSONS:
            await db.lessons.insert_one(lesson)
        logger.info(f"Seeded {len(SEED_LESSONS)} lessons")


# ============ USER ENDPOINTS ============

@api_router.post("/users", response_model=UserResponse)
async def create_or_get_user(data: UserCreate):
    existing = await db.users.find_one({"device_id": data.device_id})
    if existing:
        return _to_user_response(existing)
    user_doc = {
        "user_id": str(uuid.uuid4()),
        "device_id": data.device_id,
        "username": data.username.strip(),
        "xp": 0, "level": 1, "streak": 0,
        "last_activity": None,
        "badges": [], "completed_lessons": [],
        "total_correct": 0, "total_questions": 0,
        "created_at": datetime.now(timezone.utc)
    }
    await db.users.insert_one(user_doc)
    return _to_user_response(user_doc)


@api_router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    user = await db.users.find_one({"user_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return _to_user_response(user)


def _to_user_response(doc: dict) -> UserResponse:
    return UserResponse(
        user_id=doc["user_id"],
        username=doc["username"],
        xp=doc.get("xp", 0),
        level=doc.get("level", 1),
        streak=doc.get("streak", 0),
        last_activity=doc.get("last_activity"),
        badges=doc.get("badges", []),
        completed_lessons=doc.get("completed_lessons", []),
        total_correct=doc.get("total_correct", 0),
        total_questions=doc.get("total_questions", 0)
    )


# ============ LESSONS ENDPOINTS ============

@api_router.get("/lessons")
async def get_lessons():
    lessons = await db.lessons.find({}, {"_id": 0}).to_list(1000)
    # Group by category
    categories = {}
    for lesson in lessons:
        cat = lesson["category"]
        if cat not in categories:
            categories[cat] = {
                "name": cat,
                "emoji": lesson["category_emoji"],
                "order": lesson["category_order"],
                "lessons": []
            }
        categories[cat]["lessons"].append({
            "lesson_id": lesson["lesson_id"],
            "title": lesson["title"],
            "description": lesson["description"],
            "xp_reward": lesson["xp_reward"],
            "order": lesson["order"]
        })
    result = sorted(categories.values(), key=lambda x: x["order"])
    for cat in result:
        cat["lessons"].sort(key=lambda x: x["order"])
    return result


@api_router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: str):
    lesson = await db.lessons.find_one({"lesson_id": lesson_id}, {"_id": 0})
    if not lesson:
        raise HTTPException(status_code=404, detail="Lekce nenalezena")
    return lesson


# ============ PROGRESS ENDPOINTS ============

@api_router.post("/progress")
async def record_progress(data: ProgressCreate):
    user = await db.users.find_one({"user_id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    xp_earned = data.correct_count * 2 + (10 if data.correct_count >= 3 else 0)
    completed_lessons = user.get("completed_lessons", [])
    already_done = data.lesson_id in completed_lessons

    if not already_done:
        completed_lessons.append(data.lesson_id)

    new_xp = user.get("xp", 0) + (xp_earned if not already_done else data.correct_count * 2)
    new_level = max(1, (new_xp // 100) + 1)

    # Streak logic
    today = datetime.now(timezone.utc).date()
    last_act = user.get("last_activity")
    streak = user.get("streak", 0)
    if last_act:
        last_date = last_act.date() if hasattr(last_act, 'date') else last_act
        if last_date == today:
            pass  # same day, keep streak
        elif (today - last_date).days == 1:
            streak += 1  # consecutive day
        else:
            streak = 1  # broken streak
    else:
        streak = 1

    # Badges
    badges = list(user.get("badges", []))
    if "prvni_lekce" not in badges:
        badges.append("prvni_lekce")
    if streak >= 7 and "tyden_seria" not in badges:
        badges.append("tyden_seria")
    if streak >= 30 and "mesic_seria" not in badges:
        badges.append("mesic_seria")

    # Category completion badges
    all_lessons = await db.lessons.find({}, {"lesson_id": 1, "category": 1, "_id": 0}).to_list(1000)
    cat_map = {}
    for l in all_lessons:
        cat_map.setdefault(l["category"], []).append(l["lesson_id"])

    badge_map = {
        "Základy": "zaklady_master", "Spoření": "sporeni_master",
        "Dluhy": "dluhy_master", "Investování": "investovani_master",
        "Daně": "dane_master", "Pokročilé": "pokrocile_master"
    }
    for cat, badge_key in badge_map.items():
        if badge_key not in badges:
            cat_lessons = cat_map.get(cat, [])
            if all(l in completed_lessons for l in cat_lessons):
                badges.append(badge_key)

    if "vsechny_lekce" not in badges:
        all_ids = [l["lesson_id"] for l in all_lessons]
        if all(l in completed_lessons for l in all_ids):
            badges.append("vsechny_lekce")

    await db.users.update_one(
        {"user_id": data.user_id},
        {"$set": {
            "xp": new_xp, "level": new_level,
            "streak": streak, "last_activity": datetime.now(timezone.utc),
            "badges": badges, "completed_lessons": completed_lessons,
            "total_correct": user.get("total_correct", 0) + data.correct_count,
            "total_questions": user.get("total_questions", 0) + data.total_questions
        }}
    )

    return {
        "xp_earned": xp_earned if not already_done else data.correct_count * 2,
        "new_xp": new_xp, "new_level": new_level,
        "new_badges": [b for b in badges if b not in user.get("badges", [])],
        "streak": streak
    }


# ============ LEADERBOARD ============

@api_router.get("/leaderboard")
async def get_leaderboard():
    users = await db.users.find({}, {"_id": 0, "device_id": 0}).sort("xp", -1).limit(20).to_list(20)
    return [
        {
            "user_id": u["user_id"],
            "username": u["username"],
            "xp": u.get("xp", 0),
            "level": u.get("level", 1),
            "streak": u.get("streak", 0),
            "badges": u.get("badges", [])
        }
        for u in users
    ]


# ============ CHAT ENDPOINTS ============

@api_router.post("/chat")
async def chat_message(data: ChatMessageCreate):
    user = await db.users.find_one({"user_id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    # Store user message
    await db.chat_messages.insert_one({
        "user_id": data.user_id,
        "role": "user",
        "content": data.message,
        "timestamp": datetime.now(timezone.utc)
    })

    # Get last 8 messages for context
    history = await db.chat_messages.find(
        {"user_id": data.user_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(8).to_list(8)
    history.reverse()

    context = "\n".join([
        f"{'Uživatel' if m['role'] == 'user' else 'Asistent'}: {m['content']}"
        for m in history[:-1]  # exclude the just-added message
    ])

    system_msg = """Jsi přátelský AI finanční poradce pro česky mluvící uživatele. 
Pomáháš lidem zlepšit jejich finanční gramotnost. 
Odpovídáš vždy v češtině, jasně, srozumitelně a přívětivě.
Poskytuj konkrétní, praktické rady o spoření, investování, dluzích, daních a dalších finančních tématech.
Buď pozitivní, motivující a přizpůsob složitost odpovědí otázce.
Pokud nevíš přesnou odpověď, přiznej to a doporuč odborníka.
Odpovídej stručně (max 3-4 odstavce) ale výstižně."""

    full_message = data.message
    if context:
        full_message = f"Kontext předchozí konverzace:\n{context}\n\nNová otázka: {data.message}"

    try:
        llm_key = os.environ.get('EMERGENT_LLM_KEY', '')
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"finance_{data.user_id}",
            system_message=system_msg
        ).with_model("gemini", "gemini-2.5-flash")

        response = await chat.send_message(UserMessage(text=full_message))
        ai_response = response
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        ai_response = "Omlouvám se, momentálně nemohu odpovědět. Zkuste to prosím za chvíli."

    # Store AI response
    await db.chat_messages.insert_one({
        "user_id": data.user_id,
        "role": "assistant",
        "content": ai_response,
        "timestamp": datetime.now(timezone.utc)
    })

    return {"response": ai_response}


@api_router.get("/chat/{user_id}")
async def get_chat_history(user_id: str):
    messages = await db.chat_messages.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("timestamp", 1).limit(50).to_list(50)
    return messages


@api_router.get("/badges")
async def get_badges():
    return BADGES_CONFIG


# ============ FINANCIAL PLAN ENDPOINTS ============

async def _generate_plan_text(data: FinancialPlanCreate, user: dict) -> str:
    risk_map = {"low": "konzervativní (preferuji bezpečnost)", "medium": "vyvážená (kombinace bezpečnosti a výnosu)", "high": "agresivní (maximální výnos)"}
    goals_str = ", ".join(data.goals) if data.goals else "Obecné zlepšení financí"
    balance = data.monthly_income - data.monthly_expenses
    rate = (balance / data.monthly_income * 100) if data.monthly_income > 0 else 0
    completed = len(user.get('completed_lessons', []))

    prompt = f"""Vytvoř podrobný, personalizovaný finanční plán pro českého klienta s těmito parametry:

FINANČNÍ PROFIL:
- Věk: {data.age} let
- Čistý měsíční příjem: {data.monthly_income:,.0f} Kč
- Měsíční výdaje: {data.monthly_expenses:,.0f} Kč
- Měsíční přebytek/deficit: {balance:,.0f} Kč ({rate:.1f} % z příjmu)
- Aktuální úspory: {data.savings:,.0f} Kč
- Celkové dluhy: {data.debts:,.0f} Kč
- Finanční cíle: {goals_str}
- Tolerance rizika: {risk_map.get(data.risk_tolerance, 'vyvážená')}
- Dokončené finanční lekce: {completed}/18

Vytvoř strukturovaný plán s těmito sekcemi. Buď KONKRÉTNÍ s přesnými částkami v Kč:

## 📊 HODNOCENÍ SITUACE
Krátké zhodnocení finanční situace (2-3 věty).

## 🚨 TOP 3 PRIORITNÍ KROKY
Tři nejdůležitější akce, které má klient udělat IHNED, s konkrétními částkami.

## 💰 DOPORUČENÝ MĚSÍČNÍ ROZPOČET
Konkrétní rozpis: kolik na potřeby, přání, spoření, investice (s Kč).

## 🐷 STRATEGIE SPOŘENÍ
Doporučení pro tvorbu nouzového fondu a spoření s časovým plánem.

## 📈 INVESTIČNÍ STRATEGIE
Konkrétní doporučení dle věku a tolerance rizika (ETF, akcie, dluhopisy, DIP, penzijní připojištění).

## 🗓 PLÁN NA 12 MĚSÍCŮ
Měsíční milníky – co dělat v 1., 3., 6. a 12. měsíci."""

    try:
        llm_key = os.environ.get('EMERGENT_LLM_KEY', '')
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"plan_{data.user_id}_{uuid.uuid4().hex[:8]}",
            system_message="Jsi zkušený český finanční poradce. Vytváříš konkrétní, akční finanční plány s přesnými čísly relevantními pro Českou republiku (DIP, penzijní připojištění, stavební spoření, ČNB sazby). Odpovídáš vždy česky."
        ).with_model("gemini", "gemini-2.5-flash")
        response = await chat.send_message(UserMessage(text=prompt))
        return response
    except Exception as e:
        logger.error(f"Financial plan generation error: {e}")
        raise HTTPException(status_code=500, detail="Chyba při generování plánu")


@api_router.post("/financial-plan")
async def generate_financial_plan(data: FinancialPlanCreate):
    user = await db.users.find_one({"user_id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    plan_text = await _generate_plan_text(data, user)

    await db.financial_plans.update_one(
        {"user_id": data.user_id},
        {"$set": {
            "user_id": data.user_id,
            "plan": plan_text,
            "profile": {
                "age": data.age,
                "monthly_income": data.monthly_income,
                "monthly_expenses": data.monthly_expenses,
                "savings": data.savings,
                "debts": data.debts,
                "goals": data.goals,
                "risk_tolerance": data.risk_tolerance,
            },
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    return {"plan": plan_text, "profile": data.dict()}


@api_router.get("/financial-plan/{user_id}")
async def get_financial_plan(user_id: str):
    plan = await db.financial_plans.find_one({"user_id": user_id}, {"_id": 0})
    if not plan:
        return None
    return plan


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
