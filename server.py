#!/usr/bin/env python3
"""
MCP сервер для NewsAPI
Позволяет LLM запрашивать новости на сегодня через NewsAPI
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Попытка загрузить переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен, используем только системные переменные окружения

# Инициализация сервера
app = Server("news-api")

# Получение API ключа из переменных окружения
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_BASE_URL = "https://newsapi.org/v2/everything"


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Возвращает список доступных инструментов"""
    return [
        Tool(
            name="get_today_news",
            description="Получить свежие новости по заданному запросу. "
                       "Ищет статьи, опубликованные за последние 1-2 дня, по ключевым словам или теме. "
                       "Возвращает список статей с заголовками, описаниями, ссылками и датами публикации.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Ключевые слова или тема для поиска новостей (например: 'bitcoin', 'technology', 'politics')"
                    },
                    "language": {
                        "type": "string",
                        "description": "Язык новостей (код ISO-639-1: ru, en, de, es, fr, it, pt и др.). По умолчанию: все языки",
                        "default": None
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Сортировка результатов: 'relevancy' (релевантность), 'popularity' (популярность), 'publishedAt' (дата публикации)",
                        "enum": ["relevancy", "popularity", "publishedAt"],
                        "default": "publishedAt"
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Количество результатов на странице (максимум 100, по умолчанию 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    }
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Обработка вызовов инструментов"""
    
    if name == "get_today_news":
        return await get_today_news(
            query=arguments.get("query"),
            language=arguments.get("language"),
            sort_by=arguments.get("sort_by", "publishedAt"),
            page_size=arguments.get("page_size", 10)
        )
    else:
        raise ValueError(f"Unknown tool: {name}")


async def get_today_news(
    query: str,
    language: Optional[str] = None,
    sort_by: str = "publishedAt",
    page_size: int = 10
) -> list[TextContent]:
    """
    Получает новости на сегодня по заданному запросу
    """
    if not NEWS_API_KEY:
        return [TextContent(
            type="text",
            text="Ошибка: NEWS_API_KEY не установлен. Пожалуйста, установите переменную окружения NEWS_API_KEY."
        )]
    
    if not query:
        return [TextContent(
            type="text",
            text="Ошибка: параметр 'query' обязателен для поиска новостей."
        )]
    
    # Получаем даты: сегодня и вчера (для поиска свежих новостей)
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    today_str = today.isoformat()
    yesterday_str = yesterday.isoformat()
    
    # Формируем параметры запроса (ищем за последние 2 дня для большей вероятности найти новости)
    params = {
        "q": query,
        "from": yesterday_str,
        "to": today_str,
        "sortBy": sort_by,
        "pageSize": min(page_size, 100),  # Ограничиваем максимум 100
        "apiKey": NEWS_API_KEY
    }
    
    if language:
        params["language"] = language
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(NEWS_API_BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "error":
                error_message = data.get("message", "Неизвестная ошибка")
                return [TextContent(
                    type="text",
                    text=f"Ошибка NewsAPI: {error_message}"
                )]
            
            articles = data.get("articles", [])
            total_results = data.get("totalResults", 0)
            
            if not articles:
                return [TextContent(
                    type="text",
                    text=f"Свежие новости по запросу '{query}' не найдены за последние дни."
                )]
            
            # Форматируем результаты
            result_text = f"Найдено свежих новостей: {total_results}\n"
            result_text += f"Показано: {len(articles)}\n\n"
            result_text += "=" * 80 + "\n\n"
            
            for i, article in enumerate(articles, 1):
                result_text += f"📰 Новость #{i}\n"
                result_text += f"Заголовок: {article.get('title', 'N/A')}\n"
                
                source = article.get('source', {})
                source_name = source.get('name', 'N/A')
                result_text += f"Источник: {source_name}\n"
                
                author = article.get('author')
                if author:
                    result_text += f"Автор: {author}\n"
                
                published_at = article.get('publishedAt', '')
                if published_at:
                    result_text += f"Дата публикации: {published_at}\n"
                
                description = article.get('description', '')
                if description:
                    result_text += f"Описание: {description}\n"
                
                url = article.get('url', '')
                if url:
                    result_text += f"Ссылка: {url}\n"
                
                result_text += "\n" + "-" * 80 + "\n\n"
            
            return [TextContent(type="text", text=result_text)]
            
    except httpx.HTTPStatusError as e:
        return [TextContent(
            type="text",
            text=f"HTTP ошибка {e.response.status_code}: {e.response.text}"
        )]
    except httpx.RequestError as e:
        return [TextContent(
            type="text",
            text=f"Ошибка запроса к NewsAPI: {str(e)}"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Неожиданная ошибка: {str(e)}"
        )]


async def main():
    """Главная функция для запуска сервера"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())

