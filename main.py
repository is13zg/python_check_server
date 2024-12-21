from flask import Flask, request, send_from_directory, abort, render_template, jsonify
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

WORK_TIME = True
CON_TIME = False


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


def is_con_time():
    global CON_TIME
    return CON_TIME


def is_work_time():
    global WORK_TIME
    return WORK_TIME


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




# Главная страница
@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    topics = config["tasks"]
    names = config["names"]
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

    if not is_work_time() and not is_local_request():
        abort(403)

    if request.method == "POST":
        name = request.form.get("name").capitalize().strip()
        selected_topic = request.form.get("topic")
        selected_task = request.form.get("task")
        code = request.form.get("code")
        submit_action = request.form.get("submit_action")
        user_ip = request.remote_addr
        current_time = time.time()

        if selected_topic and selected_topic in topics:
            topic_tasks = topics[selected_topic]

        if selected_topic not in topics or selected_task not in topic_tasks:
            result_message = "Неверный номер задачи."
        else:
            task = topic_tasks[selected_task]
            task_description = task["description"]

            expected_output = task["expected_output"]

            if not code or submit_action != 'submit_code':
                return render_template("index.html",
                                       topics=topics,
                                       result_message=result_message,
                                       execution_output=execution_output,
                                       task_description=task_description,
                                       name=name,
                                       selected_topic=selected_topic,
                                       selected_task=selected_task)
            if name not in names:
                result_message = "Введите свое имя, пример: Вася"
                return render_template("index.html",
                                       topics=topics,
                                       result_message=result_message,
                                       execution_output=execution_output,
                                       task_description=task_description,
                                       name=name,
                                       selected_topic=selected_topic,
                                       selected_task=selected_task)

            # Проверка времени последнего запроса
            if user_ip in last_request_time:
                time_since_last_request = current_time - last_request_time[user_ip]
                if time_since_last_request < 5:
                    result_message = f"Слишком частые запросы. Подождите {round(5 - time_since_last_request, 2)} секунд."
                    return render_template("index.html",
                                           topics=topics,
                                           result_message=result_message,
                                           execution_output=execution_output,
                                           task_description=task_description,
                                           name=name,
                                           selected_topic=selected_topic,
                                           selected_task=selected_task)

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
                    status = "✅"
                else:
                    result_message = "Ваш код неверный."
                    status = "❌"
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

    return render_template("index.html",
                           topics=topics,
                           result_message=result_message,
                           execution_output=execution_output,
                           task_description=task_description,
                           name=name,
                           selected_topic=selected_topic,
                           selected_task=selected_task)


