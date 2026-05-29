import sqlite3
import telebot
from telebot.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from openai import OpenAI
import base64
from datetime import date 
from prompts import FOOD_ANALYSIS, FOOD_ANALYSIS_JSON
from key import BOT_KEY, AI_KEY

temp_result = {}

bot = telebot.TeleBot(BOT_KEY)

conn = sqlite3.connect('users.db', check_same_thread=False, timeout = 10)
cursor = conn.cursor()

client = OpenAI(api_key=AI_KEY)

def analyze_food(file_path):
    with open(file_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                'role': 'system',
                'content': 'Ты диетолог. Отвечай только на русском и только о еде на фото. Если не можешь распознать блюдо, скажи что плохо видно и напиши примерное количество калорий и БЖУ. Если не видишь блюдо, скажи что не можешь распознать блюдо и не пиши калории и БЖУ.'
            },
            {
                'role': 'user',
                'content':[
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/jpeg;base64,{image_data}'
                        }
                    },
                    {
                        'type': 'text',
                        'text': FOOD_ANALYSIS
                    }
                ]
            }
        ]
    )
    return response.choices[0].message.content

def analyze_food_json(description):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                'role': 'user',
                'content': f'{FOOD_ANALYSIS_JSON}\n\nОпиши: {description}'
            }
        ]
    )
    result = response.choices[0].message.content
    return result.replace('```json', '').replace('```', '').strip()

def recalculate(user_id):
    cur =  conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    if user[2] == 'Мужчина🧑':
        bmr = (10 * user[5]) + (6.25 * user[4]) - (5 * user[3]) + 5
    else:
        bmr = (10 * user[5]) + (6.25 * user[4]) - (5 * user[3]) - 161

    if user[6] == 'Сидячий образ жизни 🛋️':
        coef = 1.2
    elif user[6] == 'Умеренная активность 🚶‍♂️':
        coef = 1.55
    else:
        coef = 1.75

    cal = round(bmr * coef)

    protein = round(user[5] * 1.8)
    fat = round((cal * 0.25) / 9)
    crabs = round((cal - (protein * 4 + fat * 9)) / 4)

    cur.execute('UPDATE users SET calories = ?, protein = ?, fat = ?, crabs = ? WHERE user_id = ?', (cal, protein, fat, crabs, user_id))
    conn.commit()

def update_age(message, user_id):
    try:
        age = int(message.text)
        if age < 6 or age > 100:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный возраст (например, 25).')
        bot.register_next_step_handler(message, update_age, user_id)
        return
    cursor.execute('UPDATE users SET age = ? WHERE user_id = ?', (age, user_id))
    conn.commit()
    recalculate(user_id)
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
    markup.row(btn)
    bot.send_message(message.chat.id, 'Возраст успешно обновлён на ' + str(age) + ' лет', reply_markup=markup)


def update_height(message, user_id):
    try:
        height = int(message.text)
        if height < 50 or height > 250:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный рост (например, 170).')
        bot.register_next_step_handler(message, update_height, user_id)
        return
    cursor.execute('UPDATE users SET height = ? WHERE user_id = ?', (height, user_id))
    conn.commit()
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
    markup.row(btn)
    bot.send_message(message.chat.id, 'Рост успешно обновлён на ' + str(height) + ' см', reply_markup=markup)
    recalculate(user_id)

def update_weight(message, user_id):
    try:
        weight = int(message.text)
        if weight < 20 or weight > 300:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный вес (например, 70).')
        bot.register_next_step_handler(message, update_weight, user_id)
        return
    cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (weight, user_id))
    conn.commit()
    markup = InlineKeyboardMarkup()
    btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
    markup.row(btn)
    bot.send_message(message.chat.id, 'Вес успешно обновлён на ' + str(weight) + ' кг', reply_markup=markup)
    recalculate(user_id)

def save_male(user_id, calories, protein, fat, crabs, description):
    cur = conn.cursor()
    today = date.today().strftime("%Y-%m-%d")
    cur.execute('INSERT INTO meals (user_id, date, calories, protein, fat, crabs, description) VALUES (?, ?, ?, ?, ?, ?, ?)', (user_id, today, calories, protein, fat, crabs, description))
    conn.commit()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        gender TEXT,
        age INTEGER,
        height INTEGER,
        weight INTEGER,
        activity TEXT,
        calories INTEGER,
        protein INTEGER,
        fat INTEGER,
        crabs INTEGER,
        goal TEXT,
        coef INTEGER
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS meals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        calories INTEGER,
        protein INTEGER,
        fat INTEGER,
        crabs INTEGER,
        description TEXT,
        is_confirmes INTEGER DEFAULT 0
    )
