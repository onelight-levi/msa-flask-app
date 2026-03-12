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