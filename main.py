from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
import logging
import uuid
import random
import csv
import os
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# --- Хранение данных (в памяти) ---
users = {}  # {user_id: {'name': '...', 'groups': {group_id: True, ...}}}
groups = {} # {group_id: {'name': '...', 'admin_id': ..., 'rake': ..., 'invite_code': '...', 'members': [user_id1, user_id2, ...]}}
group_members = {} # {(user_id, group_id): {'cash': ..., 'debt': ...}}


# --- Загрузка списка русских слов ---
try:
    with open('russian_words.txt', 'r', encoding='utf-8') as f:
        russian_words = [word.strip() for word in f.readlines()]
except FileNotFoundError:
    russian_words = ["слово", "дело", "игра", "покер", "ставка"] # Запасной список

# --- Функция для генерации случайного кода из русских слов ---
# --- Загрузка слов для генерации кода ---
try:
    with open('russian_words.txt.txt', 'r', encoding='utf-8') as f:
        word_list = [word.strip() for word in f.readlines()]
except FileNotFoundError:
    word_list = ["слово", "дело", "игра", "покер", "ставка"]

def generate_invite_code_russian(num_words=5):
    return '-'.join(random.choice(word_list) for _ in range(num_words))


# --- Обработчики команд ---

async def start(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Привет! Зарегистрируйся командой /register <имя>")

async def help_command(update: Update, context: CallbackContext):
    help_text = """
Вот список команд, которые я понимаю:

/register <имя> — Зарегистрировать свой профиль. Пример: /register Вася

/create_group <название> <рейк_в_процентах> — Создать новую группу игроков. Пример: /create_group НашПокер 5 (рейк 5%)

/join <айди_группы_или_код> — Присоединиться к группе по ID или коду из 5 слов. Пример: /join a1b2c3d4 или /join слово-дело-игра-покер-ставка

/buy_in <имя игрока> <долг/кэш> <сумма> — Админ добавляет игроку фишки за долг или кэш. Пример: /buy_in Вася кэш 1000

/buy_out <имя игрока> <сумма> — Админ списывает у игрока фишки и рассчитывает кэш, долг и рейк. Пример: /buy_out Вася 5000

/match_debts — Распределить долги между игроками и группой.

/balance — Посмотреть свой баланс (кэш, долг, фишки) по всем группам.

/group_balance — Баланс группы (для админа): кэш, долги, фишки, рейк.

/end_game — Завершить игру: обнулить балансы группы и игроков.

/who — Информация о вас: имя, ID, группы.

/help — Показать эту справку.
/admin_info - руководство для администратора

    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)
async def player_info(update: Update, context: CallbackContext):
    help_text = """
🎮 Руководство для игрока:
Зарегистрироваться:

/register <имя>

Пример: /register Вася

Присоединиться к группе:

/join <код группы или ID>

Пример: /join слово-дело-игра-покер-ставка

Проверить свои балансы:

/balance

Показывает твой кэш, долг и фишки по каждой группе.

Узнать о себе:

/who

Показывает твой ID и группы, в которых ты участвуешь.

Получать уведомления:

Когда админ добавляет/забирает фишки или перераспределяет долги, ты получаешь личные сообщения с подробностями.

    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)
async def admin_info(update: Update, context: CallbackContext):
    help_text = """
📋 Руководство для администратора группы:
Зарегистрироваться:

/register <имя>

Пример: /register Андрей

Создать группу:

/create_group <название> <рейк_в_процентах>

Пример: /create_group НашПокер 5

Получить код для присоединения:

Код показывается после создания группы.

Пример: слово-дело-игра-покер-ставка

Добавить фишки игроку:

/buy_in <имя игрока> <долг/кэш> <сумма>

Пример: /buy_in Вася кэш 1000

Забрать фишки у игрока (buy-out):

/buy_out <имя игрока> <сумма>

Пример: /buy_out Вася 5000

Закрыть игру:

/end_game

Обнуляет все балансы группы и игроков.

Показать баланс группы:

/group_balance

Показывает кэш, долги, фишки, рейк и участников.

Распределить долги между игроками:

/match_debts

Автоматически находит, кто кому должен, и упрощает взаиморасчёты.

    """
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text)

import random


