# Telegram Claude Code Control Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить standalone Python Telegram-бота, дающего полный интерактивный контроль над Claude Code через PTY-прокси с поддержкой нескольких сессий, параллельного шелла и inline-подтверждений.

**Architecture:** Telegram-бот (python-telegram-bot v20) принимает сообщения и роутит их к Session Manager, который управляет именованными PTY-сессиями. Каждая сессия содержит PTY-main (процесс `claude`) и PTY-shell (bash). Вывод собирается одним сообщением, подтверждения обнаруживаются паттерн-матчингом и отправляются как inline-кнопки.

**Tech Stack:** Python 3.12, python-telegram-bot 20.x, ptyprocess, pyyaml, python-dotenv, pytest, pytest-asyncio

---

## Карта файлов

```
~/Documents/claude-tg-bot/        ← создать как отдельный репозиторий
├── bot/
│   ├── __init__.py               # пустой
│   ├── main.py                   # entrypoint: Application + handlers wire-up
│   ├── auth.py                   # whitelist: is_allowed, add_user, remove_user
│   ├── project_registry.py       # load projects.yaml → list[Project]
│   ├── pty_session.py            # PtySession: PTY-main + PTY-shell + read_until_idle
│   ├── confirmation.py           # needs_confirmation(), keyboard builders
│   ├── session_manager.py        # SessionManager: per-user sessions, timeout tracking
│   └── handlers.py               # все Telegram handlers + _send_output helper
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_project_registry.py
│   ├── test_pty_session.py
│   ├── test_confirmation.py
│   └── test_session_manager.py
├── config/
│   ├── projects.yaml
│   └── .env.example
├── deploy/
│   ├── com.claude-tg-bot.plist   # launchd для Mac
│   ├── claude-tg-bot.service     # systemd stub
│   └── Dockerfile                # Docker stub
├── Makefile
├── requirements.txt
└── pyproject.toml
```

---

## Task 1: Project scaffold

**Files:**
- Create: `~/Documents/claude-tg-bot/` (весь скелет)
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `config/projects.yaml`
- Create: `config/.env.example`

- [ ] **Step 1: Создать директорию и инициализировать git**

```bash
mkdir -p ~/Documents/claude-tg-bot
cd ~/Documents/claude-tg-bot
git init
mkdir -p bot tests config deploy
touch bot/__init__.py tests/__init__.py
```

- [ ] **Step 2: Создать `requirements.txt`**

```
python-telegram-bot[job-queue]==20.7
ptyprocess==0.7.0
pyte==0.8.0
pyyaml==6.0.1
python-dotenv==1.0.0
pytest==8.1.0
pytest-asyncio==0.23.5
```

- [ ] **Step 3: Создать `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Создать `config/projects.yaml`**

```yaml
projects:
  - name: api-getvey
    path: /Users/andreysamosuk/Documents/api-getvey
```

- [ ] **Step 5: Создать `config/.env.example`**

```env
BOT_TOKEN=your_telegram_bot_token_here
OWNER_ID=123456789
ALLOWED_USERS=123456789
```

- [ ] **Step 6: Создать `config/.gitignore`** (в корне проекта)

```
.env
config/allowed_users.json
__pycache__/
.pytest_cache/
*.pyc
```

- [ ] **Step 7: Установить зависимости**

```bash
pip install -r requirements.txt
```

- [ ] **Step 8: Commit**

```bash
git add .
git commit -m "chore: initial project scaffold"
```

---

## Task 2: Auth module

**Files:**
- Create: `bot/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Написать failing тест**

```python
# tests/test_auth.py
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_owner_is_always_allowed(tmp_path):
    users_file = tmp_path / "allowed_users.json"
    with patch.dict(os.environ, {"OWNER_ID": "100", "ALLOWED_USERS": ""}):
        import importlib
        import bot.auth as auth
        importlib.reload(auth)
        auth._USERS_FILE = users_file
        assert auth.is_allowed(100) is True


def test_unknown_user_is_denied(tmp_path):
    users_file = tmp_path / "allowed_users.json"
    with patch.dict(os.environ, {"OWNER_ID": "100", "ALLOWED_USERS": ""}):
        import importlib
        import bot.auth as auth
        importlib.reload(auth)
        auth._USERS_FILE = users_file
        assert auth.is_allowed(999) is False


def test_add_and_check_user(tmp_path):
    users_file = tmp_path / "allowed_users.json"
    with patch.dict(os.environ, {"OWNER_ID": "100", "ALLOWED_USERS": ""}):
        import importlib
        import bot.auth as auth
        importlib.reload(auth)
        auth._USERS_FILE = users_file
        auth.add_user(200)
        assert auth.is_allowed(200) is True


def test_remove_user(tmp_path):
    users_file = tmp_path / "allowed_users.json"
    with patch.dict(os.environ, {"OWNER_ID": "100", "ALLOWED_USERS": ""}):
        import importlib
        import bot.auth as auth
        importlib.reload(auth)
        auth._USERS_FILE = users_file
        auth.add_user(200)
        auth.remove_user(200)
        assert auth.is_allowed(200) is False


def test_list_users_includes_added(tmp_path):
    users_file = tmp_path / "allowed_users.json"
    with patch.dict(os.environ, {"OWNER_ID": "100", "ALLOWED_USERS": ""}):
        import importlib
        import bot.auth as auth
        importlib.reload(auth)
        auth._USERS_FILE = users_file
        auth.add_user(300)
        assert 300 in auth.list_users()
```

