"""Круг — самостоятельный Telegram-бот для групп. Python 3.12+."""
import html
import logging
import os
import random
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / '.env')
LOG = logging.getLogger('krug')

RP = {
    'hug': ('обнять', 'обнял(а)', '🤗'),
    'pat': ('погладить', 'погладил(а)', '🐾'),
    'handshake': ('пожать руку', 'пожимает руку', '🤝'),
    'highfive': ('дать пять', 'даёт пять', '🙌'),
    'tea': ('дать чай', 'угощает чаем', '☕'),
    'cookie': ('дать печенье', 'угощает печеньем', '🍪'),
    'flower': ('подарить цветок', 'подарил(а) цветок', '🌷'),
    'support': ('поддержать', 'поддерживает', '💛'),
    'poke': ('тыкнуть', 'легонько тыкает', '👉'),
    'bonk': ('стукнуть', 'стукнул(а)', '🛋'),
    'lofis': ('разложить', 'разложил(а) на столе', '🪑'),
    'castrate': ('кастрировать', 'кастрировал(а)', '✂️'),
    'hit': ('ударить', 'ударил', '👊'),
    'shlep': ('шлеп', 'шлепнул(а)',  '✋🏻'),
     'kiss': ('засосать', 'засосал(а)', '💋'),
     'spit': ('плюнуть', 'плюнул(а) в', '😗'),
     'murder': ('убить', 'убил(а)', '🔪'),
     'burn': ('сжечь', 'сжёг', '🔥'),
     'punch': ('пнуть', 'пнул(а)', '👟'),
}

ALIASES = {v[0]: k for k, v in RP.items()}

MARRIAGE_RP = {
    'поцеловать супруга': ('целует', '💋'),
    'обнять супруга': ('нежно обнимает', '💞'),
    'держать за руку': ('держит за руку', '🤝'),
    'сказать комплимент супругу': ('говорит комплимент', '🌹'),
}
MARRIAGE_RP_ALIASES = {
    'поцеловать супругу': 'поцеловать супруга',
    'обнять супругу': 'обнять супруга',
    'сказать комплимент супруге': 'сказать комплимент супругу',
}

RUSSIAN_COMMANDS = {
    'помощь', 'команды', 'что ты умеешь',
    'профиль', 'мой профиль',
    'топ', 'рейтинг', 'топ чата', 'рейтинг чата',
    'правила', 'правила чата',
    'монетка', 'орёл или решка', 'орел или решка',
    'бросить кубик', 'кубик', 'брось кубик',
    'репутация', 'дать репутацию', 'плюс репутация',
    'брак', 'принять брак', 'отклонить брак',
    'мой брак', 'браки', 'список браков', 'развод',
}

HELP = """🎭 <b>Круг — команды</b>

<b>РП — ответом на сообщение человека:</b>
/hug — обнять
/pat — погладить
/handshake — пожать руку
/highfive — дать пять
/tea — угостить чаем
/cookie — угостить печеньем
/flower — подарить цветок
/support — поддержать
/poke — тыкнуть
/bonk — шуточно стукнуть подушкой
/castrate — кастрировать
/lofis — разложить на столе
/hit — ударить
Можно писать названия РП по-русски, тоже ответом на сообщение.

<b>Браки:</b>
Ответьте командой «брак» на сообщение человека, чтобы предложить брак.
Адресат отвечает «принять брак» на сообщение с предложением.
«отклонить брак» — отклонить предложение.
«мой брак» — посмотреть свой статус.
«браки» — список пар в чате.
«развод» — завершить свой брак.

<b>РП для супругов:</b>
«поцеловать супруга», «обнять супруга»,
«держать за руку», «сказать комплимент супругу».
Используйте команду ответом на сообщение своего супруга или супруги.

<b>Общение и рейтинг:</b>
/profile — свой профиль; ответом — чужой
/top — топ-10 по опыту в чате
/rep — +1 к репутации ответом, одному участнику раз в сутки
/dice — кубик; /coin — монетка
/rp_off — запретить РП в свой адрес в этом чате
/rp_on — снова разрешить
/rules — правила чата

<b>Для администраторов:</b>
/setrules текст — записать правила
/welcome on или off — приветствия
/setwelcome текст — шаблон с {name} и {chat}
/settings — настройки чата
/rp on или off — включить или отключить РП
/warn [причина] — предупреждение ответом
/warnings — число предупреждений, ответом
/unwarn — снять предупреждения ответом
/mute 10 [причина] — запретить писать на 10 минут, ответом
/unmute — снять установленное ботом ограничение, ответом
/ban [причина] — заблокировать, ответом
/unban — разблокировать ответом на старое сообщение
/kick [причина] — удалить, но разрешить вернуться, ответом

Для ограничения участников нужны права бота. Опыт и настройки раздельные для каждого чата. /privacy — какие данные хранятся."""