async def register(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    name_parts = context.args
    if name_parts:
        name = ' '.join(name_parts)
        users[user_id] = {'name': name, 'groups': {}}  # <-- вот сюда добавляем
        await _save_players_to_file()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Зарегистрированы как {name}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Пожалуйста, укажите имя после команды /register.")


def load_players():
    if os.path.exists('players.csv'):
        with open('players.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 6:
                    user_id = int(row[0])
                    name = row[1]
                    group_id = row[2]
                    cash = float(row[3]) if row[3] else 0.0
                    debt = float(row[4]) if row[4] else 0.0
                    chips = float(row[5]) if row[5] else 0.0

                    if user_id not in users:
                        users[user_id] = {'name': name, 'groups': {}}

                    if group_id:
                        users[user_id]['groups'][group_id] = True
                        group_members[(user_id, group_id)] = {'cash': cash, 'debt': debt, 'chips': chips}

        print("Данные игроков загружены.")



async def create_group(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    print(f"CREATE_GROUP: Пользователь {user_id} вызвал команду /create_group с аргументами: {context.args}")
    if user_id not in users:
        print(f"CREATE_GROUP: Пользователь {user_id} не зарегистрирован.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала зарегистрируйтесь командой /register <имя>, прежде чем создавать группу.")
        return

    if len(context.args) < 2:
        print(f"CREATE_GROUP: Пользователь {user_id} ввел недостаточно аргументов: {context.args}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Используйте: /create_group <название> <рейк>")
        return
    group_name = context.args[0]
    rake_str = context.args[1]
    print(f"CREATE_GROUP: Название группы: '{group_name}', Рейк (строка): '{rake_str}'")
    try:
        rake = float(rake_str)
        if not 0 <= rake <= 100:
            print(f"CREATE_GROUP: Некорректный рейк: {rake}")
            raise ValueError
        rake /= 100
        print(f"CREATE_GROUP: Рейк (число): {rake}")
    except ValueError:
        print(f"CREATE_GROUP: Ошибка преобразования или некорректный формат рейка: '{rake_str}'")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Рейк должен быть числом от 0 до 100.")
        return

    group_id = str(uuid.uuid4())
    invite_code = generate_invite_code_russian()
    admin_id = update.effective_user.id
    groups[group_id] = {'name': group_name, 'admin_id': admin_id, 'rake': rake, 'invite_code': invite_code, 'members': [admin_id], 'total_rake': 0, 'group_cash': 0, 'group_debt': 0}# Инициализируем total_rake и group_cash
    print(f"CREATE_GROUP: Группа '{group_name}' (ID: {group_id}) успешно создана. Админ: {admin_id}, Код: {invite_code}")
    if admin_id in users:
        if 'groups' not in users[admin_id]:
            users[admin_id]['groups'] = {}
        users[admin_id]['groups'][group_id] = True
        await _save_players_to_file() # Перезаписываем весь файл
        print(f"CREATE_GROUP: Информация о членстве пользователя {admin_id} в группе {group_id} обновлена.")
    groups[group_id] = {
        'name': group_name,
        'admin_id': admin_id,
        'rake': rake,
        'invite_code': invite_code,
        'members': [admin_id],
        'cash': 0,  # <-- добавь это
        'debt': 0,  # <-- и это
        'chips': 0,  # <-- и это
        'total_rake': 0  # <-- и это
    }
    group_members[(admin_id, group_id)] = {'cash': 0, 'debt': 0, 'chips': 0}
    await save_groups()  # Сохраняем информацию о созданной группе
    await _save_players_to_file()
    print(f"CREATE_GROUP: Информация о группе {group_id} сохранена в groups.csv")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Группа '{group_name}' создана! ID: {group_id}, Код для присоединения: {invite_code}")

async def _update_player_file(user_id):
    with open('players.csv', 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    with open('players.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            uid = int(row[0])
            if uid == user_id:
                writer.writerow([uid, users[uid]['name'], json.dumps(users[uid].get('groups', {}))])
            else:
                writer.writerow(row)
async def join_group(update: Update, context: CallbackContext):
    print(f"join_group вызвана с аргументами: {context.args}")

    user_id = update.effective_user.id
    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Укажите ID группы или код для присоединения.")
        return

    group_identifier = context.args[0]

    if user_id not in users:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала зарегистрируйтесь командой /register <имя>")
        return

    found_group_id = None
    if group_identifier in groups:
        found_group_id = group_identifier
    else:
        print(f"Пытаюсь найти группу по коду: '{group_identifier}'")
        for gid, ginfo in groups.items():
            print(f"Сравниваю с кодом в группе: '{ginfo['invite_code']}'")
            if ginfo['invite_code'] == group_identifier:
                found_group_id = gid
                break

    if found_group_id:
        print('группа найдена')
        if (user_id, found_group_id) in group_members:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы уже в этой группе.")
            return

        # Добавляем в память
        group_members[(user_id, found_group_id)] = {'cash': 0, 'debt': 0, 'chips': 0}
        if 'groups' not in users[user_id]:
            users[user_id]['groups'] = {}
        users[user_id]['groups'][found_group_id] = True
        groups[found_group_id].setdefault('members', []).append(user_id)

        # Сохраняем
        await _save_players_to_file()
        await save_groups()

        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Вы присоединились к группе '{groups[found_group_id]['name']}'. Баланс: Кэш: 0, Долг: 0, Фишки: 0")

        admin_id = groups[found_group_id]['admin_id']
        try:
            await context.bot.send_message(chat_id=admin_id, text=f"{users[user_id]['name']} присоединился к группе '{groups[found_group_id]['name']}'.")
        except Exception as e:
            print(f"Ошибка уведомления админа: {e}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Группа с ID или кодом '{group_identifier}' не найдена.")


async def _save_players_to_file():
    with open('players.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['player_id', 'player_name', 'group_id', 'cash', 'debt', 'chips'])
        for uid, uinfo in users.items():
            user_groups = [gid for gid in uinfo.get('groups', {})]
            if not user_groups:
                writer.writerow([uid, uinfo['name'], '', 0, 0, 0])
            else:
                for gid in user_groups:
                    pinfo = group_members.get((uid, gid), {'cash': 0, 'debt': 0, 'chips': 0})
                    writer.writerow([uid, uinfo['name'], gid, pinfo['cash'], pinfo['debt'], pinfo['chips']])
    print("Файл players.csv обновлён.")



async def _save_players_to_file():
    with open('players.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['player_id', 'player_name', 'group_id', 'cash', 'debt', 'chips'])

        # Сначала пишем всех, кто в группах
        for (uid, gid), pinfo in group_members.items():
            writer.writerow([uid, users[uid]['name'], gid, pinfo['cash'], pinfo['debt'], pinfo['chips']])

        # Теперь всех, кто ЗАРЕГАН, но ещё НИ В ОДНОЙ группе
        written_users = {uid for (uid, _) in group_members.keys()}
        for uid, uinfo in users.items():
            if uid not in written_users:
                writer.writerow([uid, uinfo['name'], '', 0, 0, 0])

    print("Файл players.csv обновлен.")








async def buy_in(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id
    group_id = next((gid for gid, g in groups.items() if g['admin_id'] == admin_id), None)

    if not group_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не администратор группы.")
        return

    if len(context.args) != 3:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Используйте: /buy_in <имя игрока> <долг/кэш> <сумма>")
        return

    player_name, payment_type, amount_str = context.args
    try:
        amount = int(amount_str)
        if amount <= 0 or payment_type.lower() not in ['долг', 'кэш']:
            raise ValueError
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Некорректные параметры.")
        return

    player_name_lower = player_name.lower()
    player_user_id = next((uid for uid, u in users.items() if u['name'].lower() == player_name_lower), None)
    if not player_user_id or (player_user_id, group_id) not in group_members:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Игрок не найден в группе.")
        return

    player_info = group_members[(player_user_id, group_id)]
    group_info = groups[group_id]

    # --- Обновляем фишки ---
    player_info['chips'] += amount
    group_info['chips'] -= amount

    if payment_type.lower() == 'кэш':
        player_info['cash'] -= amount
        group_info['cash'] += amount
    else:
        player_info['debt'] -= amount
        group_info['debt'] += amount

    await _save_players_to_file()
    await save_groups()

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{amount} добавлено как '{payment_type}' игроку '{player_name}'.")

    # --- Сообщение игроку ---
    await context.bot.send_message(chat_id=player_user_id,
                                   text=f"Вам зачислено {amount} фишек как '{payment_type}'.\n"
                                        f"Текущий баланс:\n"
                                        f"- Кэш: {player_info['cash']}\n"
                                        f"- Долг: {player_info['debt']}\n"
                                        f"- Фишки: {player_info['chips']}")



async def end_game(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id
    group_id = next((gid for gid, g in groups.items() if g['admin_id'] == admin_id), None)

    if not group_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не администратор ни одной группы.")
        return

    group_info = groups[group_id]
    total_rake = group_info.get('total_rake', 0)

    # Обнуляем балансы группы
    group_info['cash'] = 0
    group_info['debt'] = 0
    group_info['chips'] = 0
    group_info['total_rake'] = 0

    # Обнуляем балансы всех игроков в этой группе
    for (uid, gid), member_info in list(group_members.items()):
        if gid == group_id:
            member_info['cash'] = 0
            member_info['debt'] = 0
            member_info['chips'] = 0

    await save_groups()
    await _save_players_to_file()

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Игра в группе '{group_info['name']}' завершена.\nИтоговый рейк сессии: {total_rake}.\nВсе балансы группы и игроков обнулены.")

async def balance(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_name = users.get(user_id, {}).get('name', 'Неизвестный')

    if not any((user_id, gid) in group_members for gid in groups):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не состоите ни в одной группе.")
        return

    balance_text = f"Баланс игрока {user_name}:\n"

    for (uid, gid), member_info in group_members.items():
        if uid == user_id:
            group_name = groups.get(gid, {}).get('name', 'Неизвестная группа')
            cash = member_info.get('cash', 0)
            debt = member_info.get('debt', 0)
            chips = member_info.get('chips', 0)

            balance_text += f"\nГруппа: '{group_name}'\n"
            balance_text += f"- Кэш: {cash}\n"
            balance_text += f"- Долг: {debt}\n"
            balance_text += f"- Фишки: {chips}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=balance_text)


async def who_am_i(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_info = users.get(user_id)

    if user_info:
        name = user_info['name']
        groups_info = user_info.get('groups', {})
        group_names = []
        for group_id in groups_info:
            group = groups.get(group_id)
            if group:
                group_names.append(f"{group['name']} (ID: {group_id})")

        groups_str = ", ".join(group_names) if group_names else "нет"

        message = f"Ваша информация:\n"
        message += f"- Зарегистрированы: Да\n"
        message += f"- Имя: {name}\n"
        message += f"- Ваш ID: {user_id}\n"
        message += f"- Вы состоите в группах: {groups_str}"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не зарегистрированы. Используйте команду /register <имя>.")


async def group_balance(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    my_groups_balance = ""
    found_group = False

    for group_id, group_info in groups.items():
        if group_info['admin_id'] == user_id:
            found_group = True
            cash = group_info.get('cash', 0)
            debt = group_info.get('debt', 0)
            chips = group_info.get('chips', 0)
            total_rake = group_info.get('total_rake', 0)
            rake_percentage = group_info.get('rake', 0) * 100

            net_balance = cash + debt + chips  # Активы - Пассивы, т.к. chips - это пассив

            # --- Получаем список игроков из group_members ---
            player_names = []
            for (uid, gid), member_info in group_members.items():
                if gid == group_id:
                    player_names.append(users[uid]['name'])
            players_str = ", ".join(player_names) if player_names else "нет"

            my_groups_balance += f"Группа '{group_info['name']}':\n"
            my_groups_balance += f"- Кэш группы: {cash}\n"
            my_groups_balance += f"- Долговые обязательства группы (актив): {debt}\n"
            my_groups_balance += f"- Фишки на руках у игроков (пассив): {chips}\n"
            my_groups_balance += f"- Накопленный рейк: {total_rake}\n"
            my_groups_balance += f"- Чистый баланс группы: {net_balance:.2f} (рейк: {rake_percentage}%)\n"
            my_groups_balance += f"- Игроки в группе: {players_str}\n\n"

    if found_group:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Баланс ваших групп:\n{my_groups_balance}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не являетесь администратором ни одной группы.")



async def save_groups():
    with open('groups.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['group_id', 'name', 'admin_id', 'rake', 'cash', 'debt', 'chips', 'total_rake', 'invite_code'])
        for gid, ginfo in groups.items():
            writer.writerow([gid, ginfo['name'], ginfo['admin_id'], ginfo['rake'], ginfo['cash'], ginfo['debt'], ginfo['chips'], ginfo['total_rake'], ginfo['invite_code']])
    print("Данные групп сохранены.")


def load_groups():
    if os.path.exists('groups.csv'):
        with open('groups.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Пропустить заголовок
            for row in reader:
                if len(row) >= 9:
                    group_id = row[0]
                    name = row[1]
                    admin_id = int(row[2])
                    rake = float(row[3])
                    cash = float(row[4])
                    debt = float(row[5])
                    chips = float(row[6])
                    total_rake = float(row[7])
                    invite_code = row[8].strip()

                    groups[group_id] = {
                        'name': name,
                        'admin_id': admin_id,
                        'rake': rake,
                        'cash': cash,
                        'debt': debt,
                        'chips': chips,
                        'total_rake': total_rake,
                        'invite_code': invite_code
                    }

        print("Данные групп загружены.")


async def post_init(app):
    load_groups()
    load_players()
    print("Данные групп загружены.")

async def buy_out(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id
    group_id = next((gid for gid, g in groups.items() if g['admin_id'] == admin_id), None)

    if not group_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не администратор группы.")
        return

    if len(context.args) != 2:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Используйте: /buy_out <имя игрока> <сумма>")
        return

    player_name, amount_str = context.args
    try:
        amount = int(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сумма должна быть положительным числом.")
        return

    player_name_lower = player_name.lower()
    player_user_id = next(
        (uid for uid, u in users.items() if u['name'].lower() == player_name_lower and group_id in u['groups']), None)

    if not player_user_id or (player_user_id, group_id) not in group_members:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Игрок не найден в группе.")
        return

    player_info = group_members[(player_user_id, group_id)]
    group_info = groups[group_id]

    # 1. Списываем фишки
    player_info['chips'] -= amount
    group_info['chips'] += amount

    # 2. Рейк
    rake_amount = int(amount * group_info['rake'])
    group_info['total_rake'] += rake_amount
    payout = amount  # Вся сумма включающая рейк, cash и debt

    # 3. Расчёт выплат
    payout_after_rake = payout - rake_amount
    payout_remaining = payout_after_rake

    # 4. Закрытие cash игрока
    cash_to_close = min(payout_remaining, -player_info['cash'])
    player_info['cash'] += cash_to_close
    group_info['cash'] -= cash_to_close
    payout_remaining -= cash_to_close

    # 5. Закрытие debt игрока
    debt_to_close = min(payout_remaining, -player_info['debt'])
    player_info['debt'] += debt_to_close
    group_info['debt'] -= debt_to_close
    payout_remaining -= debt_to_close

    # 6. Остаток — если остался — это прибыль игрока
    # --- 5. Остаток как прибыль ---
    cash_profit = 0
    debt_added = 0  # Новое поле: долг, который добавим, если не хватает кэша

    if payout_remaining > 0:
        if group_info['cash'] >= payout_remaining:
            cash_profit = payout_remaining
            player_info['cash'] += cash_profit
            group_info['cash'] -= cash_profit
        else:
            cash_profit = group_info['cash']
            player_info['cash'] += cash_profit
            payout_remaining -= cash_profit
            group_info['cash'] = 0

            # Оставшееся — в долг
            debt_added = payout_remaining
            player_info['debt'] += debt_added
            group_info['debt'] += debt_added


    await _save_players_to_file()
    await save_groups()

    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=f"Buy-out '{player_name}' на {amount} фишек.\n"
                                        f"Рейк: {rake_amount}, Закрытие cash: {cash_to_close}, Закрытие debt: {debt_to_close}, Профит: {payout_remaining}.\n"
                                        f"Баланс игрока: Cash: {player_info['cash']}, Debt: {player_info['debt']}, Chips: {player_info['chips']}.\n"
                                        f"Баланс группы: Cash: {group_info['cash']}, Debt: {group_info['debt']}, Chips: {group_info['chips']}, Rake: {group_info['total_rake']}.")
    debt_now = player_info['debt']
    if debt_now < 0:
        debt_msg = f"Вы должны группе {-debt_now} долга."
    elif debt_now > 0:
        debt_msg = f"Группа должна вам {debt_now} долга."
    else:
        debt_msg = "Вы ничего не должны."

    await context.bot.send_message(chat_id=player_user_id,
                                   text=f"Вы отдали {amount} фишек.\n"
                                        f"Вы получили {cash_to_close + cash_profit} кэша.\n"
                                        f"У вас было списано {debt_to_close} долга.\n"
                                        f"{debt_msg}")

async def match_debts(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id
    group_id = next((gid for gid, g in groups.items() if g['admin_id'] == admin_id), None)

    if not group_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы не администратор группы.")
        return

    group_info = groups[group_id]
    group_debt = group_info['debt']

    # Собираем должников и кредиторов
    debtors = []
    creditors = []

    for (uid, gid), pinfo in group_members.items():
        if gid == group_id:
            debt = pinfo['debt']
            if debt < 0:
                debtors.append({'id': uid, 'name': users[uid]['name'], 'amount': -debt})
            elif debt > 0:
                creditors.append({'id': uid, 'name': users[uid]['name'], 'amount': debt})

    matches = []
    player_messages = {}

    # Перераспределение долгов: группа должна игроку, а кто-то должен группе
    for creditor in creditors:
        if group_debt < creditor['amount']:
            credit_to_cover = group_debt
        else:
            credit_to_cover = creditor['amount']

        if credit_to_cover > 0:
            for debtor in debtors:
                if debtor['amount'] == 0:
                    continue

                pay_amount = min(credit_to_cover, debtor['amount'])

                if pay_amount > 0:
                    # Обновляем балансы
                    debtor['amount'] -= pay_amount
                    credit_to_cover -= pay_amount
                    group_debt -= pay_amount

                    # Записываем сделку
                    matches.append(f"{debtor['name']} должен {creditor['name']} {pay_amount}")

                    # Сообщения игрокам
                    player_messages.setdefault(debtor['id'], []).append(f"Вы должны {creditor['name']} {pay_amount}")
                    player_messages.setdefault(creditor['id'], []).append(f"{debtor['name']} должен вам {pay_amount}")

                if credit_to_cover == 0:
                    break

            # Остаток после перераспределения – остаётся группе
            creditor['amount'] = credit_to_cover

    # Оставшиеся долги между игроками и группой
    for debtor in debtors:
        if debtor['amount'] > 0:
            matches.append(f"{debtor['name']} должен Группа {debtor['amount']}")
            player_messages.setdefault(debtor['id'], []).append(f"Вы должны группе {debtor['amount']}")
            group_debt += debtor['amount']

    for creditor in creditors:
        if creditor['amount'] > 0:
            matches.append(f"Группа должна {creditor['name']} {creditor['amount']}")
            player_messages.setdefault(creditor['id'], []).append(f"Группа должна вам {creditor['amount']}")
            group_debt -= creditor['amount']

    group_info['debt'] = group_debt
    await save_groups()

    result_text = "Распределение долгов:\n" + "\n".join(matches) if matches else "Нет долгов между игроками и группой."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=result_text)

    for uid, msg_list in player_messages.items():
        personal_text = "Ваши взаиморасчёты:\n" + "\n".join(msg_list)
        try:
            await context.bot.send_message(chat_id=uid, text=personal_text)
        except Exception as e:
            print(f"Не удалось отправить сообщение игроку {uid}: {e}")



async def pre_shutdown(app):
    await save_groups()
    await _save_players_to_file()
    print("Данные групп и игроков сохранены.")


    with open('players.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['player_id', 'player_name', 'groups'])
        for uid, uinfo in users.items():
            print(f"Сохраняем информацию об игроке {uid}: {json.dumps(uinfo.get('groups', {}))}")
            writer.writerow([uid, uinfo['name'], json.dumps(uinfo.get('groups', {}))])
    print("Данные групп и игроков сохранены.")
async def _save_players_to_file():
    with open('players.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['player_id', 'player_name', 'group_id', 'cash', 'debt', 'chips'])

        for uid, uinfo in users.items():
            user_written = False
            for (uid2, gid), pinfo in group_members.items():
                if uid2 == uid:
                    writer.writerow([uid, uinfo['name'], gid, pinfo['cash'], pinfo['debt'], pinfo['chips']])
                    user_written = True
            if not user_written:
                writer.writerow([uid, uinfo['name'], '', 0, 0, 0])

    print("Файл players.csv обновлен.")



def main():
    # Замените 'YOUR_BOT_TOKEN' на токен вашего бота
    application = ApplicationBuilder().token('YOUR_BOT_TOKEN').post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('admin_info', admin_info))
    application.add_handler(CommandHandler('player_info', player_info))
    application.add_handler(CommandHandler('register', register))
    application.add_handler(CommandHandler('create_group', create_group))
    application.add_handler(CommandHandler('join', join_group))
    application.add_handler(CommandHandler('buy_in', buy_in))
    application.add_handler(CommandHandler('buy_out', buy_out))
    application.add_handler(CommandHandler('balance', balance))
    application.add_handler(CommandHandler('group_balance', group_balance))
    application.add_handler(CommandHandler('who', who_am_i)) # Добавляем обработчик для /whoIam
    application.add_handler(CommandHandler('end_game', end_game)) # Добавляем обработчик для /whoIam
    application.add_handler(CommandHandler('match_debts', match_debts))

    application.run_polling()

if __name__ == '__main__':
    main()