''')

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if user and user[7] is not None:
        bot.send_message(message.chat.id, 'Ты уже есть в базе! Напиши команду /my_calories, чтобы узнать свои данные или /update, чтобы изменить их☺️.')
        return
    
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton('Начать 🚀', callback_data='start_registration')
    btn2 = InlineKeyboardButton('Выйти ❌', callback_data='start_exit')
    markup.row(btn1, btn2)

    bot.send_message(message.chat.id, 'Привет 👋! Я бот для предоставлении информации о твоём БЖУ🍔. Я буду задавать вопросы, а ты отвечаешь)☺️!', reply_markup=markup) 

def get_age(message, user_id):
    try:
        age = int(message.text)
        if age < 6 or age > 100:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный возраст (например, 25).')
        bot.register_next_step_handler(message, get_age, user_id)
        return
    
    cur = conn.cursor() 
    cur.execute('UPDATE users SET age = ? WHERE user_id = ?', (age, user_id))    
    conn.commit()

    bot.send_message(message.chat.id, 'Какой у тебя рост? (в см)')            
    bot.register_next_step_handler(message, get_height, user_id)

def get_height(message, user_id):
    try:
        height = int(message.text)
        if height < 50 or height > 250:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный рост (например, 170).')
        bot.register_next_step_handler(message, get_height, user_id)
        return
    
    cur = conn.cursor() 
    cur.execute('UPDATE users SET height = ? WHERE user_id = ?', (height, user_id))    
    conn.commit()

    bot.send_message(message.chat.id, 'Какой у тебя вес? (в кг)')            
    bot.register_next_step_handler(message, get_weight, user_id)

def get_weight(message, user_id):
    try:
        weight = int(message.text)
        if weight < 20 or weight > 300:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введи корректный вес (например, 70).')
        bot.register_next_step_handler(message, get_weight, user_id)
        return

    cur = conn.cursor()
    cur.execute('UPDATE users SET weight = ? WHERE user_id = ?', (weight, user_id))
    conn.commit()

    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton('Сидячий образ жизни 🛋️', callback_data='reg_activity_1')
    btn2 = InlineKeyboardButton('Умеренная активность 🚶‍♂️', callback_data='reg_activity_2')
    btn3 = InlineKeyboardButton('Высокая активность 🏋️‍♂️', callback_data='reg_activity_3')
    markup.row(btn1)
    markup.row(btn2)
    markup.row(btn3)

    bot.send_message(message.chat.id, 'Какой у тебя уровень активности?', reply_markup=markup)

def get_bju(message, user_id):
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    if user[2] == 'Мужчина🧑':
        bmr = (10 * user[5]) + (6.25 * user[4]) - (5 * user[3]) + 5
    else:
        bmr = (10 * user[5]) + (6.25 * user[4]) - (5 * user[3]) - 161

    cal = round(bmr * user[12])

    loss = round(cal * 0.85)
    norm = cal
    gain = round(cal * 1.15)

    cur.execute('UPDATE users SET calories = ? WHERE user_id = ?', (cal, user_id))
    conn.commit()

    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton('Минимум 🥗', callback_data='reg_goal_lose')
    btn2 = InlineKeyboardButton('Норма 🍽️', callback_data='reg_goal_maintain')
    btn3 = InlineKeyboardButton('Набор массы 💪', callback_data='reg_goal_gain')
    markup.row(btn1)
    markup.row(btn2)
    markup.row(btn3)

    bot.send_message(message.chat.id, f'Выбери цель, которая тебе подходит:', reply_markup=markup)

@bot.message_handler(commands = ['my_calories'])
def mydata (message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[7] is None:
        bot.send_message(message.chat.id, 'Вас нету в базе, пожалуйста с начало введи команду /start ☺️')
    else:    
        bot.send_message(message.chat.id, f'Так я вас нашел по базе и у вам нужно для {user[6]} вам нужно: \n\n🔥Калорий - {user[7]}\n🥩Белков - {user[8]}\n🧈Жиров - {user[9]}\n🍞Угливодов - {user[10]}')

@bot.message_handler(commands = ['delete'])
def delete (message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[7] is None:
        bot.send_message(message.chat.id, 'Вас нету в базе, пожалуйста с начало введи команду /start ☺️')
    else:
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.commit()
        bot.send_message(message.chat.id, 'Данные были удалены успешно! Напишите команду /start, чтобы начать заново ☺️')

@bot.message_handler(commands = ['update'])
def start (message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[7] is None:
        bot.send_message(message.chat.id, 'Вас нету в базе, пожалуйста с начало введи команду /start ☺️')
        return

    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton('Пол ♂️/♀️', callback_data = 'menu_gender')
    btn2 = InlineKeyboardButton('Возраст 🎂', callback_data = 'menu_age')
    btn3 = InlineKeyboardButton('Рост 📏', callback_data = 'menu_height')
    btn4 = InlineKeyboardButton('Вес ⚖️', callback_data = 'menu_weight')
    btn5 = InlineKeyboardButton('Активность 🏃', callback_data = 'menu_activity')
    btn6 = InlineKeyboardButton('Цель 🎯', callback_data = 'menu_goal')

    markup.row(btn1, btn2, btn3)
    markup.row(btn4, btn6)
    markup.row(btn5)
    
    bot.send_message(message.chat.id, 'Выбери что-бы ты хотел изменить☺️:', reply_markup=markup)    

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == 'start_registration':
        user_id = call.from_user.id
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
            conn.commit()
        
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('Мужчина🧑', callback_data = 'reg_gender_male')
        btn2 = InlineKeyboardButton('Женщина👩', callback_data = 'reg_gender_female')
        markup.row(btn1, btn2)

        bot.edit_message_text('Отлично! Давай начнем с твоего пола⚧️.\nВыбери пол, используя кнопки ниже.', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'start_exit':
        bot.edit_message_text('Окей, если передумаешь, просто напиши /start ☺️', call.message.chat.id, call.message.message_id)
    
    elif call.data == 'reg_gender_male':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', ('Мужчина🧑', user_id))
        conn.commit()
        bot.edit_message_text('Теперь напиши свой возраст в годах.', call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, get_age, user_id)

    elif call.data == 'reg_gender_female':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', ('Женщина👩', user_id))
        conn.commit()
        bot.edit_message_text('Теперь напиши свой возраст в годах.', call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, get_age, user_id)

    elif call.data == 'reg_activity_1':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET activity = ?, coef = ? WHERE user_id = ?', ('Сидячий образ жизни 🛋️', 1.2, user_id))
        conn.commit()
        bot.edit_message_text('Спасибо за информацию!', call.message.chat.id, call.message.message_id)
        get_bju(call.message, user_id)
    
    elif call.data == 'reg_activity_2':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET activity = ?, coef = ? WHERE user_id = ?', ('Умеренная активность 🚶‍♂️', 1.55, user_id))
        conn.commit()
        bot.edit_message_text('Спасибо за информацию!', call.message.chat.id, call.message.message_id)
        get_bju(call.message, user_id)
    
    elif call.data == 'reg_activity_3':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET activity = ?, coef = ? WHERE user_id = ?', ('Высокая активность 🏋️‍♂️', 1.75, user_id))
        conn.commit()
        bot.edit_message_text('Спасибо за информацию!', call.message.chat.id, call.message.message_id)
        get_bju(call.message, user_id)

    elif call.data == 'reg_goal_lose':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        cal = round(user[7] * 0.85)
        label = 'похудения'
        protein = round(user[5] * 1.8)
        fat = round((cal * 0.25) / 9)
        crabs = round((cal - (protein * 4 + fat * 9)) / 4)
        cur.execute('UPDATE users SET calories = ?, goal = ?, protein = ?, fat = ?, crabs = ? WHERE user_id = ?', (cal, 'Минимум 🥗', protein, fat, crabs, user_id))
        conn.commit()
        bot.edit_message_text(f'Для {label} тебе нужно {cal} ккал в день.\n\nБелки: {protein} г\nЖиры: {fat} г\nУглеводы: {crabs} г', call.message.chat.id, call.message.message_id)

    elif call.data == 'reg_goal_maintain':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        cal = round(user[7])
        label = 'поддержания веса'
        protein = round(user[5] * 1.8)
        fat = round((cal * 0.25) / 9)
        crabs = round((cal - (protein * 4 + fat * 9)) / 4)
        cur.execute('UPDATE users SET calories = ?, goal = ?, protein = ?, fat = ?, crabs = ? WHERE user_id = ?', (cal, 'Норма 🍽️', protein, fat, crabs, user_id))
        conn.commit()
        bot.edit_message_text(f'Для {label} тебе нужно {cal} ккал в день.\n\nБелки: {protein} г\nЖиры: {fat} г\nУглеводы: {crabs} г', call.message.chat.id, call.message.message_id)

    elif call.data == 'reg_goal_gain':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        cal = round(user[7] * 1.15)
        label = 'набор массы'
        protein = round(user[5] * 1.8)
        fat = round((cal * 0.25) / 9)
        crabs = round((cal - (protein * 4 + fat * 9)) / 4)
        cur.execute('UPDATE users SET calories = ?, goal = ?, protein = ?, fat = ?, crabs = ? WHERE user_id = ?', (cal, 'Набор массы 💪', protein, fat, crabs, user_id))
        conn.commit()
        bot.edit_message_text(f'Для {label} тебе нужно {cal} ккал в день.\n\nБелки: {protein} г\nЖиры: {fat} г\nУглеводы: {crabs} г', call.message.chat.id, call.message.message_id)

    elif call.data == 'menu_gender':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('Мужчина🧑', callback_data = 'gender_male')
        btn2 = InlineKeyboardButton('Женщина👩', callback_data = 'gender_female')
        markup.row(btn1, btn2)
        bot.edit_message_text('Нажмите на нужный вам вариант',call.message.chat.id, call.message.message_id, reply_markup=markup)


    elif call.data == 'menu_age':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('18 лет', callback_data = 'age_18')
        btn2 = InlineKeyboardButton('25 лет', callback_data = 'age_25')
        btn3 = InlineKeyboardButton('35 лет', callback_data = 'age_35')
        markup.row(btn1, btn2, btn3)
        bot.edit_message_text('Нажмите на нужный вам вариант или впишите свой:', call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.register_next_step_handler(call.message, update_age, call.from_user.id)

        
    elif call.data == 'menu_height':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('150 см', callback_data = 'height_150')
        btn2 = InlineKeyboardButton('160 см', callback_data = 'height_160')
        btn3 = InlineKeyboardButton('170 см', callback_data = 'height_170')
        btn4 = InlineKeyboardButton('180 см', callback_data = 'height_180')
        markup.row(btn1, btn2)
        markup.row(btn3, btn4)
        bot.edit_message_text('Нажмите на нужный вам вариант или впишите свой:', call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.register_next_step_handler(call.message, update_height, call.from_user.id)

        
    elif call.data == 'menu_weight':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('50 кг', callback_data = 'weight_50')
        btn2 = InlineKeyboardButton('60 кг', callback_data = 'weight_60')
        btn3 = InlineKeyboardButton('70 кг', callback_data = 'weight_70')
        btn4 = InlineKeyboardButton('80 кг', callback_data = 'weight_80')
        btn5 = InlineKeyboardButton('90 кг', callback_data = 'weight_90')
        btn6 = InlineKeyboardButton('100 кг', callback_data = 'weight_100')
        markup.row(btn1, btn2, btn3)
        markup.row(btn4, btn5, btn6)
        bot.edit_message_text('Нажмите на нужный вам вариант или впишите свой:', call.message.chat.id, call.message.message_id, reply_markup=markup)
        bot.register_next_step_handler(call.message, update_weight, call.from_user.id)

    elif call.data == 'menu_activity':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('Сидячий образ жизни 🛋️', callback_data =  'activity_sitter')
        btn2 = InlineKeyboardButton('Умеренная активность 🚶‍♂️', callback_data =  'activity_normal')
        btn3 = InlineKeyboardButton('Высокая активность 🏋️‍♂️''', callback_data = 'activity_high')
        markup.row(btn1)
        markup.row(btn2)
        markup.row(btn3)
        bot.edit_message_text('Нажмите на нужный вам вариант.', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'menu_goal':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('Минимум 🥗', callback_data = 'goal_lose')
        btn2 = InlineKeyboardButton('Норма 🍽️', callback_data = 'goal_maintain')
        btn3 = InlineKeyboardButton('Набор массы 💪', callback_data = 'goal_gain')
        markup.row(btn1)
        markup.row(btn2)
        markup.row(btn3)
        bot.edit_message_text('Нажмите на нужный вам вариант.', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'gender_male':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', ('Мужчина🧑', user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Пол успешно обновлён на Муржской🧑', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'gender_female':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', ('Женщина👩', user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Пол успешно обновлён на Женский👩', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'age_18':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET age = ? WHERE user_id = ?', (18, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Возраст успешно обновлён на 18 лет', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'age_25':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET age = ? WHERE user_id = ?', (25, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Возраст успешно обновлён на 25 лет', call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == 'age_35':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET age = ? WHERE user_id = ?', (35, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Возраст успешно обновлён на 35 лет', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'height_150':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET height = ? WHERE user_id = ?', (150, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Рост успешно обновлён на 150 см', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'height_160':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET height = ? WHERE user_id = ?', (160, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Рост успешно обновлён на 160 см', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'height_170':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET height = ? WHERE user_id = ?', (170, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Рост успешно обновлён на 170 см', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'height_180':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET height = ? WHERE user_id = ?', (180, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Рост успешно обновлён на 180 см', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_50':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (50, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 50 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_60':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (60, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 60 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_70':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (70, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 70 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_80':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (80, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 80 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_90':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (90, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 90 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'weight_100':
        user_id = call.from_user.id
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        cursor.execute('UPDATE users SET weight = ? WHERE user_id = ?', (100, user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Вес успешно обновлён на 100 кг', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'activity_sitter':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET activity = ? WHERE user_id = ?', ('Сидячий образ жизни 🛋️', user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Уровень активности успешно обновлён на Сидячий образ жизни 🛋️', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'activity_normal':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET activity = ? WHERE user_id = ?', ('Умеренная активность 🚶‍♂️', user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Уровень активности успешно обновлён на Умеренная активность 🚶‍♂️', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'activity_high':
        user_id = call.from_user.id
        cursor.execute('UPDATE users SET activity = ? WHERE user_id = ?', ('Высокая активность 🏋️‍♂️', user_id))
        conn.commit()
        recalculate(user_id)
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Уровень активности успешно обновлён на Высокая активность 🏋️‍♂️', call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == 'goal_lose':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET goal = ? WHERE user_id = ?', ('Похудение 🥗', user_id))
        conn.commit()
        recalculate(user_id)
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        new_cal=round(user[7] * 0.85)
        cur.execute('UPDATE users SET calories = ? WHERE user_id = ?', (new_cal, user_id))
        conn.commit()
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Цель успешно обновлён на Похудение 🥗', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'goal_maintain':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET goal = ? WHERE user_id = ?', ('Норма 🍽️', user_id))
        conn.commit()
        recalculate(user_id)
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        new_cal = round(user[7])
        cur.execute('UPDATE users SET calories = ? WHERE user_id = ?', (new_cal, user_id))
        conn.commit()
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Цель успешно обновлён на Норма 🍽️', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'goal_gain':
        user_id = call.from_user.id
        cur = conn.cursor()
        cur.execute('UPDATE users SET goal = ? WHERE user_id = ?', ('Набор массы 💪', user_id))
        conn.commit()
        recalculate(user_id)
        cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cur.fetchone()
        new_cal = round(user[7] * 1.15)
        cur.execute('UPDATE users SET calories = ? WHERE user_id = ?', (new_cal, user_id))
        conn.commit()
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton('◀️ Назад', callback_data='back_to_menu')
        markup.row(btn)
        bot.edit_message_text('Цель успешно обновлён на Набор массы 💪', call.message.chat.id, call.message.message_id, reply_markup=markup)
    
    elif call.data == 'back_to_menu':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('Пол ♂️/♀️', callback_data = 'menu_gender')
        btn2 = InlineKeyboardButton('Возраст 🎂', callback_data = 'menu_age')
        btn3 = InlineKeyboardButton('Рост 📏', callback_data = 'menu_height')
        btn4 = InlineKeyboardButton('Вес ⚖️', callback_data = 'menu_weight')
        btn5 = InlineKeyboardButton('Активность 🏃', callback_data = 'menu_activity')
        btn6 = InlineKeyboardButton('Цель 🎯', callback_data = 'menu_goal')
        markup.row(btn1, btn2, btn3)
        markup.row(btn4, btn6)
        markup.row(btn5)
        bot.edit_message_text('Выбери что-бы ты хотел изменить', call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == 'save_meal':
        user_id = call.from_user.id
        result = temp_result.get(user_id)
        if not result:
            bot.edit_message_text('Не нашел данные для сохранения.', call.message.chat.id, call.message.message_id)
            return
        
        bot.edit_message_text('Сохраняю...⏳', call.message.chat.id, call.message.message_id)

        json_result = analyze_food_json(result)

        try:
            import json
            data = json.loads(json_result)
            total = data['total']
            save_male(user_id, total['calories'], total['protein'], total['fat'], total['carbs'], result)
            bot.edit_message_text('✅ Приём пищи записан в дневник!', call.message.chat.id, call.message.message_id)

        except Exception as e:
            print(f"Error occurred: {e}")
            bot.edit_message_text('❌ Не удалось сохранить приём пищи. Произошла ошибка при обработке данных.', call.message.chat.id, call.message.message_id)
        
    elif call.data == 'skip_save':
        bot.edit_message_text('Окей, не сохраняю.', call.message.chat.id, call.message.message_id)

@bot.message_handler(commands = ['my_date'])
def my_date(message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        bot.send_message(message.chat.id, f'Ваши данные:\n⚧️ Пол: {user[2]}\n🎂 Возраст: {user[3]} лет\n📏 Рост: {user[4]} см\n⚖️ Вес: {user[5]} кг\n🎯 Цель: {user[11]}\n🏃 Уровень активности: {user[6]}\n🔥 Калории: {user[7]} ккал\n🥩 Белки: {user[8]} г\n🧈 Жиры: {user[9]} г\n🍞 Углеводы: {user[10]} г')
    else:
        bot.send_message(message.chat.id, 'Вас нету в базе, пожалуйста с начало введи команду /start')

@bot.message_handler(content_types = ['photo'])
def get_photo(message):
    user_id = message.from_user.id
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user or user[7] is None:
        bot.send_message(message.chat.id, 'Пожалуйста, сначала введи свои данные с помощью команды /start, чтобы я мог анализировать твои фото.')
        return
    else:
        file_id= message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open('temp_food.jpg', 'wb') as f:
            f.write(downloaded_file)
    
        bot.send_message(message.chat.id, 'Фото получено, начинаю анализировать...')
        result = analyze_food('temp_food.jpg')
        temp_result[user_id] = result

        if 'не могу' in result.lower() or 'не распознаю' in result.lower() or 'неопределенно' in result.lower() or 'неизвестно' in result.lower() or 'неясно' in result.lower() or 'неразборчиво' in result.lower():
            bot.send_message(message.chat.id, 'Сфоткайте пожалуйста более качественно, я не могу распознать что это за еда на фото.')
            bot.send_message(message.chat.id, 'Можете уточнить что на фото.\nИли ввести данные вручную в формате: "калории, белки, жиры, углеводы" (например: "500 ккал, 30 г белков, 20 г жиров, 50 г углеводов").\nЕсли хотите пропустить, напишите /skip.')
            bot.register_next_step_handler(message, manual_input)
        else:
            bot.send_message(message.chat.id, result)
            bot.send_message(message.chat.id, 'Хочешь уточнить что-то? Если нет напиши команду /skip чтобы пропустить этот шаг.')
            bot.register_next_step_handler(message, ask_for_details, result)

def manual_input(message):
    if message.content_type == 'photo':
        bot.send_message(message.chat.id, 'Пожалуйста напишите текст или /skip, а не отправляйте фото.')
        bot.register_next_step_handler(message, manual_input)
        return
    
    if message.text is None:
        bot.send_message(message.chat.id, 'Пожалуйста напишите текст или /skip.')
        bot.register_next_step_handler(message, manual_input)
        return
    
    if message.text.lower() == '/skip':
        bot.send_message(message.chat.id, 'Окей, пропускаем.')
        return
    
    bot.send_message(message.chat.id, 'Уточняю данные🔄')

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": 'Ты - помощник бота, который помогает пользователю анализировать данные о еде. Пользователь предоставил тебе данные о еде, распознанные с фотографии, и теперь он может уточнить эти данные или ввести их вручную. Твоя задача - пересчитать БЖУ и калории на основе новой информации, которую предоставит пользователь, и дать ему обновленные данные.'},
            {"role": "user", "content": f"Пересчитай строго по формуле {FOOD_ANALYSIS}: {message.text}"}
        ]
    )

    result = response.choices[0].message.content
    bot.send_message(message.chat.id, result)

def ask_for_details(message, previos_result):
    if message.content_type == 'photo' or message.text is None:
        bot.send_message(message.chat.id, 'Пожалуйста напишите текст или /skip, а не отправляйте фото.')
        bot.register_next_step_handler(message, ask_for_details, previos_result)
        return
    
    if message.text.lower() == '/skip':
        markup = InlineKeyboardMarkup()
        btn1 = InlineKeyboardButton('✅ Да', callback_data='save_meal')
        btn2 = InlineKeyboardButton('❌ Нет', callback_data='skip_save')
        markup.row(btn1, btn2)
        bot.send_message(message.chat.id, 'Записать этот приём пищи в дневник🤔', reply_markup=markup)
        return
    
    clarification = message.text
    bot.send_message(message.chat.id, 'Уточняю данные🔄')

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "assistant", "content": previos_result},
            {"role": "user", "content": f"Распознанные данные: {clarification}. Пересчитай и ответь строго по формуле {FOOD_ANALYSIS}"}
        ]
    )

    updated_result = response.choices[0].message.content
    bot.send_message(message.chat.id, updated_result)

    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton('✅ Да', callback_data='save_meal')
    btn2 = InlineKeyboardButton('❌ Нет', callback_data='skip_save')
    markup.row(btn1, btn2)
    bot.send_message(message.chat.id, 'Записать этот приём пищи в дневник🤔', reply_markup=markup)

@bot.message_handler(commands = ['today'])
def today(message):
    user_id = message.from_user.id
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()

    if not user or user[7] is None:
        bot.send_message(message.chat.id, 'Вас нету в базе, пожалуйста с начало введи команду /start ☺️')
        return
    
    today_date = date.today().strftime('%Y-%m-%d')
    cur.execute('SELECT * FROM meals WHERE user_id = ? AND date = ?', (user_id, today_date))
    meals = cur.fetchall()

    if not meals:
        bot.send_message(message.chat.id, 'Сегодня ты ещё не добавлял приёмы пищи. Сфоткай свой обед или ужин, и я помогу тебе проанализировать его!☺️')
        return
    
    total_cal = sum(m[3] for m in meals)
    total_protein = sum(m[4] for m in meals)
    total_fat = sum(m[5] for m in meals)
    total_carbs = sum(m[6] for m in meals)

    norm_cal = user[7]
    norm_protein = user[8]
    norm_fat = user[9]
    norm_carbs = user[10]

    left_cal = norm_cal - total_cal
    left_protein = norm_protein - total_protein
    left_fat = norm_fat - total_fat
    left_carbs = norm_carbs - total_carbs

    text = f'📅 Сегодня съел:\n\n'
    text += f'🔥 Калории: {total_cal} из {norm_cal} ккал\n'
    text += f'🥩 Белки: {total_protein} из {norm_protein} г\n'
    text += f'🧈 Жиры: {total_fat} из {norm_fat} г\n'
    text += f'🍞 Углеводы: {total_carbs} из {norm_carbs} г\n\n'
    text += f'📊 Осталось:\n'
    text += f'🔥 {left_cal} ккал\n'
    text += f'🥩 {left_protein} г белков\n'
    text += f'🧈 {left_fat} г жиров\n'
    text += f'🍞 {left_carbs} г углеводов'

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands = ['help'])
def help (message):
    bot.send_message(message.chat.id, '📋 Список команд:\n\n'
    '🚀 /start - Начать подсчёт калорий\n'
    '📊 /my_date - Показать все твои данные\n'
    '🔥 /my_calories - Показать калории и БЖУ\n'
    '✏️ /update - Изменить конкретный параметр\n'
    '🗑️ /delete - Удалить твои данные из базы\n'
    '📸 Фото еды - Анализ калорий и БЖУ блюда')
    
bot.polling(none_stop=True)