- [ ] **Step 2: Запустить тесты — убедиться что падают**

```bash
cd ~/Documents/claude-tg-bot
pytest tests/test_auth.py -v
```

Ожидаемо: `ModuleNotFoundError: No module named 'bot.auth'`

- [ ] **Step 3: Реализовать `bot/auth.py`**

```python
import os
import json
from pathlib import Path

OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
_USERS_FILE = Path("config/allowed_users.json")


def _load_users() -> set[int]:
    if _USERS_FILE.exists():
        return set(json.loads(_USERS_FILE.read_text()))
    raw = os.getenv("ALLOWED_USERS", "")
    return {int(uid) for uid in raw.split(",") if uid.strip().isdigit()}


def _save_users(users: set[int]) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(sorted(users)))


def is_allowed(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    return user_id in _load_users()


def add_user(user_id: int) -> None:
    users = _load_users()
    users.add(user_id)
    _save_users(users)


def remove_user(user_id: int) -> None:
    users = _load_users()
    users.discard(user_id)
    _save_users(users)


def list_users() -> list[int]:
    return sorted(_load_users())
```

- [ ] **Step 4: Запустить тесты — должны пройти**

```bash
pytest tests/test_auth.py -v
```

Ожидаемо: все 5 тестов `PASSED`

- [ ] **Step 5: Commit**

```bash
git add bot/auth.py tests/test_auth.py
git commit -m "feat: auth module with whitelist"
```

---

## Task 3: Project Registry

**Files:**
- Create: `bot/project_registry.py`
- Create: `tests/test_project_registry.py`

- [ ] **Step 1: Написать failing тест**

```python
# tests/test_project_registry.py
import pytest
from pathlib import Path
import tempfile
import yaml
from bot.project_registry import load_projects, get_project, Project


def _write_yaml(tmp_path: Path, data: dict) -> Path:
    f = tmp_path / "projects.yaml"
    f.write_text(yaml.dump(data))
    return str(f)


def test_load_projects_returns_list(tmp_path):
    cfg = _write_yaml(tmp_path, {
        "projects": [
            {"name": "foo", "path": "/tmp/foo"},
            {"name": "bar", "path": "/tmp/bar"},
        ]
    })
    projects = load_projects(cfg)
    assert len(projects) == 2
    assert projects[0].name == "foo"
    assert projects[0].path == Path("/tmp/foo")


def test_get_project_found(tmp_path):
    cfg = _write_yaml(tmp_path, {
        "projects": [{"name": "myapp", "path": "/tmp/myapp"}]
    })
    p = get_project("myapp", cfg)
    assert p is not None
    assert p.name == "myapp"


def test_get_project_not_found(tmp_path):
    cfg = _write_yaml(tmp_path, {
        "projects": [{"name": "myapp", "path": "/tmp/myapp"}]
    })
    assert get_project("other", cfg) is None
```

- [ ] **Step 2: Запустить — убедиться что падают**

```bash
pytest tests/test_project_registry.py -v
```

Ожидаемо: `ModuleNotFoundError`

- [ ] **Step 3: Реализовать `bot/project_registry.py`**

```python
from dataclasses import dataclass
from pathlib import Path
import yaml

DEFAULT_CONFIG = "config/projects.yaml"


@dataclass
class Project:
    name: str
    path: Path


def load_projects(config_path: str = DEFAULT_CONFIG) -> list[Project]:
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return [Project(name=p["name"], path=Path(p["path"])) for p in data["projects"]]


def get_project(name: str, config_path: str = DEFAULT_CONFIG) -> Project | None:
    for p in load_projects(config_path):
        if p.name == name:
            return p
    return None
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/test_project_registry.py -v
```

