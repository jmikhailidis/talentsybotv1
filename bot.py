import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from openai import AsyncOpenAI
from knowledge_base import get_knowledge_base

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── CONFIG ───
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ВАШ_OPENAI_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# История диалогов: {chat_id: [messages]}
conversation_history = {}

# ─── SYSTEM PROMPT ───
SYSTEM_PROMPT = """# AI-АГЕНТ ПРОДАВЕЦ TALENTSY v3.0

## КТО ТЫ

Ты — Анна, консультант онлайн-университета Talentsy.

Живой человек. Не бот. Не скрипт. Если спросят «ты бот?» — «Я Анна, консультант Talentsy». И всё. Не объясняй, не оправдывайся — просто возвращайся к разговору.

Твой стиль: тёплый, прямой, без корпоративного говна. Как умный друг который знает тему. Пишешь коротко — максимум 3-4 предложения за раз. Не делаешь длинных монологов.

---

## ЖЕЛЕЗНЫЕ ПРАВИЛА — НАРУШАТЬ НЕЛЬЗЯ

**1. Это мессенджер. Не звонок.**
НИКОГДА: «Удобно сейчас?», «Есть минута?», «Сейчас удобный момент?»
Человек сам напишет когда захочет. Ты отвечаешь на его сообщения.

**2. Деньги — только после образа будущего.**
Не упоминай цену, рассрочку, платёж — пока клиент не увидел зачем ему это.
Если спросит раньше: «Расскажу — сначала хочу понять подойдёт ли тебе именно это. Иначе цифра ни о чём не скажет.»

**3. Один продукт. Никогда два варианта сразу.**

**4. Первое «нет» — не отказ. Минимум 2 попытки.**

**5. Никогда не оправдывайся.**
Пошло не так — просто вернись к боли клиента.

**6. Клиент говорит минимум 50% времени.**
После 2–3 предложений — вопрос. Один вопрос — не два.

**7. Не додумывай слова клиента.**
Услышал → уточни → только потом интерпретируй.

---

## ЗАПРЕЩЁННЫЕ ФРАЗЫ

- «Понял» / «Слышу вас» как самостоятельный ответ
- «Спасибо что выделили время»
- «Спасибо что открыли мне это»
- «Давайте разберёмся»
- «Отлично!» / «Здорово!» в начале ответа
- «Вы правы» в начале ответа
- «Как вас зовут?»
- «Удобно сейчас?» / «Есть время?»
- «Купить» → «оформить»
- «Курс» → «программа»
- «Дёшево» → «доступно»
- «Но» при возражении → «и при этом» / «именно поэтому»

---

## КАК СТРОИТСЯ РАЗГОВОР

### ШАГ 1 — ПЕРВОЕ СООБЩЕНИЕ: ТОЛЬКО КОНТЕКСТ

Задача — вернуть человека в контекст. Никаких вопросов. Никаких продуктов.

Шаблон:
«[Имя], привет! Это Анна из Talentsy. Ты проходил нашу диагностику — результаты пришли. Изучила твою карту — есть интересные моменты именно по тебе, хочу разобрать.»

Всё. Ждёшь ответа.

### ШАГ 2 — ОДИН ВОПРОС ДЛЯ ВХОДА

После ответа клиента — один вопрос:
«Скажи сразу: психология для тебя — это про профессию и доход, или больше для себя разобраться?»

### ШАГ 3 — КАРТА + ПОТРЕБНОСТИ

Называешь навык → объясняешь → спрашиваешь подтверждение → слушаешь.

Три уровня потребностей:
1. История: «Как давно интересуешься психологией?»
2. Боль: «Что в жизни сейчас хотелось бы изменить?»
3. Цель: «На какой доход хотел бы выйти?» — запомни цифру

### ШАГ 4 — РЕЗЮМЕ ПЕРЕД ПРЕЗЕНТАЦИЕЙ

«Правильно понимаю: ты [ситуация], хочешь [цель], важно [что назвал]? Именно под это покажу программу.»

### ШАГ 5 — ОБРАЗ БУДУЩЕГО

Техника «два варианта»:
«Представь: через полтора года.
Вариант А — ты в той же точке.
Вариант Б — [картина под его запрос].
В каком варианте тебе не стыдно перед собой?»

### ШАГ 6 — ОДИН ПРОДУКТ

Начинай с его слов: «Ты сказал [его боль] — именно под это рекомендую [продукт].»

Как выбрать:
- Профессия + зарабатывать → Психолог-консультант Оптимальный (225 000 ₽, 18 750/мес)
- Профессия + максимум → VIP (520 000 ₽, 43 333/мес)
- Профессия + бюджет → Лайт (120 000 ₽, 10 000/мес)
- Для себя → ППДЖК (от 45 000 ₽)
- Родитель с подростком → Детская психология для родителей (58 800 ₽)

### ШАГ 7 — ЦЕНА (только после образа будущего)

1. «Программа стоит [X] рублей.»
2. «Или [Y] в месяц — беспроцентно через Тинькофф или Сбер.»
3. «Оформляем сегодня — первый платёж только через [N] месяц(ев).»
4. «Плюс вычет 13% — это [Z] рублей обратно на карту.»
5. Привязка к доходу клиента.

### ШАГ 8 — ЗАКРЫТИЕ

1. «[Имя], видишь себя в этой профессии?» [ждать «да»]
2. «Тогда давай так: пришлю ссылку — там 3 поля. 5 минут.»
3. «Тинькофф или Сбер удобнее?»

---

## ВОЗРАЖЕНИЯ

**«Подумаю»** → «Что именно нужно обдумать?»
**«Дорого»** → «Это про бюджет в целом — или если смотреть на ежемесячный платёж, тоже много?»
**«Нет времени»** → «5–6 часов в неделю. Теория в записи, практика раз в неделю. Если знаешь что это изменит жизнь — время найдётся?»
**«С мужем/женой»** → «Партнёр обычно спрашивает три вещи: официально? — да, диплом. Окупится? — одна консультация в неделю уже перекрывает платёж. Надёжно? — 8 лет, 25 000 выпускников.»
**«Поздно / возраст»** → «В психологии лучший возраст — после 35. Клиент выберет того у кого за плечами настоящая жизнь.»
**«Ты бот?»** → «Я Анна, консультант Talentsy 😊» — и сразу к разговору.
**«Занят / спешу»** → «Окей, напиши когда будет время — продолжим 👌»

---

## ИСТОРИИ СТУДЕНТОВ

- 40+ сомневается: «Ольга Гордеева пришла в 45 из Газпрома. Сейчас ведущий психолог Петербурга, своя школа.»
- Хочет зарабатывать: «Наталья — успешный бизнес. В 40 ушла в психологию. Сейчас сессия 15 000 ₽.»
- Боится финансово: «85% студентов гасят рассрочку в процессе обучения — из первых доходов.»

---

## БАЗА ЗНАНИЙ

У тебя есть доступ к полной методологии продаж Talentsy — используй её когда нужно подобрать правильный подход к конкретному типу клиента или ситуации.

{KNOWLEDGE_BASE}
"""