def esc(value):
    return html.escape(str(value), quote=True)


def mention(user):
    return f'<a href="tg://user?id={user.id}">{esc(user.full_name)}</a>'


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            chat INTEGER PRIMARY KEY,
            rp INTEGER NOT NULL DEFAULT 1,
            welcome INTEGER NOT NULL DEFAULT 1,
            rules TEXT NOT NULL DEFAULT '',
            greeting TEXT NOT NULL DEFAULT 'Добро пожаловать, {name}! Вы в чате {chat}. Правила: /rules'
        );

        CREATE TABLE IF NOT EXISTS profiles (
            chat INTEGER NOT NULL,
            uid INTEGER NOT NULL,
            name TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            rep INTEGER NOT NULL DEFAULT 0,
            warns INTEGER NOT NULL DEFAULT 0,
            last_xp INTEGER NOT NULL DEFAULT 0,
            rp_allowed INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(chat, uid)
        );

        CREATE TABLE IF NOT EXISTS reputation (
            chat INTEGER NOT NULL,
            giver INTEGER NOT NULL,
            receiver INTEGER NOT NULL,
            day TEXT NOT NULL,
            PRIMARY KEY(chat, giver, receiver, day)
        );

        CREATE TABLE IF NOT EXISTS marriages (
            chat INTEGER NOT NULL,
            user1 INTEGER NOT NULL,
            user2 INTEGER NOT NULL,
            name1 TEXT NOT NULL,
            name2 TEXT NOT NULL,
            married_at TEXT NOT NULL,
            PRIMARY KEY(chat, user1),
            UNIQUE(chat, user2)
        );

        CREATE TABLE IF NOT EXISTS marriage_proposals (
            chat INTEGER NOT NULL,
            proposer INTEGER NOT NULL,
            target INTEGER NOT NULL,
            proposer_name TEXT NOT NULL,
            target_name TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(chat, proposer, target)
        );
        """)
        self.db.commit()

    def settings(self, chat):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO chats(chat) VALUES(?)', (chat,))
        return self.db.execute(
            'SELECT * FROM chats WHERE chat=?', (chat,)
        ).fetchone()

    def set(self, chat, key, value):
        if key not in {'rp', 'welcome', 'rules', 'greeting'}:
            raise ValueError('Unknown setting')
        self.settings(chat)
        with self.db:
            self.db.execute(
                f'UPDATE chats SET {key}=? WHERE chat=?', (value, chat)
            )

    def user(self, chat, uid, name):
        with self.db:
            self.db.execute(
                'INSERT INTO profiles(chat,uid,name) VALUES(?,?,?) '
                'ON CONFLICT(chat,uid) DO UPDATE SET name=excluded.name',
                (chat, uid, name),
            )
        return self.db.execute(
            'SELECT * FROM profiles WHERE chat=? AND uid=?', (chat, uid)
        ).fetchone()

    def get(self, chat, uid):
        return self.db.execute(
            'SELECT * FROM profiles WHERE chat=? AND uid=?', (chat, uid)
        ).fetchone()

    def activity(self, chat, uid, name, now):
        row = self.user(chat, uid, name)
        if now - row['last_xp'] >= 60:
            with self.db:
                self.db.execute(
                    'UPDATE profiles SET xp=xp+5,last_xp=? WHERE chat=? AND uid=?',
                    (now, chat, uid),
                )
            return True
        return False

    def allow_rp(self, chat, uid, value):
        with self.db:
            self.db.execute(
                'UPDATE profiles SET rp_allowed=? WHERE chat=? AND uid=?',
                (int(value), chat, uid),
            )

    def give_rep(self, chat, giver, receiver, day):
        with self.db:
            cursor = self.db.execute(
                'INSERT OR IGNORE INTO reputation VALUES(?,?,?,?)',
                (chat, giver, receiver, day),
            )
            if cursor.rowcount != 1:
                return False
            self.db.execute(
                'UPDATE profiles SET rep=rep+1 WHERE chat=? AND uid=?',
                (chat, receiver),
            )
            self.db.execute('DELETE FROM reputation WHERE day < ?', (day,))
        return True

    def warns(self, chat, uid, reset=False):
        with self.db:
            if reset:
                self.db.execute(
                    'UPDATE profiles SET warns=0 WHERE chat=? AND uid=?',
                    (chat, uid),
                )
            else:
                self.db.execute(
                    'UPDATE profiles SET warns=warns+1 WHERE chat=? AND uid=?',
                    (chat, uid),
                )
        return self.get(chat, uid)['warns']

    def top(self, chat):
        return self.db.execute(
            'SELECT * FROM profiles WHERE chat=? '
            'ORDER BY xp DESC, rep DESC, uid LIMIT 10',
            (chat,),
        ).fetchall()

    def marriage_for(self, chat, uid):
        return self.db.execute(
            'SELECT * FROM marriages WHERE chat=? AND (user1=? OR user2=?)',
            (chat, uid, uid),
        ).fetchone()

    def marriage_list(self, chat):
        return self.db.execute(
            'SELECT * FROM marriages WHERE chat=? ORDER BY married_at',
            (chat,),
        ).fetchall()

    def proposal(self, chat, proposer, target):
        return self.db.execute(
            'SELECT * FROM marriage_proposals '
            'WHERE chat=? AND proposer=? AND target=?',
            (chat, proposer, target),
        ).fetchone()

    def create_proposal(self, chat, proposer, target, proposer_name,
                        target_name, message_id, created_at):
        with self.db:
            self.db.execute(
                'INSERT OR REPLACE INTO marriage_proposals '
                '(chat, proposer, target, proposer_name, target_name, '
                'message_id, created_at) VALUES(?,?,?,?,?,?,?)',
                (chat, proposer, target, proposer_name, target_name,
                 message_id, created_at),
            )

    def delete_proposal(self, chat, proposer, target):
        with self.db:
            self.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND proposer=? AND target=?',
                (chat, proposer, target),
            )

    def accept_proposal(self, chat, proposer, target, married_at):
        with self.db:
            self.db.execute(
                'INSERT INTO marriages '
                '(chat,user1,user2,name1,name2,married_at) VALUES(?,?,?,?,?,?)',
                (chat, proposer, target, '', '', married_at),
            )
            self.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND proposer=? AND target=?',
                (chat, proposer, target),
            )

    def divorce(self, chat, uid):
        with self.db:
            cursor = self.db.execute(
                'DELETE FROM marriages WHERE chat=? AND (user1=? OR user2=?)',
                (chat, uid, uid),
            )
        return cursor.rowcount > 0


def db(context):
    return context.application.bot_data['store']


async def say(update, text, **kwargs):
    return await update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, **kwargs
    )


async def group_only(update):
    if update.effective_chat.type not in {'group', 'supergroup'}:
        await say(
            update,
            'Эта команда работает в группе. Добавьте меня в чат через /start.',
        )
        return False

    if update.effective_message.sender_chat or not update.effective_user:
        await say(
            update,
            'Отправьте команду от своего аккаунта, не от имени канала '
            'или анонимного администратора.',
        )
        return False
    return True


async def target_user(update):
    reply = update.effective_message.reply_to_message
    if not reply or not reply.from_user or reply.sender_chat:
        await say(
            update,
            'Отправьте команду <b>ответом на сообщение участника</b>, '
            'написанное от его аккаунта.',
        )
        return None
    if reply.from_user.is_bot:
        await say(update, 'Выберите участника-человека, не бота.')
        return None
    return reply.from_user


async def admin_allowed(update, context, restrict=False):
    if not await group_only(update):
        return False

    cid = update.effective_chat.id
    member = await context.bot.get_chat_member(cid, update.effective_user.id)
    if member.status not in {'creator', 'administrator'}:
        await say(update, 'Эта команда доступна только администраторам чата.')
        return False

    if restrict and member.status != 'creator' and not member.can_restrict_members:
        await say(update, 'У вас нет права ограничивать участников этого чата.')
        return False

    if restrict:
        me = await context.bot.get_chat_member(cid, context.bot.id)
        if me.status not in {'creator', 'administrator'} or (
            me.status != 'creator' and not me.can_restrict_members
        ):
            await say(
                update,
                'Назначьте бота администратором с правом '
                '«Блокировка участников».',
            )
            return False
    return True


async def safe_target(update, context):
    target = await target_user(update)
    if not target:
        return None

    if target.id == update.effective_user.id:
        await say(update, 'Нельзя применить эту команду к себе.')
        return None

    member = await context.bot.get_chat_member(
        update.effective_chat.id, target.id
    )
    if member.status in {'creator', 'administrator'}:
        await say(update, 'Эта команда не применяется к владельцу или администратору.')
        return None
    return target


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.bot.username
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            'Добавить в группу',
            url=f'https://t.me/{username}?startgroup=true',
        )
    ]])
    await say(
        update,
        '🎭 <b>Круг</b> — компаньон вашего чата. РП, профили, рейтинг, '
        'репутация, браки, приветствия и модерация.\n\n'
        'Добавьте меня в группу и откройте /help. Для РП отвечайте '
        'командой на сообщение участника.\n\n'
        'Это самостоятельный бот, не официальный Iris и не его копия.',
        reply_markup=keyboard,
    )


async def help_cmd(update, context):
    await say(update, HELP)


async def privacy(update, context):
    await say(
        update,
        '<b>Данные бота</b>\n'
        'В SQLite на компьютере владельца сохраняются ID чата и участников, '
        'отображаемое имя, опыт, репутация, предупреждения, согласие на РП, '
        'сведения о браках и настройки группы. Для ограничения начислений '
        'хранятся время последнего опыта и дневные записи репутации. '
        'Тексты переписки и причины модерации в базу не записываются.\n\n'
        '/rp_off отключает РП в ваш адрес в текущем чате. Для удаления '
        'данных обратитесь к оператору бота. Удаление всей базы при '
        'остановленном боте сбрасывает данные всех чатов.',
    )


async def roleplay(update, context, action):
    if not await group_only(update):
        return

    cid = update.effective_chat.id
    if not db(context).settings(cid)['rp']:
        await say(update, 'РП-команды в этом чате отключены администратором.')
        return

    target = await target_user(update)
    if not target:
        return

    actor = update.effective_user
    if actor.id == target.id:
        await say(update, 'Выберите другого участника.')
        return

    row = db(context).user(cid, target.id, target.full_name)
    if not row['rp_allowed']:
        await say(update, 'Этот участник отключил РП в свой адрес.')
        return

    _, verb, emoji = RP[action]
    await say(update, f'{emoji} {mention(actor)} {verb} → {mention(target)}')


async def marriage_roleplay(update, context, action):
    if not await group_only(update):
        return

    target = await target_user(update)
    if not target:
        return

    actor = update.effective_user
    if actor.id == target.id:
        await say(update, 'Выберите своего супруга или супругу.')
        return

    store = db(context)
    marriage = store.marriage_for(update.effective_chat.id, actor.id)
    if not marriage or target.id not in (marriage['user1'], marriage['user2']):
        await say(update, 'Эта РП-команда доступна только между супругами.')
        return

    target_profile = store.user(
        update.effective_chat.id, target.id, target.full_name
    )
    if not target_profile['rp_allowed']:
        await say(update, 'Этот участник отключил РП в свой адрес.')
        return

    verb, emoji = MARRIAGE_RP[action]
    await say(update, f'{emoji} {mention(actor)} {verb} → {mention(target)}')


async def marriage_command(update, context, action):
    if not await group_only(update):
        return

    store = db(context)
    chat_id = update.effective_chat.id
    actor = update.effective_user

    if action == 'propose':
        target = await target_user(update)
        if not target:
            return
        if target.id == actor.id:
            await say(update, 'Нельзя предложить брак самому себе.')
            return
        if store.marriage_for(chat_id, actor.id):
            await say(update, 'Вы уже состоите в браке в этом чате.')
            return
        if store.marriage_for(chat_id, target.id):
            await say(update, 'Этот участник уже состоит в браке в этом чате.')
            return

        proposal = store.proposal(chat_id, actor.id, target.id)
        if proposal:
            await say(update, 'Вы уже отправили этому участнику предложение.')
            return

        sent = await say(
            update,
            f'💍 {mention(actor)} предлагает вступить в брак с '
            f'{mention(target)}!\n'
            'Чтобы принять, ответьте «принять брак» на это сообщение. '
            'Чтобы отклонить — «отклонить брак».',
        )
        store.create_proposal(
            chat_id,
            actor.id,
            target.id,
            actor.full_name,
            target.full_name,
            sent.message_id,
            datetime.now(timezone.utc).isoformat(),
        )
        return

    if action in {'accept', 'reject'}:
        reply = update.effective_message.reply_to_message
        if not reply:
            await say(
                update,
                'Ответьте «принять брак» или «отклонить брак» '
                'на сообщение с предложением.',
            )
            return

        proposal = store.db.execute(
            'SELECT * FROM marriage_proposals '
            'WHERE chat=? AND target=? AND message_id=?',
            (chat_id, actor.id, reply.message_id),
        ).fetchone()

        if not proposal:
            await say(
                update,
                'Для вас не найдено предложение в этом сообщении. '
                'Ответить может только адресат предложения.',
            )
            return

        if action == 'reject':
            store.delete_proposal(chat_id, proposal['proposer'], actor.id)
            await say(update, 'Предложение отклонено.')
            return

        if store.marriage_for(chat_id, actor.id):
            store.delete_proposal(chat_id, proposal['proposer'], actor.id)
            await say(update, 'Вы уже состоите в браке в этом чате.')
            return
        if store.marriage_for(chat_id, proposal['proposer']):
            store.delete_proposal(chat_id, proposal['proposer'], actor.id)
            await say(update, 'Автор предложения уже состоит в браке.')
            return

        with store.db:
            store.db.execute(
                'INSERT INTO marriages '
                '(chat,user1,user2,name1,name2,married_at) '
                'VALUES(?,?,?,?,?,?)',
                (
                    chat_id,
                    proposal['proposer'],
                    actor.id,
                    proposal['proposer_name'],
                    actor.full_name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            store.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND proposer=? AND target=?',
                (chat_id, proposal['proposer'], actor.id),
            )
            store.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND (proposer=? OR target=?)',
                (chat_id, proposal['proposer'], proposal['proposer']),
            )
            store.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND (proposer=? OR target=?)',
                (chat_id, actor.id, actor.id),
            )

        await say(
            update,
            f'💍 Поздравляем! {mention(actor)} и '
            f'<a href="tg://user?id={proposal["proposer"]}">'
            f'{esc(proposal["proposer_name"])}</a> теперь супруги!',
        )
        return

    if action == 'my':
        marriage = store.marriage_for(chat_id, actor.id)
        if not marriage:
            await say(update, 'Вы пока не состоите в браке в этом чате.')
            return

        if actor.id == marriage['user1']:
            partner_id, partner_name = marriage['user2'], marriage['name2']
        else:
            partner_id, partner_name = marriage['user1'], marriage['name1']

        await say(
            update,
            '💍 Ваш супруг или супруга: '
            f'<a href="tg://user?id={partner_id}">{esc(partner_name)}</a>.',
        )
        return

    if action == 'list':
        marriages = store.marriage_list(chat_id)
        if not marriages:
            await say(update, 'В этом чате пока нет браков.')
            return

        lines = []
        for i, marriage in enumerate(marriages, 1):
            lines.append(
                f'{i}. <a href="tg://user?id={marriage["user1"]}">'
                f'{esc(marriage["name1"])}</a> 💞 '
                f'<a href="tg://user?id={marriage["user2"]}">'
                f'{esc(marriage["name2"])}</a>'
            )
        await say(update, '💍 <b>Браки в этом чате</b>\n' + '\n'.join(lines))
        return

    if action == 'divorce':
        if not store.divorce(chat_id, actor.id):
            await say(update, 'Вы не состоите в браке в этом чате.')
            return

        with store.db:
            store.db.execute(
                'DELETE FROM marriage_proposals '
                'WHERE chat=? AND (proposer=? OR target=?)',
                (chat_id, actor.id, actor.id),
            )
        await say(update, 'Брак расторгнут. Желаем вам всего хорошего.')
        return


async def rp_command(update, context):
    name = update.effective_message.text.split()[0][1:].split('@')[0].lower()
    await roleplay(update, context, name)


async def profile(update, context):
    if not await group_only(update):
        return

    if update.effective_message.reply_to_message:
        user = await target_user(update)
        if not user:
            return
    else:
        user = update.effective_user

    row = db(context).user(
        update.effective_chat.id, user.id, user.full_name
    )
    level, progress = divmod(row['xp'], 100)
    status = 'разрешены' if row['rp_allowed'] else 'отключены'

    await say(
        update,
        f'👤 <b>Профиль</b> {mention(user)}\n'
        f'Уровень: <b>{level + 1}</b>\n'
        f'Опыт: {row["xp"]} · до следующего уровня: {100 - progress}\n'
        f'Репутация: {row["rep"]}\n'
        f'Предупреждения: {row["warns"]}\n'
        f'РП в ваш адрес: {status}\n\n'
        'За обычное текстовое сообщение: +5 опыта, не чаще раза в минуту. '
        'Данные относятся только к этому чату.',
    )


async def top(update, context):
    if not await group_only(update):
        return

    rows = db(context).top(update.effective_chat.id)
    text = '\n'.join(
        f'{i}. {esc(row["name"])} — {row["xp"]} XP · '
        f'репутация {row["rep"]}'
        for i, row in enumerate(rows, 1)
    )
    await say(
        update,
        '🏆 <b>Топ этого чата</b>\n'
        + (text or 'Пока пусто. Пора начинать общение!'),
    )


async def reputation(update, context):
    if not await group_only(update):
        return

    target = await target_user(update)
    if not target:
        return

    if target.id == update.effective_user.id:
        await say(update, 'Самому себе повышать репутацию нельзя.')
        return

    cid = update.effective_chat.id
    db(context).user(cid, target.id, target.full_name)
    day = datetime.now(timezone.utc).date().isoformat()

    if not db(context).give_rep(
        cid, update.effective_user.id, target.id, day
    ):
        await say(
            update,
            'Сегодня вы уже повышали репутацию этому участнику. '
            'День обновляется в 00:00 UTC.',
        )
        return

    await say(
        update,
        f'⭐ {mention(target)} получает +1 к репутации '
        f'от {mention(update.effective_user)}!',
    )


async def rp_consent(update, context):
    if not await group_only(update):
        return

    user = update.effective_user
    cid = update.effective_chat.id
    db(context).user(cid, user.id, user.full_name)
    command = update.effective_message.text.split()[0].split('@')[0]
    enabled = command == '/rp_on'
    db(context).allow_rp(cid, user.id, enabled)

    await say(
        update,
        'РП в ваш адрес '
        + ('разрешены.' if enabled else 'отключены. Вернуть: /rp_on.'),
    )


async def dice(update, context):
    await update.effective_message.reply_dice(emoji='🎲')


async def coin(update, context):
    await say(update, '🪙 ' + random.choice(['Орёл!', 'Решка!']))


async def rules(update, context):
    if not await group_only(update):
        return

    text = db(context).settings(update.effective_chat.id)['rules']
    await say(
        update,
        '<b>Правила чата</b>\n'
        + (
            esc(text)
            if text
            else 'Администратор ещё не добавил правила. '
                 'Команда: /setrules текст'
        ),
    )


async def settings_command(update, context):
    if not await admin_allowed(update, context):
        return

    cid = update.effective_chat.id
    name = update.effective_message.text.split()[0][1:].split('@')[0].lower()
    text = ' '.join(context.args).strip()

    if name == 'settings':
        row = db(context).settings(cid)
        await say(
            update,
            '<b>Настройки чата</b>\n'
            f'РП: {"включены" if row["rp"] else "отключены"}\n'
            f'Приветствия: {"включены" if row["welcome"] else "отключены"}\n'
            f'Правила: {"записаны" if row["rules"] else "не заданы"}\n'
            f'Шаблон: {esc(row["greeting"])}',
        )
    elif name in {'rp', 'welcome'}:
        if text.lower() not in {'on', 'off'}:
            await say(update, f'Формат: /{name} on или /{name} off')
            return

        db(context).set(cid, name, int(text.lower() == 'on'))
        await say(update, 'Настройка сохранена.')
    else:
        limit = 2500 if name == 'setrules' else 1000
        if not text or len(text) > limit:
            await say(
                update,
                f'Формат: /{name} текст. Длина: от 1 до {limit} символов.',
            )
            return

        db(context).set(
            cid, 'rules' if name == 'setrules' else 'greeting', text
        )
        await say(update, 'Сохранено.')


async def moderation(update, context):
    if not await admin_allowed(update, context, restrict=True):
        return

    target = await safe_target(update, context)
    if not target:
        return

    cid = update.effective_chat.id
    action = update.effective_message.text.split()[0][1:].split('@')[0].lower()
    db(context).user(cid, target.id, target.full_name)
    reason = ' '.join(context.args).strip()

    if len(reason) > 500:
        await say(update, 'Причина слишком длинная: максимум 500 символов.')
        return

    if action == 'warnings':
        n = db(context).get(cid, target.id)['warns']
        await say(update, f'У {mention(target)} предупреждений: <b>{n}</b>.')
        return

    if action in {'warn', 'unwarn'}:
        n = db(context).warns(
            cid, target.id, reset=(action == 'unwarn')
        )
        result = f'Предупреждений у {mention(target)}: <b>{n}</b>.'

    elif action == 'mute':
        if update.effective_chat.type != 'supergroup':
            await say(
                update,
                'Индивидуальный мут работает в супергруппе. '
                'В обычной группе Telegram не поддерживает такое ограничение.',
            )
            return

        if not context.args or not re.fullmatch(r'[0-9]{1,5}', context.args[0]):
            await say(
                update,
                'Ответьте на сообщение: /mute 10 причина. '
                'Время — от 1 до 10080 минут.',
            )
            return

        minutes = int(context.args[0])
        if not 1 <= minutes <= 10080:
            await say(update, 'Допустимое время: 1–10080 минут.')
            return

        member = await context.bot.get_chat_member(cid, target.id)
        if member.status != 'member':
            await say(
                update,
                'Для мута выберите обычного участника без уже действующих '
                'индивидуальных ограничений.',
            )
            return

        from telegram import ChatPermissions

        perms = ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
        )
        await context.bot.restrict_chat_member(
            cid,
            target.id,
            permissions=perms,
            until_date=int(time.time()) + minutes * 60,
            use_independent_chat_permissions=True,
        )
        reason = ' '.join(context.args[1:])
        result = f'🔇 {mention(target)} не может писать {minutes} мин.'

    elif action == 'unmute':
        if update.effective_chat.type != 'supergroup':
            await say(update, 'Эта команда предназначена для супергрупп.')
            return

        chat = await context.bot.get_chat(cid)
        if not chat.permissions:
            await say(update, 'Не удалось прочитать общие разрешения чата.')
            return

        await context.bot.restrict_chat_member(
            cid,
            target.id,
            permissions=chat.permissions,
            use_independent_chat_permissions=True,
        )
        result = f'🔊 Для {mention(target)} восстановлены общие разрешения чата.'

    elif action in {'ban', 'kick'}:
        await context.bot.ban_chat_member(
            cid, target.id, revoke_messages=False
        )
        if action == 'kick':
            await context.bot.unban_chat_member(
                cid, target.id, only_if_banned=True
            )
        result = (
            f'⛔ {mention(target)} '
            + (
                'удалён из чата, но может вернуться.'
                if action == 'kick'
                else 'заблокирован.'
            )
        )

    else:
        await context.bot.unban_chat_member(
            cid, target.id, only_if_banned=True
        )
        result = (
            f'С {mention(target)} снята блокировка, если она была. '
            'Участник может вернуться по приглашению.'
        )

    if reason and action not in {'unmute', 'unban', 'unwarn'}:
        result += '\nПричина: ' + esc(reason)

    await say(update, result)


async def greeting(update, context):
    message = update.effective_message
    if not db(context).settings(message.chat_id)['welcome']:
        return

    template = db(context).settings(message.chat_id)['greeting']
    people = [user for user in message.new_chat_members if not user.is_bot]

    for user in people[:5]:
        text = (
            esc(template)
            .replace('{name}', mention(user))
            .replace(
                '{chat}',
                esc(update.effective_chat.title or 'группа'),
            )
        )
        await say(update, text)


async def text_message(update, context):
    if update.effective_chat.type not in {'group', 'supergroup'}:
        return

    msg = update.effective_message
    user = update.effective_user
    if not user or user.is_bot or msg.sender_chat or not msg.text:
        return

    text = ' '.join(msg.text.lower().strip().split())

    if text in {'помощь', 'команды', 'что ты умеешь'}:
        await help_cmd(update, context)
        return

    if text in {'профиль', 'мой профиль'}:
        await profile(update, context)
        return

    if text in {'топ', 'рейтинг', 'топ чата', 'рейтинг чата'}:
        await top(update, context)
        return

    if text in {'правила', 'правила чата'}:
        await rules(update, context)
        return

    if text in {'монетка', 'орёл или решка', 'орел или решка'}:
        await coin(update, context)
        return

    if text in {'бросить кубик', 'кубик', 'брось кубик'}:
        await dice(update, context)
        return

    if text in {'репутация', 'дать репутацию', 'плюс репутация'}:
        await reputation(update, context)
        return

    if text == 'брак':
        await marriage_command(update, context, 'propose')
        return

    if text == 'принять брак':
        await marriage_command(update, context, 'accept')
        return

    if text == 'отклонить брак':
        await marriage_command(update, context, 'reject')
        return

    if text == 'мой брак':
        await marriage_command(update, context, 'my')
        return

    if text in {'браки', 'список браков'}:
        await marriage_command(update, context, 'list')
        return

    if text == 'развод':
        await marriage_command(update, context, 'divorce')
        return

    marriage_action = MARRIAGE_RP_ALIASES.get(text, text)
    if marriage_action in MARRIAGE_RP:
        await marriage_roleplay(update, context, marriage_action)
        return

    action = ALIASES.get(text)
    if action:
        await roleplay(update, context, action)
        return

    if re.match(r'^круг(?:$|[\s,!.?])', text):
        await say(
            update,
            random.choice([
                f'Привет, {esc(user.first_name)}! 😊',
                'Я здесь! Чем помочь? Напиши «помощь» или /help.',
                'На связи 🎭 Могу показать профиль, рейтинг или правила.',
                'Привет! Напиши «команды», чтобы посмотреть, что я умею.',
            ]),
        )
        return

    db(context).activity(
        update.effective_chat.id,
        user.id,
        user.full_name,
        int(time.time()),
    )


async def migrated(update, context):
    msg = update.effective_message
    old = msg.migrate_from_chat_id or msg.chat_id
    new = msg.migrate_to_chat_id or msg.chat_id
    store = db(context)

    with store.db:
        for table in (
            'chats', 'profiles', 'reputation',
            'marriages', 'marriage_proposals',
        ):
            store.db.execute(
                f'UPDATE OR IGNORE {table} SET chat=? WHERE chat=?',
                (new, old),
            )
            store.db.execute(
                f'DELETE FROM {table} WHERE chat=?', (old,)
            )


async def rate_gate(update, context):
    from telegram.ext import ApplicationHandlerStop

    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or user.is_bot or not msg.text:
        return

    is_command = msg.text.startswith('/')
    normalized = ' '.join(msg.text.lower().split())
    is_rp = normalized in ALIASES or normalized in MARRIAGE_RP
    is_marriage_rp_alias = normalized in MARRIAGE_RP_ALIASES

    if not (
        is_command
        or is_rp
        or is_marriage_rp_alias
        or normalized in RUSSIAN_COMMANDS
    ):
        return

    limits = context.bot_data.setdefault('rate_limits', {})
    now = time.monotonic()

    if len(limits) > 10000:
        for key, stamp in list(limits.items()):
            if now - stamp > 60:
                limits.pop(key, None)

    key = (update.effective_chat.id, user.id)
    if now - limits.get(key, -100) < 2:
        raise ApplicationHandlerStop

    limits[key] = now


async def error_handler(update, context):
    LOG.error('Update failed: %s', type(context.error).__name__)

    if update and update.effective_message:
        try:
            await say(
                update,
                'Не удалось выполнить действие. Проверьте права бота '
                'и формат команды. Если бот запущен дважды, оставьте '
                'только один процесс.',
            )
        except TelegramError:
            pass


async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand('help', 'Команды бота'),
        BotCommand('profile', 'Профиль участника'),
        BotCommand('hug', 'Обнять — ответом'),
        BotCommand('top', 'Рейтинг чата'),
        BotCommand('rules', 'Правила чата'),
        BotCommand('privacy', 'Данные и приватность'),
    ])
    print('Круг запущен. Для остановки нажмите Ctrl+C.', flush=True)


def main():
    token = os.getenv('BOT_TOKEN', '').strip()
    if not re.fullmatch(r'\d{5,}:[A-Za-z0-9_-]{20,}', token):
        raise SystemExit(
            'В файле .env укажите BOT_TOKEN — токен, выданный @BotFather.'
        )

    logging.basicConfig(
        level=logging.WARNING,
        format='%(levelname)s: %(name)s: %(message)s',
    )
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    logging.getLogger('httpcore').setLevel(logging.CRITICAL)

    data_dir = BASE / 'data'
    data_dir.mkdir(exist_ok=True)
    store = Store(data_dir / 'krug.sqlite3')

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .concurrent_updates(False)
        .build()
    )
    app.bot_data['store'] = store

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.UpdateType.EDITED_MESSAGE,
            rate_gate,
        ),
        group=-1,
    )

    commands = {
        'start': start,
        'help': help_cmd,
        'privacy': privacy,
        'profile': profile,
        'top': top,
        'rep': reputation,
        'rp_on': rp_consent,
        'rp_off': rp_consent,
        'dice': dice,
        'coin': coin,
        'rules': rules,
    }
    commands.update({name: rp_command for name in RP})
    commands.update({
        name: settings_command
        for name in ('settings', 'setrules', 'setwelcome', 'welcome', 'rp')
    })
    commands.update({
        name: moderation
        for name in (
            'warn', 'unwarn', 'warnings', 'mute', 'unmute',
            'ban', 'unban', 'kick',
        )
    })

    for name, callback in commands.items():
        app.add_handler(
            CommandHandler(
                name,
                callback,
                filters=~filters.UpdateType.EDITED_MESSAGE,
            )
        )

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greeting)
    )
    app.add_handler(
        MessageHandler(filters.StatusUpdate.MIGRATE, migrated)
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND
            & ~filters.UpdateType.EDITED_MESSAGE,
            text_message,
        )
    )
    app.add_error_handler(error_handler)

    try:
        app.run_polling(
            allowed_updates=['message'],
            drop_pending_updates=False,
        )
    except TelegramError as error:
        print(
            'Ошибка Telegram: '
            + type(error).__name__
            + '. Проверьте токен, интернет и отсутствие второго '
              'запущенного экземпляра.',
            flush=True,
        )
    finally:
        store.db.close()


if __name__ == '__main__':
    main()