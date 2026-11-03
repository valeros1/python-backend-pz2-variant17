# Практическая работа №2 — вариант 17

Тема вычислительной задачи: преобразование GIF в WebM. Первый этап —
утилита командной строки, которая получает байты GIF из стандартного
ввода и передаёт байты WebM в стандартный вывод. Второй этап добавил
HTTP API, третий — хранение данных в SQLite.

## Как работает утилита

`src.converter.main()` запускает FFmpeg через `subprocess` и соединяет
его входной и выходной потоки с потоками утилиты. FFmpeg декодирует GIF
и кодирует видео VP9 в контейнер WebM. Нечётные размеры кадра дополняются
до чётных, чтобы использовать формат пикселей `yuv420p`. Диагностика
FFmpeg направляется в стандартный поток ошибок; при ошибке утилита
возвращает ненулевой код завершения.

Исполняемый файл FFmpeg предоставляет пакет `imageio-ffmpeg`. Его можно
переопределить переменной окружения `IMAGEIO_FFMPEG_EXE`. Утилита
не принимает позиционных аргументов. Выходные GIF и WebM-файлы в
`build/examples/` создаются только для демонстрации и исключены из Git.

## Установка и запуск

Требуется Python 3.13. Из корня проекта выполните:

```bash
make install
make examples
make test
make lint
```

`make examples` генерирует пять GIF, запускает утилиту для каждого,
проверяет декодирование и число кадров результата, затем сохраняет файлы
в `build/examples/`.
Примеры: неподвижный кадр, два кадра, разные задержки кадров, нечётные
размеры и восемь кадров. Исходные GIF строятся кодом в `examples/demo.py`;
бинарные файлы не входят в репозиторий.

Ручной запуск на одном из созданных примеров:

```bash
.venv/bin/python -m src.converter \
  < build/examples/two_frames.gif \
  > build/examples/manual.webm
```

Здесь `<` направляет содержимое GIF в стандартный ввод программы, а `>`
сохраняет её стандартный вывод в файл. При успешном преобразовании
утилита ничего не печатает в терминал: её результатом являются байты
WebM. `make test` проверяет все пять примеров и некорректный вход;
`make lint` проверяет стиль Python-кода.

## Файлы первого этапа

| Путь | Назначение |
| --- | --- |
| `src/converter.py` | Потоковая утилита GIF → WebM |
| `examples/demo.py` | Генерация и запуск пяти примеров |
| `tests/test_converter.py` | Проверка полученного видео и ошибок |
| `Makefile` | Команды установки, показа и проверок |

## HTTP API второго этапа

Сервер запускается командой `make run` и принимает запросы на
`http://127.0.0.1:8000`. При первом запуске он читает демонстрационные
настройки из `config.example.json`: логин `student`, пароль `change-me`,
тестовый режим включён. Для собственных настроек скопируйте этот файл
в `config.json` и измените поля. `config.json` не попадает в Git.

Проверка из другого окна терминала:

```bash
curl -u student:change-me -H 'Content-Type: application/xml' \
  -d '<member><ip>127.0.0.1</ip><locale>ru</locale><platform>macOS</platform></member>' \
  http://127.0.0.1:8000/api/submit-member
```

Ответ содержит XML-запись `Member` с новым `identifier`. Без параметра
`-u` этот же запрос получит HTTP 401. Данные сохраняются в SQLite-файле
`build/app.sqlite3` и остаются после перезапуска сервера.

Все десять адресов из задания созданы в `src/server.py`. XML-запросы
содержат плоские элементы: `<member>`, `<query>` или `<filter>`.
В `POST /api/submit-query` поле `<argument>` содержит GIF, закодированный
в Base64. Сервер создаёт Query с `executing=1` и запускает фоновую задачу.
Если `test_mode=true`, результат получает статус `test` без вызова
конвертера. При `test_mode=false` вызывается `src.converter` через
`subprocess`; полученный WebM записывается в `Response.output` как Base64.
В обоих случаях после завершения задачи `executing` становится `0`.

| HTTP-запрос | Метод клиента | XML-запрос |
| --- | --- | --- |
| `POST /api/submit-member` | `submit_member` | `<member>` |
| `GET /api/discard-member?identifier=...` | `discard_member` | нет |
| `POST /api/collect-member` | `collect_member` | `<filter>` |
| `POST /api/adjust-member` | `adjust_member` | `<member>` |
| `POST /api/submit-query` | `submit_query` | `<query>` |
| `GET /api/discard-query?identifier=...` | `discard_query` | нет |
| `POST /api/collect-query/{member}` | `collect_query` | `<filter>` |
| `POST /api/adjust-query` | `adjust_query` | `<query>` |
| `POST /api/collect-response/{query}` | `collect_response` | `<filter>` |
| `POST /api/collect-report` | `collect_report` | нет |

Пустой фильтр записывается как `<filter />`. Изменение записи передаёт
`identifier` и изменяемые поля внутри `<member>` или `<query>`.
При удалении завершённой Query удаляются и её Response, поскольку
отдельного HTTP-маршрута для удаления Response в задании нет.
Выполняющуюся Query удалять нельзя. Member с существующими Query тоже
не удаляется: сначала нужно удалить его задачи.
Для реального преобразования создайте `config.json` с `test_mode: false`
и перезапустите сервер; тогда результат можно получить через
`collect_response(query)`.

Класс `ApiClient` в `src/client.py` скрывает HTTP и XML за методами с
именами операций модели. Например, `submit_member(...)` отправляет
`POST /api/submit-member`, а `collect_response(query)` получает результат
задачи. Через него работают тесты `tests/test_api_stateful.py`.

Тесты на основе `RuleBasedStateMachine` из Hypothesis создают и меняют
записи. `Bundle` передаёт идентификаторы созданных записей следующим
правилам. После каждого шага тест сравнивает состояние API с независимой
моделью и проверяет отчёт. Команда
`make coverage` запускает **только эти тесты** с измерением ветвей;
сохранённый результат для текущего слоя SQLite находится в
`reports/coverage-stage3.txt`. Отчёт второго этапа сохранён отдельно в
`reports/coverage-stage2.txt`.
`make test` также запускает проверки конвертера первого этапа и
SQLite-модели третьего этапа.

## SQLite на третьем этапе

`src/sqlite_model.py` реализует те же операции, что прежняя модель в
памяти, но выполняет явные SQL-запросы через стандартный модуль `sqlite3`.
Сервер по умолчанию использует этот слой. Таблицы `members`, `queries` и
`responses` создаются автоматически при первом запуске; поле `member`
ссылается на `members.identifier`, а поле `query` — на
`queries.identifier`. Включён режим `PRAGMA foreign_keys = ON`.

Завершённую Query можно удалить вместе с её Response. Удаление Member
со связанными Query отклоняется. Отчёт выполняет SQL `FULL OUTER JOIN`,
фильтр `Response.datetime >= now - 420` и выбор трёх полей из формулы.
Проверка `tests/test_sqlite_model.py` закрывает и заново открывает файл
базы, чтобы убедиться в сохранении записей.
