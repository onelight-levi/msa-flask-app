@app.route('/diary')
@app.route('/diary/<int:year>/<int:month>')
def diary_calendar(year=None, month=None):
    """사용자별 월 달력을 표시하고 일기 기록 여부를 나타냅니다."""
    if 'loggedin' not in session:
        flash('일기장을 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    today = datetime.now()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    if not (1 <= month <= 12 and 1900 <= year <= 2100):
        flash('유효하지 않은 연도 또는 월입니다.', 'error')
        return redirect(url_for('diary_calendar'))

    prev_month_date = (datetime(year, month, 1) - timedelta(days=1)).replace(day=1)
    next_month_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1)

    prev_year, prev_month = prev_month_date.year, prev_month_date.month
    next_year, next_month = next_month_date.year, next_month_date.month

    cal = calendar.Calendar(firstweekday=6) # 일요일부터 시작
    month_days = cal.monthdayscalendar(year, month)

    user_id = session['id']
    diary_dates = set()

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT DATE_FORMAT(entry_date, '%%Y-%%m-%%d') AS entry_date_str FROM diaries WHERE user_id = %s AND YEAR(entry_date) = %s AND MONTH(entry_date) = %s"
            cursor.execute(sql, (user_id, year, month))
            for row in cursor.fetchall():
                diary_dates.add(row['entry_date_str'])
    except Exception as e:
        print(f"DEBUG: 일기 데이터를 불러오는 데 오류 발생: {e}")
        flash('일기 데이터를 불러오는 데 실패했습니다.', 'error')
    finally:
        if conn:
            conn.close()

    return render_template('diary_calendar.html',
                           year=year,
                           month=month,
                           month_name=datetime(year, month, 1).strftime('%B'),
                           month_days=month_days,
                           diary_dates=diary_dates,
                           prev_year=prev_year,
                           prev_month=prev_month,
                           next_year=next_year,
                           next_month=next_month,
                           current_day=today.day if today.year == year and today.month == month else None,
                           today=today,
                           username=session['username'])

