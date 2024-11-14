from flask import Flask, request, render_template_string, send_from_directory, abort
import json
import subprocess
import os
from datetime import datetime
import time
import nbformat
from nbconvert import HTMLExporter

app = Flask(__name__)
last_request_time = {}

# Константы
CONFIG_FILE = "config.json"
RESULTS_FILE = "results.json"
FILES_FOLDER = "files"
INFO_DIRECTORY = "infofiles"
CONRESULTS_FILE = "conresults.json"


# Загрузка конфигурации задач
def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_results(results):
    with open(RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4, ensure_ascii=False)


def load_results():
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def save_conresults(results):
    with open(CONRESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4, ensure_ascii=False)


def load_conresults():
    if os.path.exists(CONRESULTS_FILE):
        with open(CONRESULTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def is_local_request():
    """Проверяет, что запрос поступил с локального компьютера."""
    user_ip = request.remote_addr
    return user_ip in ["127.0.0.1", "::1"]


# Выполнение пользовательского кода
def execute_code(user_code):
    try:
        temp_filename = "temp_script.py"
        with open(temp_filename, "w", encoding="utf-8") as temp_file:
            temp_file.write(user_code)

        result = subprocess.run(
            ["python", temp_filename],
            text=True,
            capture_output=True,
            timeout=3  # Таймаут 3 секунд
        )
        os.remove(temp_filename)
        return {"stdout": result.stdout, "stderr": result.stderr, "success": result.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"error": "Превышено время выполнения кода. Проверьте, нет ли бесконечного цикла."}
    except Exception as e:
        return {"error": str(e)}


def render_page2(topics, result_message, execution_output, task_description, name, selected_topic, selected_task):
    """Функция для рендера страницы"""
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Python Code Checker</title>
    </head>
    <body>
        <h1>Python Code Checker</h1>
        <form method="POST" action="/">
            <label>Имя ученика:</label><br>
            <input type="text" name="name" value="{{ name or '' }}" required><br><br>

            <label>Выберите тему:</label><br>
            <select name="topic" required onchange="this.form.submit()">
                <option value="" disabled selected>Выберите тему</option>
                {% for topic in topics.keys() %}
                    <option value="{{ topic }}" {% if topic == selected_topic %}selected{% endif %}>{{ topic }}</option>
                {% endfor %}
            </select><br><br>

            {% if selected_topic %}
            <label>Выберите задачу:</label><br>
            <select name="task" required onchange="this.form.submit()">
                <option value="" disabled selected>Выберите задачу</option>
                {% for task_id, task in topics[selected_topic].items() %}
                    <option value="{{ task_id }}" {% if task_id == selected_task %}selected{% endif %}>Задача {{ task_id }}</option>
                {% endfor %}
            </select><br><br>
            {% endif %}

            {% if task_description %}
            <h3>Условие задачи:</h3>
            <p>{{ task_description }}</p>
            {% endif %}

            <label>Введите ваш код:</label><br>
            <textarea name="code" rows="10" cols="50" required>{{ request.form.get('code') or '' }}</textarea><br><br>
            
            <!-- Скрытое поле для проверки, была ли нажата кнопка -->
            <input type="hidden" name="submit_action" value="">
            
            <button type="submit" onclick="document.getElementsByName('submit_action')[0].value = 'submit_code'" >Отправить</button>
        </form>

        {% if result_message %}
        <h2>Результат:</h2>
        <p>{{ result_message }}</p>
        {% if execution_output %}
        <h3>Вывод программы:</h3>
        <pre>{{ execution_output }}</pre>
        {% endif %}
        {% endif %}
    </body>
    </html>
    """, topics=topics, result_message=result_message, execution_output=execution_output,
                                  task_description=task_description, name=name,
                                  selected_topic=selected_topic, selected_task=selected_task)


# Главная страница
@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    topics = config["tasks"]
    topic_tasks = None
    result_message = None
    execution_output = None
    task_description = None
    name = None
    selected_topic = None
    selected_task = None
    code = None
    submit_action = None
    global last_request_time

    if request.method == "POST":
        name = request.form.get("name")
        selected_topic = request.form.get("topic")
        selected_task = request.form.get("task")
        code = request.form.get("code")
        submit_action = request.form.get("submit_action")
        user_ip = request.remote_addr
        current_time = time.time()
        print(request.form)

        if selected_topic and selected_topic in topics:
            topic_tasks = topics[selected_topic]

        if selected_topic not in topics or selected_task not in topic_tasks:
            result_message = "Неверный номер задачи."
        else:
            task = topic_tasks[selected_task]
            task_description = task["description"]
            expected_output = task["expected_output"]

            if not code or submit_action != 'submit_code':
                return render_page2(topics, result_message, execution_output, task_description, name, selected_topic,
                                    selected_task)

            # Проверка времени последнего запроса
            if user_ip in last_request_time:
                time_since_last_request = current_time - last_request_time[user_ip]
                if time_since_last_request < 5:
                    result_message = f"Слишком частые запросы. Подождите {round(5 - time_since_last_request, 2)} секунд."
                    return render_page2(topics, result_message, execution_output, task_description, name,
                                        selected_topic, selected_task)

            # Обновляем время последнего запроса
            last_request_time[user_ip] = current_time

            execution_result = execute_code(code)
            if "error" in execution_result:
                result_message = execution_result["error"]
            elif execution_result["stderr"]:
                result_message = "Ошибка в коде."
                execution_output = execution_result["stderr"]
            else:
                if execution_result["stdout"] == expected_output + "\n":
                    result_message = "Ваш код верный!"
                    status = "Успех"
                else:
                    result_message = "Ваш код неверный."
                    status = "Неудача"
                execution_output = execution_result["stdout"]

                # Сохраняем результат в JSON
                results = load_results()
                if name not in results:
                    results[name] = {"tasks": {}, "history": [], "ip": user_ip}

                # Обновляем данные
                results[name]["tasks"][" ".join((str(selected_task), str(selected_topic)))] = status
                results[name]["history"].append({
                    "topic": selected_topic,
                    "task_id": selected_task,
                    "code": code,
                    "result": status,
                    "timestamp": datetime.now().isoformat(),
                    "ip": user_ip
                })

                save_results(results)

    return render_page2(topics, result_message, execution_output, task_description, name, selected_topic, selected_task)


@app.route("/res", methods=["GET"])
def results():
    if not is_local_request():
        abort(403)  # Доступ запрещён

    results = load_results()
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Результаты</title>
    </head>
    <body>
        <h1>Результаты учеников</h1>
        <table border="1">
            <tr>
                <th>Имя</th>
                <th>Задачи</th>
                <th>ip</th>

            </tr>
            {% for name, data in results.items() %}
                <tr>
                    <td><a href="/res/{{ name }}">{{ name }}</a></td>
                    <td>
                        {% for task_id, status in data['tasks'].items() %}
                            Задача {{ task_id }}: {{ status }}<br>
                        {% endfor %}
                    </td>
                     <td>{{ data['ip'] }}</td>
                </tr>
            {% endfor %}
        </table>
        <a href="/">Вернуться на главную</a>
    </body>
    </html>
    """, results=results)


