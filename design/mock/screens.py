"""Разметка экранов макета (кроме главного): шторка стран, инструменты, режимы, PIN, чаты, переписка,
приветствие. Значки — токены {{ico:имя:размер}}, их подставляет build.py (design/icons/icons.py)."""


def ico(name, px):
    return "{{ico:%s:%d}}" % (name, px)


CHEV = '<span class="chev"></span>'

COUNTRIES = [("🇵🇱", "Польша", "42 мс", "g", True, True), ("🇩🇪", "Германия", "61 мс", "g", True, False),
             ("🇳🇱", "Нидерланды", "75 мс", "g", True, False), ("🇺🇸", "США", "180 мс", "y", True, False),
             ("🇯🇵", "Япония", "290 мс", "y", True, False), ("🇸🇬", "Сингапур", "…", "n", False, False),
             ("🇧🇷", "Бразилия", "нет связи", "rd", False, False)]


def sheet():
    rows = ""
    for fl, nm, ms, c, ok, sel in COUNTRIES:
        bars = '<div class="bars' + ('' if ok else ' grey') + '"><i></i><i></i><i></i><i></i></div>'
        tail = '<div class="chk">✓</div>' if sel else CHEV
        red = ' style="color:#ff8a94"' if c == "rd" else ""
        rows += (f'<div class="row press{" sel" if sel else ""}" data-name="{nm}"><div class="fl">{fl}</div>'
                 f'<div class="nm">{nm}</div><div class="d {c}"></div><div class="p"{red}>{ms}</div>{bars}{tail}</div>')
    return f'''
    <div class="dim" id="dim"></div>
    <div class="sheet" id="sheet">
      <div class="handle"></div>
      <div class="sh-head"><div class="circ" style="width:40px;height:40px">{ico("globe", 24)}</div><h2>Выберите страну</h2>
        <div class="circ" id="closeSheet"><span class="x">✕</span></div></div>
      <div class="search">{ico("search", 20)}<input id="q" placeholder="Поиск страны"></div>
      <div class="label"><span>РЕКОМЕНДУЕМ</span></div>
      <div class="rec">
        <div class="card press"><div class="ic">{ico("rocket", 32)}</div><div class="t"><b>Лучший сервер</b><small>Выбирает самый быстрый сам</small></div>{CHEV}</div>
        <div class="card press"><div class="ic">{ico("gamepad", 32)}</div><div class="t"><b>Игры</b><small>Напрямую, ровный пинг</small></div>{CHEV}</div>
      </div>
      <div class="label"><span>ВСЕ СТРАНЫ</span><div class="sortp" id="sort">⇅ По пингу ⌄</div></div>
      <div class="rows" id="rows">{rows}</div>
    </div>'''


def tool(icon, t, sub, right, top, h=50):
    return (f'<div class="card tool press" style="top:{top}px;height:{h}px"><div class="sq">{ico(icon, 30)}</div>'
            f'<div class="tt"><b>{t}</b><small>{sub}</small></div>{right}</div>')


def act(w):
    return f'<div class="act">{w}{CHEV}</div>'


def head(title, back="home"):
    return f'<div class="pagehead"><div class="back" data-go="{back}"><span class="lt">‹</span></div><h1>{title}</h1></div>'


def tools():
    val = lambda v: f'<span class="val">{v}</span>{CHEV}'
    return f'''
  <div class="view hidden" id="tools">
    <div class="earthtop"></div>
    {head("Инструменты")}
    <div class="card speed">
      <div class="gauge">{GAUGE}</div>
      <div class="st"><b>Тест скорости</b><small>Проверьте ваше соединение</small></div>
      <div class="startbtn press" id="startTest"><svg width="14" height="16" viewBox="0 0 14 16"><path d="M1 1l12 7-12 7z" fill="#fff"/></svg><span>Начать</span></div>
      <div class="metrics"><div>{ico("down", 20)}Загрузка<b id="tD">85 Мбит/с</b></div><div>{ico("up", 20)}Отдача<b id="tU">20 Мбит/с</b></div><div>{ico("clock", 20)}Пинг<b id="tP">42 мс</b></div></div>
    </div>
    {tool("shield", "Защита от утечек", "Без VPN интернет блокируется", act("Настроить"), 307)}
    {tool("apps", "Приложения мимо VPN", "Банки, Госуслуги и свои", val("52"), 364)}
    {tool("globe", "DNS", "1.1.1.1 · быстрый и приватный", val("Cloudflare"), 417)}
    {tool("power", "Автоподключение", "При включении телефона", '<div class="sw" id="auto"></div>', 470)}
    {tool("bolt", "Кнопка в шторке", "Включать VPN, не открывая приложение", act("Добавить"), 524, 56)}
    {tool("bell", "Уведомления", "Разрешены", act("Настроить"), 586)}
    {tool("refresh", "Обновление приложения", "Сейчас 0.1.49", act("Проверить"), 639)}
    {tool("crown", "Обновить подписку", "Страны и срок — с сервера", CHEV, 690)}
    {tool("swap", "Сменить подписку", "Удалить эту и добавить другую", CHEV, 744)}
    <div class="foot">Arise VPN 0.1.49</div>
  </div>'''