Ожидаемо: все 3 теста `PASSED`

- [ ] **Step 5: Commit**

```bash
git add bot/project_registry.py tests/test_project_registry.py
git commit -m "feat: project registry from projects.yaml"
```

---

## Task 4: Confirmation Detector

**Files:**
- Create: `bot/confirmation.py`
- Create: `tests/test_confirmation.py`

- [ ] **Step 1: Написать failing тест**

```python
# tests/test_confirmation.py
import pytest
from bot.confirmation import needs_confirmation, confirmation_keyboard, timeout_keyboard


@pytest.mark.parametrize("text", [
    "Do you want to delete these files? [Y/n]",
    "Proceed? (y/n)",
    "Are you sure? yes/no",
    "Continue? [y/N]",
    "Do you want to continue?",
    "Are you sure you want to proceed?",
])
def test_detects_confirmation(text):
    assert needs_confirmation(text) is True


@pytest.mark.parametrize("text", [
    "Writing file output.py",
    "Running tests...",
    "Done! 3 files modified.",
    "",
])
def test_no_false_positives(text):
    assert needs_confirmation(text) is False


def test_confirmation_keyboard_has_yes_no():
    kb = confirmation_keyboard("my-session")
    buttons = kb.inline_keyboard[0]
    callbacks = [b.callback_data for b in buttons]
    assert "confirm:yes:my-session" in callbacks
    assert "confirm:no:my-session" in callbacks


def test_timeout_keyboard_has_keep_kill():
    kb = timeout_keyboard("my-session")
    buttons = kb.inline_keyboard[0]
    callbacks = [b.callback_data for b in buttons]
    assert "timeout:keep:my-session" in callbacks
    assert "timeout:kill:my-session" in callbacks
```

- [ ] **Step 2: Запустить — убедиться что падают**

```bash
pytest tests/test_confirmation.py -v
```

- [ ] **Step 3: Реализовать `bot/confirmation.py`**

```python
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_PATTERNS = [
    re.compile(r'\[Y/n\]', re.IGNORECASE),
    re.compile(r'\[y/N\]', re.IGNORECASE),
    re.compile(r'\(y/n\)', re.IGNORECASE),
    re.compile(r'yes/no', re.IGNORECASE),
    re.compile(r'proceed\?', re.IGNORECASE),
    re.compile(r'do you want to', re.IGNORECASE),
    re.compile(r'are you sure', re.IGNORECASE),
    re.compile(r'continue\?', re.IGNORECASE),
]


def needs_confirmation(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def confirmation_keyboard(session_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes", callback_data=f"confirm:yes:{session_name}"),
        InlineKeyboardButton("❌ No", callback_data=f"confirm:no:{session_name}"),
    ]])


def timeout_keyboard(session_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Всё норм", callback_data=f"timeout:keep:{session_name}"),
        InlineKeyboardButton("🛑 Завершить", callback_data=f"timeout:kill:{session_name}"),
    ]])
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/test_confirmation.py -v
```

Ожидаемо: все 8 тестов `PASSED`

- [ ] **Step 5: Commit**

```bash
git add bot/confirmation.py tests/test_confirmation.py
git commit -m "feat: confirmation pattern detector + keyboard builders"
```

---

## Task 5: PTY Session

**Files:**
- Create: `bot/pty_session.py`
- Create: `tests/test_pty_session.py`

- [ ] **Step 1: Написать failing тест**

```python
# tests/test_pty_session.py
import pytest
import asyncio
from pathlib import Path
from bot.pty_session import PtySession, strip_ansi


def test_strip_ansi_removes_escape_codes():
    raw = "\x1b[32mHello\x1b[0m World"
    assert strip_ansi(raw) == "Hello World"


def test_strip_ansi_clean_text_unchanged():
    assert strip_ansi("plain text") == "plain text"


def test_session_starts_and_is_alive(tmp_path):
    session = PtySession(name="test", project_path=tmp_path)
    # Spawn echo instead of claude to avoid needing claude installed in tests
    session.start(command=["bash", "--norc", "--noprofile"])
    assert session.is_alive()
    session.kill()
    assert not session.is_alive()


def test_session_shell_mode_toggle(tmp_path):
    session = PtySession(name="test", project_path=tmp_path)
    assert not session.in_shell_mode
    session.enter_shell_mode()
    assert session.in_shell_mode
    session.exit_shell_mode()
    assert not session.in_shell_mode


@pytest.mark.asyncio
async def test_read_until_idle_returns_output(tmp_path):
    session = PtySession(name="test", project_path=tmp_path)
    # Use a shell that prints something and pauses
    session.start(command=["bash", "--norc", "--noprofile"])
    session.write_raw("echo hello_world\n")
    output = await session.read_until_idle(idle_timeout=1.0)
    session.kill()
    assert "hello_world" in output
```