# Кастомный фильтр для форматирования даты
@app.template_filter('format_datetime')
def format_datetime(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m %H:%M")
    except ValueError:
        return value

@app.route("/res", methods=["GET"])
def results():
    if not is_local_request():
        abort(403)  # Доступ запрещён

    results = load_results()
    for student, data in results.items():
        data["history"].sort(key=lambda x: x["timestamp"], reverse=True)

    return render_template("results.html", results=results)


# Страница со списком файлов
@app.route("/files", methods=["GET"])
def list_files():
    if not os.path.exists(FILES_FOLDER):
        os.makedirs(FILES_FOLDER)

    files = os.listdir(FILES_FOLDER)
    return render_template("list_files.html", files=files)


@app.route("/res/<name>", methods=["GET"])
def student_results(name):
    results = load_results()
    if name not in results:
        return render_template("student_results.html", name=name, student_data=None)

    student_data = results[name]
    # Сортируем историю по времени в обратном порядке
    sorted_history = sorted(student_data["history"], key=lambda x: x["timestamp"], reverse=True)

    return render_template("student_results.html", name=name, student_data=student_data, sorted_history=sorted_history)


# Скачивание файлов
@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(FILES_FOLDER, filename, as_attachment=True)


@app.route("/info", methods=["GET"])
def info():
    if not is_work_time() and not is_local_request():
        abort(403)
    try:
        # Ищем все файлы, начинающиеся с "info" и заканчивающиеся на ".ipynb"
        info_files = [f for f in os.listdir(INFO_DIRECTORY) if f.startswith("info") and f.endswith(".ipynb")]

        if not info_files:
            return "<h1>Файлы info*.ipynb не найдены.</h1>"

        # Рендерим список доступных файлов
        return render_template("info.html", info_files=info_files)

    except Exception as e:
        return f"<h1>Ошибка при обработке файлов: {str(e)}</h1>"


@app.route("/info/<filename>", methods=["GET"])
def render_info_file(filename):
    if not is_work_time() and not is_local_request():
        abort(403)
    try:
        filepath = os.path.join(INFO_DIRECTORY, filename)

        # Проверяем, существует ли файл
        if not os.path.isfile(filepath):
            return f"<h1>Файл {filename} не найден.</h1>"

        # Читаем содержимое файла
        with open(filepath, "r", encoding="utf-8") as file:
            notebook = nbformat.read(file, as_version=4)

            # Удаляем код в ячейках, содержащих "display(HTML(html_code))"
            for cell in notebook['cells']:
                if cell['cell_type'] == 'code':
                    if "display(HTML(html_code))" in cell.get('source', ''):
                        # Оставляем только вывод ячейки
                        cell['source'] = ""

        # Конвертируем в HTML
        html_exporter = HTMLExporter()
        html_exporter.exclude_input = False  # Показывать или скрывать код
        html_body, _ = html_exporter.from_notebook_node(notebook)

        # Рендерим HTML
        return render_template("info_view.html", filename=filename, html_body=html_body)

    except Exception as e:
        return f"<h1>Ошибка при обработке файла {filename}: {str(e)}</h1>"


@app.route("/con", methods=["GET", "POST"])
def con():
    if not is_con_time() and not is_local_request():
        abort(403)
    config = load_config()
    tasks = config["contask"]
    names = config["names"]
    result_message = None
    execution_output = None
    task_description = None
    task_img = None
    name = None
    task_id = None
    code = None
    submit_action = None
    global last_request_time



    if request.method == "POST":
        name = request.form.get("name").capitalize().strip()
        task_id = request.form.get("task")
        code = request.form.get("code")
        submit_action = request.form.get("submit_action")
        user_ip = request.remote_addr
        current_time = time.time()


        if task_id not in tasks:
            result_message = "Неверный номер задачи."
            return render_template("contest.html", tasks=tasks, result_message=result_message,
                                   execution_output=execution_output, task_description=task_description,
                                   task_img=task_img, name=name)

        task = tasks[task_id]
        task_description = task["description"]
        if "image" in task:
            task_img = task["image"]


        if not code or submit_action != 'submit_code':
            return render_template("contest.html", tasks=tasks, result_message=result_message,
                                   execution_output=execution_output, task_description=task_description,
                                   task_img=task_img, name=name)


        if name not in names:
            result_message = "Введите свое имя, пример: Вася"
            return render_template("contest.html", tasks=tasks, result_message=result_message,
                                   execution_output=execution_output, task_description=task_description,
                                   task_img=task_img, name=name)

            # Проверка времени последнего запроса
        if user_ip in last_request_time:
            time_since_last_request = current_time - last_request_time[user_ip]
            if time_since_last_request < 5:
                result_message = f"Слишком частые запросы. Подождите {round(5 - time_since_last_request, 2)} секунд."
                return render_template("contest.html", tasks=tasks, result_message=result_message,
                                       execution_output=execution_output, task_description=task_description,
                                       task_img=task_img, name=name)

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

    return render_template("contest.html", tasks=tasks, result_message=result_message,
                           execution_output=execution_output, task_description=task_description,
                           task_img=task_img, name=name)


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

    # Определяем время самой последней сдачи для каждой задачи
    latest_task_timestamps = {
        task_id: max(row["timestamp"] for row in rows)
        for task_id, rows in latest_submissions.items()
    }

    # Сортируем задачи по времени последней сдачи в порядке убывания
    sorted_task_ids = sorted(
        latest_task_timestamps.keys(),
        key=lambda task_id: latest_task_timestamps[task_id],
        reverse=True
    )

    # Строим таблицы для каждой задачи
    sorted_latest_submissions = {
        task_id: latest_submissions[task_id]
        for task_id in sorted_task_ids
    }

    return render_template("con_results.html", sorted_latest_submissions=sorted_latest_submissions)


@app.route('/upc', methods=['GET'])
def update_config():
    if not is_local_request():
        abort(403)
    global WORK_TIME, CON_TIME
    # Проверяем и обновляем переменные напрямую
    if 'work' in request.args:
        WORK_TIME = request.args.get('work').lower() in ['true', '1', 'yes']
    if 'con' in request.args:
        CON_TIME = request.args.get('con').lower() in ['true', '1', 'yes']
    return jsonify({
        "status": "success",
        "work": WORK_TIME,
        "con": CON_TIME
    })


if __name__ == "__main__":
    while True:
        try:
            app.run(host="0.0.0.0", port=5000)
        except Exception as e:
            print(f"Ошибка сервера: {e}. Перезапуск через 2 секунд...")
            time.sleep(2)
