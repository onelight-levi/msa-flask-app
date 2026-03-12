@app.route('/')
def index():
    if 'loggedin' in session:
        return render_template('main_logged_in.html')
    return render_template('default.html')
    
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username'].strip()
    phone_number = request.form['phone_number'].strip()
    password = request.form['password'].strip()

    if not all([username, phone_number, password]):
        flash('사용자 이름, 휴대폰 번호, 비밀번호를 모두 입력해주세요.', 'error')
        return redirect(url_for('index'))

    if not is_valid_phone_number(phone_number):
        flash('올바른 핸드폰 번호 형식이 아닙니다. (예: 01012345678)', 'error')
        return redirect(url_for('index'))

    if not is_password_strong(password):
        flash('비밀번호는 8자 이상이며, 영문 대/소문자, 숫자, 특수문자를 모두 포함해야 합니다.', 'error')
        return redirect(url_for('index'))

    hashed_password = generate_password_hash(password)
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cursor.fetchone():
                flash('이미 존재하는 사용자 이름입니다.', 'error')
                return redirect(url_for('index'))

            cursor.execute("SELECT id FROM users WHERE phone_number = %s", (phone_number,))
            if cursor.fetchone():
                flash('이미 등록된 휴대폰 번호입니다.', 'error')
                return redirect(url_for('index'))

            sql = "INSERT INTO users (username, phone_number, password) VALUES (%s, %s, %s)"
            cursor.execute(sql, (username, phone_number, hashed_password))
        conn.commit()
        flash('회원가입에 성공했습니다! 이제 로그인할 수 있습니다.', 'success')
    except Exception as e:
        flash('회원가입에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('index'))

    @app.route('/login', methods=['POST'])
def login():
    username = request.form['username'].strip()
    password = request.form['password'].strip()

    if not username or not password:
        flash('사용자 이름과 비밀번호를 모두 입력해주세요.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT id, username, password FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session['loggedin'] = True
                session['id'] = user['id']
                session['username'] = user['username']
                flash(f'환영합니다, {user["username"]}님!', 'success')
                return redirect(url_for('index'))
            else:
                flash('잘못된 사용자 이름 또는 비밀번호입니다.', 'error')
    except Exception as e:
        flash('로그인에 실패했습니다. 서버 오류입니다.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash('성공적으로 로그아웃되었습니다.', 'success')
    return redirect(url_for('index'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form['username'].strip()
        phone_number = request.form['phone_number'].strip()

        if not username or not is_valid_phone_number(phone_number):
            flash('아이디와 올바른 핸드폰 번호 형식을 모두 입력해주세요.', 'error')
            return redirect(url_for('forgot_password'))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql = "SELECT id FROM users WHERE username = %s AND phone_number = %s"
                cursor.execute(sql, (username, phone_number))
                user = cursor.fetchone()
                if user:
                    session['phone_to_reset'] = phone_number
                    flash('계정이 확인되었습니다. 새 비밀번호를 설정해주세요.', 'success')
                    return redirect(url_for('reset_password'))
                else:
                    flash('입력하신 정보와 일치하는 계정을 찾을 수 없습니다.', 'error')
        except Exception as e:
            flash('오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 'error')
        finally:
            if conn:
                conn.close()
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if 'phone_to_reset' not in session:
        flash('먼저 계정 확인 절차를 진행해주세요.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form['new_password'].strip()
        confirm_password = request.form['confirm_password'].strip()

        if new_password != confirm_password:
            flash('새 비밀번호가 일치하지 않습니다.', 'error')
            return render_template('reset_password.html')

        if not is_password_strong(new_password):
            flash('새 비밀번호는 8자 이상이며, 영문 대/소문자, 숫자, 특수문자를 모두 포함해야 합니다.', 'error')
            return render_template('reset_password.html')

        hashed_password = generate_password_hash(new_password)
        phone_number = session['phone_to_reset']

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql = "UPDATE users SET password = %s WHERE phone_number = %s"
                cursor.execute(sql, (hashed_password, phone_number))
            conn.commit()
            flash('비밀번호가 성공적으로 변경되었습니다. 새로운 비밀번호로 로그인해주세요.', 'success')
            session.pop('phone_to_reset', None)
            return redirect(url_for('index'))
        except Exception as e:
            flash('비밀번호 변경 중 오류가 발생했습니다.', 'error')
        finally:
            if conn:
                conn.close()
    return render_template('reset_password.html')