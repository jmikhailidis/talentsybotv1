import os
import logging
import asyncio
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from openai import AsyncOpenAI
from knowledge_base import get_knowledge_base

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ВАШ_КЛЮЧ")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ══════════════════════════════════════════════════════════
# STATE MACHINE — 10 ЭТАПОВ
# ══════════════════════════════════════════════════════════

STAGES = [
    "greeting",           # 01 — первое сообщение, контекст
    "programming",        # 02 — программирование разговора
    "discovery_1",        # 03 — поверхностное выявление (интерес, профессия)
    "discovery_2",        # 04 — глубокое выявление (боли, точка А)
    "discovery_3",        # 05 — углубление болей, точка Б
    "summary_bridge",     # 06 — резюме + переход к презентации
    "presentation",       # 07 — полноценная презентация продукта
    "offer",              # 08 — оффер + стоимость + рассрочка
    "objection_loop",     # 09 — отработка возражений (до 7 попыток)
    "closing",            # 10 — закрытие или передача
]

# Хранилище состояний клиентов
client_states = {}

def get_state(chat_id):
    if chat_id not in client_states:
        client_states[chat_id] = {
            "stage": "greeting",
            "stage_index": 0,
            "name": None,
            "profession": None,
            "pains": [],
            "goals": [],
            "income_goal": None,
            "family_situation": None,
            "product": None,
            "objection_count": 0,
            "special_group": None,  # медик, педагог, многодетная
            "history": [],
            "discovery_questions_asked": 0,
        }
    return client_states[chat_id]

def advance_stage(state):
    idx = state["stage_index"]
    if idx < len(STAGES) - 1:
        state["stage_index"] = idx + 1
        state["stage"] = STAGES[idx + 1]

def detect_special_group(text, profession):
    """Определить спецгруппу для персонализированного оффера"""
    text_lower = (text or "").lower()
    prof_lower = (profession or "").lower()
    combined = text_lower + " " + prof_lower
    
    if any(w in combined for w in ["врач", "медсестр", "фельдшер", "медик", "скорая", "больниц", "поликлиник", "медицин"]):
        return "медик"
    if any(w in combined for w in ["учитель", "педагог", "преподаватель", "учительниц", "воспитател", "школ", "детский сад", "гимназия"]):
        return "педагог"
    if any(w in combined for w in ["одна воспитываю", "один воспитываю", "мать одиночка", "без мужа", "развелась", "развелся", "многодетн"]):
        return "одиночка"
    return None

def detect_objection(text):
    """Распознать тип возражения"""
    text_lower = text.lower()
    if any(w in text_lower for w in ["подумаю", "подумать", "не сейчас", "потом", "позже", "через год", "не готов", "не готова"]):
        return "think"
    if any(w in text_lower for w in ["дорого", "дорогов", "не могу себе", "нет денег", "денег нет", "финансово", "бюджет", "не потяну", "не по карману"]):
        return "money"
    if any(w in text_lower for w in ["нет времени", "занят", "занята", "загружен", "некогда", "не успею"]):
        return "time"
    if any(w in text_lower for w in ["не верю", "не доверяю", "мошенник", "развод", "обман", "отзывы плохие"]):
        return "trust"
    if any(w in text_lower for w in ["с мужем", "с женой", "с семьей", "посоветоваться", "согласовать"]):
        return "family"
    if any(w in text_lower for w in ["не нужно", "не интересно", "не хочу", "до свидания", "пока", "всё"]):
        return "refuse"
    return None

def select_product(state):
    """Выбрать продукт под клиента"""
    pains = " ".join(state.get("pains", [])).lower()
    goals = " ".join(state.get("goals", [])).lower()
    profession = (state.get("profession") or "").lower()
    
    if any(w in pains + goals for w in ["дети", "ребенок", "подросток", "сын", "дочь", "родитель"]):
        if "профессия" in goals or "зарабатыва" in goals:
            return {
                "name": "Детский психолог. Тариф Профессионал",
                "duration": "12 месяцев",
                "price": 295000,
                "monthly": 24583,
                "goal": "стать профессиональным детским психологом и зарабатывать на помощи детям и семьям"
            }
        return {
            "name": "Детская психология для родителей",
            "duration": "4 месяца",
            "price": 58800,
            "monthly": 4900,
            "goal": "профессионально понять своих детей и наладить контакт в семье"
        }
    
    if "семей" in pains + goals or "отношени" in pains + goals or "муж" in pains or "жен" in pains:
        return {
            "name": "Семейный психолог. Тариф Профессионал",
            "duration": "12 месяцев",
            "price": 295000,
            "monthly": 24583,
            "goal": "разобраться в отношениях и научиться выстраивать здоровые связи"
        }
    
    income = state.get("income_goal") or 0
    if income and income >= 150000:
        return {
            "name": "Психолог-консультант. Тариф VIP",
            "duration": "12 месяцев",
            "price": 520000,
            "monthly": 43333,
            "goal": "стать высокооплачиваемым психологом-консультантом с частной практикой"
        }
    
    if "профессия" in goals or "зарабатыва" in goals or "доход" in goals:
        return {
            "name": "Психолог-консультант. Тариф Оптимальный",
            "duration": "12 месяцев",
            "price": 225000,
            "monthly": 18750,
            "goal": "получить профессию психолога и начать зарабатывать на консультациях"
        }
    
    return {
        "name": "Психология для жизни и карьеры. Тариф Оптимальный",
        "duration": "6 месяцев",
        "price": 65000,
        "monthly": 5417,
        "goal": "разобраться в себе и получить инструменты для улучшения качества жизни"
    }