# Страница со списком файлов
@app.route("/files", methods=["GET"])
def list_files():
    if not os.path.exists(FILES_FOLDER):
        os.makedirs(FILES_FOLDER)

    files = os.listdir(FILES_FOLDER)
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Список файлов</title>
    </head>
    <body>
        <h1>Список файлов</h1>
        <ul>
            {% for file in files %}
                <li><a href="/download/{{ file }}">{{ file }}</a></li>
            {% endfor %}
        </ul>
        <a href="/">Вернуться на главную</a>
    </body>
    </html>
    """, files=files)


@app.route("/res/<name>", methods=["GET"])
def student_results(name):
    results = load_results()
    if name not in results:
        return render_template_string("""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>Результаты ученика</title>
        </head>
        <body>
            <h1>Результаты ученика {{ name }}</h1>
            <p>Ученик с таким именем не найден.</p>
            <a href="/res">Вернуться к общим результатам</a>
        </body>
        </html>
        """, name=name)

    student_data = results[name]
    # Сортируем историю по времени в обратном порядке
    sorted_history = sorted(student_data["history"], key=lambda x: x["timestamp"], reverse=True)

    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Результаты ученика</title>
    </head>
    <body>
        <h1>Результаты ученика {{ name }}</h1>
        <h2>Итоги:</h2>
        <ul>
            {% for task_id, status in student_data['tasks'].items() %}
                <li>Задача {{ task_id }}: {{ status }}</li>
            {% endfor %}
        </ul>
        <h2>История попыток:</h2>
        <table border="1">
            <tr>
                <th>Номер задачи</th>
                <th>Код</th>
                <th>Результат</th>
                <th>Время</th>
                <th>ip</th>
            </tr>
            {% for attempt in sorted_history  %}
                <tr>
                    <td>{{ attempt['topic']+" "+ attempt['task_id'] }}</td>
                    <td><pre>{{ attempt['code'] }}</pre></td>
                    <td>{{ attempt['result'] }}</td>
                    <td>{{ attempt['timestamp'] }}</td>
                    <td>{{ attempt['ip'] }}</td>
                </tr>
            {% endfor %}
        </table>
        <a href="/res">Вернуться к общим результатам</a>
    </body>
    </html>
    """, name=name, student_data=student_data, sorted_history=sorted_history)


