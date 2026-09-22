# Трансформация ZeroScript → ZeroAPI

## Исходная архитектура ZeroScript

ZeroScript - это расширение для браузера + локальный bridge, который превращает чаты AI (ChatGPT, DeepSeek и т.д.) в агента для Roblox Studio.

```
AI Chat (браузер) -> ZeroScript Extension -> Bridge (ws://127.0.0.1:17613) -> Roblox Studio MCP
```

Компоненты:
- `bridge.py` - WebSocket сервер + MCP менеджер для Roblox Studio
- `zeroscript-extension/` - Расширение браузера
  - `core/config.js` - Системный промпт, категории инструментов
  - `core/parser.js` - Парсер команд ZeroScript (###LUA###, JSON)
  - `core/main.js` - Агентный цикл: ждет ответ AI, парсит команды, отправляет в bridge
  - `providers/*.js` - Абстракция для каждого сайта (DeepSeek, ChatGPT, Gemini...)
  - `background.js` - Service worker, держит WebSocket к bridge

Логика:
1. Пользователь пишет в чате AI "построй дом"
2. Extension внедряет системный промпт с описанием команд
3. AI отвечает JSON `{"command": "execute_luau", "params": {...}}`
4. Extension парсит, отправляет в bridge
5. Bridge вызывает Roblox Studio MCP tool
6. Результат возвращается в чат как следующее сообщение

## Новая архитектура ZeroAPI

Задача: переделать из тулза для Roblox Studio в сервер для OpenAI Based API, который взаимодействует с браузером и чатом внутри, передавая все в API с помощью основы ZeroScript.

```
OpenAI Client -> ZeroAPI Server (FastAPI :8000) -> WebSocket -> Extension -> AI Chat -> Ответ
```

### Что сохранено от ZeroScript (основа):

1. **Provider abstraction** (`providers/*.js`) - весь код для работы с DOM каждого сайта (как найти input, как отправить, как читать ответ) - используется без изменений. Это самая ценная часть.

2. **WebSocket bridge концепция** - из `bridge.py` взята идея resilient WebSocket сервера, который держит соединение с расширением. Переработано в `server/ws_manager.py`.

3. **MCP Manager** - сохранен как опциональный `server/mcp_manager.py` для совместимости с Roblox.

4. **Parser** (`core/parser.js`) - может использоваться для tool calling, если AI возвращает команды.

5. **Background service worker** паттерн - переработан для поддержки двух соединений (legacy 17613 + API 8000).

### Что добавлено / изменено:

#### Сервер (Python):

**Было:** `bridge.py` - только WebSocket сервер для MCP

**Стало:** `server/` пакет:
- `main.py` - FastAPI сервер с OpenAI-совместимыми эндпоинтами
  - `GET /v1/models` - список моделей
  - `POST /v1/chat/completions` - основной endpoint, streaming и non-streaming
  - `POST /v1/completions` - legacy completions
  - `WS /ws` - WebSocket для расширения
  - `GET /` - Dashboard UI
  - `GET /health`, `/api/status` - статус

- `ws_manager.py` - Менеджер браузерных клиентов
  - Регистрация клиентов с provider info
  - Выбор клиента по provider (model -> provider mapping)
  - Очереди для streaming (asyncio.Queue)
  - Future для non-streaming запросов
  - Обработка busy статуса

- `openai_models.py` - Pydantic модели для OpenAI API

- `config.py` - Маппинг моделей на провайдеры, конфиг

- `combined.py` - Запуск обоих серверов одновременно

Логика инвертирована:
- Было: Extension -> Server (extension инициирует tool calls)
- Стало: Server -> Extension (server инициирует chat requests, extension выполняет)

#### Расширение (JS):

**Было:** Только агентный режим для Roblox

**Стало:** Дуальный режим:
- `core/api_handler.js` - НОВЫЙ файл, обработчик API запросов
  - Слушает `zeroapi-chat-request` от background
  - Использует `ZSProvider.typeAndSend()` для отправки промпта (переиспользует логику ZeroScript)
  - Использует `ZSProvider.readAssistant()` и `isGenerating()` для чтения ответа
  - Поддержка streaming: отправляет chunks по мере появления текста
  - Отправляет финальный ответ или ошибку

- `background.js` - Переработан:
  - Два WebSocket соединения: legacy (17613) и API (8000)
  - Роутинг `chat_request` от сервера к подходящей вкладке браузера (по provider)
  - Форвардинг chunks от content script к серверу
  - Обновление provider info при `zeroapi-handler-ready`

- `manifest.json` - Добавлены permissions для localhost:8000, tabs, обновлены content_scripts чтобы включать api_handler.js

- `popup.html/js` - Новый UI с API статусом, кнопкой Dashboard

### Поток данных (OpenAI API):

1. Клиент делает `POST /v1/chat/completions` с `messages`
2. `server/main.py` конвертирует `messages` в `prompt` (messages_to_prompt)
3. `ws_manager.select_client()` выбирает браузер по модели (deepseek-chat -> DeepSeek вкладка)
4. Отправляет `chat_request` через WebSocket в extension background
5. Background находит вкладку с нужным провайдером, отправляет `zeroapi-chat-request` в content script
6. `api_handler.js` вызывает `ZSProvider.typeAndSend(prompt)`
7. Provider-specific код (deepseek.js) находит textarea, устанавливает value через native setter, кликает send
8. AI начинает генерировать, `api_handler` поллит `readAssistant()` и `isGenerating()`
9. Для streaming: каждый новый кусок текста отправляется как `chat_chunk` -> background -> WebSocket -> server -> SSE к клиенту
10. Для non-streaming: ждет завершения, отправляет `chat_response`
11. Server формирует OpenAI-совместимый ответ

### Почему ZeroScript - хорошая основа:

- **Provider abstraction** уже решает самую сложную часть: как работать с DOM каждого AI сайта (селекторы меняются, нужны хаки для React/Vue)
- **Resilient WebSocket** уже реализован с реконнектами, heartbeat, stale detection
- **Composing / Sending** логика уже есть: как правильно вставить текст чтобы React/Vue его принял
- **Response detection** уже есть: как понять что AI закончил генерировать (по кнопке stop, по росту текста, по reasoning)
- **Multi-tab support** уже есть в background

Мы просто инвертировали направление: вместо "AI пишет команды -> мы выполняем в Roblox" стало "Мы пишем промпт -> AI отвечает -> мы возвращаем".

### Дополнительные улучшения:

- Dashboard UI на `/` с автообновлением
- Swagger UI на `/docs`
- Поддержка всех OpenAI параметров (temperature, max_tokens передаются но пока игнорируются браузером - можно добавить в prompt)
- Маппинг моделей на провайдеры
- Очередь и busy статус чтобы не отправлять два запроса в одну вкладку
- Совместимость со старым Roblox режимом

### Что можно улучшить дальше:

- ~~Tool calling~~ **сделано**: `server/tool_calling.py` эмулирует OpenAI tool calling - спеки тулов уходят в промпт, ответ модели парсится в `tool_calls`, результаты `role="tool"` возвращаются в промпт (`[Tool result: name]`). MCP-серверы читаются из `zeroapi_config.json` (`mcp_servers`), при `mcp_tools.auto_execute` сервер сам исполняет MCP-вызовы и продолжает диалог; `GET /v1/tools`, `GET /api/tools`, `POST /api/tool/call`.
- Session persistence: сохранять conversation history по session_id в одной вкладке
- Vision: поддержка image input (screen_capture уже есть в ZeroScript)
- Auth: API key проверка
- Rate limiting
- Multi-browser: балансировка между несколькими браузерами
- Headless: Playwright/Puppeteer вместо расширения для серверного деплоя
