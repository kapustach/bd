import oracledb
import tkinter as tk
from tkinter import messagebox
import time
import logging

# Настройка логирования
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


class WordSearchGame:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Игра 'Найди слова'")
        self.root.geometry("900x700")

        self.conn = None
        self.cursor = None
        self.db_connect()

        self.current_player_id = None
        self.current_session_id = None
        self.current_level = 1
        self.words_to_find = []
        self.found_words = []
        self.game_field = []
        self.time_left = 0
        self.start_time = 0
        self.field_size = 0
        self.selected_theme_id = None
        self.max_levels = 5

        self.cell_labels = []
        self.words_listbox = None
        self.word_entry = None
        self.time_label = None
        self.timer_id = None
        self.selected_cells = []
        self.current_selection = []

        self.show_main_menu()

    def db_connect(self):
        try:
            self.conn = oracledb.connect(
                user="C##developer",
                password="1234",
                dsn="localhost:1521/XE"
            )
            self.cursor = self.conn.cursor()
            logging.info("Подключение к базе данных установлено")
        except Exception as e:
            messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к БД:\n{str(e)}")
            logging.error(f"Ошибка подключения к БД: {str(e)}")
            self.root.destroy()

    def show_main_menu(self):
        self.clear_window()
        tk.Label(self.root, text="Добро пожаловать в игру 'Найди слова'",
                 font=("Arial", 16)).pack(pady=20)
        tk.Label(self.root, text="Введите ваше имя:").pack()
        self.player_name_entry = tk.Entry(self.root, width=30)
        self.player_name_entry.pack(pady=5)
        tk.Button(self.root, text="Начать игру", command=self.handle_player_login).pack(pady=20)
        tk.Button(self.root, text="Топ игроков", command=self.show_top_players).pack(pady=10)
        tk.Button(self.root, text="Выход", command=self.root.quit).pack(pady=10)

    def handle_player_login(self):
        player_name = self.player_name_entry.get().strip()
        if not player_name:
            messagebox.showwarning("Ошибка", "Введите имя игрока")
            return

        try:
            self.cursor.execute("""
                SELECT player_id FROM C##developer.game_players 
                WHERE UPPER(player_name) = UPPER(:name)
            """, name=player_name)
            result = self.cursor.fetchone()
            if result:
                self.current_player_id = result[0]
                messagebox.showinfo("Добро пожаловать", f"С возвращением, {player_name}!")
                logging.info(f"Игрок {player_name} вошел с ID {self.current_player_id}")
            else:
                out_var = self.cursor.var(oracledb.NUMBER)
                self.cursor.execute("""
                    INSERT INTO C##developer.game_players (player_id, player_name)
                    VALUES (C##developer.player_seq.NEXTVAL, :name)
                    RETURNING player_id INTO :out_var
                """, name=player_name, out_var=out_var)
                self.current_player_id = int(out_var.getvalue()[0])
                self.conn.commit()
                messagebox.showinfo("Регистрация", f"Игрок {player_name} зарегистрирован!")
                logging.info(f"Игрок {player_name} зарегистрирован с ID {self.current_player_id}")
            self.show_theme_selection()
        except oracledb.Error as e:
            messagebox.showerror("Ошибка БД", f"Ошибка при регистрации:\n{str(e)}")
            logging.error(f"Ошибка входа/регистрации: {str(e)}")

    def show_theme_selection(self):
        self.clear_window()
        tk.Label(self.root, text="Выберите тему:", font=("Arial", 14)).pack(pady=20)
        try:
            self.cursor.execute("""
                SELECT t.theme_id, t.theme_name, COUNT(w.word) as word_count
                FROM C##developer.game_themes t
                LEFT JOIN C##developer.game_words w ON t.theme_id = w.theme_id
                GROUP BY t.theme_id, t.theme_name
                HAVING COUNT(w.word) >= 3
                ORDER BY t.theme_name
            """)
            themes = self.cursor.fetchall()

            if not themes:
                messagebox.showerror("Ошибка", "Нет доступных тем с достаточным количеством слов!")
                self.show_main_menu()
                return

            for theme_id, theme_name, word_count in themes:
                btn_text = f"{theme_name} ({word_count} слов)"
                tk.Button(
                    self.root,
                    text=btn_text,
                    command=lambda tid=theme_id: self.start_new_game(tid),
                    width=25, height=2
                ).pack(pady=5)

            tk.Button(self.root, text="Назад", command=self.show_main_menu).pack(pady=20)
            logging.info(f"Загружено {len(themes)} тем")

        except oracledb.Error as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить темы:\n{str(e)}")
            logging.error(f"Ошибка загрузки тем: {str(e)}")

    def start_new_game(self, theme_id):
        self.selected_theme_id = theme_id
        try:
            logging.info(f"Начинаем новую игру для темы ID: {theme_id}")

            out_var = self.cursor.var(oracledb.NUMBER)
            self.cursor.callproc("C##developer.word_search_pkg.create_session",
                                 [int(self.current_player_id), int(theme_id), out_var])
            self.current_session_id = int(out_var.getvalue())
            self.current_level = 1
            logging.info(f"Создана игровая сессия ID: {self.current_session_id}")
            self.start_level()

        except oracledb.Error as e:
            error_msg = str(e)
            logging.error(f"Ошибка начала игры: {error_msg}")
            messagebox.showerror("Ошибка", f"Не удалось начать игру:\n{error_msg}")
            self.show_main_menu()

    def start_level(self):
        self.clear_window()
        self.start_time = time.time()
        self.selected_cells = []
        self.current_selection = []

        try:
            words_count_var = self.cursor.var(oracledb.NUMBER)
            field_size_var = self.cursor.var(oracledb.NUMBER)
            time_limit_var = self.cursor.var(oracledb.NUMBER)
            words_cursor = self.cursor.var(oracledb.CURSOR)
            field_cursor = self.cursor.var(oracledb.CURSOR)

            logging.info(f"Запуск уровня {self.current_level}")

            self.cursor.callproc("C##developer.word_search_pkg.start_level",
                                 [self.current_session_id, self.current_level, self.selected_theme_id,
                                  words_count_var, field_size_var, time_limit_var,
                                  words_cursor, field_cursor])

            self.field_size = int(field_size_var.getvalue())
            self.time_left = int(time_limit_var.getvalue())
            words_count = int(words_count_var.getvalue())

            # Получаем слова
            words_result = words_cursor.getvalue()
            if words_result:
                self.words_to_find = [row[0].upper() for row in words_result]
            else:
                self.words_to_find = []

            self.found_words = []

            # Создаем игровое поле
            self.game_field = [['' for _ in range(self.field_size)] for _ in range(self.field_size)]

            # Заполняем поле из базы данных
            field_data = field_cursor.getvalue()
            if field_data:
                for row in field_data:
                    row_num, col_num, letter = row
                    if 1 <= row_num <= self.field_size and 1 <= col_num <= self.field_size:
                        self.game_field[row_num - 1][col_num - 1] = letter
            else:
                logging.error("Не удалось получить игровое поле из базы данных")
                messagebox.showerror("Ошибка", "Не удалось сгенерировать игровое поле!")
                self.show_main_menu()
                return

            logging.info(
                f"Уровень {self.current_level} запущен: {words_count} слов, поле {self.field_size}x{self.field_size}")
            self.display_game_interface()
            self.update_timer()

        except oracledb.Error as e:
            error_msg = str(e)
            logging.error(f"Ошибка запуска уровня: {error_msg}")
            messagebox.showerror("Ошибка", f"Ошибка при запуске уровня:\n{error_msg}")
            self.cancel_timer()
            self.show_main_menu()

    def display_game_interface(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Левая часть - игровое поле
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(left_frame, text=f"Уровень {self.current_level}",
                 font=("Arial", 16, "bold")).pack(pady=10)

        # Контейнер для поля с прокруткой если нужно
        field_container = tk.Frame(left_frame)
        field_container.pack(pady=10)

        self.cell_labels = []
        for i in range(self.field_size):
            row_labels = []
            for j in range(self.field_size):
                cell_text = self.game_field[i][j]
                cell = tk.Label(field_container, text=cell_text, width=3, height=1,
                                relief="raised", font=("Arial", 14, "bold"),
                                borderwidth=2, bg="white")
                cell.grid(row=i, column=j, padx=2, pady=2)
                cell.bind("<Button-1>", lambda e, row=i, col=j: self.select_cell(row, col))
                cell.bind("<B1-Motion>", lambda e, row=i, col=j: self.select_cell(row, col))
                row_labels.append(cell)
            self.cell_labels.append(row_labels)

        # Правая часть - управление
        right_frame = tk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=20)

        tk.Label(right_frame, text="Слова для поиска:",
                 font=("Arial", 12, "bold")).pack(pady=10)

        # Список слов с прокруткой
        words_frame = tk.Frame(right_frame)
        words_frame.pack(fill=tk.BOTH, expand=True)

        self.words_listbox = tk.Listbox(words_frame, width=20, height=12,
                                        font=("Arial", 11))
        scrollbar = tk.Scrollbar(words_frame, orient=tk.VERTICAL)
        self.words_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.words_listbox.yview)

        self.words_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for word in self.words_to_find:
            self.words_listbox.insert(tk.END, word)

        # Выделенное слово
        selected_word_frame = tk.Frame(right_frame)
        selected_word_frame.pack(pady=10)
        tk.Label(selected_word_frame, text="Выделено:", font=("Arial", 11)).pack()
        self.selected_word_label = tk.Label(selected_word_frame, text="",
                                            font=("Arial", 12, "bold"), fg="blue")
        self.selected_word_label.pack()

        # Кнопки
        button_frame = tk.Frame(right_frame)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Проверить слово",
                  command=self.check_selected_word,
                  font=("Arial", 11), bg="#4CAF50", fg="white").pack(pady=5)

        tk.Button(button_frame, text="Сбросить выделение",
                  command=self.clear_selection,
                  font=("Arial", 10)).pack(pady=2)

        # Таймер
        self.time_label = tk.Label(right_frame,
                                   text=f"Осталось: {self.time_left // 60}:{self.time_left % 60:02d}",
                                   font=("Arial", 14, "bold"), fg="red")
        self.time_label.pack(pady=10)

        # Кнопка выхода
        tk.Button(right_frame, text="Завершить игру",
                  command=self.exit_game,
                  bg="#FF6B6B", fg="white",
                  font=("Arial", 10)).pack(pady=20)

    def select_cell(self, row, col):
        if (row, col) not in self.current_selection:
            self.current_selection.append((row, col))
            self.cell_labels[row][col].config(bg="lightblue")
            self.update_selected_word()

    def clear_selection(self):
        for row, col in self.current_selection:
            self.cell_labels[row][col].config(bg="white")
        self.current_selection = []
        self.selected_word_label.config(text="")

    def update_selected_word(self):
        word = ""
        for row, col in self.current_selection:
            word += self.game_field[row][col]
        self.selected_word_label.config(text=word)

    def check_selected_word(self):
        if not self.current_selection:
            messagebox.showwarning("Ошибка", "Выделите слово на поле!")
            return

        word = self.selected_word_label.cget("text")
        if not word:
            return

        word = word.upper()

        if word in self.found_words:
            messagebox.showinfo("Уже найдено", "Вы уже нашли это слово!")
            self.clear_selection()
            return

        if word not in self.words_to_find:
            messagebox.showinfo("Не найдено", f"Слово '{word}' не в списке!")
            self.clear_selection()
            return

        try:
            is_valid_var = self.cursor.var(oracledb.NUMBER)
            positions_cursor = self.cursor.var(oracledb.CURSOR)

            self.cursor.callproc("C##developer.word_search_pkg.check_word",
                                 [self.current_session_id, self.current_level, word,
                                  is_valid_var, positions_cursor])

            is_valid = is_valid_var.getvalue()

            if is_valid == 1:
                self.found_words.append(word)

                # Подсвечиваем найденное слово
                for row, col in self.current_selection:
                    self.cell_labels[row][col].config(bg="lightgreen")
                self.selected_cells.extend(self.current_selection)

                # Обновляем список слов
                for i, w in enumerate(self.words_to_find):
                    if w == word:
                        self.words_listbox.delete(i)
                        self.words_listbox.insert(i, f"✓ {word}")
                        self.words_listbox.itemconfig(i, {'fg': 'green'})
                        break

                messagebox.showinfo("Успех", f"Слово '{word}' найдено!")
                self.current_selection = []
                self.selected_word_label.config(text="")

                # Проверяем завершение уровня
                if len(self.found_words) == len(self.words_to_find):
                    self.cancel_timer()
                    self.level_completed()
            else:
                messagebox.showinfo("Не найдено", f"Слово '{word}' не найдено на поле!")
                self.clear_selection()

        except oracledb.Error as e:
            messagebox.showerror("Ошибка", f"Ошибка проверки слова:\n{str(e)}")
            self.clear_selection()

    def level_completed(self):
        time_spent = int(time.time() - self.start_time)
        try:
            result_id_var = self.cursor.var(oracledb.NUMBER)
            self.cursor.callproc("C##developer.word_search_pkg.save_level_results",
                                 [self.current_session_id, self.current_level,
                                  len(self.found_words), time_spent, result_id_var])
            self.conn.commit()

            messagebox.showinfo("Уровень завершен",
                                f"Найдено слов: {len(self.found_words)} из {len(self.words_to_find)}\n"
                                f"Время: {time_spent} сек")

            if self.current_level < self.max_levels:
                self.current_level += 1
                self.start_level()
            else:
                self.end_game("Поздравляем! Вы прошли все уровни!")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка сохранения: {str(e)}")
            self.show_main_menu()

    def exit_game(self):
        if messagebox.askyesno("Подтверждение", "Завершить игру и вернуться в меню?"):
            self.cancel_timer()
            self.show_main_menu()

    def update_timer(self):
        if self.time_left > 0:
            mins, secs = divmod(self.time_left, 60)
            self.time_label.config(text=f"Осталось: {mins}:{secs:02d}")
            self.time_left -= 1
            self.timer_id = self.root.after(1000, self.update_timer)
        else:
            self.level_completed()

    def cancel_timer(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None

    def end_game(self, message):
        try:
            final_score_var = self.cursor.var(oracledb.NUMBER)
            self.cursor.callproc("C##developer.word_search_pkg.end_session",
                                 [self.current_session_id, final_score_var])
            score = final_score_var.getvalue() or 0

            messagebox.showinfo("Игра завершена", f"{message}\nФинальный счет: {score}")
            self.show_main_menu()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка завершения: {str(e)}")
            self.show_main_menu()

    def clear_window(self):
        self.cancel_timer()
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_top_players(self):
        self.clear_window()
        tk.Label(self.root, text="Топ игроков", font=("Arial", 16)).pack(pady=20)

        try:
            self.cursor.execute("""
                SELECT p.player_name, MAX(s.score) as max_score
                FROM C##developer.game_players p
                JOIN C##developer.game_sessions s ON p.player_id = s.player_id
                WHERE s.score IS NOT NULL
                GROUP BY p.player_name
                ORDER BY max_score DESC
                FETCH FIRST 10 ROWS ONLY
            """)
            players = self.cursor.fetchall()

            if players:
                for i, (name, score) in enumerate(players, 1):
                    tk.Label(self.root, text=f"{i}. {name}: {score} очков",
                             font=("Arial", 12)).pack()
            else:
                tk.Label(self.root, text="Пока нет результатов",
                         font=("Arial", 12)).pack()

        except oracledb.Error as e:
            tk.Label(self.root, text="Ошибка загрузки рейтинга",
                     font=("Arial", 12), fg="red").pack()

        tk.Button(self.root, text="Назад", command=self.show_main_menu,
                  font=("Arial", 12)).pack(pady=20)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()


if __name__ == "__main__":
    game = WordSearchGame()
    game.run()
