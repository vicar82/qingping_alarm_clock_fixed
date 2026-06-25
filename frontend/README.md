# Qingping Alarm Clock Lovelace Card

Кастомная карточка для управления будильником Qingping CGD1 прямо из Lovelace UI.

## Возможности

- Установка времени будильника
- Выбор дней недели (визуальные чипы)
- Включение / выключение / удаление будильников
- Список установленных будильников (не более 5 по умолчанию)
- Отображение текущей даты и времени
- Кнопка принудительной синхронизации времени

## Установка

1. Скопируй файл `qingping-alarm-clock-card.js` в папку:

```
/config/www/community/qingping-alarm-clock-card/
```

2. Добавь ресурс в Home Assistant:

**Настройки → Панель управления → Ресурсы панели управления → Добавить ресурс**

```
/local/community/qingping-alarm-clock-card/qingping-alarm-clock-card.js
```

Тип: **JavaScript Module**.

3. Перезагрузи интерфейс (Ctrl+F5 / Cmd+Shift+R).

## Использование

Добавь карточку в Lovelace dashboard в режиме YAML:

```yaml
type: custom:qingping-alarm-clock-card
device_id: a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
max_alarms: 5
title: Будильник в спальне
```

### Как узнать device_id

1. Открой карточку устройства Qingping Alarm Clock.
2. Нажми ⋮ → **Разработчики инструментов** или найди в URL `/config/devices/device/<device_id>`.
3. Скопируй ID устройства.

## Опции

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `device_id` | string | обязательно | ID устройства Qingping Alarm Clock |
| `max_alarms` | number | 5 | Максимальное количество будильников в списке |
| `title` | string | "Будильник Qingping" | Заголовок карточки |

## Зависимости

Требуется интеграция `qingping_alarm_clock` с сервисами:
- `qingping_alarm_clock.get_alarms`
- `qingping_alarm_clock.set_alarm`
- `qingping_alarm_clock.delete_alarm`
- `qingping_alarm_clock.sync_time`