GAUGE = '''<svg viewBox="0 0 80 80"><defs><linearGradient id="gg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#1f4fd6"/><stop offset="1" stop-color="#8cc0ff"/></linearGradient></defs><path d="M12 58A32 32 0 1 1 68 58" fill="none" stroke="url(#gg)" stroke-width="7" stroke-linecap="round" style="filter:drop-shadow(0 0 6px #3d7bff)"/><path d="M40 12v6M17 24l4 4M63 24l-4 4M10 42h6M64 42h6" stroke="#4f8dff" stroke-width="2.5" stroke-linecap="round"/><path d="M40 46 55 30" stroke="#8cc0ff" stroke-width="4" stroke-linecap="round"/><circle cx="40" cy="46" r="6" fill="#0b1630" stroke="#8cc0ff" stroke-width="3"/></svg>'''


def mode(i, icon, name, desc, plus, minus, top, h, sel=False, badge=False):
    if sel:
        body = (f'<div class="split"><div><i style="background:#2fcf5a">+</i>{plus}</div>'
                f'<div><i style="background:#f5a03b">−</i>{minus}</div></div>')
    else:
        body = (f'<div class="chips"><div class="chip plus"><i>+</i>{plus}</div>'
                f'<div class="chip minus"><i>−</i>{minus}</div></div>')
    tail = '<div class="mchk">✓</div>' if sel else f'<div class="mchev">{CHEV}</div>'
    b = '<span class="badge">★ Рекомендуем</span>' if badge else ''
    return (f'<div class="card mcard press{" sel" if sel else ""}" data-m="{i}" style="top:{top}px;height:{h}px">'
            f'<div class="big">{ico(icon, 46)}</div><div class="mt"><b>{name}</b>{b}<p>{desc}</p>{body}</div>{tail}</div>')


def modes():
    return f'''
  <div class="view hidden" id="modes">
    <div class="earthtop"></div>
    {head("Режим соединения")}
    <div class="lead">Каждый режим по-настоящему меняет настройки VPN. Чем-то всегда жертвуем — честно пишем, чем.</div>
    {mode(0, "bolt", "Баланс", "Оптимальное сочетание скорости<br>и стабильности.", "Стабильно<br>и быстро", "Не максимум<br>скорости", 166, 129, True, True)}
    {mode(1, "gamepad", "Игровой", "Ровный пинг без скачков.", "Меньше лагов", "До 30 Мбит/с", 307, 92)}
    {mode(2, "rocket", "Турбо", "Максимум скорости для фильмов<br>и загрузок.", "До 500 Мбит/с", "Пинг может прыгать", 411, 98)}
    {mode(3, "hat", "Невидимка", "Весь трафик через VPN, даже<br>российские сайты.", "Макс. приватность", "Банки могут сбоить", 521, 98)}
    {mode(4, "battery", "Эконом", "Реже фоновые проверки.", "Батарея и трафик", "Медленнее", 634, 90)}
    <div class="card info">{ico("info", 26)}Выбранный режим можно изменить<br>в любое время</div>
  </div>'''


