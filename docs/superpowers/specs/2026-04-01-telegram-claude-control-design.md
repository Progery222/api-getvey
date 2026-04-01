# Telegram Claude Code Control — Design Spec

**Date:** 2026-04-01  
**Status:** Approved

## Overview

Standalone Python application — Telegram-бот для полного управления Claude Code с Mac (и в будущем с сервера). Позволяет управлять несколькими проектами одновременно через именованные сессии, получать вывод и отвечать на подтверждения через inline-кнопки.

---

## Architecture

```
Telegram ←→ Bot Layer ←→ Session Manager ←→ PTY-main (claude CLI)
                              ↓                   ↕
                       Project Registry      PTY-shell (bash)
                       Auth Whitelist
```

### Компоненты

**Bot Layer** (`python-telegram-bot` v20, async)
- Принимает текстовые сообщения и нажатия inline-кнопок
- Auth middleware: проверяет `user_id` по whitelist перед любым действием
- Роутит сообщения к активной сессии пользователя

**Session Manager**
- Хранит все активные сессии пользователя (несколько одновременно)
- Каждый пользователь имеет одну *активную* сессию — туда идут сообщения
- Переключение через `/session switch <name>`
- Таймаут: 30 мин без активности → предупреждение + кнопки → 10 мин → автокилл

**PTY Session** (на каждую сессию)
- `PTY-main` — процесс `claude` в директории проекта
- `PTY-shell` — отдельный bash в той же директории (параллельный терминал)
- Буфер вывода, стрипинг ANSI-кодов через `pyte`

**Confirmation Detector**
- Таймаут 2с без новых байт + процесс жив = Claude ждёт ввода
- Паттерн-матчинг: `y/n`, `[Y/n]`, `yes/no`, `proceed?`, `Do you want to`
- При детекции → inline-кнопки ✅ / ❌ в Telegram

**Project Registry**
- `config/projects.yaml` — список проектов: имя + абсолютный путь
- Команды `/projects`, `/session new <project>`

**Auth / Whitelist**
- `OWNER_ID` в `.env` — владелец, может `/adduser` и `/removeuser`
- `ALLOWED_USERS` — список разрешённых `user_id`

---

## Data Flow

### Основной флоу (команда → ответ)

```
1. Пользователь пишет сообщение
2. Auth check → если не в whitelist, игнор
3. Session Manager: найти активную сессию пользователя
4. Записать текст в PTY-main stdin
5. Читать stdout в буфер
6. Ждать:
   a) Таймаут 2с, процесс жив + паттерн y/n →
      прислать inline-кнопки ✅ / ❌
      нажатие → y или n → PTY-main stdin → вернуться к шагу 5
   b) Процесс завершился или сессия idle →
      собрать буфер → отправить как сообщение (или .txt если >4096 символов)
7. Ответ помечен: [api-getvey] результат...
```

### Параллельный терминал

```
/shell <команда>  →  PTY-shell stdin
! npm test        →  шорткат, то же самое
/shell            →  интерактивный режим (все сообщения → PTY-shell)
/back             →  вернуться к claude (PTY-main)
```

PTY-main при этом не блокируется и продолжает работу.

### Таймаут сессии

```
30 мин без активности →
  [project] ⚠️ Сессия неактивна 30 мин
  [✅ Всё норм] [🛑 Завершить]
  ↓ нет ответа 10 мин → автокилл + уведомление
```

---

## Commands Reference

### Сессии
| Команда | Действие |
|---------|---------|
| `/session new <project>` | Создать новую сессию для проекта |
| `/session list` | Список активных сессий |
| `/session switch <name>` | Переключить активную сессию |
| `/session kill <name>` | Завершить сессию |

### Проекты
| Команда | Действие |
|---------|---------|
| `/projects` | Список доступных проектов из projects.yaml |

### Терминал
| Команда | Действие |
|---------|---------|
| `/shell <cmd>` или `! <cmd>` | Выполнить в параллельном bash |
| `/shell` | Войти в интерактивный shell режим |
| `/back` | Вернуться к claude сессии |

### Авторизация (только owner)
| Команда | Действие |
|---------|---------|
| `/adduser <user_id>` | Добавить пользователя в whitelist |
| `/removeuser <user_id>` | Убрать пользователя |
| `/users` | Список разрешённых пользователей |

---

## Project Structure

```
claude-tg-bot/
├── bot/
│   ├── main.py              # entrypoint, запуск бота
│   ├── auth.py              # whitelist, add/remove users
│   ├── handlers.py          # message/callback handlers
│   ├── session_manager.py   # хранит все сессии всех пользователей
│   ├── pty_session.py       # PTY-main + PTY-shell + буфер
│   ├── confirmation.py      # детектор y/n, генерация кнопок
│   └── project_registry.py  # projects.yaml reader
├── config/
│   ├── projects.yaml        # список проектов: name + path
│   └── .env.example         # BOT_TOKEN, OWNER_ID, ALLOWED_USERS
├── deploy/
│   ├── com.claude-tg-bot.plist   # launchd для Mac (автозапуск)
│   ├── claude-tg-bot.service     # systemd stub (для сервера)
│   └── Dockerfile                # Docker stub (для сервера)
├── Makefile                 # make install / make uninstall / make run
├── requirements.txt
└── README.md
```

---

## Error Handling

| Ситуация | Поведение |
|---------|---------|
| PTY упал неожиданно | `[project] ❌ Сессия завершилась с ошибкой. Код: N` |
| Telegram недоступен | Буфер сохраняется, отправится при переподключении |
| Неавторизованный пользователь | Молчаливый игнор (без ответа) |
| Сессия зависла (30 мин) | Предупреждение + кнопки → автокилл через 10 мин |
| Вывод > 4096 символов | Отправляется как файл `output.txt` |

---

## Deployment

### Mac (основной)
- Запуск: `make install` → устанавливает `launchd` plist → автозапуск при логине
- Остановка: `make uninstall`
- Логи: `~/Library/Logs/claude-tg-bot.log`

### Сервер (заглушки, будущее)
- `deploy/Dockerfile` — базовый образ Python, готов к `docker-compose`
- `deploy/claude-tg-bot.service` — systemd unit, закомментированный шаблон

### Config
```yaml
# config/projects.yaml
projects:
  - name: api-getvey
    path: /Users/andreysamosuk/Documents/api-getvey
  - name: other-project
    path: /Users/andreysamosuk/Documents/other-project
```

```env
# .env
BOT_TOKEN=your_bot_token
OWNER_ID=123456789
ALLOWED_USERS=123456789,987654321
```

---

## Tech Stack

| Библиотека | Назначение |
|-----------|-----------|
| `python-telegram-bot` v20 | Async Telegram Bot API |
| `ptyprocess` | Псевдотерминал, управление процессами |
| `pyte` | Эмулятор терминала, стрипинг ANSI |
| `pyyaml` | Чтение projects.yaml |
| `python-dotenv` | Загрузка .env |