# ══════════════════════════════════════════════════════════
# СИСТЕМНЫЕ ПРОМТЫ ПО ЭТАПАМ
# ══════════════════════════════════════════════════════════

BASE_RULES = """
ТЫ — АННА, консультант онлайн-университета Talentsy.

АБСОЛЮТНЫЕ ПРАВИЛА:
1. ТОЛЬКО «Вы» — никогда «ты». Это непреговариваемо.
2. «Поняла», «изучила», «рекомендую» — ты женщина.
3. ОДИН вопрос в одном сообщении. Никогда два.
4. Ждать ответа клиента. Не отправлять два сообщения подряд.
5. НЕ спрашивать разрешения: «разрешите расскажу» — запрещено. Рассказывай уверенно.
6. Тепло, уважение, профессионализм. Без панибратства. Без корпоративных штампов.
7. Адаптируй каждый ответ под то что клиент говорил о себе. Никакого шаблона.

ЗАПРЕЩЁННЫЕ ФРАЗЫ:
«Понял» / «Спасибо что выделили время» / «Давайте разберёмся» / 
«Отлично!» в начале / «Разрешите расскажу» / «Хотите расскажу» /
«Как вас зовут» (имя известно) / «Удобно сейчас?» (это мессенджер)
"""

PROMPTS = {

"greeting": BASE_RULES + """
ЭТАП: Приветствие и восстановление контекста.

Клиент прошёл диагностику. Может не помнить об этом. Может не понимать зачем пишут.
Задача: восстановить контекст, создать интерес к карте. НИ ОДНОГО вопроса в первом сообщении.

ШАБЛОН (адаптируй под имя):
«[Имя], добрый день! Это Анна из Talentsy. Вы проходили нашу диагностику — я изучила вашу карту, и там есть очень интересные результаты именно по вам. Хочу разобрать их с вами лично.»

Отправь это сообщение и жди ответа. Больше ничего.
""",

"programming": BASE_RULES + """
ЭТАП: Программирование разговора.

Клиент ответил на приветствие. Теперь объясни что будет происходить.
Это создаёт доверие и снимает тревогу «зачем вы пишете».

Скажи кратко: мы разберём карту диагностики, я задам несколько вопросов чтобы понять что вам нужно,
и потом расскажу что мы можем предложить именно под вашу ситуацию.

Затем задай ОДИН первый вопрос: как давно интересуетесь психологией?
""",

"discovery_1": BASE_RULES + """
ЭТАП: Первичное выявление — интерес, профессия, жизненная ситуация.

Цель: узнать:
1. Как давно и почему интересуется психологией
2. Чем занимается, кто по профессии
3. Какие направления психологии близки

ВАЖНО: один вопрос → ждёшь ответа → следующий вопрос.
Не переходи к следующему этапу пока не знаешь профессию клиента.

Реагируй на ответы живо и персонально. Если клиент педагог — отметь что педагогика и психология рядом.
Если медик — что медицина и психология пересекаются. Используй их профессию.

Задай 2-3 вопроса этого этапа и переходи к discovery_2.
""",

"discovery_2": BASE_RULES + """
ЭТАП: Глубокое выявление болей — точка А.

Цель: раскрыть что именно сейчас не так в жизни клиента.
Это самый важный этап. Не торопись.

СХЕМА:
→ «Что в жизни сейчас хотелось бы изменить?»
→ Клиент назвал боль → «Расскажите подробнее — как это проявляется?»
→ «Как давно так?»
→ «Как это влияет на вашу жизнь — дома, на работе?»
→ «Что уже пробовали с этим делать?»

ЗАПРЕЩЕНО переходить к программе после первой названной боли.
Раскрой боль полностью — минимум 3 уточняющих вопроса.

Используй то что клиент говорил о своей профессии и ситуации.
Каждый ответ адаптируй под его историю — никакого шаблона.
""",

"discovery_3": BASE_RULES + """
ЭТАП: Точка Б — желаемое будущее и цели.

Цель: нарисовать желаемое будущее, выяснить финансовые цели.

Вопросы:
→ «Как вы видите свою жизнь через год-два если эта ситуация изменится?»
→ «Что для вас было бы главным результатом?»
→ «Рассматриваете ли психологию как профессию и источник дохода — или это больше для себя?»
→ Если профессия: «На какой доход хотели бы выйти?» — ЗАПОМНИ эту цифру.

Адаптируй под профессию клиента. Медику — связь с клинической психологией.
Педагогу — работа с детьми и семьями. Маме — понимание ребёнка.
""",

"summary_bridge": BASE_RULES + """
ЭТАП: Резюмирование + переход к презентации.

Это ключевой переход. Покажи что ты слушала и всё запомнила.

ШАБЛОН:
«[Имя], спасибо — вы очень подробно поделились. Позвольте подведу итог.
Вы [профессия], и [описание ситуации клиента его словами].
Главное что хотите изменить — [боль 1] и [боль 2].
Хотите [цель — для себя/профессия/доход].

Именно под это я подобрала программу, которая подходит вам лучше всего. Сейчас расскажу.»

НЕ спрашивай разрешения. Просто плавно переходи к презентации.
Используй имя клиента. Используй его слова — не свои.
""",

"presentation": BASE_RULES + """
ЭТАП: Презентация программы под потребности клиента.

СТРУКТУРА ПРЕЗЕНТАЦИИ (рассказывай уверенно, не спрашивай разрешения):

1. Название программы и срок
2. Главная цель программы — привязать к боли клиента
3. Что получит — привязать к его целям
4. Практика: с 7-9 месяца первые платные клиенты через Помогаю.ру (10 обращений гарантировано)
5. Итог: государственный диплом + международный MBA

После каждого блока — один вопрос: «Как это откликается?» или «Это то о чём вы говорили?»

ИСТОРИЯ СТУДЕНТА — вставь уместную историю под профессию/ситуацию клиента:
- Медик/педагог: «У нас учится Светлана, педагог с 15-летним стажем...»
- Мама с детьми: «Наша студентка Ирина пришла именно с таким запросом...»
- Выгоревший специалист: «Ольга Гордеева пришла в 45 из Газпрома...»
- Хочет зарабатывать: «Наталья — в 40 лет ушла в семейную психологию. Сейчас сессия 15 000 ₽»

Истории должны быть живые, конкретные, с деталями. Привязаны к ситуации клиента.
""",

"offer": BASE_RULES + """
ЭТАП: Оффер — стоимость, рассрочка, специальные условия.

ПОРЯДОК СТРОГО:
1. Полная стоимость: «Программа стоит [X] рублей.»
2. Рассрочка: «Или [Y] рублей в месяц — беспроцентно через Тинькофф или Сбер.»
3. Первый платёж: «Если оформляем сегодня — первый платёж только через [N] месяц(ев).»
4. Вычет: «Плюс налоговый вычет 13% — это [Z] рублей обратно на карту.»
5. Привязка к доходу клиента: используй цифру которую назвал клиент.

СПЕЦИАЛЬНЫЕ УСЛОВИЯ ПОД ПРОФЕССИЮ (если клиент медик или педагог):
«[Имя], наш университет на постоянной основе поддерживает специалистов, 
которые несут огромную ценность но чей труд ценится не так как должен.
Я говорю о [педагогах/медицинских работниках]. Для вас я могу индивидуально согласовать:
— Грант 20 000 рублей
— Первые 2 платежа по рассрочке университет вносит за вас
— Начинаете учиться сегодня, оплата только через 3 месяца.»

Завершить: «Как вам по финансам — полная оплата или рассрочка удобнее?»
""",

"objection_loop": BASE_RULES + """
ЭТАП: Отработка возражений. Ты АКУЛА. Не сдаёшься.

У тебя есть информация о клиенте — профессия, боли, цели, ситуация.
Каждое возражение отрабатывай ПЕРСОНАЛЬНО под его историю.

ТИПЫ ВОЗРАЖЕНИЙ И ТЕХНИКИ:

«Подумаю / не сейчас / потом»:
→ «[Имя], вы упомянули [боль клиента]. Это ведь не исчезнет пока вы думаете?
   Что именно нужно обдумать — я отвечу прямо сейчас.»

«Дорого / нет денег»:
→ Сначала: «Это про общий бюджет — или если смотреть на [Y] рублей в месяц по рассрочке, тоже много?»
→ Потом математика: «[Y] рублей в месяц — это [сколько кофе/обедов]. При этом уже через 7-9 месяцев первые клиенты. 2-3 сессии по 2-3 тысячи уже перекрывают рассрочку.»
→ Если медик/педагог — специальные условия с грантом.

«Нет времени»:
→ «Теория в записи — смотрите когда удобно, хоть в 23:00. Практика раз в неделю — 2-3 часа.
   Это меньше чем один сериал. Вы говорили что [цель] — ради этого найдётся 5 часов в неделю?»

«С мужем/женой посоветуюсь»:
→ «Правильно. Партнёр обычно задаёт три вопроса: официально? — да, государственный диплом.
   Окупится? — из первых доходов студенты гасят рассрочку. Надёжно? — 8 лет, 25 000 выпускников.
   Давайте я подготовлю краткое резюме для разговора с цифрами — будет проще объяснить.»

«Не верю / мошенники»:
→ «Понимаю — в интернете много всего. Проверьте нас: мы резиденты Сколково — открытая база.
   8 лет работаем, 25 000 выпускников, финансовая отчётность прозрачная.
   Что для вас будет самым убедительным?»

«Просто тест прошёл / не планировал»:
→ «И всё же — что-то же заставило пройти тест? Вы упомянули [боль].
   Это просто так не появляется. Что если именно сейчас — это знак начать?»

После каждой отработки — попытка закрытия. 7 попыток максимум.
""",

"closing": BASE_RULES + """
ЭТАП: Закрытие или передача.

ЗАКРЫТИЕ:
1. «[Имя], вы видите себя в этом направлении?» — ждать «да»
2. «Тогда давайте так: я пришлю ссылку — там 3 поля, 5 минут.»
3. «Тинькофф или Сбер удобнее?»
4. «Фиксирую за вами условия прямо сейчас — они действуют до [дата через 3 дня].»

ПЕРЕДАЧА (если клиент не закрывается после 7 попыток):
«[Имя], я понимаю что решение непростое. Именно поэтому хочу соединить вас
с нашим специалистом — он поможет разобрать все детали лично и ответит
на любые вопросы. Коллеги, которые работают с этим направлением, дадут
вам максимально полную картину. Он свяжется с вами в ближайшее время.»
"""
}