def pin():
    keys = ""
    letters = {"2": "ABC", "3": "DEF", "4": "GHI", "5": "JKL", "6": "MNO", "7": "PQRS", "8": "TUV", "9": "WXYZ"}
    for k in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"]:
        if not k:
            keys += '<div></div>'
        elif k == "⌫":
            keys += f'<div class="key press" data-k="del">{ico("backspace", 30)}</div>'
        else:
            keys += f'<div class="key press" data-k="{k}"><b>{k}</b><small>{letters.get(k, "")}</small></div>'
    return f'''
  <div class="view hidden" id="pin">
    <div class="earthtop"></div>
    <div class="pagehead"><div class="back" data-go="home"><span class="lt">‹</span></div></div>
    <div class="lockbadge">{ico("lock", 56)}</div>
    <h2 class="pintitle">Введите PIN</h2>
    <div class="dots" id="dots">{"<i></i>" * 6}</div>
    <p class="pinhint">{ico("shield", 20)}<span>Без PIN переписку не открыть,<br>даже если телефон в чужих руках.</span></p>
    <div class="keys" id="keys">{keys}</div>
    <div class="forgot">Забыли PIN? Начать новый чат →</div>
  </div>'''


CHATS = [("А", "Артём", "Хорошо, давай позже", "21:47", 2), ("М", "Мама", "Люблю тебя ❤️", "19:32", 0),
         ("Р", "Работа", "Документы готовы", "16:20", 0)]


def chats():
    rows = ""
    for i, (a, n, last, t, unread) in enumerate(CHATS):
        badge = f'<i class="unread">{unread}</i>' if unread else ''
        rows += (f'<div class="card crow press" data-go="talk" style="top:{232 + i * 92}px"><div class="ava">{a}</div>'
                 f'<div class="ct"><b>{n}</b><span>{last}</span><small>{ico("lock", 13)} зашифровано</small></div>'
                 f'<div class="cr"><em>{t}</em>{badge}</div></div>')
    return f'''
  <div class="view hidden" id="chats">
    <div class="earthtop"></div>
    <div class="chathead"><div class="back" data-go="home"><span class="lt">‹</span></div><h1>Чаты</h1>
      <div class="circ big press">＋</div><div class="circ big press">{ico("shield", 24)}</div></div>
    <div class="card codecard"><div class="ic2">{ico("shield", 30)}</div><div class="cc"><small>Мой код:</small><b>K7M-2QX-9TR</b></div>
      <div class="share press">{ico("share", 18)}Поделиться</div></div>
    {rows}
    <div class="card tabs"><div class="tab on">{ico("bubble", 26)}<span>Чаты</span></div><div class="tab">{ico("gear", 24)}<span>Настройки</span></div></div>
  </div>'''


def talk():
    msgs = [(True, "Брат, всё норм?", "21:40"), (False, "Да, бро 👍", "21:41"), (True, "Скинь фотку", "21:42"),
            (False, "PHOTO", "21:43"), (True, "Красавчик 😍", "21:44"), (False, "Угу 😏", "21:45")]
    html = ""
    for out, text, t in msgs:
        if text == "PHOTO":
            html += f'<div class="msg in photo"><img src="PHOTO_DATA" alt=""><em>{t}</em></div>'
        else:
            html += f'<div class="msg {"out" if out else "in"}">{text}<em>{t}{" ✓" if out else ""}</em></div>'
    return f'''
  <div class="view hidden" id="talk">
    <div class="earthtop"></div>
    <div class="talkhead"><div class="back" data-go="chats"><span class="lt">‹</span></div><div class="ava sm">А</div>
      <div class="th"><b>Артём</b><small>{ico("lock", 12)} код безопасности сверен</small></div><div class="circ">⋮</div></div>
    <div class="msgs" id="msgs">{html}</div>
    <div class="inputbar"><div class="circ big press">{ico("clip", 24)}</div><input id="msgIn" placeholder="Сообщение"><div class="sendb press" id="sendB">{ico("send", 26)}</div></div>
  </div>'''