- [ ] **Step 2: Запустить — убедиться что падают**

```bash
pytest tests/test_pty_session.py -v
```

- [ ] **Step 3: Реализовать `bot/pty_session.py`**

```python
import asyncio
import re
import time
from pathlib import Path
import ptyprocess

_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub('', text)


class PtySession:
    def __init__(self, name: str, project_path: Path):
        self.name = name
        self.project_path = project_path
        self._main: ptyprocess.PtyProcess | None = None
        self._shell: ptyprocess.PtyProcess | None = None
        self._shell_mode: bool = False
        self._last_activity: float = time.time()

    def start(self, command: list[str] | None = None) -> None:
        main_cmd = command or ["claude"]
        self._main = ptyprocess.PtyProcess.spawn(
            main_cmd,
            cwd=str(self.project_path),
            dimensions=(50, 220),
        )
        shell_cmd = ["bash", "--login"] if command is None else command
        self._shell = ptyprocess.PtyProcess.spawn(
            shell_cmd,
            cwd=str(self.project_path),
            dimensions=(50, 220),
        )
        self._last_activity = time.time()

    def is_alive(self) -> bool:
        return self._main is not None and self._main.isalive()

    def write(self, text: str) -> None:
        self._last_activity = time.time()
        target = self._shell if self._shell_mode else self._main
        target.write((text + "\n").encode())

    def write_raw(self, data: str) -> None:
        self._last_activity = time.time()
        self._main.write(data.encode())

    def enter_shell_mode(self) -> None:
        self._shell_mode = True

    def exit_shell_mode(self) -> None:
        self._shell_mode = False

    @property
    def in_shell_mode(self) -> bool:
        return self._shell_mode

    @property
    def last_activity(self) -> float:
        return self._last_activity

    async def read_until_idle(self, idle_timeout: float = 2.0) -> str:
        """Read PTY output until no new bytes for idle_timeout seconds."""
        loop = asyncio.get_event_loop()
        target = self._shell if self._shell_mode else self._main
        chunks: list[str] = []

        while self.is_alive():
            try:
                chunk = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: target.read(4096)),
                    timeout=idle_timeout,
                )
                if chunk:
                    chunks.append(chunk.decode(errors="replace"))
            except asyncio.TimeoutError:
                break
            except EOFError:
                break

        return strip_ansi("".join(chunks))

    def kill(self) -> None:
        for proc in (self._main, self._shell):
            if proc and proc.isalive():
                proc.terminate(force=True)
        self._main = None
        self._shell = None
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/test_pty_session.py -v
```

Ожидаемо: все 5 тестов `PASSED`

- [ ] **Step 5: Commit**

```bash
git add bot/pty_session.py tests/test_pty_session.py
git commit -m "feat: PTY session with read_until_idle and shell mode"
```

---

## Task 6: Session Manager

**Files:**
- Create: `bot/session_manager.py`
- Create: `tests/test_session_manager.py`

- [ ] **Step 1: Написать failing тест**

```python
# tests/test_session_manager.py
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from bot.session_manager import SessionManager


def _mock_session(name: str, last_activity: float | None = None) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.last_activity = last_activity or time.time()
    s.is_alive.return_value = True
    return s


def test_new_session_becomes_active():
    mgr = SessionManager()
    with patch("bot.session_manager.PtySession") as MockPty:
        MockPty.return_value = _mock_session("proj")
        session = mgr.new_session(user_id=1, project_name="proj", project_path=Path("/tmp"))
    assert mgr.get_active_session(1) is session


def test_switch_session():
    mgr = SessionManager()
    with patch("bot.session_manager.PtySession") as MockPty:
        MockPty.return_value = _mock_session("a")
        mgr.new_session(1, "a", Path("/tmp/a"))
        MockPty.return_value = _mock_session("b")
        mgr.new_session(1, "b", Path("/tmp/b"))

    mgr.switch_session(1, "a")
    assert mgr.get_active_session(1).name == "a"


def test_kill_session_removes_it():
    mgr = SessionManager()
    with patch("bot.session_manager.PtySession") as MockPty:
        MockPty.return_value = _mock_session("proj")
        mgr.new_session(1, "proj", Path("/tmp"))

    mgr.kill_session(1, "proj")
    assert mgr.get_active_session(1) is None


def test_list_sessions():
    mgr = SessionManager()
    with patch("bot.session_manager.PtySession") as MockPty:
        MockPty.return_value = _mock_session("a")
        mgr.new_session(1, "a", Path("/tmp/a"))
        MockPty.return_value = _mock_session("b")
        mgr.new_session(1, "b", Path("/tmp/b"))

    sessions = mgr.list_sessions(1)
    names = [s for s, _ in sessions]
    assert "a" in names and "b" in names


def test_get_idle_sessions():
    mgr = SessionManager()
    old_time = time.time() - 1900  # 31+ minutes ago
    with patch("bot.session_manager.PtySession") as MockPty:
        mock = _mock_session("old", last_activity=old_time)
        MockPty.return_value = mock
        mgr.new_session(1, "old", Path("/tmp"))

    idle = mgr.get_idle_sessions()
    assert len(idle) == 1
    assert idle[0][1] == "old"
```