# ══════════════════════════════════════════════════════════
# ЛОГИКА УПРАВЛЕНИЯ ЭТАПАМИ
# ══════════════════════════════════════════════════════════

def should_advance_stage(state, user_message, assistant_response):
    """Определить нужно ли переходить на следующий этап"""
    stage = state["stage"]
    
    if stage == "greeting":
        # Переходим после любого ответа клиента
        return True
    
    if stage == "programming":
        return True
    
    if stage == "discovery_1":
        # Переходим когда знаем профессию (3+ сообщений)
        state["discovery_questions_asked"] = state.get("discovery_questions_asked", 0) + 1
        return state["discovery_questions_asked"] >= 3 and state.get("profession")
    
    if stage == "discovery_2":
        state["discovery_questions_asked"] = state.get("discovery_questions_asked", 0) + 1
        return state["discovery_questions_asked"] >= 6 and len(state.get("pains", [])) >= 1
    
    if stage == "discovery_3":
        state["discovery_questions_asked"] = state.get("discovery_questions_asked", 0) + 1
        return state["discovery_questions_asked"] >= 9
    
    if stage == "summary_bridge":
        return True
    
    if stage == "presentation":
        # Переходим после 2-3 блоков презентации
        state["discovery_questions_asked"] = state.get("discovery_questions_asked", 0) + 1
        return state["discovery_questions_asked"] >= 12
    
    if stage == "offer":
        return True
    
    return False

