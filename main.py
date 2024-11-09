from flask import Flask, request, render_template_string, send_from_directory
import json
import subprocess
import os
from datetime import datetime
import time
import nbformat
from nbconvert import HTMLExporter

app = Flask(__name__)

# Константы
CONFIG_FILE = "config.json"
RESULTS_FILE = "results.json"
FILES_FOLDER = "files"
INFO_FILE = "info.ipynb"  # Файл, который нужно отображать


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
            timeout=5  # Таймаут 5 секунд
        )
        os.remove(temp_filename)
        return {"stdout": result.stdout, "stderr": result.stderr, "success": result.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"error": "Превышено время выполнения кода. Проверьте, нет ли бесконечного цикла."}
    except Exception as e:
        return {"error": str(e)}


# Главная страница
@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    tasks = config["tasks"]
    result_message = None
    execution_output = None
    task_description = None
    name = None
    task_id = None
    code = None

    if request.method == "POST":
        name = request.form.get("name")
        task_id = request.form.get("task")
        code = request.form.get("code")
        user_ip = request.remote_addr

        if task_id not in tasks:
            result_message = "Неверный номер задачи."
        else:
            task = tasks[task_id]
            task_description = task["description"]
            expected_output = task["expected_output"]

            execution_result = execute_code(code)
            if "error" in execution_result:
                result_message = execution_result["error"]
            elif execution_result["stderr"]:
                result_message = "Ошибка в коде."
                execution_output = execution_result["stderr"]
            else:
                if execution_result["stdout"] == expected_output+"\n":
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
                results[name]["tasks"][task_id] = status
                results[name]["history"].append({
                    "task_id": task_id,
                    "code": code,
                    "result": status,
                    "timestamp": datetime.now().isoformat(),
                    "ip":user_ip
                })

                save_results(results)

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

            <button type="submit">Отправить</button>
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


@app.route("/results", methods=["GET"])
def results():
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
            </tr>
            {% for name, data in results.items() %}
                <tr>
                    <td>{{ name }}</td>
                    <td>
                        {% for task_id, status in data['tasks'].items() %}
                            Задача {{ task_id }}: {{ status }}<br>
                        {% endfor %}
                    </td>
                    <td><a href="/results/{{ name }}">{{ name }}</a></td>
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

@app.route("/results/<name>", methods=["GET"])
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
            <a href="/results">Вернуться к общим результатам</a>
        </body>
        </html>
        """, name=name)

    student_data = results[name]
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
            {% for attempt in student_data['history'] %}
                <tr>
                    <td>{{ attempt['task_id'] }}</td>
                    <td><pre>{{ attempt['code'] }}</pre></td>
                    <td>{{ attempt['result'] }}</td>
                    <td>{{ attempt['timestamp'] }}</td>
                    <td>{{ attempt['ip'] }}</td>
                </tr>
            {% endfor %}
        </table>
        <a href="/results">Вернуться к общим результатам</a>
    </body>
    </html>
    """, name=name, student_data=student_data)


# Скачивание файлов
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(FILES_FOLDER, filename, as_attachment=True)

# Страница info
@app.route("/info", methods=["GET"])
def info():
    try:
        with open(INFO_FILE, "r", encoding="utf-8") as file:
            notebook = nbformat.read(file, as_version=4)

        html_exporter = HTMLExporter()
        html_exporter.exclude_input = False  # Показывать или скрывать код
        html_body, _ = html_exporter.from_notebook_node(notebook)

        return render_template_string("""
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>Просмотр info.ipynb</title>
        </head>
        <body>
            <h1>Просмотр файла info.ipynb</h1>
            <div>{{ html_body|safe }}</div>
            <a href="/">Вернуться на главную</a>
        </body>
        </html>
        """, html_body=html_body)
    except FileNotFoundError:
        return "<h1>Файл info.ipynb не найден.</h1>"


if __name__ == "__main__":
    while True:
        try:
            app.run(host="0.0.0.0", port=5000)
        except Exception as e:
            print(f"Ошибка сервера: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)
