import os
import re
from datetime import datetime, timedelta
import calendar
from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify,send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql.cursors
import uuid
from werkzeug.utils import secure_filename

dotenv_path = find_dotenv('/var/www/html/your_flask_app/.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

app = Flask(__name__)

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