def welcome():
    feat = lambda i, t: f'<div class="ft"><div class="fsq">{ico(i, 32)}</div><span>{t}</span></div>'
    return f'''
  <div class="view hidden" id="welcome">
    <div class="wmark"><svg class="orbit2" viewBox="0 0 220 120"><ellipse cx="110" cy="60" rx="104" ry="30" transform="rotate(-14 110 60)"/></svg>
      <svg class="mk" viewBox="218 265 820 672"><defs><linearGradient id="mg2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#eaf5ff"/><stop offset="1" stop-color="#2563ff"/></linearGradient></defs>
      <polygon fill="url(#mg2)" points="628,265 1038,937 713,815 683,704 776,741 628,515 480,741 573,704 543,815 218,937"/></svg></div>
    <h1 class="wtitle">Arise VPN</h1>
    <p class="wtag">Быстрый и приватный интернет без границ</p>
    <div class="wglobe"></div>
    <div class="feats">{feat("bolt", "Высокая<br>скорость")}<i class="sep"></i>{feat("shield", "Без логов")}<i class="sep"></i>{feat("globe", "Десятки<br>стран")}</div>
    <div class="wbtn press" data-go="home">Попробовать бесплатно <span>›</span></div>
    <div class="wbtn2 press">{ico("clip", 22)}Вставить ссылку подписки</div>
    <div class="wfoot">Подписку можно купить в Telegram-боте @AriseVPN_bot</div>
  </div>'''


def views():
    return tools() + modes() + pin() + chats() + talk() + welcome()