# Скачивание файлов
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(FILES_FOLDER, filename, as_attachment=True)


@app.route("/info", methods=["GET"])
def info():
    try:
        # Ищем все файлы, начинающиеся с "info" и заканчивающиеся на ".ipynb"
        info_files = [f for f in os.listdir(INFO_DIRECTORY) if f.startswith("info") and f.endswith(".ipynb")]

        if not info_files:
            return "<h1>Файлы info*.ipynb не найдены.</h1>"

        # Рендерим список доступных файлов
        return render_template_string("""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>Доступные файлы</title>
        </head>
        <body>
            <h1>Доступные файлы info</h1>
            <ul>
                {% for file in info_files %}
                    <li><a href="/info/{{ file }}">{{ file }}</a></li>
                {% endfor %}
            </ul>
            <a href="/">Вернуться на главную</a>
        </body>
        </html>
        """, info_files=info_files)

    except Exception as e:
        return f"<h1>Ошибка при обработке файлов: {str(e)}</h1>"


@app.route("/info/<filename>", methods=["GET"])
def render_info_file(filename):
    try:
        filepath = os.path.join(INFO_DIRECTORY, filename)

        # Проверяем, существует ли файл
        if not os.path.isfile(filepath):
            return f"<h1>Файл {filename} не найден.</h1>"

        # Читаем содержимое файла
        with open(filepath, "r", encoding="utf-8") as file:
            notebook = nbformat.read(file, as_version=4)

        # Конвертируем в HTML
        html_exporter = HTMLExporter()
        html_exporter.exclude_input = False  # Показывать или скрывать код
        html_body, _ = html_exporter.from_notebook_node(notebook)

        # Рендерим HTML
        return render_template_string("""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>Просмотр {{ filename }}</title>
        </head>
        <body>
            <h1>Просмотр файла {{ filename }}</h1>
            <div>{{ html_body|safe }}</div>
            <a href="/info">Вернуться к списку файлов</a>
            <a href="/">Вернуться на главную</a>
        </body>
        </html>
        """, filename=filename, html_body=html_body)

    except Exception as e:
        return f"<h1>Ошибка при обработке файла {filename}: {str(e)}</h1>"


@app.route("/con", methods=["GET", "POST"])
def con():
    config = load_config()
    tasks = config["contask"]
    result_message = None
    execution_output = None
    task_description = None
    name = None
    task_id = None
    code = None
    submit_action = None
    global last_request_time

    if request.method == "POST":
        name = request.form.get("name")
        task_id = request.form.get("task")
        code = request.form.get("code")
        submit_action = request.form.get("submit_action")
        user_ip = request.remote_addr
        current_time = time.time()

        if task_id not in tasks:
            result_message = "Неверный номер задачи."
        else:
            task = tasks[task_id]
            task_description = task["description"]

            if not code or submit_action != 'submit_code':
                return render_con_page(tasks, result_message, execution_output, task_description, name)

            # Проверка времени последнего запроса
            if user_ip in last_request_time:
                time_since_last_request = current_time - last_request_time[user_ip]
                if time_since_last_request < 5:
                    result_message = f"Слишком частые запросы. Подождите {round(5 - time_since_last_request, 2)} секунд."
                    return render_con_page(tasks, result_message, execution_output, task_description, name)



                # Обновляем время последнего запроса
            last_request_time[user_ip] = current_time

            # Выполняем код
            execution_result = execute_code(code)
            if "error" in execution_result:
                result_message = execution_result["error"]
                execution_output = execution_result["error"]
            elif execution_result["stderr"]:
                result_message = "Ошибка в коде."
                execution_output = execution_result["stderr"]
            else:
                result_message = "Задача отправлена!"
                execution_output = execution_result["stdout"]

                # Сохраняем результат в JSON
                results = load_conresults()
                if task_id not in results:
                    results[task_id] = []

                # Обновляем данные (сохраняем последнее решение)
                results[task_id].append({
                    "name": name,
                    "ip": user_ip,
                    "code": code,
                    "output": execution_output,
                    "timestamp": datetime.now().isoformat()
                })

                save_conresults(results)

    return render_con_page(tasks, result_message, execution_output, task_description, name)


