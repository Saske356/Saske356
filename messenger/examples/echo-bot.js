// Пример бота для Орбиты. Запуск:
//   ORBITA_URL=http://localhost:3000 BOT_TOKEN=123:abc... node examples/echo-bot.js
// API повторяет Telegram Bot API, только адрес сервера свой.

const BASE = (process.env.ORBITA_URL || 'http://localhost:3000').replace(/\/$/, '');
const TOKEN = process.env.BOT_TOKEN;
if (!TOKEN) { console.error('Укажите BOT_TOKEN (выдаётся в Профиль → Мои боты)'); process.exit(1); }

async function api(method, params = {}) {
  const res = await fetch(`${BASE}/bot${TOKEN}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(`${method}: ${data.description}`);
  return data.result;
}

const dice = () => 1 + Math.floor(Math.random() * 6);
const rollKb = { inline_keyboard: [[{ text: '🎲 Бросить ещё', callback_data: 'roll' }, { text: '🪙 Монетка', callback_data: 'coin' }], [{ text: 'Документация', url: 'https://core.telegram.org/bots/api' }]] };

async function onMessage(m) {
  const chat = m.chat.id;
  const text = (m.text || '').trim();
  const cmd = text.startsWith('/') ? text.split(/[\s@]/)[0].slice(1) : null;
  if (cmd === 'start' || cmd === 'help') {
    return api('sendMessage', { chat_id: chat, text: `Привет, ${m.from.first_name}! Я **эхо-бот**.\n\n/roll — бросить кубик\n/menu — клавиатура\n/poll — опрос\nПришлите фото или файл — расскажу о нём.` });
  }
  if (cmd === 'roll') return api('sendMessage', { chat_id: chat, text: `Выпало: ${dice()}`, reply_markup: rollKb });
  if (cmd === 'menu') {
    return api('sendMessage', { chat_id: chat, text: 'Выберите вариант', reply_markup: { keyboard: [['Погода', 'Новости'], ['Скрыть клавиатуру']], one_time_keyboard: false, input_field_placeholder: 'Нажмите кнопку' } });
  }
  if (text === 'Скрыть клавиатуру') return api('sendMessage', { chat_id: chat, text: 'Готово', reply_markup: { remove_keyboard: true } });
  if (cmd === 'poll') return api('sendPoll', { chat_id: chat, question: 'Какой язык для ботов лучше?', options: ['JavaScript', 'Python', 'Go', 'Rust'] });
  const file = m.photo?.at(-1) || m.document || m.voice || m.video;
  if (file) {
    const info = await api('getFile', { file_id: file.file_id });
    const res = await fetch(`${BASE}/file/bot${TOKEN}/${info.file_path}`);
    const bytes = (await res.arrayBuffer()).byteLength;
    return api('sendMessage', { chat_id: chat, reply_to_message_id: m.message_id, text: `Получил ${m.photo ? 'фото' : m.voice ? 'голосовое' : 'файл'}: ${bytes} байт` });
  }
  if (text) {
    await api('sendChatAction', { chat_id: chat, action: 'typing' });
    return api('sendMessage', { chat_id: chat, text, reply_to_message_id: m.message_id });
  }
}

async function onCallback(q) {
  const value = q.data === 'coin' ? (Math.random() < 0.5 ? 'Орёл' : 'Решка') : `Выпало: ${dice()}`;
  await api('editMessageText', { chat_id: q.message.chat.id, message_id: q.message.message_id, text: value, reply_markup: rollKb });
  await api('answerCallbackQuery', { callback_query_id: q.id, text: value });
}

(async () => {
  const me = await api('getMe');
  await api('deleteWebhook');
  await api('setMyCommands', { commands: [
    { command: 'start', description: 'Начать' }, { command: 'roll', description: 'Бросить кубик' },
    { command: 'menu', description: 'Показать клавиатуру' }, { command: 'poll', description: 'Опрос' }] });
  console.log(`@${me.username} запущен, жду сообщений…`);
  let offset = 0;
  for (;;) {
    try {
      const updates = await api('getUpdates', { offset, timeout: 30 });
      for (const u of updates) {
        offset = u.update_id + 1;
        if (u.message) await onMessage(u.message).catch(e => console.error(e.message));
        if (u.callback_query) await onCallback(u.callback_query).catch(e => console.error(e.message));
      }
    } catch (e) { console.error(e.message); await new Promise(r => setTimeout(r, 3000)); }
  }
})();