- [ ] **Step 2: Запустить — убедиться что падают**

```bash
pytest tests/test_session_manager.py -v
```

- [ ] **Step 3: Реализовать `bot/session_manager.py`**

```python
import time
from dataclasses import dataclass, field
from pathlib import Path
from bot.pty_session import PtySession

IDLE_WARN_SECONDS = 30 * 60   # 30 min
IDLE_KILL_SECONDS = 40 * 60   # 40 min (30 + 10 grace)


@dataclass
class _UserState:
    sessions: dict[str, PtySession] = field(default_factory=dict)
    active: str | None = None


class SessionManager:
    def __init__(self) -> None:
        self._users: dict[int, _UserState] = {}

    def _state(self, user_id: int) -> _UserState:
        if user_id not in self._users:
            self._users[user_id] = _UserState()
        return self._users[user_id]

    def new_session(self, user_id: int, project_name: str, project_path: Path) -> PtySession:
        state = self._state(user_id)
        session = PtySession(name=project_name, project_path=project_path)
        session.start()
        state.sessions[project_name] = session
        state.active = project_name
        return session

    def get_active_session(self, user_id: int) -> PtySession | None:
        state = self._users.get(user_id)
        if not state or not state.active:
            return None
        return state.sessions.get(state.active)

    def get_session(self, user_id: int, name: str) -> PtySession | None:
        state = self._users.get(user_id)
        if not state:
            return None
        return state.sessions.get(name)

    def switch_session(self, user_id: int, name: str) -> bool:
        state = self._users.get(user_id)
        if not state or name not in state.sessions:
            return False
        state.active = name
        return True

    def kill_session(self, user_id: int, name: str) -> bool:
        state = self._users.get(user_id)
        if not state or name not in state.sessions:
            return False
        state.sessions[name].kill()
        del state.sessions[name]
        if state.active == name:
            remaining = list(state.sessions.keys())
            state.active = remaining[0] if remaining else None
        return True

    def list_sessions(self, user_id: int) -> list[tuple[str, bool]]:
        state = self._users.get(user_id)
        if not state:
            return []
        return [(name, name == state.active) for name in state.sessions]

    def get_idle_sessions(self) -> list[tuple[int, str, float]]:
        """Returns (user_id, session_name, idle_seconds) for sessions idle >= IDLE_WARN_SECONDS."""
        now = time.time()
        result = []
        for user_id, state in self._users.items():
            for name, session in state.sessions.items():
                idle = now - session.last_activity
                if idle >= IDLE_WARN_SECONDS:
                    result.append((user_id, name, idle))
        return result
```

- [ ] **Step 4: Запустить тесты**

```bash
pytest tests/test_session_manager.py -v
```

Ожидаемо: все 5 тестов `PASSED`

- [ ] **Step 5: Commit**

```bash
git add bot/session_manager.py tests/test_session_manager.py
git commit -m "feat: session manager with multi-session support and idle tracking"
```

---

## Task 7: Bot Handlers — команды сессий и проектов

**Files:**
- Create: `bot/handlers.py` (первая часть)

- [ ] **Step 1: Создать `bot/handlers.py` с командами `/session` и `/projects`**

