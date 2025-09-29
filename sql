
CREATE OR REPLACE PACKAGE C##developer.word_search_pkg AS
    PROCEDURE create_session(
        p_player_id IN NUMBER,
        p_theme_id IN NUMBER,
        p_session_id OUT NUMBER
    );

    PROCEDURE start_level(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_theme_id IN NUMBER,
        p_words_count OUT NUMBER,
        p_field_size OUT NUMBER,
        p_time_limit OUT NUMBER,
        p_words OUT SYS_REFCURSOR,
        p_game_field OUT SYS_REFCURSOR
    );

    PROCEDURE check_word(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_word IN VARCHAR2,
        p_is_valid OUT NUMBER,
        p_word_positions OUT SYS_REFCURSOR
    );

    PROCEDURE save_level_results(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_words_found IN NUMBER,
        p_time_spent IN NUMBER,
        p_result_id OUT NUMBER
    );

    PROCEDURE end_session(
        p_session_id IN NUMBER,
        p_final_score OUT NUMBER
    );
END word_search_pkg;
/

CREATE OR REPLACE PACKAGE BODY C##developer.word_search_pkg AS
    FUNCTION get_random_letter RETURN VARCHAR2 IS
        v_letters CONSTANT VARCHAR2(33 CHAR) := 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ';
    BEGIN
        RETURN SUBSTR(v_letters, TRUNC(DBMS_RANDOM.VALUE(1, 34)), 1);
    END;

    PROCEDURE create_session(
        p_player_id IN NUMBER,
        p_theme_id IN NUMBER,
        p_session_id OUT NUMBER
    ) IS
    BEGIN
        INSERT INTO C##developer.game_sessions (
            session_id, player_id, start_time, theme_id, score
        ) VALUES (
            C##developer.session_seq.NEXTVAL, p_player_id, SYSTIMESTAMP, p_theme_id, 0
        )
        RETURNING session_id INTO p_session_id;
        COMMIT;
    END;

    PROCEDURE start_level(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_theme_id IN NUMBER,
        p_words_count OUT NUMBER,
        p_field_size OUT NUMBER,
        p_time_limit OUT NUMBER,
        p_words OUT SYS_REFCURSOR,
        p_game_field OUT SYS_REFCURSOR
    ) IS
        v_min_word_length NUMBER;
        v_max_word_length NUMBER;
        v_word VARCHAR2(50 CHAR);
        TYPE t_field IS TABLE OF VARCHAR2(1 CHAR) INDEX BY PLS_INTEGER;
        TYPE t_field_matrix IS TABLE OF t_field INDEX BY PLS_INTEGER;
        v_field t_field_matrix;
        v_placed BOOLEAN;
        v_attempts NUMBER;
        v_direction VARCHAR2(20);
        v_row NUMBER;
        v_col NUMBER;
        v_word_len NUMBER;
        v_can_place BOOLEAN;
        v_word_count NUMBER;
        v_temp_words SYS_REFCURSOR;
    BEGIN
        -- Calculate level parameters
        p_words_count := LEAST(3 + p_level, 5);
        v_min_word_length := GREATEST(2, LEAST(2 + FLOOR(p_level / 2), 4));
        p_time_limit := GREATEST(300 - (p_level * 20), 180);

        -- Check available words
        SELECT COUNT(*)
        INTO v_word_count
        FROM C##developer.game_words
        WHERE theme_id = p_theme_id
        AND LENGTH(word) >= v_min_word_length;

        IF v_word_count < p_words_count THEN
            -- Try with smaller words
            v_min_word_length := 2;
            SELECT COUNT(*)
            INTO v_word_count
            FROM C##developer.game_words
            WHERE theme_id = p_theme_id
            AND LENGTH(word) >= v_min_word_length;

            IF v_word_count < p_words_count THEN
                p_words_count := GREATEST(1, v_word_count);
            END IF;
        END IF;

        IF p_words_count = 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Недостаточно слов для выбранной темы');
        END IF;

        -- Get random words for placement
        OPEN v_temp_words FOR
            SELECT word
            FROM C##developer.game_words
            WHERE theme_id = p_theme_id
            AND LENGTH(word) >= v_min_word_length
            ORDER BY DBMS_RANDOM.VALUE
            FETCH FIRST p_words_count ROWS ONLY;

        -- Return words to player
        OPEN p_words FOR
            SELECT word
            FROM C##developer.game_words
            WHERE theme_id = p_theme_id
            AND LENGTH(word) >= v_min_word_length
            ORDER BY DBMS_RANDOM.VALUE
            FETCH FIRST p_words_count ROWS ONLY;

        -- Calculate field size based on actual words
        BEGIN
            SELECT MAX(LENGTH(word))
            INTO v_max_word_length
            FROM (
                SELECT word
                FROM C##developer.game_words
                WHERE theme_id = p_theme_id
                AND LENGTH(word) >= v_min_word_length
                ORDER BY DBMS_RANDOM.VALUE
                FETCH FIRST p_words_count ROWS ONLY
            );
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                v_max_word_length := 6;
        END;

        p_field_size := GREATEST(v_max_word_length + 3, 8, p_words_count + 2);

        -- Initialize field with random letters
        FOR i IN 1..p_field_size LOOP
            FOR j IN 1..p_field_size LOOP
                IF v_field.EXISTS(i) THEN
                    v_field(i)(j) := get_random_letter();
                ELSE
                    v_field(i) := t_field();
                    v_field(i)(j) := get_random_letter();
                END IF;
            END LOOP;
        END LOOP;

        -- Place words in the field
        LOOP
            FETCH v_temp_words INTO v_word;
            EXIT WHEN v_temp_words%NOTFOUND;

            v_word := UPPER(TRIM(v_word));
            v_word_len := LENGTH(v_word);
            v_placed := FALSE;
            v_attempts := 0;

            WHILE NOT v_placed AND v_attempts < 100 LOOP
                v_attempts := v_attempts + 1;
                v_direction := CASE TRUNC(DBMS_RANDOM.VALUE(1, 5))
                    WHEN 1 THEN 'horizontal'
                    WHEN 2 THEN 'vertical' 
                    WHEN 3 THEN 'diagonal_down'
                    WHEN 4 THEN 'diagonal_up'
                END;

                IF v_direction = 'horizontal' THEN
                    v_row := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size + 1));
                    v_col := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                    v_can_place := TRUE;

                    FOR i IN 0..v_word_len-1 LOOP
                        IF v_col + i > p_field_size THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                        IF v_field(v_row).EXISTS(v_col + i) AND 
                           v_field(v_row)(v_col + i) != SUBSTR(v_word, i + 1, 1) THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                    END LOOP;

                    IF v_can_place THEN
                        FOR i IN 0..v_word_len-1 LOOP
                            v_field(v_row)(v_col + i) := SUBSTR(v_word, i + 1, 1);
                        END LOOP;
                        v_placed := TRUE;
                    END IF;

                ELSIF v_direction = 'vertical' THEN
                    v_row := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                    v_col := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size + 1));
                    v_can_place := TRUE;

                    FOR i IN 0..v_word_len-1 LOOP
                        IF v_row + i > p_field_size THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                        IF v_field(v_row + i).EXISTS(v_col) AND 
                           v_field(v_row + i)(v_col) != SUBSTR(v_word, i + 1, 1) THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                    END LOOP;

                    IF v_can_place THEN
                        FOR i IN 0..v_word_len-1 LOOP
                            v_field(v_row + i)(v_col) := SUBSTR(v_word, i + 1, 1);
                        END LOOP;
                        v_placed := TRUE;
                    END IF;

                ELSIF v_direction = 'diagonal_down' THEN
                    v_row := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                    v_col := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                    v_can_place := TRUE;

                    FOR i IN 0..v_word_len-1 LOOP
                        IF v_row + i > p_field_size OR v_col + i > p_field_size THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                        IF v_field(v_row + i).EXISTS(v_col + i) AND 
                           v_field(v_row + i)(v_col + i) != SUBSTR(v_word, i + 1, 1) THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                    END LOOP;

                    IF v_can_place THEN
                        FOR i IN 0..v_word_len-1 LOOP
                            v_field(v_row + i)(v_col + i) := SUBSTR(v_word, i + 1, 1);
                        END LOOP;
                        v_placed := TRUE;
                    END IF;

                ELSIF v_direction = 'diagonal_up' THEN
                    v_row := TRUNC(DBMS_RANDOM.VALUE(v_word_len, p_field_size));
                    v_col := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                    v_can_place := TRUE;

                    FOR i IN 0..v_word_len-1 LOOP
                        IF v_row - i < 1 OR v_col + i > p_field_size THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                        IF v_field(v_row - i).EXISTS(v_col + i) AND 
                           v_field(v_row - i)(v_col + i) != SUBSTR(v_word, i + 1, 1) THEN
                            v_can_place := FALSE;
                            EXIT;
                        END IF;
                    END LOOP;

                    IF v_can_place THEN
                        FOR i IN 0..v_word_len-1 LOOP
                            v_field(v_row - i)(v_col + i) := SUBSTR(v_word, i + 1, 1);
                        END LOOP;
                        v_placed := TRUE;
                    END IF;
                END IF;
            END LOOP;

            -- Force placement if couldn't place normally
            IF NOT v_placed THEN
                v_row := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size + 1));
                v_col := TRUNC(DBMS_RANDOM.VALUE(1, p_field_size - v_word_len + 2));
                IF v_col + v_word_len - 1 <= p_field_size THEN
                    FOR i IN 0..v_word_len-1 LOOP
                        v_field(v_row)(v_col + i) := SUBSTR(v_word, i + 1, 1);
                    END LOOP;
                END IF;
            END IF;
        END LOOP;

        CLOSE v_temp_words;

        -- Fill remaining empty cells
        FOR i IN 1..p_field_size LOOP
            FOR j IN 1..p_field_size LOOP
                IF NOT v_field(i).EXISTS(j) OR v_field(i)(j) IS NULL THEN
                    v_field(i)(j) := get_random_letter();
                END IF;
            END LOOP;
        END LOOP;

        -- Clear previous field and store new one
        DELETE FROM C##developer.game_field 
        WHERE session_id = p_session_id AND level_number = p_level;

        FOR i IN 1..p_field_size LOOP
            FOR j IN 1..p_field_size LOOP
                INSERT INTO C##developer.game_field (
                    field_id, session_id, level_number, row_num, col_num, letter
                ) VALUES (
                    C##developer.field_seq.NEXTVAL, p_session_id, p_level, i, j,
                    v_field(i)(j)
                );
            END LOOP;
        END LOOP;

        COMMIT;

        -- Return game field
        OPEN p_game_field FOR
            SELECT row_num, col_num, letter
            FROM C##developer.game_field
            WHERE session_id = p_session_id
            AND level_number = p_level
            ORDER BY row_num, col_num;

    EXCEPTION
        WHEN OTHERS THEN
            IF v_temp_words%ISOPEN THEN
                CLOSE v_temp_words;
            END IF;
            RAISE;
    END;

    PROCEDURE check_word(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_word IN VARCHAR2,
        p_is_valid OUT NUMBER,
        p_word_positions OUT SYS_REFCURSOR
    ) IS
        v_count NUMBER;
        v_word_upper VARCHAR2(100) := UPPER(TRIM(p_word));
        v_word_len NUMBER := LENGTH(v_word_upper);
    BEGIN
        p_is_valid := 0;

        -- Check if word exists in theme
        SELECT COUNT(*)
        INTO v_count
        FROM C##developer.game_words w
        JOIN C##developer.game_sessions s ON w.theme_id = s.theme_id
        WHERE s.session_id = p_session_id
        AND UPPER(w.word) = v_word_upper;

        IF v_count = 0 THEN
            RETURN;
        END IF;

        p_is_valid := 1;

        -- Find word positions using simpler approach
        OPEN p_word_positions FOR
            WITH field_data AS (
                SELECT row_num, col_num, letter,
                       session_id, level_number
                FROM C##developer.game_field
                WHERE session_id = p_session_id
                AND level_number = p_level
            )
            -- Horizontal
            SELECT row_num, col_num
            FROM field_data
            WHERE (row_num, col_num) IN (
                SELECT f.row_num, f.col_num
                FROM field_data f
                CONNECT BY PRIOR row_num = row_num 
                       AND PRIOR col_num = col_num - 1
                       AND LEVEL <= v_word_len
                GROUP BY f.row_num, f.col_num
                HAVING LISTAGG(letter, '') WITHIN GROUP (ORDER BY col_num) = v_word_upper
                   AND COUNT(*) = v_word_len
            )
            UNION ALL
            -- Vertical
            SELECT row_num, col_num
            FROM field_data
            WHERE (row_num, col_num) IN (
                SELECT f.row_num, f.col_num
                FROM field_data f
                CONNECT BY PRIOR row_num = row_num - 1 
                       AND PRIOR col_num = col_num
                       AND LEVEL <= v_word_len
                GROUP BY f.row_num, f.col_num
                HAVING LISTAGG(letter, '') WITHIN GROUP (ORDER BY row_num) = v_word_upper
                   AND COUNT(*) = v_word_len
            );

    EXCEPTION
        WHEN OTHERS THEN
            p_is_valid := 0;
            OPEN p_word_positions FOR 
                SELECT 1 as row_num, 1 as col_num FROM DUAL WHERE 1 = 0;
    END;

    PROCEDURE save_level_results(
        p_session_id IN NUMBER,
        p_level IN NUMBER,
        p_words_found IN NUMBER,
        p_time_spent IN NUMBER,
        p_result_id OUT NUMBER
    ) IS
    BEGIN
        INSERT INTO C##developer.game_level_results (
            result_id, session_id, level_number, words_found, time_spent
        ) VALUES (
            C##developer.result_seq.NEXTVAL,
            p_session_id,
            p_level,
            p_words_found,
            p_time_spent
        )
        RETURNING result_id INTO p_result_id;
        COMMIT;
    END;

    PROCEDURE end_session(
        p_session_id IN NUMBER,
        p_final_score OUT NUMBER
    ) IS
    BEGIN
        UPDATE C##developer.game_sessions
        SET end_time = SYSTIMESTAMP,
            score = NVL((
                SELECT SUM(words_found * 100 - time_spent)
                FROM C##developer.game_level_results
                WHERE session_id = p_session_id
            ), 0)
        WHERE session_id = p_session_id
        RETURNING score INTO p_final_score;
        COMMIT;
    END;
END word_search_pkg;