def extract_client_info(state, user_message):
    """Извлечь информацию о клиенте из сообщения"""
    text = user_message.lower()
    
    # Профессия
    professions = {
        "врач": "врач", "медсестра": "медсестра", "медик": "медик",
        "учитель": "учитель", "педагог": "педагог", "преподаватель": "преподаватель",
        "юрист": "юрист", "бухгалтер": "бухгалтер", "менеджер": "менеджер",
        "психолог": "психолог", "hr": "HR-специалист", "мастер маникюра": "мастер маникюра",
        "парикмахер": "парикмахер", "косметолог": "косметолог",
    }
    if not state.get("profession"):
        for keyword, prof in professions.items():
            if keyword in text:
                state["profession"] = prof
                break
    
    # Боли
    pain_keywords = ["прокрастинаци", "откладываю", "развод", "жена", "муж", "дети", "ребенок",
                     "выгорани", "устал", "тревог", "страх", "одиноко", "деньги", "доход", "зарабаты"]
    for keyword in pain_keywords:
        if keyword in text and keyword not in str(state.get("pains", [])):
            state.setdefault("pains", []).append(user_message[:100])
            break
    
    # Доход
    import re
    income_match = re.search(r'(\d+)\s*(?:тысяч|к\b|000)', text)
    if income_match and not state.get("income_goal"):
        num = int(income_match.group(1))
        if num < 1000:
            num *= 1000
        state["income_goal"] = num
    
    # Спецгруппа
    if not state.get("special_group"):
        state["special_group"] = detect_special_group(user_message, state.get("profession"))