@app.route('/diary/entry/<string:date_str>', methods=['GET', 'POST'])
def diary_entry(date_str):
    """특정 날짜의 일기를 작성/조회/수정합니다."""
    if 'loggedin' not in session:
        flash('일기를 작성/조회하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    entry_date = None
    try:
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('유효하지 않은 날짜 형식입니다.', 'error')
        return redirect(url_for('diary_calendar'))

    diary = None
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT id, title, content, DATE_FORMAT(entry_date, '%%Y-%%m-%%d') AS entry_date_str FROM diaries WHERE user_id = %s AND entry_date = %s"
            cursor.execute(sql, (user_id, entry_date))
            diary = cursor.fetchone()

        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            content = request.form['content'].strip()

            if not content:
                flash('일기 내용은 비워둘 수 없습니다.', 'error')
                return redirect(url_for('diary_entry', date_str=date_str))

            with conn.cursor() as cursor:
                if diary: # 기존 일기 수정
                    sql = "UPDATE diaries SET title = %s, content = %s WHERE id = %s AND user_id = %s"
                    cursor.execute(sql, (title, content, diary['id'], user_id))
                    flash('일기가 성공적으로 수정되었습니다!', 'success')
                else: # 새 일기 작성
                    sql = "INSERT INTO diaries (user_id, entry_date, title, content) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (user_id, entry_date, title, content))
                    flash('일기가 성공적으로 작성되었습니다!', 'success')
            conn.commit()
            return redirect(url_for('diary_calendar', year=entry_date.year, month=entry_date.month))

    except Exception as e:
        print(f"DEBUG: diary_entry에서 데이터베이스 오류: {e}")
        flash('일기 처리 중 오류가 발생했습니다.', 'error')
    finally:
        if conn:
            conn.close()

    return render_template('diary_entry.html', diary=diary, date_str=date_str, username=session['username'])


# --- To-Do List 관련 라우트 ---

@app.route('/todos')
def todos_list():
    """To-Do 목록을 표시하고 필터링 옵션을 제공합니다."""
    if 'loggedin' not in session:
        flash('To-Do List를 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    status_filter = request.args.get('status', 'all').strip() # 'all' 또는 특정 상태 (예: '미완료')
    search_query = request.args.get('query', '').strip() # 검색어

    conn = None
    todos = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # due_date를 YYYY-MM-DD 형식의 문자열로 가져오도록 수정
            sql = "SELECT id, task, DATE_FORMAT(due_date, '%%Y-%%m-%%d') AS due_date, status, created_at FROM todos WHERE user_id = %s"
            params = [user_id]

            if status_filter != 'all':
                sql += " AND status = %s"
                params.append(status_filter)

            if search_query:
                sql += " AND task LIKE %s"
                params.append(f"%{search_query}%")

            sql += " ORDER BY created_at DESC" # 또는 due_date ASC

            cursor.execute(sql, params)
            todos = cursor.fetchall()
    except Exception as e:
        print(f"DEBUG: To-Do 목록 불러오기 오류: {e}")
        flash('To-Do 목록을 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()

    return render_template('todos_list.html',
                           todos=todos,
                           username=session['username'],
                           status_filter=status_filter,
                           search_query=search_query,
                           all_statuses=['미완료', '진행중', '완료', '기간연장'])


@app.route('/todos/add', methods=['POST'])
def add_todo():
    """새 To-Do 항목을 추가합니다."""
    if 'loggedin' not in session:
        flash('To-Do 항목을 추가하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    task = request.form['task'].strip()
    due_date_str = request.form.get('due_date', '').strip()
    status = request.form.get('status', '미완료').strip() # 기본 상태 '미완료'

    if not task:
        flash('할 일 내용을 비워둘 수 없습니다.', 'error')
        return redirect(url_for('todos_list'))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('유효하지 않은 마감일 형식입니다.', 'error')
            return redirect(url_for('todos_list'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "INSERT INTO todos (user_id, task, due_date, status) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (user_id, task, due_date, status))
        conn.commit()
        flash('To-Do 항목이 성공적으로 추가되었습니다!', 'success')
    except Exception as e:
        print(f"DEBUG: To-Do 항목 추가 오류: {e}")
        flash('To-Do 항목 추가에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('todos_list'))

@app.route('/todos/update_status/<int:todo_id>/<string:new_status>', methods=['POST'])
def update_todo_status(todo_id, new_status):
    """To-Do 항목의 상태를 업데이트합니다."""
    if 'loggedin' not in session:
        flash('To-Do 항목 상태를 변경하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    valid_statuses = ['미완료', '진행중', '완료', '기간연장'] # 모든 유효 상태 포함

    if new_status not in valid_statuses:
        flash('유효하지 않은 To-Do 상태입니다.', 'error')
        return redirect(url_for('todos_list'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 해당 사용자의 To-Do 항목인지 확인
            sql_check = "SELECT id FROM todos WHERE id = %s AND user_id = %s"
            cursor.execute(sql_check, (todo_id, user_id))
            if not cursor.fetchone():
                flash('To-Do 항목을 찾을 수 없거나 권한이 없습니다.', 'error')
                return redirect(url_for('todos_list'))

            sql = "UPDATE todos SET status = %s WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (new_status, todo_id, user_id))
        conn.commit()
        flash('To-Do 항목 상태가 성공적으로 업데이트되었습니다!', 'success')
    except Exception as e:
        print(f"DEBUG: To-Do 상태 업데이트 오류: {e}")
        flash('To-Do 항목 상태 업데이트에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('todos_list'))

@app.route('/todos/delete/<int:todo_id>', methods=['POST'])
def delete_todo(todo_id):
    """To-Do 항목을 삭제합니다."""
    if 'loggedin' not in session:
        flash('To-Do 항목을 삭제하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 해당 사용자의 To-Do 항목인지 확인
            sql_check = "SELECT id FROM todos WHERE id = %s AND user_id = %s"
            cursor.execute(sql_check, (todo_id, user_id))
            if not cursor.fetchone():
                flash('To-Do 항목을 찾을 수 없거나 권한이 없습니다.', 'error')
                return redirect(url_for('todos_list'))

            sql = "DELETE FROM todos WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (todo_id, user_id))
        conn.commit()
        flash('To-Do 항목이 성공적으로 삭제되었습니다!', 'success')
    except Exception as e:
        print(f"DEBUG: To-Do 항목 삭제 오류: {e}")
        flash('To-Do 항목 삭제에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('todos_list'))

# --- To-Do 기간 연장 (재조정) 라우트 ---

@app.route('/todos/reschedule/<int:todo_id>')
@app.route('/todos/reschedule/<int:todo_id>/<int:year>/<int:month>')
def reschedule_todo_calendar(todo_id, year=None, month=None):
    """
    특정 To-Do 항목의 마감일을 재조정하기 위한 달력을 표시합니다.
    """
    if 'loggedin' not in session:
        flash('To-Do 항목 마감일을 재조정하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    todo_item = None
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 재조정할 To-Do 항목의 정보를 가져옵니다.
            # due_date가 None일 경우 Jinja2에서 오류 나지 않도록 DATE_FORMAT 사용
            sql = "SELECT id, task, DATE_FORMAT(due_date, '%%Y-%%m-%%d') AS due_date, status FROM todos WHERE id = %s AND user_id = %s"
            cursor.execute(sql, (todo_id, user_id))
            todo_item = cursor.fetchone()
            if not todo_item:
                flash('To-Do 항목을 찾을 수 없거나 권한이 없습니다.', 'error')
                if conn: conn.close()
                return redirect(url_for('todos_list'))
    except Exception as e:
        print(f"DEBUG: Error fetching todo item for reschedule: {e}")
        flash('To-Do 항목 정보를 불러오는 데 실패했습니다.', 'error')
        if conn: conn.close()
        return redirect(url_for('todos_list'))
    finally:
        if conn: conn.close()

    today = datetime.now()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # 유효한 연도와 월인지 확인
    if not (1 <= month <= 12 and 1900 <= year <= 2100):
        flash('유효하지 않은 연도 또는 월입니다.', 'error')
        return redirect(url_for('reschedule_todo_calendar', todo_id=todo_id))

    # 이전 달, 다음 달 계산
    prev_month_date = (datetime(year, month, 1) - timedelta(days=1)).replace(day=1)
    next_month_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1)

    prev_year, prev_month = prev_month_date.year, prev_month_date.month
    next_year, next_month = next_month_date.year, next_month_date.month

    cal = calendar.Calendar(firstweekday=6) # 일요일부터 시작
    month_days = cal.monthdayscalendar(year, month) # month_days 변수 정의 및 들여쓰기 수정됨

    return render_template('todos_reschedule.html',
                           todo_item=todo_item,
                           year=year,
                           month=month,
                           month_name=datetime(year, month, 1).strftime('%B'),
                           month_days=month_days, # 템플릿으로 month_days 전달
                           prev_year=prev_year,
                           prev_month=prev_month,
                           next_year=next_year,
                           next_month=next_month,
                           current_day=today.day if today.year == year and today.month == month else None,
                           today=today, # today 변수도 템플릿으로 전달
                           username=session['username'])

@app.route('/todos/set_due_date/<int:todo_id>', methods=['POST'])
def set_new_due_date(todo_id):
    """선택된 날짜로 To-Do 항목의 마감일을 설정합니다."""
    if 'loggedin' not in session:
        flash('To-Do 항목 마감일을 설정하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    user_id = session['id']
    new_due_date_str = request.form.get('new_due_date').strip()

    if not new_due_date_str:
        flash('새로운 마감일을 선택해야 합니다.', 'error')
        return redirect(url_for('todos_list'))

    new_due_date = None
    try:
        new_due_date = datetime.strptime(new_due_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('유효하지 않은 날짜 형식입니다.', 'error')
        return redirect(url_for('todos_list'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 해당 사용자의 To-Do 항목인지 확인
            sql_check = "SELECT id, status FROM todos WHERE id = %s AND user_id = %s"
            cursor.execute(sql_check, (todo_id, user_id))
            item_data = cursor.fetchone()
            if not item_data:
                flash('To-Do 항목을 찾을 수 없거나 권한이 없습니다.', 'error')
                return redirect(url_for('todos_list'))

            # 마감일 업데이트, 상태는 '완료'가 아니면 '진행중'으로 설정
            # 사용자 요청에 따라 '기간연장' 상태는 유지하거나, '미완료'로 변경할 수 있습니다.
            new_status_after_reschedule = item_data['status'] # 기본적으로 현재 상태 유지
            if item_data['status'] == '완료':
                new_status_after_reschedule = '미완료' # 완료된 항목을 재조정하면 미완료로 돌림
            elif item_data['status'] == '기간연장':
                # '기간연장' 상태를 유지하도록 합니다.
                new_status_after_reschedule = '기간연장'
            else: # '미완료'나 '진행중'인 경우
                new_status_after_reschedule = '진행중'


            sql_update = "UPDATE todos SET due_date = %s, status = %s WHERE id = %s AND user_id = %s"
            cursor.execute(sql_update, (new_due_date, new_status_after_reschedule, todo_id, user_id))
        conn.commit()
        flash(f'할 일의 마감일이 {new_due_date_str}으로 성공적으로 재조정되었습니다!', 'success')
    except Exception as e:
        print(f"DEBUG: To-Do 마감일 설정 오류: {e}")
        flash('마감일 재조정에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('todos_list'))