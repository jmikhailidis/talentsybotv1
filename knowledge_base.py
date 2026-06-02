import os
import logging
import re
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Google Docs IDs из ссылок
GOOGLE_DOCS_IDS = [
    "1pOQ7D7_CxEi7s4AoT-vS5jtLqrfR6C8jGJ7XUTVNPtk",  # Структура звонков
    "1QShKoPQt3qwmt7_h-vpXNZWLM7eSiezehXW3esWR4e8",  # Разбор диагностической карты
    "1oisu9EUqfuml09-j1lxhTaUIu23wedgjM64d09UTg34",   # Выявление потребностей
    "1HtIT2MQCSeypzrAWWvFoBdeanungUqXNhopHshCRqS0",   # Презентация по потребностям
    "1auelA4qK_6JqCeJjHp0eYilwknvSgm8ZRkincf-T_sw",   # Работа с возражениями
    "1P_FeMrpzYY-ZnlgFWyxk7p9UrHaaYcLoIFKBVA7E2Hc",  # Портреты клиентов
    "1iwALLQbcCuFWqHZoDNyrfthqef_xiX9DMDF8jifP-EM",   # Реальные истории
]

DOC_NAMES = [
    "Структура и правила звонков",
    "Разбор диагностической карты",
    "Выявление потребностей",
    "Презентация по потребностям",
    "Работа с возражениями",
    "Работа с портретами и профессиями",
    "Реальные истории студентов",
]

# Прайс-лист (Google Sheets CSV)
PRICE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vREi3Q_LqY8yfYVSXFtojgH7IFiorNSGL_zm79KlvnicXmcBYNZhUF8HGGLSRm5hw5pHuAzuG8NltHO/pub?gid=935807166&single=true&output=csv"

# Кэш базы знаний
_knowledge_cache = None


def fetch_google_doc(doc_id: str) -> str:
    """Скачать Google Doc как plain text через публичный экспорт"""
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            # Убираем лишние пустые строки
            content = re.sub(r'\n{3,}', '\n\n', content)
            return content.strip()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning(f"Doc {doc_id}: нет доступа (403). Открой доступ по ссылке в Google Docs.")
        else:
            logger.error(f"Doc {doc_id}: HTTP ошибка {e.code}")
        return ""
    except Exception as e:
        logger.error(f"Doc {doc_id}: ошибка загрузки: {e}")
        return ""


def fetch_price_sheet() -> str:
    """Скачать прайс-лист из Google Sheets"""
    try:
        req = urllib.request.Request(PRICE_SHEET_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            lines = content.strip().split(chr(10))
            result = []
            for line in lines:
                if line.strip() and line.strip() != ',' * line.count(','):
                    result.append(line)
            return chr(10).join(result)
    except Exception as e:
        logger.error(f"Прайс: ошибка загрузки: {e}")
        return ""


def load_knowledge_base() -> str:
    """Загрузить все документы и собрать в единую базу знаний"""
    global _knowledge_cache
    
    if _knowledge_cache:
        return _knowledge_cache
    
    logger.info("Загружаю базу знаний из Google Docs...")
    
    all_content = []
    loaded = 0
    
    for i, (doc_id, name) in enumerate(zip(GOOGLE_DOCS_IDS, DOC_NAMES)):
        logger.info(f"  [{i+1}/{len(GOOGLE_DOCS_IDS)}] {name}...")
        content = fetch_google_doc(doc_id)
        
        if content:
            all_content.append(f"=== {name.upper()} ===\n\n{content}")
            loaded += 1
            logger.info(f"  ✓ {name} загружен ({len(content)} символов)")
        else:
            logger.warning(f"  ✗ {name} не загружен")
    
    if all_content:
        result = "\n\n" + "="*50 + "\n\n".join(all_content)
        _knowledge_cache = result
        logger.info(f"База знаний готова: {loaded}/{len(GOOGLE_DOCS_IDS)} документов, {len(result)} символов")
        return result
    else:
        logger.error("Ни один документ не загружен! Проверь доступ к Google Docs.")
        return "База знаний недоступна. Используй общие знания о психологическом образовании."


def get_knowledge_base() -> str:
    """Получить базу знаний (с кэшированием)"""
    return load_knowledge_base()


def refresh_knowledge_base():
    """Сбросить кэш и перезагрузить документы"""
    global _knowledge_cache
    _knowledge_cache = None
    return load_knowledge_base()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    kb = load_knowledge_base()
    print(f"\nЗагружено {len(kb)} символов")
    print(kb[:500] + "...")
