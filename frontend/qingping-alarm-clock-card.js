class QingpingAlarmClockCard extends HTMLElement {
  constructor() {
    super();
    this._alarms = [];
    this._clockTimer = null;
    this._refreshTimer = null;
    this._dayMap = [
      { key: 'mon', label: 'Пн' },
      { key: 'tue', label: 'Вт' },
      { key: 'wed', label: 'Ср' },
      { key: 'thu', label: 'Чт' },
      { key: 'fri', label: 'Пт' },
      { key: 'sat', label: 'Сб' },
      { key: 'sun', label: 'Вс' },
    ];
  }

  setConfig(config) {
    if (!config.device_id) {
      throw new Error('device_id is required');
    }
    this.config = {
      max_alarms: 5,
      title: 'Будильник Qingping',
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._render();
      this._refreshAlarms();
      this._startClock();
      this._refreshTimer = setInterval(() => this._refreshAlarms(), 30000);
    }
  }

  connectedCallback() {
    this._startClock();
  }

  disconnectedCallback() {
    if (this._clockTimer) clearInterval(this._clockTimer);
    if (this._refreshTimer) clearInterval(this._refreshTimer);
  }

  _startClock() {
    if (this._clockTimer) return;
    this._clockTimer = setInterval(() => this._updateClock(), 1000);
    this._updateClock();
  }

  _updateClock() {
    const now = new Date();
    const dateStr = now.toLocaleDateString('ru-RU', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
    const timeStr = now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const dateEl = this.querySelector('.qp-clock-date');
    const timeEl = this.querySelector('.qp-clock-time');
    if (dateEl) dateEl.textContent = dateStr;
    if (timeEl) timeEl.textContent = timeStr;
  }

  async _refreshAlarms() {
    if (!this._hass || !this._hass.connection) return;
    try {
      const resp = await this._hass.connection.sendMessagePromise({
        type: 'call_service',
        domain: 'qingping_alarm_clock',
        service: 'get_alarms',
        service_data: { device_id: this.config.device_id },
        return_response: true,
      });
      const result = resp && resp.response;
      this._alarms = (result && result.alarms) || [];
      this._renderAlarms();
      this._renderAddForm();
    } catch (err) {
      console.error('Qingping card: failed to get alarms', err);
    }
  }

  async _callService(domain, service, data) {
    if (!this._hass) return;
    try {
      await this._hass.callService(domain, service, data);
      setTimeout(() => this._refreshAlarms(), 500);
    } catch (err) {
      console.error(`Qingping card: ${service} failed`, err);
      alert('Ошибка: ' + (err.message || err));
    }
  }

  _formatTime(timeObj) {
    if (!timeObj) return '--:--';
    if (typeof timeObj === 'string') {
      if (timeObj.includes('T')) {
        const d = new Date(timeObj);
        return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
      }
      return timeObj.slice(0, 5);
    }
    const h = String(timeObj.hour || 0).padStart(2, '0');
    const m = String(timeObj.minute || 0).padStart(2, '0');
    return `${h}:${m}`;
  }

  _parseTime(timeStr) {
    const [h, m] = timeStr.split(':').map(Number);
    return { hour: h, minute: m };
  }

  _parseDays(daysString) {
    if (!daysString) return [];
    return daysString.split(',').filter(Boolean);
  }

  _render() {
    this.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          background: var(--card-background-color, var(--ha-card-background, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,0.1));
          color: var(--primary-text-color, #212121);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .qp-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }
        .qp-title {
          font-size: 1.2em;
          font-weight: 500;
        }
        .qp-sync-btn {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
          border: none;
          border-radius: 20px;
          padding: 6px 14px;
          cursor: pointer;
          font-size: 0.9em;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .qp-clock {
          text-align: center;
          margin-bottom: 20px;
        }
        .qp-clock-time {
          font-size: 2.4em;
          font-weight: 300;
          letter-spacing: 2px;
        }
        .qp-clock-date {
          font-size: 0.95em;
          opacity: 0.8;
          margin-top: 4px;
        }
        .qp-section-title {
          font-size: 0.9em;
          text-transform: uppercase;
          opacity: 0.7;
          margin: 16px 0 8px;
        }
        .qp-alarm-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .qp-alarm-item {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 12px;
          background: var(--secondary-background-color, rgba(0,0,0,0.04));
          border-radius: 10px;
        }
        .qp-alarm-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
        }
        .qp-alarm-time {
          font-size: 1.5em;
          font-weight: 500;
          font-variant-numeric: tabular-nums;
        }
        .qp-alarm-time input {
          font-size: 1em;
          padding: 4px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff);
          color: inherit;
        }
        .qp-days {
          display: flex;
          gap: 4px;
          flex-wrap: wrap;
        }
        .qp-day-chip {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          border: 1px solid var(--divider-color, #ccc);
          background: transparent;
          color: var(--primary-text-color, #212121);
          cursor: pointer;
          font-size: 0.75em;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .qp-day-chip.active {
          background: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
          border-color: var(--primary-color, #03a9f4);
        }
        .qp-delete-btn {
          background: var(--error-color, #f44336);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 6px 10px;
          cursor: pointer;
          font-size: 0.85em;
        }
        .qp-add-form {
          display: flex;
          flex-direction: column;
          gap: 10px;
          padding: 12px;
          background: var(--secondary-background-color, rgba(0,0,0,0.04));
          border-radius: 10px;
          margin-top: 12px;
        }
        .qp-add-row {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .qp-add-row input[type="time"] {
          font-size: 1.1em;
          padding: 6px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #ccc);
          background: var(--card-background-color, #fff);
          color: inherit;
        }
        .qp-add-btn {
          background: var(--success-color, #4caf50);
          color: #fff;
          border: none;
          border-radius: 6px;
          padding: 8px 16px;
          cursor: pointer;
          font-size: 0.95em;
        }
        .qp-add-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .qp-limit-msg {
          text-align: center;
          opacity: 0.7;
          margin-top: 12px;
          font-size: 0.9em;
        }
        .qp-empty {
          text-align: center;
          opacity: 0.6;
          padding: 16px;
        }
        .qp-toggle {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.9em;
        }
        .qp-toggle input {
          width: 18px;
          height: 18px;
          cursor: pointer;
        }
      </style>
      <div class="qp-header">
        <div class="qp-title">${this.config.title}</div>
        <button class="qp-sync-btn" title="Синхронизировать время">
          <span>🔄</span> Sync
        </button>
      </div>
      <div class="qp-clock">
        <div class="qp-clock-time">--:--:--</div>
        <div class="qp-clock-date">--</div>
      </div>
      <div class="qp-section-title">Будильники</div>
      <div class="qp-alarm-list"></div>
      <div class="qp-add-section"></div>
    `;

    this.querySelector('.qp-sync-btn').addEventListener('click', () => {
      this._callService('qingping_alarm_clock', 'sync_time', {
        device_id: this.config.device_id,
      });
    });
  }

  _renderAlarms() {
    const listEl = this.querySelector('.qp-alarm-list');
    if (!listEl) return;

    const configured = this._alarms.filter((a) => a.enabled !== null && a.enabled !== undefined);
    if (configured.length === 0) {
      listEl.innerHTML = '<div class="qp-empty">Нет установленных будильников</div>';
      return;
    }

    listEl.innerHTML = configured
      .slice(0, this.config.max_alarms)
      .map((alarm) => this._alarmHtml(alarm))
      .join('');

    configured.slice(0, this.config.max_alarms).forEach((alarm) => {
      this._bindAlarmEvents(alarm);
    });
  }

  _alarmHtml(alarm) {
    const days = this._parseDays(alarm.days);
    const timeStr = this._formatTime(alarm.time);
    const dayChips = this._dayMap
      .map(
        (d) =>
          `<button class="qp-day-chip ${days.includes(d.key) ? 'active' : ''}" data-day="${d.key}">${d.label}</button>`
      )
      .join('');

    return `
      <div class="qp-alarm-item" data-slot="${alarm.slot}">
        <div class="qp-alarm-row">
          <div class="qp-alarm-time"><input type="time" value="${timeStr}"></div>
          <label class="qp-toggle">
            <input type="checkbox" ${alarm.enabled ? 'checked' : ''}>
            Вкл
          </label>
          <button class="qp-delete-btn">Удалить</button>
        </div>
        <div class="qp-days">${dayChips}</div>
      </div>
    `;
  }

  _bindAlarmEvents(alarm) {
    const el = this.querySelector(`.qp-alarm-item[data-slot="${alarm.slot}"]`);
    if (!el) return;

    const timeInput = el.querySelector('input[type="time"]');
    timeInput.addEventListener('change', () => {
      const time = this._parseTime(timeInput.value);
      const days = this._collectDays(el);
      this._callService('qingping_alarm_clock', 'set_alarm', {
        device_id: this.config.device_id,
        slot: alarm.slot,
        time: time,
        days: days.join(','),
        enabled: alarm.enabled,
        snooze: alarm.snooze,
      });
    });

    const enableInput = el.querySelector('input[type="checkbox"]');
    enableInput.addEventListener('change', () => {
      this._callService('qingping_alarm_clock', 'set_alarm', {
        device_id: this.config.device_id,
        slot: alarm.slot,
        enabled: enableInput.checked,
      });
    });

    el.querySelectorAll('.qp-day-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        chip.classList.toggle('active');
        const days = this._collectDays(el);
        this._callService('qingping_alarm_clock', 'set_alarm', {
          device_id: this.config.device_id,
          slot: alarm.slot,
          days: days.join(','),
          enabled: alarm.enabled,
        });
      });
    });

    el.querySelector('.qp-delete-btn').addEventListener('click', () => {
      this._callService('qingping_alarm_clock', 'delete_alarm', {
        device_id: this.config.device_id,
        slot: alarm.slot,
      });
    });
  }

  _collectDays(el) {
    const days = [];
    el.querySelectorAll('.qp-day-chip.active').forEach((chip) => {
      days.push(chip.dataset.day);
    });
    return days;
  }

  _renderAddForm() {
    const section = this.querySelector('.qp-add-section');
    if (!section) return;

    const configured = this._alarms.filter((a) => a.enabled !== null && a.enabled !== undefined);
    if (configured.length >= this.config.max_alarms) {
      section.innerHTML = '<div class="qp-limit-msg">Достигнут лимит в 5 будильников</div>';
      return;
    }

    section.innerHTML = `
      <div class="qp-section-title">Добавить будильник</div>
      <div class="qp-add-form">
        <div class="qp-add-row">
          <input type="time" class="qp-new-time" value="07:00">
        </div>
        <div class="qp-days qp-new-days">
          ${this._dayMap
            .map(
              (d) =>
                `<button class="qp-day-chip" data-day="${d.key}">${d.label}</button>`
            )
            .join('')}
        </div>
        <button class="qp-add-btn">Добавить</button>
      </div>
    `;

    const form = section.querySelector('.qp-add-form');
    form.querySelectorAll('.qp-day-chip').forEach((chip) => {
      chip.addEventListener('click', () => chip.classList.toggle('active'));
    });

    form.querySelector('.qp-add-btn').addEventListener('click', () => {
      const timeStr = form.querySelector('.qp-new-time').value;
      if (!timeStr) return;
      const days = [];
      form.querySelectorAll('.qp-new-days .qp-day-chip.active').forEach((chip) => {
        days.push(chip.dataset.day);
      });

      const emptySlot = this._findEmptySlot();
      if (emptySlot === null) {
        alert('Нет свободных слотов');
        return;
      }

      this._callService('qingping_alarm_clock', 'set_alarm', {
        device_id: this.config.device_id,
        slot: emptySlot,
        time: this._parseTime(timeStr),
        days: days.join(','),
        enabled: true,
      });
    });
  }

  _findEmptySlot() {
    for (let i = 0; i < 16; i++) {
      const alarm = this._alarms.find((a) => a.slot === i);
      if (!alarm || alarm.enabled === null || alarm.enabled === undefined) {
        return i;
      }
    }
    return null;
  }

  getCardSize() {
    return 6;
  }
}

customElements.define('qingping-alarm-clock-card', QingpingAlarmClockCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'qingping-alarm-clock-card',
  name: 'Qingping Alarm Clock',
  description: 'Карточка управления будильником Qingping CGD1',
  preview: true,
});
