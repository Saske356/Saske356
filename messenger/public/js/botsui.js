// Bot management ("Мои боты") and small bot-related UI helpers.
import { S } from './state.js';
import { rpc } from './net.js';
import { $, el, esc, icon, toast } from './util.js';
import { avatar } from './avatar.js';
import { modal, head, confirmBox } from './modals.js';

export const botChip = u => (u?.bot ? '<span class="bot-chip">бот</span>' : '');

export function botsModal() {
  const { m } = modal(`${head('Мои боты', 'Боты работают через HTTP API, похожий на Telegram Bot API')}<div class="m-body" id="botsBody"><div class="empty-note">Загружаем…</div></div>`, { cls: 'bots-modal' });
  const body = $('#botsBody', m);
  const apiBase = location.origin;

  async function list() {
    const bots = await rpc('myBots');
    body.innerHTML = `
      ${bots.length ? bots.map(b => `<button class="bot-row" data-bot="${b.id}">${avatar(b, 'md')}<span class="pick-txt"><b>${esc(b.name)}</b><small>@${esc(b.username)} · ${b.webhook ? 'вебхук' : 'long polling'}${b.pending ? ` · в очереди: ${b.pending}` : ''}</small></span>${icon('back', 'flip')}</button>`).join('')
        : '<div class="empty-note">Ботов пока нет. Создайте первого — это займёт минуту.</div>'}
      <form class="bot-new" id="botNew">
        <h3 class="sect">Новый бот</h3>
        <label class="field"><span>Имя</span><input name="name" maxlength="64" placeholder="Например, Погода"></label>
        <label class="field"><span>Логин (заканчивается на bot)</span><input name="username" maxlength="32" placeholder="weather_bot" autocapitalize="off" spellcheck="false"></label>
        <button class="btn primary wide" type="submit">Создать бота</button>
      </form>`;
    $('#botNew', body).onsubmit = async e => {
      e.preventDefault();
      const f = e.target.elements;
      try {
        const r = await rpc('createBot', { name: f.name.value, username: f.username.value });
        details(r.bot, r.token);
      } catch (x) { toast(x.message, 'bad'); }
    };
  }

  function details(b, token) {
    const curl = token ? `curl ${apiBase}/bot${token}/getMe` : '';
    body.innerHTML = `
      <button class="link sm" data-back>${icon('back', 'xs')} Все боты</button>
      <div class="bot-head">${avatar(b, 'lg')}<div><b>${esc(b.name)}</b><small class="muted">@${esc(b.username)} · id ${b.id}</small></div></div>
      ${token ? `<div class="token-box"><div class="d-title">${icon('key')}<b>Токен доступа</b></div>
        <p class="muted small">Покажем один раз. Храните его в секрете: с ним можно писать от имени бота и читать его беседы.</p>
        <code class="token" id="tok">${esc(token)}</code>
        <div class="row-btns"><button class="btn ghost sm" data-copy="${esc(token)}">${icon('copy')} Скопировать</button></div>
        <p class="muted small">Проверка: <code>${esc(curl)}</code></p></div>` : ''}
      <label class="field"><span>Имя</span><input id="bName" maxlength="64" value="${esc(b.name)}"></label>
      <label class="field"><span>Описание (видно перед первым сообщением)</span><textarea id="bDesc" rows="3" maxlength="512" placeholder="Что умеет бот">${esc(b.description)}</textarea></label>
      <label class="field"><span>О боте (в профиле)</span><input id="bAbout" maxlength="160" value="${esc(b.bio || '')}"></label>
      <label class="toggle"><input type="checkbox" id="bPriv" ${b.privacy ? 'checked' : ''}><i></i><span>Режим приватности в группах<br><small class="muted">Бот получает только команды, упоминания и ответы на свои сообщения</small></span></label>
      <div class="bot-meta">
        <div><small class="muted">Команды</small><b>${b.commands.length ? b.commands.map(c => '/' + esc(c.command)).join(' ') : 'не заданы — через setMyCommands'}</b></div>
        <div><small class="muted">Получение обновлений</small><b>${b.webhook ? esc(b.webhook) : 'getUpdates (long polling)'}</b>${b.webhookError ? `<small class="missed">${esc(b.webhookError)}</small>` : ''}</div>
      </div>
      <div class="m-foot flush">
        <button class="btn danger sm" data-del>Удалить</button><span class="grow"></span>
        <button class="btn ghost sm" data-token>Новый токен</button>
        <button class="btn primary sm" data-save>Сохранить</button>
      </div>
      <details class="api-help"><summary>Как написать бота</summary>
        <p>Адрес API: <code>${esc(apiBase)}/bot&lt;ТОКЕН&gt;/&lt;метод&gt;</code>. Методы и формат ответов совпадают с Telegram Bot API, поэтому подходят многие библиотеки, где можно поменять адрес сервера.</p>
        <p>Поддерживаются: getMe, getUpdates, setWebhook, deleteWebhook, getWebhookInfo, sendMessage (inline- и обычные клавиатуры), sendPhoto, sendDocument, sendVideo, sendAudio, sendVoice, sendPoll, editMessageText, editMessageReplyMarkup, deleteMessage, answerCallbackQuery, sendChatAction, setMyCommands, getMyCommands, setMyDescription, getChat, getFile.</p>
        <p>Готовый пример — <code>examples/echo-bot.js</code> в репозитории.</p>
      </details>`;
    body.onclick = async e => {
      const t = e.target;
      if (t.closest('[data-back]')) { body.onclick = null; return list(); }
      const cp = t.closest('[data-copy]');
      if (cp) return navigator.clipboard?.writeText(cp.dataset.copy).then(() => toast('Токен скопирован'));
      if (t.closest('[data-save]')) {
        try { const nb = await rpc('updateBot', { botId: b.id, name: $('#bName').value, description: $('#bDesc').value, about: $('#bAbout').value, privacy: $('#bPriv').checked }); Object.assign(b, nb); toast('Сохранено'); }
        catch (x) { toast(x.message, 'bad'); }
      }
      if (t.closest('[data-token]')) {
        if (!await confirmBox('Выпустить новый токен?', 'Старый токен перестанет работать сразу.', 'Выпустить')) return;
        const r = await rpc('newBotToken', { botId: b.id }); details(b, r.token);
      }
      if (t.closest('[data-del]')) {
        if (!await confirmBox('Удалить бота?', `@${b.username} покинет все беседы, токен перестанет работать.`, 'Удалить')) return;
        await rpc('deleteBot', { botId: b.id }); body.onclick = null; list();
      }
    };
  }

  body.addEventListener('click', async e => {
    const r = e.target.closest('[data-bot]');
    if (!r) return;
    const bots = await rpc('myBots');
    const b = bots.find(x => x.id === Number(r.dataset.bot));
    if (b) details(b);
  });
  list().catch(e => toast(e.message, 'bad'));
}

// Inline keyboard under a bot message.
export function inlineKb(m) {
  const kb = m.p?.kb;
  if (!kb?.length || !S.users[m.from]?.bot) return '';
  return `<div class="kb">${kb.map((row, r) => `<div class="kb-row">${row.map((b, c) => b.u
    ? `<a class="kb-btn" href="${esc(b.u)}" target="_blank" rel="noopener noreferrer">${esc(b.t)}${icon('forward', 'xs')}</a>`
    : `<button class="kb-btn" data-cb="${r}:${c}">${esc(b.t)}</button>`).join('')}</div>`).join('')}</div>`;
}

export function showBotAnswer(evt) {
  if (!evt.text) return;
  if (evt.alert) {
    const name = S.users[evt.botId]?.name || 'Бот';
    modal(`${head(name)}<div class="m-body"><p>${esc(evt.text)}</p></div><div class="m-foot"><button class="btn primary" data-close>OK</button></div>`, { cls: 'small' });
  } else toast(evt.text);
}
export { el };