```python
# bot/handlers.py
import asyncio
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from bot.auth import is_allowed, add_user, remove_user, list_users, OWNER_ID
from bot.session_manager import SessionManager, IDLE_KILL_SECONDS, IDLE_WARN_SECONDS
from bot.project_registry import load_projects, get_project
from bot.confirmation import needs_confirmation, confirmation_keyboard, timeout_keyboard

logger = logging.getLogger(__name__)
session_manager = SessionManager()


# ── /projects ──────────────────────────────────────────────────────────────
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        return
    try:
        projects = load_projects()
    except Exception as e:
        await update.message.reply_text(f"Ошибка чтения projects.yaml: {e}")
        return
    lines = [f"• {p.name} — {p.path}" for p in projects]
    await update.message.reply_text("Доступные проекты:\n" + "\n".join(lines))


# ── /session ───────────────────────────────────────────────────────────────
async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    args = context.args  # list of words after /session
    if not args:
        await update.message.reply_text(
            "Использование:\n"
            "/session new <project>\n"
            "/session list\n"
            "/session switch <name>\n"
            "/session kill <name>"
        )
        return

    sub = args[0]

    if sub == "list":
        sessions = session_manager.list_sessions(user_id)
        if not sessions:
            await update.message.reply_text("Нет активных сессий.")
            return
        lines = [f"{'→' if active else '  '} {name}" for name, active in sessions]
        await update.message.reply_text("Сессии:\n" + "\n".join(lines))

    elif sub == "new":
        if len(args) < 2:
            await update.message.reply_text("Укажи проект: /session new <project>")
            return
        project_name = args[1]
        project = get_project(project_name)
        if not project:
            await update.message.reply_text(f"Проект '{project_name}' не найден. Проверь /projects")
            return
        session = session_manager.new_session(user_id, project_name, project.path)
        await update.message.reply_text(f"✅ Сессия [{project_name}] запущена.")

    elif sub == "switch":
        if len(args) < 2:
            await update.message.reply_text("Укажи имя: /session switch <name>")
            return
        name = args[1]
        if session_manager.switch_session(user_id, name):
            await update.message.reply_text(f"Переключено на [{name}]")
        else:
            await update.message.reply_text(f"Сессия '{name}' не найдена.")

    elif sub == "kill":
        if len(args) < 2:
            await update.message.reply_text("Укажи имя: /session kill <name>")
            return
        name = args[1]
        if session_manager.kill_session(user_id, name):
            await update.message.reply_text(f"Сессия [{name}] завершена.")
        else:
            await update.message.reply_text(f"Сессия '{name}' не найдена.")

    else:
        await update.message.reply_text(f"Неизвестная подкоманда: {sub}")
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: /session and /projects handlers"
```

---

## Task 8: Bot Handlers — message routing, shell mode, output

**Files:**
- Modify: `bot/handlers.py` (добавить в конец файла)

- [ ] **Step 1: Добавить helper `_send_output` и `_collect_output`**

```python
# Добавить в bot/handlers.py


async def _send_output(update: Update, session_name: str, text: str) -> None:
    prefix = f"[{session_name}]\n"
    full = prefix + (text or "(нет вывода)")
    if len(full) > 4096:
        await update.message.reply_document(
            document=full.encode("utf-8"),
            filename="output.txt",
            caption=f"[{session_name}] Вывод слишком длинный, отправлен как файл.",
        )
    else:
        await update.message.reply_text(full)


async def _collect_and_respond(update: Update, session) -> None:
    """Read PTY output; send inline buttons if confirmation detected, else send text."""
    output = await session.read_until_idle(idle_timeout=2.0)

    if session.is_alive() and needs_confirmation(output):
        prefix = f"[{session.name}]\n"
        full = prefix + output
        if len(full) > 4096:
            full = full[-4090:]  # trim to last 4090 chars
        await update.message.reply_text(
            full,
            reply_markup=confirmation_keyboard(session.name),
        )
    else:
        await _send_output(update, session.name, output)
```

- [ ] **Step 2: Добавить `/shell`, `/back` и основной message handler**

```python
# Добавить в bot/handlers.py


async def cmd_shell(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    session = session_manager.get_active_session(user_id)
    if not session:
        await update.message.reply_text("Нет активной сессии.")
        return

    if context.args:
        # /shell <command> — single command
        cmd = " ".join(context.args)
        session.enter_shell_mode()
        session.write(cmd)
        output = await session.read_until_idle(idle_timeout=2.0)
        session.exit_shell_mode()
        await _send_output(update, session.name + ":shell", output)
    else:
        # /shell — enter interactive shell mode
        session.enter_shell_mode()
        await update.message.reply_text(
            f"[{session.name}] Shell режим активен. Отправляй команды, /back — вернуться к claude."
        )


async def cmd_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return
    session = session_manager.get_active_session(user_id)
    if not session:
        await update.message.reply_text("Нет активной сессии.")
        return
    session.exit_shell_mode()
    await update.message.reply_text(f"[{session.name}] Вернулись к claude.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        return

    text = update.message.text

    # ! shortcut for shell
    if text.startswith("!"):
        session = session_manager.get_active_session(user_id)
        if not session:
            await update.message.reply_text("Нет активной сессии.")
            return
        cmd = text[1:].strip()
        session.enter_shell_mode()
        session.write(cmd)
        output = await session.read_until_idle(idle_timeout=2.0)
        session.exit_shell_mode()
        await _send_output(update, session.name + ":shell", output)
        return

    session = session_manager.get_active_session(user_id)
    if not session:
        await update.message.reply_text(
            "Нет активной сессии. Создай через /session new <project>"
        )
        return

    if not session.is_alive():
        await update.message.reply_text(f"[{session.name}] ❌ Сессия мертва. Пересоздай через /session new.")
        return

    session.write(text)
    await _collect_and_respond(update, session)
```

