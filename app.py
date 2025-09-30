import os
import re
from datetime import datetime, timedelta
import calendar
from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql.cursors
import uuid
from werkzeug.utils import secure_filename

dotenv_path = find_dotenv('/var/www/html/your_flask_app/.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

app = Flask(__name__)
# ★★★ 추가된 부분: 최대 요청 크기를 100MB로 설정 ★★★
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '192.168.0.13'),
    'user': os.getenv('DB_USER', 'flask_user'),
    'password': os.getenv('DB_PASSWORD', 'P@ssw0rd'),
    'db': os.getenv('DB_NAME', 'flask_auth_db'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    """데이터베이스 연결을 설정하고 반환합니다."""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        return conn
    except pymysql.Error as e:
        flash('데이터베이스 연결 오류가 발생했습니다. 잠시 후 다시 시도해주세요.', 'error')
        print(f"DB Connection Error: {e}") # 서버 로그에는 에러를 남김
        raise

# --- Helper Functions ---
def is_password_strong(password):
    """암호 복잡도 규칙(8자 이상, 대/소문자, 숫자, 특수문자 조합)을 검증합니다."""
    if len(password) < 8:
        return False
    rules = [
        any(c.isupper() for c in password),
        any(c.islower() for c in password),
        any(c.isdigit() for c in password),
        any(c in "!@#$%^&*()_+=:;\"'><.,?/[]}{" for c in password)
    ]
    return sum(rules) == 4

def is_valid_phone_number(phone_number):
    """대한민국 핸드폰 번호 형식인지 정규표현식으로 검증합니다."""
    pattern = re.compile(r'^(010\d{8}|01[1,6-9]\d{7,8})$')
    return pattern.match(phone_number)

def is_admin():
    """세션에 로그인된 사용자가 관리자인지 확인하는 헬퍼 함수"""
    return 'username' in session and session['username'] in ['kevin', 'kwangjin']

# --- 사용자 인증 및 암호 재설정 관련 라우트 ---
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

# 관리자 학습 컨텐츠 관리
@app.route('/admin/upload_image', methods=['POST'])
def upload_image():
    """Summernote 에디터에서 이미지 업로드를 처리합니다."""
    if not is_admin():
        return jsonify({'error': '권한이 없습니다.'}), 403

    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다.'}), 400

    if file:
        filename = secure_filename(file.filename)
        extension = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{extension}"

        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if extension not in allowed_extensions:
            return jsonify({'error': '허용되지 않는 파일 형식입니다.'}), 400

        save_path = os.path.join(app.root_path, 'static/uploads', unique_filename)

        try:
            file.save(save_path)
            url = url_for('static', filename=f'uploads/{unique_filename}')
            return jsonify({'url': url})
        except Exception as e:
            app.logger.error(f"Image save failed: {e}", exc_info=True)
            return jsonify({'error': '파일 저장 중 서버 오류가 발생했습니다.'}), 500

    return jsonify({'error': '알 수 없는 오류가 발생했습니다.'}), 500

@app.route('/admin/content')
def manage_content():
    """전체 학습 콘텐츠 목록을 보여주는 관리 페이지"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT c.id, c.title, c.content_type, s.name as subject_name
                FROM contents c
                JOIN subjects s ON c.subject_id = s.id
                ORDER BY s.name, c.created_at DESC
            """
            cursor.execute(sql)
            contents = cursor.fetchall()
        return render_template('manage_content.html', contents=contents)
    except Exception as e:
        app.logger.error(f"Failed to load content list: {e}", exc_info=True)
        flash('콘텐츠 목록을 불러오는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('admin_dashboard'))
    finally:
        if conn:
            conn.close()

# app.py

@app.route('/admin/edit_content/<int:content_id>', methods=['GET', 'POST'])
def edit_content(content_id):
    """기존 학습 콘텐츠를 수정하는 페이지 (최종 수정안)"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if request.method == 'POST':
                storage_type = request.form.get('storage_type')
                subject_id = request.form.get('subject_id')
                content_type = request.form.get('content_type')
                title = request.form.get('title', '').strip()

                if storage_type == 'editor':
                    body = request.form.get('body', '').strip()
                    sql = "UPDATE contents SET subject_id=%s, content_type=%s, storage_type='editor', title=%s, body=%s, pdf_path=NULL WHERE id=%s"
                    cursor.execute(sql, (subject_id, content_type, title, body, content_id))

                elif storage_type == 'pdf':
                    pdf_path_updated = False
                    if 'pdf_file' in request.files and request.files['pdf_file'].filename != '':
                        file = request.files['pdf_file']
                        if file and allowed_pdf_file(file.filename):
                            filename = secure_filename(file.filename)
                            unique_filename = f"{uuid.uuid4()}_{filename}"
                            save_path = os.path.join(app.root_path, 'static/pdfs', unique_filename)
                            file.save(save_path)
                            pdf_path = f"pdfs/{unique_filename}"
                            sql = "UPDATE contents SET subject_id=%s, content_type=%s, storage_type='pdf', title=%s, body=NULL, pdf_path=%s WHERE id=%s"
                            cursor.execute(sql, (subject_id, content_type, title, pdf_path, content_id))
                            pdf_path_updated = True
                        else:
                            flash('PDF 파일만 업로드할 수 있습니다.', 'error')

                    if not pdf_path_updated: # 새 파일이 업로드되지 않은 경우
                        sql = "UPDATE contents SET subject_id=%s, content_type=%s, storage_type='pdf', title=%s WHERE id=%s"
                        cursor.execute(sql, (subject_id, content_type, title, content_id))

                conn.commit()
                flash('콘텐츠가 성공적으로 수정되었습니다.', 'success')
                return redirect(url_for('manage_content'))

            # GET 요청 처리
            cursor.execute("SELECT * FROM contents WHERE id = %s", (content_id,))
            content = cursor.fetchone()
            cursor.execute("SELECT id, name FROM subjects ORDER BY name ASC")
            subjects = cursor.fetchall()
            return render_template('edit_content.html', content=content, subjects=subjects)

    except Exception as e:
        app.logger.error(f"Failed to edit content: {e}", exc_info=True)
        flash('콘텐츠 처리 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('manage_content'))
    finally:
        if conn:
            conn.close()

@app.route('/admin/delete_content/<int:content_id>', methods=['POST'])
def delete_content(content_id):
    """특정 학습 콘텐츠를 삭제합니다."""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM contents WHERE id = %s", (content_id,))
        conn.commit()
        flash('콘텐츠가 삭제되었습니다.', 'success')
    except Exception as e:
        app.logger.error(f"Failed to delete content: {e}", exc_info=True)
        flash('콘텐츠 삭제 중 오류가 발생했습니다.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('manage_content'))


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


# --- 게시판 관련 라우트 ---

@app.route('/board')
def board_list():
    """검색 기능을 포함한 게시글 목록을 표시합니다."""
    if 'loggedin' not in session:
        flash('게시판을 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    search_query = request.args.get('query', '').strip()

    conn = None
    posts = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT b.id, b.title, b.content, b.created_at, b.updated_at, u.username " \
                  "FROM board b JOIN users u ON b.user_id = u.id"
            params = []

            if search_query:
                sql += " WHERE b.title LIKE %s OR b.content LIKE %s"
                params.append(f"%{search_query}%")
                params.append(f"%{search_query}%")

            sql += " ORDER BY b.created_at DESC" # 정렬 기준은 최신순 유지

            cursor.execute(sql, params) # 파라미터화된 쿼리 실행
            posts = cursor.fetchall()
    except Exception as e:
        print(f"데이터베이스 오류 (게시글 불러오기 및 검색): {e}")
        flash('게시판 글을 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return render_template('board_list.html', posts=posts, username=session['username'], search_query=search_query)

@app.route('/board/write', methods=['GET', 'POST'])
def write_post():
    """새 게시글 작성을 처리합니다."""
    if 'loggedin' not in session:
        flash('게시글을 작성하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title'].strip()
        content = request.form['content'].strip()
        user_id = session['id']

        if not title or not content:
            flash('제목과 내용은 비워둘 수 없습니다.', 'error')
            return redirect(url_for('write_post'))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql = "INSERT INTO board (user_id, title, content) VALUES (%s, %s, %s)"
                cursor.execute(sql, (user_id, title, content))
            conn.commit()
            flash('게시글이 성공적으로 작성되었습니다!', 'success')
        except Exception as e:
            print(f"데이터베이스 오류 (게시글 작성): {e}")
            flash('게시글 작성에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
        finally:
            if conn:
                conn.close()
        return redirect(url_for('board_list'))
    return render_template('write_post.html', username=session['username'])

@app.route('/board/view/<int:post_id>')
def view_post(post_id):
    """단일 게시글과 해당 댓글을 표시합니다."""
    if 'loggedin' not in session:
        flash('게시글을 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    post = None
    comments = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql_post = "SELECT b.id, b.title, b.content, b.created_at, b.updated_at, b.user_id, u.username " \
                       "FROM board b JOIN users u ON b.user_id = u.id WHERE b.id = %s"
            cursor.execute(sql_post, (post_id,))
            post = cursor.fetchone()

            if not post:
                flash('게시글을 찾을 수 없습니다.', 'error')
                return redirect(url_for('board_list'))

            sql_comments = "SELECT c.id, c.content, c.created_at, u.username, c.user_id " \
                           "FROM comments c JOIN users u ON c.user_id = u.id WHERE c.board_id = %s ORDER BY c.created_at ASC"
            cursor.execute(sql_comments, (post_id,))
            comments = cursor.fetchall()

    except Exception as e:
        print(f"데이터베이스 오류 (게시글 조회): {e}")
        flash('게시글을 불러오는 데 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return render_template('view_post.html', post=post, comments=comments, username=session['username'])

@app.route('/board/edit/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    """기존 게시글 편집을 처리합니다."""
    if 'loggedin' not in session:
        flash('게시글을 수정하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    post = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT id, title, content, user_id FROM board WHERE id = %s"
            cursor.execute(sql, (post_id,))
            post = cursor.fetchone()

            if not post:
                flash('게시글을 찾을 수 없습니다.', 'error')
                return redirect(url_for('board_list'))

            if post['user_id'] != session['id']:
                flash('이 게시글을 수정할 권한이 없습니다.', 'error')
                return redirect(url_for('view_post', post_id=post_id))

        if request.method == 'POST':
            title = request.form['title'].strip()
            content = request.form['content'].strip()

            if not title or not content:
                flash('제목과 내용은 비워둘 수 없습니다.', 'error')
                return redirect(url_for('edit_post', post_id=post_id))

            with conn.cursor() as cursor:
                sql = "UPDATE board SET title = %s, content = %s WHERE id = %s"
                cursor.execute(sql, (title, content, post_id))
            conn.commit()
            flash('게시글이 성공적으로 수정되었습니다!', 'success')
            return redirect(url_for('view_post', post_id=post_id))
    except Exception as e:
        print(f"데이터베이스 오류 (게시글 수정): {e}")
        flash('게시글 수정에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return render_template('edit_post.html', post=post, username=session['username'])

@app.route('/board/delete/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    """게시글 삭제를 처리합니다."""
    if 'loggedin' not in session:
        flash('게시글을 삭제하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql_check = "SELECT user_id FROM board WHERE id = %s"
            cursor.execute(sql_check, (post_id,))
            post_owner = cursor.fetchone()

            if not post_owner:
                flash('게시글을 찾을 수 없습니다.', 'error')
                return redirect(url_for('board_list'))

            if post_owner['user_id'] != session['id']:
                flash('이 게시글을 삭제할 권한이 없습니다.', 'error')
                return redirect(url_for('view_post', post_id=post_id))

            sql_delete = "DELETE FROM board WHERE id = %s"
            cursor.execute(sql_delete, (post_id,))
        conn.commit()
        flash('게시글이 성공적으로 삭제되었습니다!', 'success')
    except Exception as e:
        print(f"데이터베이스 오류 (게시글 삭제): {e}")
        flash('게시글 삭제에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('board_list'))


@app.route('/comment/add/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    """게시글에 댓글 추가를 처리합니다."""
    if 'loggedin' not in session:
        flash('댓글을 작성하려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    content = request.form['content'].strip()
    user_id = session['id']

    if not content:
        flash('댓글 내용은 비워둘 수 없습니다.', 'error')
        return redirect(url_for('view_post', post_id=post_id))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM board WHERE id = %s", (post_id,))
            if not cursor.fetchone():
                flash('댓글을 달 게시글을 찾을 수 없습니다.', 'error')
                return redirect(url_for('board_list'))

            sql = "INSERT INTO comments (board_id, user_id, content) VALUES (%s, %s, %s)"
            cursor.execute(sql, (post_id, user_id, content))
        conn.commit()
        flash('댓글이 성공적으로 작성되었습니다!', 'success')
    except Exception as e:
        print(f"데이터베이스 오류 (댓글 작성): {e}")
        flash('댓글 작성에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('view_post', post_id=post_id))


# --- 일기장 관련 라우트 ---

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



# --- 학습 콘텐츠 관련 라우트 ---
@app.route('/study')
def study_list():
    """전체 학습 과목 목록을 표시합니다."""
    if 'loggedin' not in session:
        flash('학습 콘텐츠를 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    subjects = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM subjects ORDER BY name ASC")
            subjects = cursor.fetchall()
    except Exception as e:
        print(f"데이터베이스 오류 (과목 목록 불러오기): {e}")
        flash('과목 목록을 불러오는 데 실패했습니다.', 'error')
    finally:
        if conn:
            conn.close()

    return render_template('study_list.html', subjects=subjects, username=session['username'])

@app.route('/study/<int:subject_id>')
def subject_detail(subject_id):
    """특정 과목의 이론/실습 콘텐츠 목록을 표시합니다."""
    if 'loggedin' not in session:
        flash('학습 콘텐츠를 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    subject = None
    theory_contents = []
    lab_contents = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 과목 정보 가져오기
            cursor.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
            subject = cursor.fetchone()

            if not subject:
                flash('존재하지 않는 과목입니다.', 'error')
                return redirect(url_for('study_list'))

            # 이론 콘텐츠 목록 가져오기 (is_active 컬럼 포함)
            sql_theory = "SELECT id, title, created_at, is_active FROM contents WHERE subject_id = %s AND content_type = '이론' ORDER BY created_at ASC"
            cursor.execute(sql_theory, (subject_id,))
            theory_contents = cursor.fetchall()

            # 실습 콘텐츠 목록 가져오기 (is_active 컬럼 포함)
            sql_lab = "SELECT id, title, created_at, is_active FROM contents WHERE subject_id = %s AND content_type = '실습' ORDER BY created_at ASC"
            cursor.execute(sql_lab, (subject_id,))
            lab_contents = cursor.fetchall()

    except Exception as e:
        print(f"데이터베이스 오류 (콘텐츠 목록 불러오기): {e}")
        flash('콘텐츠 목록을 불러오는 데 실패했습니다.', 'error')
    finally:
        if conn:
            conn.close()

    return render_template('subject_detail.html',
                           subject=subject,
                           theory_contents=theory_contents,
                           lab_contents=lab_contents,
                           username=session['username'])


@app.route('/content/<int:content_id>')
def view_content(content_id):
    """개별 콘텐츠(이론 또는 실습)의 상세 내용을 표시합니다."""
    if 'loggedin' not in session:
        flash('콘텐츠를 보려면 로그인해야 합니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = """
                SELECT c.id, c.title, c.body, c.content_type, c.storage_type,
                       c.pdf_path, c.created_at, c.is_active, s.name as subject_name, c.subject_id
                FROM contents c
                JOIN subjects s ON c.subject_id = s.id
                WHERE c.id = %s
            """
            cursor.execute(sql, (content_id,))
            content = cursor.fetchone()

            if not content:
                flash('존재하지 않는 콘텐츠입니다.', 'error')
                return redirect(url_for('study_list'))

            # ★★★ 수정된 최종 접근 제어 로직 ★★★
            # 관리자가 아닌 경우에만, 비활성 콘텐츠 접근을 차단합니다.
            if not is_admin() and not content['is_active']:
                flash('아직 활성화되지 않은 콘텐츠입니다.', 'error')
                return redirect(url_for('subject_detail', subject_id=content['subject_id']))

            return render_template('view_content.html', content=content)

    except Exception as e:
        app.logger.error(f"Failed to view content: {e}", exc_info=True)
        flash('콘텐츠를 불러오는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('study_list'))
    finally:
        if conn:
            conn.close()

@app.route('/content/toggle_status/<int:content_id>', methods=['POST'])
def toggle_content_status(content_id):
    """학습 콘텐츠의 활성화 상태를 변경(토글)합니다."""
    # ★★★ 관리자 권한 체크 ★★★
    # 세션에 사용자 이름이 없거나, 사용자 이름이 관리자 목록에 없으면 작업을 차단합니다.
    # 참고: 이 방식은 간단하지만, 사용자가 많아지면 DB에 'role' 컬럼을 만들어 관리하는 것이 더 효율적입니다.
    if 'username' not in session or session['username'] not in ['kevin', 'kwangjin']:
        flash('이 작업을 수행할 권한이 없습니다.', 'error')
        return redirect(request.referrer or url_for('study_list')) # 이전 페이지로 리디렉션

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 리디렉션을 위해 subject_id를 먼저 조회합니다.
            cursor.execute("SELECT subject_id FROM contents WHERE id = %s", (content_id,))
            content = cursor.fetchone()
            if not content:
                flash('존재하지 않는 콘텐츠입니다.', 'error')
                return redirect(url_for('study_list'))

            subject_id = content['subject_id']

            # is_active 상태를 현재와 반대로(0->1, 1->0) 업데이트합니다.
            sql_update = "UPDATE contents SET is_active = NOT is_active WHERE id = %s"
            cursor.execute(sql_update, (content_id,))
        conn.commit()
        flash('콘텐츠 상태가 성공적으로 변경되었습니다.', 'success')
        return redirect(url_for('subject_detail', subject_id=subject_id))
    except Exception as e:
        print(f"데이터베이스 오류 (콘텐츠 상태 변경): {e}")
        flash('콘텐츠 상태 변경에 실패했습니다.', 'error')
        return redirect(request.referrer or url_for('study_list'))
    finally:
        if conn:
            conn.close()

# --- ★★★ 관리자 페이지 관련 라우트 (신규 추가) ★★★ ---

def is_admin():
    """세션에 로그인된 사용자가 관리자인지 확인하는 헬퍼 함수"""
    return 'username' in session and session['username'] in ['kevin', 'kwangjin']

@app.route('/admin')
def admin_dashboard():
    """관리자 메인 대시보드 페이지"""
    # 관리자가 아니면 접근 차단
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    return render_template('admin_dashboard.html', username=session['username'])

def allowed_pdf_file(filename):
    """PDF 파일 확장자만 허용하는지 확인하는 헬퍼 함수"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'pdf'}

@app.route('/admin/add_content', methods=['GET', 'POST'])
def add_content():
    """새로운 학습 콘텐츠를 등록하는 페이지 및 처리"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # GET과 POST 모두에서 과목 목록이 필요하므로 먼저 불러옵니다.
            cursor.execute("SELECT id, name FROM subjects ORDER BY name ASC")
            subjects = cursor.fetchall()

            if request.method == 'POST':
                storage_type = request.form.get('storage_type')
                subject_id = request.form.get('subject_id')
                content_type = request.form.get('content_type')
                title = request.form.get('title', '').strip()

                if not all([storage_type, subject_id, content_type, title]):
                    flash('저장 방식, 과목, 타입, 제목은 필수 항목입니다.', 'error')
                    return render_template('add_content.html', subjects=subjects)

                if storage_type == 'editor':
                    body = request.form.get('body', '').strip()
                    if not body:
                        flash('에디터 내용을 입력해주세요.', 'error')
                        return render_template('add_content.html', subjects=subjects)

                    sql = "INSERT INTO contents (subject_id, content_type, storage_type, title, body, is_active) VALUES (%s, %s, %s, %s, %s, 1)"
                    cursor.execute(sql, (subject_id, content_type, storage_type, title, body))

                elif storage_type == 'pdf':
                    if 'pdf_file' not in request.files or request.files['pdf_file'].filename == '':
                        flash('PDF 파일을 선택해주세요.', 'error')
                        return render_template('add_content.html', subjects=subjects)

                    file = request.files['pdf_file']
                    if not (file and allowed_pdf_file(file.filename)):
                        flash('PDF 파일만 업로드할 수 있습니다.', 'error')
                        return render_template('add_content.html', subjects=subjects)

                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    save_path = os.path.join(app.root_path, 'static/pdfs', unique_filename)
                    file.save(save_path)
                    pdf_path = f"pdfs/{unique_filename}"
                    sql = "INSERT INTO contents (subject_id, content_type, storage_type, title, pdf_path, is_active) VALUES (%s, %s, %s, %s, %s, 1)"
                    cursor.execute(sql, (subject_id, content_type, storage_type, title, pdf_path))

                conn.commit()
                flash('새로운 콘텐츠가 성공적으로 등록되었습니다.', 'success')
                return redirect(url_for('manage_content'))

            # GET 요청 처리
            return render_template('add_content.html', subjects=subjects)

    except Exception as e:
        app.logger.error(f"Failed to add content: {e}", exc_info=True)
        flash('콘텐츠 추가 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('admin_dashboard'))
    finally:
        if conn:
            conn.close()

# 신규 추가: 과목 관리(CRUD) 관련 라우트

@app.route('/admin/subjects', methods=['GET', 'POST'])
def manage_subjects():
    """과목 목록을 보고, 새 과목을 등록하는 페이지"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        # 새 과목 등록 처리 (POST)
        if request.method == 'POST':
            name = request.form['name'].strip()
            if name:
                with conn.cursor() as cursor:
                    # 중복 이름 확인
                    cursor.execute("SELECT id FROM subjects WHERE name = %s", (name,))
                    if cursor.fetchone():
                        flash('이미 존재하는 과목 이름입니다.', 'error')
                    else:
                        cursor.execute("INSERT INTO subjects (name) VALUES (%s)", (name,))
                        conn.commit()
                        flash('새로운 과목이 성공적으로 등록되었습니다.', 'success')
            else:
                flash('과목 이름을 입력해주세요.', 'error')
            return redirect(url_for('manage_subjects'))

        # 과목 목록 조회 (GET)
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, name FROM subjects ORDER BY name ASC")
            subjects = cursor.fetchall()

        return render_template('manage_subjects.html', subjects=subjects, username=session['username'])

    except Exception as e:
        print(f"과목 관리 페이지 오류: {e}")
        flash('과목 관리 페이지를 로드하는 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('admin_dashboard'))
    finally:
        if conn:
            conn.close()

@app.route('/admin/edit_subject/<int:subject_id>', methods=['GET', 'POST'])
def edit_subject(subject_id):
    """기존 과목의 이름을 수정하는 페이지"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # POST 요청 처리 (이름 수정)
            if request.method == 'POST':
                new_name = request.form['name'].strip()
                if not new_name:
                    flash('과목 이름은 비워둘 수 없습니다.', 'error')
                else:
                    # 다른 과목과 이름이 중복되는지 확인
                    cursor.execute("SELECT id FROM subjects WHERE name = %s AND id != %s", (new_name, subject_id))
                    if cursor.fetchone():
                        flash('이미 존재하는 과목 이름입니다.', 'error')
                    else:
                        cursor.execute("UPDATE subjects SET name = %s WHERE id = %s", (new_name, subject_id))
                        conn.commit()
                        flash('과목 이름이 성공적으로 수정되었습니다.', 'success')
                        return redirect(url_for('manage_subjects'))

            # GET 요청 처리 (수정할 과목 정보 불러오기)
            cursor.execute("SELECT id, name FROM subjects WHERE id = %s", (subject_id,))
            subject = cursor.fetchone()
            if not subject:
                flash('존재하지 않는 과목입니다.', 'error')
                return redirect(url_for('manage_subjects'))

            return render_template('edit_subject.html', subject=subject, username=session['username'])

    except Exception as e:
        print(f"과목 수정 오류: {e}")
        flash('과목 수정 중 오류가 발생했습니다.', 'error')
        return redirect(url_for('manage_subjects'))
    finally:
        if conn:
            conn.close()

@app.route('/admin/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    """특정 과목을 삭제하는 기능"""
    if not is_admin():
        flash('접근 권한이 없습니다.', 'error')
        return redirect(url_for('index'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 경고: ON DELETE CASCADE로 인해 연결된 contents도 모두 삭제됩니다.
            cursor.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
        conn.commit()
        flash('과목 및 관련 콘텐츠가 모두 삭제되었습니다.', 'success')
    except Exception as e:
        print(f"과목 삭제 오류: {e}")
        flash('과목 삭제 중 오류가 발생했습니다.', 'error')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('manage_subjects'))


# 개발용 블록입니다. Apache/mod_wsgi로 배포 시에는 사용되지 않습니다.
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')