CSS = r'''
.chev{display:inline-block;width:9px;height:9px;border-right:2.4px solid #8fb5ff;border-top:2.4px solid #8fb5ff;transform:rotate(45deg);margin:0 6px 0 4px;flex-shrink:0}
.ico{display:inline-block;flex-shrink:0}.ico svg{width:100%;height:100%;display:block}
.lt{font-size:30px;line-height:30px;color:#dbe8ff;margin-top:-4px}
.x{font-size:16px;color:#fff}
.chk,.mchk{color:#fff;font-weight:700}
/* PIN */
.lockbadge{position:absolute;top:118px;left:50%;margin-left:-50px;width:100px;height:100px;border-radius:50%;display:grid;place-items:center;
  background:radial-gradient(circle,rgba(60,120,255,.5),rgba(10,20,46,.7));border:1.5px solid rgba(140,185,255,.6);box-shadow:0 0 30px rgba(47,107,255,.6)}
.pintitle{position:absolute;top:236px;left:0;right:0;text-align:center;font-size:27px;font-weight:700}
.dots{position:absolute;top:286px;left:0;right:0;display:flex;justify-content:center;gap:16px;transition:transform .05s}
.dots i{width:18px;height:18px;border-radius:50%;border:1.5px solid rgba(140,185,255,.6);background:rgba(10,20,46,.6);transition:transform .25s cubic-bezier(.3,1.8,.5,1),background .2s}
.dots i.f{background:radial-gradient(circle at 40% 35%,#eaf4ff,#3d7bff);border-color:#cfe0ff;box-shadow:0 0 10px #3d7bff;transform:scale(1.12)}
.dots.shake{animation:shake .35s}@keyframes shake{20%{transform:translateX(14px)}40%{transform:translateX(-12px)}60%{transform:translateX(8px)}80%{transform:translateX(-4px)}}
.pinhint{position:absolute;top:324px;left:0;right:0;display:flex;justify-content:center;gap:10px;font-size:13.5px;color:#c9d8f5;line-height:1.35;align-items:center}
.keys{position:absolute;top:392px;left:50%;margin-left:-142px;width:284px;display:grid;grid-template-columns:repeat(3,76px);gap:12px 28px}
.key{width:76px;height:76px;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;
  background:radial-gradient(circle at 50% 30%,rgba(34,60,120,.7),rgba(8,16,38,.85));border:1px solid rgba(140,185,255,.5);box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 0 12px rgba(40,100,255,.2)}
.key b{font-size:28px;font-weight:500;line-height:30px}.key small{font-size:9.5px;letter-spacing:1px;color:#b9c9e8;height:11px}
.forgot{position:absolute;top:790px;left:0;right:0;text-align:center;font-size:14px;color:#7fb2ff}
/* чаты */
.chathead{position:absolute;top:48px;left:17px;right:17px;display:flex;align-items:center;gap:10px;z-index:3}
.chathead h1{flex:1;font-size:30px;font-weight:700;margin-left:8px}
.circ.big{width:46px;height:46px;font-size:24px;color:#cfe0ff}
.codecard{top:118px;height:88px;display:flex;align-items:center;padding:0 12px;border-color:rgba(150,195,255,.75);box-shadow:0 0 24px rgba(40,100,255,.4)}
.ic2{width:50px;height:50px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle,rgba(60,120,255,.5),rgba(10,20,46,.6));border:1px solid rgba(140,185,255,.5)}
.cc{flex:1;margin-left:12px;min-width:0}.cc small{display:block;font-size:13px;color:#c9d8f5}.cc b{display:block;font-size:17px;font-weight:600;letter-spacing:.3px;white-space:nowrap}
.share{display:flex;align-items:center;gap:6px;height:34px;padding:0 12px;flex-shrink:0;border-radius:18px;font-size:13.5px;font-weight:600;
  background:linear-gradient(180deg,#4a86ff,#1d4fd8);border:1px solid rgba(190,215,255,.8);box-shadow:0 0 14px rgba(60,120,255,.6)}
.crow{height:80px;display:flex;align-items:center;padding:0 14px 0 12px;cursor:pointer}
.ava{width:54px;height:54px;border-radius:50%;display:grid;place-items:center;font-size:24px;font-weight:700;color:#cfe2ff;flex-shrink:0;
  background:radial-gradient(circle at 45% 35%,#3d7bff,#0e1a36);border:1.5px solid rgba(150,195,255,.7);box-shadow:0 0 14px rgba(47,107,255,.5)}
.ava.sm{width:44px;height:44px;font-size:20px}
.ct{flex:1;margin-left:14px;min-width:0}.ct b{display:block;font-size:16.5px;font-weight:600}.ct span{display:block;font-size:13.5px;color:#c9d8f5;margin-top:1px}
.ct small{display:flex;gap:6px;align-items:center;font-size:12px;color:#93a6cc;margin-top:3px}
.cr{display:flex;flex-direction:column;align-items:flex-end;gap:8px;align-self:flex-start;margin-top:14px}.cr em{font-style:normal;font-size:12.5px;color:#c9d8f5}
.unread{font-style:normal;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;background:#2f6bff;box-shadow:0 0 10px #3d7bff}
.tabs{top:774px;height:62px;display:flex;border-radius:22px}.tab{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:12px;color:#93a6cc}
.tab.on{color:#cfe2ff}
/* переписка */
.talkhead{position:absolute;top:44px;left:12px;right:12px;height:64px;display:flex;align-items:center;gap:10px;z-index:3;padding:0 6px;border-radius:22px;
  background:linear-gradient(180deg,rgba(14,28,62,.8),rgba(6,12,30,.6));border-bottom:1px solid rgba(110,160,255,.25)}
.th{flex:1}.th b{display:block;font-size:18px;font-weight:700}.th small{display:flex;gap:5px;align-items:center;font-size:12.5px;color:#c9d8f5}
.msgs{position:absolute;top:122px;left:14px;right:14px;bottom:86px;display:flex;flex-direction:column;gap:12px;overflow:auto;padding-bottom:6px}
.msg{max-width:72%;padding:11px 14px;border-radius:20px;font-size:15.5px;line-height:1.3;display:flex;gap:10px;align-items:flex-end;animation:pop .35s cubic-bezier(.3,1.5,.5,1)}
@keyframes pop{from{transform:scale(.85);opacity:0}to{transform:none;opacity:1}}
.msg em{font-style:normal;font-size:11px;color:rgba(230,240,255,.75);white-space:nowrap}
.msg.out{align-self:flex-end;border-bottom-right-radius:6px;background:linear-gradient(180deg,#3f7bff,#1c48c8);border:1px solid rgba(170,205,255,.7);box-shadow:0 0 14px rgba(47,107,255,.45)}
.msg.in{align-self:flex-start;border-bottom-left-radius:6px;background:linear-gradient(180deg,rgba(26,44,92,.85),rgba(10,20,44,.85));border:1px solid rgba(140,185,255,.45)}
.msg.photo{padding:6px;position:relative}.msg.photo img{width:200px;height:130px;object-fit:cover;border-radius:14px;display:block}
.msg.photo em{position:absolute;right:14px;bottom:12px;background:rgba(0,0,0,.55);padding:2px 7px;border-radius:9px}
.inputbar{position:absolute;left:12px;right:12px;bottom:22px;height:60px;display:flex;align-items:center;gap:8px;padding:0 5px;border-radius:28px;
  background:linear-gradient(180deg,rgba(14,28,62,.8),rgba(6,12,30,.8));border:1px solid rgba(110,160,255,.3)}
.inputbar input{flex:1;height:44px;border-radius:22px;border:1px solid rgba(140,185,255,.45);background:rgba(10,20,46,.6);color:#fff;padding:0 16px;font:inherit;font-size:15px;outline:0}
.sendb{width:50px;height:50px;border-radius:50%;display:grid;place-items:center;cursor:pointer;background:linear-gradient(180deg,#4a86ff,#1d4fd8);border:1px solid rgba(190,215,255,.85);box-shadow:0 0 18px rgba(60,120,255,.8)}
/* приветствие */
.wmark{position:absolute;top:78px;left:50%;margin-left:-90px;width:180px;height:150px}
.wmark .mk{position:absolute;left:38px;top:8px;width:104px;height:104px;filter:drop-shadow(0 0 14px rgba(60,120,255,.95)) drop-shadow(0 0 30px rgba(47,107,255,.6))}
.orbit2{position:absolute;left:-20px;top:22px;width:220px;height:120px;overflow:visible}.orbit2 ellipse{fill:none;stroke:#6fa8ff;stroke-width:4;filter:drop-shadow(0 0 6px #3d7bff)}
.wtitle{position:absolute;top:212px;left:0;right:0;text-align:center;font-size:44px;font-weight:700;background:linear-gradient(180deg,#fff,#9fc3ff);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 14px rgba(60,120,255,.6))}
.wtag{position:absolute;top:276px;left:0;right:0;text-align:center;font-size:16px;color:#9cc2ff}
.wglobe{position:absolute;top:300px;left:50%;margin-left:-160px;width:320px;height:320px;background:var(--earth) center/contain no-repeat;animation:breathe 6s ease-in-out infinite}
.feats{position:absolute;top:606px;left:20px;right:20px;display:flex;justify-content:space-between;align-items:flex-start}
.ft{width:104px;display:flex;flex-direction:column;align-items:center;gap:8px;font-size:14px;text-align:center;line-height:1.25}
.fsq{width:58px;height:58px;border-radius:18px;display:grid;place-items:center;background:radial-gradient(circle,rgba(60,120,255,.45),rgba(10,20,46,.7));border:1px solid rgba(140,185,255,.55);box-shadow:0 0 16px rgba(47,107,255,.4)}
.sep{width:1px;height:70px;background:rgba(140,185,255,.3);margin-top:6px}
.wbtn{position:absolute;top:704px;left:18px;right:18px;height:54px;border-radius:27px;display:flex;align-items:center;justify-content:center;gap:12px;font-size:18px;font-weight:600;cursor:pointer;
  background:linear-gradient(180deg,#4a86ff,#1d4fd8);border:1.5px solid rgba(200,225,255,.9);box-shadow:0 0 26px rgba(60,120,255,.8),inset 0 1px 0 rgba(255,255,255,.35)}
.wbtn span{font-size:26px;color:#cfe2ff}
.wbtn2{position:absolute;top:770px;left:18px;right:18px;height:50px;border-radius:25px;display:flex;align-items:center;justify-content:center;gap:12px;font-size:16px;cursor:pointer;
  background:rgba(10,20,46,.6);border:1px solid rgba(140,185,255,.55)}
.wfoot{position:absolute;top:832px;left:0;right:0;text-align:center;font-size:11.5px;color:#93a6cc}
'''

JS = r'''
// ---------- PIN ----------
let pinv='';
function dots(){document.querySelectorAll('#dots i').forEach((d,i)=>d.classList.toggle('f',i<pinv.length))}
document.querySelectorAll('.key').forEach(k=>k.onclick=()=>{const v=k.dataset.k;
  if(v==='del')pinv=pinv.slice(0,-1);else if(pinv.length<6)pinv+=v;dots();
  if(pinv.length===6){setTimeout(()=>{if(pinv==='000000'){const d=document.getElementById('dots');d.classList.remove('shake');void d.offsetWidth;d.classList.add('shake');pinv='';dots()}else{pinv='';dots();go('chats')}},250)}});
// ---------- переписка ----------
function send(){const i=document.getElementById('msgIn');const t=i.value.trim();if(!t)return;const m=document.createElement('div');m.className='msg out';
  const now=new Date();m.innerHTML=t.replace(/</g,'&lt;')+'<em>'+String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0')+' ✓</em>';
  const box=document.getElementById('msgs');box.appendChild(m);box.scrollTop=1e6;i.value=''}
document.getElementById('sendB').onclick=send;document.getElementById('msgIn').onkeydown=e=>{if(e.key==='Enter')send()};
'''