- [ ] **Step 3: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: message routing, shell mode, output helpers"
```

---

## Task 9: Bot Handlers — confirmation callbacks и timeout

**Files:**
- Modify: `bot/handlers.py` (добавить в конец файла)

- [ ] **Step 1: Добавить callback handler для кнопок**

```python
# Добавить в bot/handlers.py


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    if not is_allowed(user_id):
        return

    await query.answer()
    parts = query.data.split(":")  # e.g. ["confirm", "yes", "api-getvey"]
    action = parts[0]

    if action == "confirm":
        choice = parts[1]   # "yes" or "no"
        session_name = ":".join(parts[2:])
        session = session_manager.get_session(user_id, session_name)
        if not session:
            await query.edit_message_text(f"Сессия '{session_name}' не найдена.")
            return
        session.write_raw("y\n" if choice == "yes" else "n\n")
        await query.edit_message_reply_markup(reply_markup=None)
        output = await session.read_until_idle(idle_timeout=2.0)
        if output:
            await _send_output_to_chat(query.message.chat_id, context, session_name, output)

    elif action == "timeout":
        decision = parts[1]   # "keep" or "kill"
        session_name = ":".join(parts[2:])
        await query.edit_message_reply_markup(reply_markup=None)
        if decision == "kill":
            session_manager.kill_session(user_id, session_name)
            await query.edit_message_text(f"[{session_name}] 🛑 Сессия завершена.")
        else:
            session = session_manager.get_session(user_id, session_name)
            if session:
                import time
                session._last_activity = time.time()
            await query.edit_message_text(f"[{session_name}] ✅ Сессия продолжает работу.")


async def _send_output_to_chat(chat_id: int, context, session_name: str, text: str) -> None:
    prefix = f"[{session_name}]\n"
    full = prefix + (text or "(нет вывода)")
    if len(full) > 4096:
        await context.bot.send_document(
            chat_id=chat_id,
            document=full.encode("utf-8"),
            filename="output.txt",
            caption=f"[{session_name}] Вывод слишком длинный.",
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=full)
```

- [ ] **Step 2: Добавить auth команды и timeout checker job**

```python
# Добавить в bot/handlers.py


# ── Auth commands (owner only) ─────────────────────────────────────────────

async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /adduser <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    add_user(uid)
    await update.message.reply_text(f"✅ Пользователь {uid} добавлен.")


async def cmd_removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Использование: /removeuser <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    remove_user(uid)
    await update.message.reply_text(f"✅ Пользователь {uid} удалён.")


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    users = list_users()
    if not users:
        await update.message.reply_text("Список пуст (только owner имеет доступ).")
        return
    await update.message.reply_text("Разрешённые пользователи:\n" + "\n".join(str(u) for u in users))


# ── Timeout checker (runs as job every 5 min) ──────────────────────────────

async def check_idle_sessions(context) -> None:
    idle = session_manager.get_idle_sessions()
    for user_id, session_name, idle_secs in idle:
        if idle_secs >= IDLE_KILL_SECONDS:
            session_manager.kill_session(user_id, session_name)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"[{session_name}] 🛑 Сессия автоматически завершена (неактивна {int(idle_secs // 60)} мин).",
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"[{session_name}] ⚠️ Сессия неактивна {int(idle_secs // 60)} мин.",
                reply_markup=timeout_keyboard(session_name),
            )
```

- [ ] **Step 3: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: confirmation callbacks, auth commands, idle timeout checker"
```

---

## Task 10: Main entrypoint

**Files:**
- Create: `bot/main.py`

- [ ] **Step 1: Создать `bot/main.py`**