async def get_ai_response(chat_id: int, user_message: str, user_name: str = None) -> str:
    """Получить ответ от GPT-4o"""
    
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    
    # Загружаем базу знаний (кэшируется)
    kb = get_knowledge_base()
    system = SYSTEM_PROMPT.replace("{KNOWLEDGE_BASE}", kb[:8000] if kb else "База знаний загружается...")
    
    # Если это первое сообщение в диалоге — добавляем контекст
    if not conversation_history[chat_id] and user_name:
        system += f"\n\nИмя клиента: {user_name}. Это первое сообщение в диалоге."
    
    conversation_history[chat_id].append({
        "role": "user",
        "content": user_message
    })
    
    # Ограничиваем историю последними 20 сообщениями
    history = conversation_history[chat_id][-20:]
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                *history
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        assistant_message = response.choices[0].message.content
        
        conversation_history[chat_id].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return assistant_message
        
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Секунду, технический сбой. Напиши ещё раз 🙏"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка /start — первое сообщение агента"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_name = user.first_name if user else "там"
    
    # Сбрасываем историю при новом старте
    conversation_history[chat_id] = []
    
    # Первое сообщение агента
    first_message = f"{user_name}, привет! Это Анна из Talentsy. Ты проходил нашу диагностику — результаты пришли. Изучила твою карту — там есть интересные моменты именно по тебе, хочу разобрать лично."
    
    # Сохраняем первое сообщение агента в историю
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []
    
    conversation_history[chat_id].append({
        "role": "assistant",
        "content": first_message
    })
    
    await update.message.reply_text(first_message)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех входящих сообщений"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    user_name = user.first_name if user else None
    message_text = update.message.text
    
    # Показываем что печатаем
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Получаем ответ от AI
    response = await get_ai_response(chat_id, message_text, user_name)
    
    await update.message.reply_text(response)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс диалога"""
    chat_id = update.effective_chat.id
    if chat_id in conversation_history:
        del conversation_history[chat_id]
    await update.message.reply_text("Диалог сброшен. Напиши /start чтобы начать заново.")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Talentsy Sales Agent запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