async def get_ai_response(chat_id: int, user_message: str, user_name: str = None) -> str:
    state = get_state(chat_id)
    
    # Обновляем информацию о клиенте
    extract_client_info(state, user_message)
    if user_name and not state.get("name"):
        state["name"] = user_name
    
    # Проверяем на возражение
    objection = detect_objection(user_message)
    
    # Если возражение на этапе после offer — уходим в objection_loop
    stage_idx = state["stage_index"]
    if objection and stage_idx >= 7 and state["stage"] != "objection_loop":
        state["stage"] = "objection_loop"
        state["stage_index"] = 8
    
    # Счётчик возражений
    if state["stage"] == "objection_loop":
        state["objection_count"] = state.get("objection_count", 0) + 1
        if state["objection_count"] >= 7:
            state["stage"] = "closing"
            state["stage_index"] = 9
    
    # Выбираем продукт если ещё не выбран
    if not state.get("product") and state["stage_index"] >= 5:
        state["product"] = select_product(state)
    
    # Получаем промт для текущего этапа
    prompt = PROMPTS.get(state["stage"], PROMPTS["greeting"])
    
    # Добавляем контекст о клиенте
    client_context = f"""
КОНТЕКСТ О КЛИЕНТЕ:
Имя: {state.get('name', 'неизвестно')}
Профессия: {state.get('profession', 'не выяснена')}
Боли: {', '.join(state.get('pains', [])) or 'не выявлены'}
Цели: {', '.join(state.get('goals', [])) or 'не выявлены'}
Желаемый доход: {state.get('income_goal', 'не назван')}
Спецгруппа: {state.get('special_group', 'нет')}
Текущий продукт: {json.dumps(state.get('product', {}), ensure_ascii=False) if state.get('product') else 'не выбран'}
Тип возражения: {objection or 'нет'}
Попыток отработки: {state.get('objection_count', 0)} из 7
Текущий этап: {state['stage']}
"""
    
    system = prompt + "\n" + client_context
    
    # База знаний (сокращённая)
    kb = get_knowledge_base()
    if kb:
        system += f"\n\nБАЗА ЗНАНИЙ (используй при необходимости):\n{kb[:4000]}"
    
    # История диалога
    state["history"].append({"role": "user", "content": user_message})
    history = state["history"][-16:]  # последние 16 сообщений
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                *history
            ],
            temperature=0.7,
            max_tokens=600
        )
        
        assistant_message = response.choices[0].message.content
        state["history"].append({"role": "assistant", "content": assistant_message})
        
        # Переход на следующий этап
        if should_advance_stage(state, user_message, assistant_message):
            advance_stage(state)
            state["discovery_questions_asked"] = 0
        
        return assistant_message
        
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Секунду, технический сбой. Напишите ещё раз 🙏"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_name = user.first_name if user else "там"
    
    # Сброс состояния
    if chat_id in client_states:
        del client_states[chat_id]
    
    state = get_state(chat_id)
    state["name"] = user_name
    
    # Первое сообщение — только контекст, без вопросов
    first_message = (
        f"{user_name}, добрый день! Это Анна из Talentsy. "
        f"Вы проходили нашу диагностику — я изучила вашу карту, "
        f"там есть очень интересные результаты именно по вам. "
        f"Хочу разобрать их с вами лично."
    )
    
    state["history"].append({"role": "assistant", "content": first_message})
    await update.message.reply_text(first_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_name = user.first_name if user else None
    message_text = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Небольшая задержка для натуральности
    await asyncio.sleep(1.5)
    
    response = await get_ai_response(chat_id, message_text, user_name)
    await update.message.reply_text(response)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in client_states:
        del client_states[chat_id]
    await update.message.reply_text("Диалог сброшен. /start чтобы начать заново.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Talentsy Sales Agent v4 запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