```python
# bot/main.py
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(Path.home() / "Library" / "Logs" / "claude-tg-bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.environ["BOT_TOKEN"]

    from bot.handlers import (
        handle_message,
        handle_callback,
        cmd_session,
        cmd_projects,
        cmd_shell,
        cmd_back,
        cmd_adduser,
        cmd_removeuser,
        cmd_users,
        check_idle_sessions,
    )

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("session", cmd_session))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("shell", cmd_shell))
    app.add_handler(CommandHandler("back", cmd_back))
    app.add_handler(CommandHandler("adduser", cmd_adduser))
    app.add_handler(CommandHandler("removeuser", cmd_removeuser))
    app.add_handler(CommandHandler("users", cmd_users))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Check idle sessions every 5 minutes
    app.job_queue.run_repeating(check_idle_sessions, interval=300, first=60)

    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Создать `.env` из примера и проверить запуск (только синтаксис)**

```bash
cp config/.env.example .env
# Заполни BOT_TOKEN и OWNER_ID реальными значениями
python -c "from bot.main import main; print('OK')"
```

Ожидаемо: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot/main.py
git commit -m "feat: main entrypoint, wire all handlers and idle job"
```

---

## Task 11: Deploy — launchd, stubs, Makefile

**Files:**
- Create: `deploy/com.claude-tg-bot.plist`
- Create: `deploy/claude-tg-bot.service`
- Create: `deploy/Dockerfile`
- Create: `Makefile`

- [ ] **Step 1: Создать `deploy/com.claude-tg-bot.plist`**

Замени `/Users/andreysamosuk` на свой реальный home path.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-tg-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>bot.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/andreysamosuk/Documents/claude-tg-bot</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/andreysamosuk/Library/Logs/claude-tg-bot.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/andreysamosuk/Library/Logs/claude-tg-bot-error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

- [ ] **Step 2: Создать `deploy/claude-tg-bot.service` (systemd stub)**

```ini
# systemd service stub — для будущего деплоя на сервер
# Раскомментировать и адаптировать при переезде

# [Unit]
# Description=Claude Telegram Bot
# After=network.target
#
# [Service]
# Type=simple
# User=ubuntu
# WorkingDirectory=/opt/claude-tg-bot
# ExecStart=/usr/bin/python3 -m bot.main
# Restart=always
# RestartSec=5
# EnvironmentFile=/opt/claude-tg-bot/.env
#
# [Install]
# WantedBy=multi-user.target
```

- [ ] **Step 3: Создать `deploy/Dockerfile` (stub)**

```dockerfile
# Docker stub — для будущего деплоя на сервер
# Раскомментировать при переезде

# FROM python:3.12-slim
#
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
#
# COPY . .
#
# CMD ["python", "-m", "bot.main"]
```

- [ ] **Step 4: Создать `Makefile`**

```makefile
PLIST_NAME = com.claude-tg-bot
PLIST_SRC  = deploy/$(PLIST_NAME).plist
PLIST_DST  = $(HOME)/Library/LaunchAgents/$(PLIST_NAME).plist

.PHONY: run install uninstall logs test

run:
	python -m bot.main

install:
	cp $(PLIST_SRC) $(PLIST_DST)
	launchctl load $(PLIST_DST)
	@echo "✅ Bot installed as launchd service. Starts automatically on login."

uninstall:
	launchctl unload $(PLIST_DST) 2>/dev/null || true
	rm -f $(PLIST_DST)
	@echo "✅ Bot service removed."

logs:
	tail -f $(HOME)/Library/Logs/claude-tg-bot.log

test:
	pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add deploy/ Makefile
git commit -m "chore: deploy files — launchd, systemd stub, Dockerfile stub, Makefile"
```

---

## Task 12: Smoke test — запуск и проверка

- [ ] **Step 1: Запустить все тесты**

```bash
cd ~/Documents/claude-tg-bot
pytest tests/ -v
```

Ожидаемо: все тесты `PASSED`, 0 failures

- [ ] **Step 2: Запустить бота локально**

```bash
# .env должен содержать реальные BOT_TOKEN и OWNER_ID
make run
```

Ожидаемо: лог `Bot started.`

- [ ] **Step 3: В Telegram — базовая проверка**

Открой бот в Telegram и выполни:
1. `/projects` — должен вернуть список из `config/projects.yaml`
2. `/session new api-getvey` — должно ответить `✅ Сессия [api-getvey] запущена.`
3. `/session list` — должен показать сессию `→ api-getvey`
4. Напиши `hello` — Claude должен ответить, ответ придёт одним сообщением

- [ ] **Step 4: Установить как launchd сервис**

```bash
make install
```

Ожидаемо: бот запускается при логине, перезапускается при падении

- [ ] **Step 5: Финальный commit**

```bash
git add .
git commit -m "chore: verified smoke test, ready for use"
```