@app.route("/conres", methods=["GET"])
def conresult():
    if not is_local_request():
        abort(403)  # Доступ запрещён

    results = load_conresults()

    # Для каждой задачи отбираем последние сдачи от каждого ученика
    latest_submissions = {}
    for task_id, submissions in results.items():
        # Используем словарь для хранения последнего решения от каждого ученика
        latest_by_user = {}
        for submission in submissions:
            latest_by_user[submission["name"]] = submission

        # Преобразуем обратно в список для рендера
        latest_submissions[task_id] = list(latest_by_user.values())

    # Строим таблицы для каждой задачи
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Результаты самостоятельных задач</title>
    </head>
    <body>
        <h1>Результаты самостоятельных задач</h1>
        {% for task_id, rows in latest_submissions.items() %}
            <h2>Задача {{ task_id }}</h2>
            <table border="1">
                <tr>
                    <th>Имя пользователя</th>
                    <th>IP-адрес</th>
                    <th>Код</th>
                    <th>Вывод</th>
                    <th>Время отправки</th>
                </tr>
                {% for row in rows %}
                <tr>
                    <td>{{ row['name'] }}</td>
                    <td>{{ row['ip'] }}</td>
                    <td><pre>{{ row['code'] }}</pre></td>
                    <td>{{ row['output'] }}</td>
                    <td>{{ row['timestamp'] }}</td>
                </tr>
                {% endfor %}
            </table>
        {% endfor %}
        <a href="/">Вернуться на главную</a>
    </body>
    </html>
    """, latest_submissions=latest_submissions)


def render_con_page(tasks, result_message, execution_output, task_description, name):
    """Функция для рендера страницы самостоятельных заданий"""
    return render_template_string("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <title>Самостоятельные задачи</title>
    </head>
    <body>
        <h1>Самостоятельные задачи</h1>
        <form method="POST" action="/con">
            <label>Имя ученика:</label><br>
            <input type="text" name="name" value="{{ name or '' }}" required><br><br>

            <label>Выберите номер задачи:</label><br>
            
            <select name="task" required onchange="this.form.submit()">
                <option value="" disabled selected>Выберите задачу</option>
                {% for task_id, task in tasks.items() %}
                    <option value="{{ task_id }}" {% if task_id == request.form.get('task') %}selected{% endif %}>Задача {{ task_id }}</option>
                {% endfor %}
            </select><br><br>

            {% if task_description %}
            <h3>Условие задачи:</h3>
            <p>{{ task_description }}</p>
            {% endif %}

            <label>Введите ваш код:</label><br>
            <textarea name="code" rows="10" cols="50" required>{{ request.form.get('code') or '' }}</textarea><br><br>

             <!-- Скрытое поле для проверки, была ли нажата кнопка -->
            <input type="hidden" name="submit_action" value="">
            
            <button type="submit" onclick="document.getElementsByName('submit_action')[0].value = 'submit_code'" >Отправить</button>
        </form>

        {% if result_message %}
        <h2>Результат:</h2>
        <p>{{ result_message }}</p>
        {% if execution_output %}
        <h3>Вывод программы:</h3>
        <pre>{{ execution_output }}</pre>
        {% endif %}
        {% endif %}
    </body>
    </html>
    """, tasks=tasks, result_message=result_message, execution_output=execution_output,
                                  task_description=task_description, name=name)


if __name__ == "__main__":
    while True:
        try:
            app.run(host="0.0.0.0", port=5000)
        except Exception as e:
            print(f"Ошибка сервера: {e}. Перезапуск через 2 секунд...")
            time.sleep(2)
