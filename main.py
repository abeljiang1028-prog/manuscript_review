
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pwdlib import PasswordHash

from db import getDB, lifespan

load_dotenv()

# 建立 FastAPI 應用程式
app = FastAPI(
    title="投稿審查系統",
    lifespan=lifespan
)

# 登入狀態管理
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET"],
    same_site="lax",
    https_only=False  # 本機 HTTP 測試使用
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 密碼雜湊工具
password_hash = PasswordHash.recommended()


# 取得目前登入者
async def current_user(request, db):
    user_id = request.session.get("user_id")

    if user_id is None:
        return None

    cur = await db.execute(
        "SELECT id, username, role FROM users WHERE id = %s",
        (user_id,)
    )

    return await cur.fetchone()


# 首頁
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


# 顯示註冊頁面
@app.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html"
    )


# 處理作者註冊
@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(getDB)
):
    username = username.strip()

    if not (3 <= len(username) <= 50) or len(password) < 8:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "帳號需為3～50字，密碼至少8字"},
            status_code=400
        )

    # 雜湊密碼，不儲存明文
    hashed = password_hash.hash(password)

    # 註冊時只能建立作者帳號
    cur = await db.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, %s, 'author')
        ON CONFLICT (username) DO NOTHING
        RETURNING id
        """,
        (username, hashed)
    )

    new_user = await cur.fetchone()

    if new_user is None:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"error": "這個帳號已經有人使用"},
            status_code=400
        )

    request.session["user_id"] = new_user["id"]

    return RedirectResponse("/author", status_code=303)


# 顯示登入頁面
@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )


# 處理登入
@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db=Depends(getDB)
):
    cur = await db.execute(
        "SELECT * FROM users WHERE username = %s",
        (username.strip(),)
    )

    user = await cur.fetchone()

    if user is None or not password_hash.verify(
        password, user["password_hash"]
    ):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "帳號或密碼錯誤"},
            status_code=401
        )

    # 記錄登入者 ID
    request.session.clear()
    request.session["user_id"] = user["id"]

    # 依角色導向不同頁面
    if user["role"] == "editor":
        return RedirectResponse("/editor", status_code=303)

    return RedirectResponse("/author", status_code=303)

# 作者投稿清單
@app.get("/author")
async def author_page(
    request: Request,
    db=Depends(getDB)
):
    user = await current_user(request, db)

    if user is None:
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "author":
        raise HTTPException(status_code=403, detail="沒有作者權限")

    # 只查詢這位作者的文章
    cur = await db.execute(
        """
        SELECT m.*,
            (
                SELECT r.reason
                FROM review_logs r
                WHERE r.manuscript_id = m.id
                  AND r.action = 'returned'
                ORDER BY r.reviewed_at DESC, r.id DESC
                LIMIT 1
            ) AS return_reason
        FROM manuscripts m
        WHERE m.author_id = %s
        ORDER BY m.created_at DESC, m.id DESC
        """,
        (user["id"],)
    )

    manuscripts = await cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="author_dashboard.html",
        context={
            "user": user,
            "manuscripts": manuscripts,
            "status_names": {
                "editing": "編輯中",
                "under_review": "審查中",
                "approved": "已通過"
            }
        }
    )




# 編輯審查清單
@app.get("/editor")
async def editor_page(
    request: Request,
    db=Depends(getDB)
):
    user = await current_user(request, db)

    if user is None:
        return RedirectResponse("/login", status_code=303)

    if user["role"] != "editor":
        raise HTTPException(
            status_code=403,
            detail="沒有編輯權限"
        )

    # 只顯示審查中的稿件
    # 越早送審的文章排越上面
    cur = await db.execute(
        """
        SELECT
            m.id,
            m.category,
            m.title,
            m.status,
            m.submitted_at,
            u.username AS author_name,
            TO_CHAR(
                m.submitted_at AT TIME ZONE 'Asia/Taipei',
                'YYYY-MM-DD HH24:MI'
            ) AS submitted_time
        FROM manuscripts m
        JOIN users u ON m.author_id = u.id
        WHERE m.status = 'under_review'
        ORDER BY m.submitted_at ASC NULLS LAST, m.id ASC
        """
    )

    manuscripts = await cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="editor_dashboard.html",
        context={
            "user": user,
            "manuscripts": manuscripts
        }
    )


# 登出
@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# 資料庫連線測試
@app.get("/db-test")
async def test_database(db=Depends(getDB)):
    cur = await db.execute("""
        SELECT
            current_database() AS database,
            (SELECT COUNT(*) FROM users) AS users_count
    """)

    result = await cur.fetchone()

    return {
        "message": "資料庫連線成功",
        "database": result["database"],
        "users_count": result["users_count"]
    }

# ========================================
# 作者投稿功能
# ========================================

# 文章類別
CATEGORIES = ["文學", "科技", "生活"]


# 驗證作者身分
async def require_author(request, db):
    user = await current_user(request, db)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="請先登入"
        )

    if user["role"] != "author":
        raise HTTPException(
            status_code=403,
            detail="只有作者可以操作投稿"
        )

    return user


# 驗證文章資料
def validate_manuscript(category, title, content):
    if category not in CATEGORIES:
        return "請選擇正確的文章類別"

    if not title or len(title) > 200:
        return "標題不能空白，且不可超過200字"

    if not content:
        return "文章內容不能空白"

    return None


# 1. 顯示新增投稿頁面
@app.get("/manuscripts/new")
async def new_manuscript_page(
    request: Request,
    db=Depends(getDB)
):
    await require_author(request, db)

    return templates.TemplateResponse(
        request=request,
        name="manuscript_form.html",
        context={
            "mode": "new",
            "categories": CATEGORIES,
            "manuscript": {
                "title": "",
                "category": "文學",
                "content": ""
            }
        }
    )


# 2. 新增文章到資料庫
@app.post("/manuscripts/new")
async def create_manuscript(
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    db=Depends(getDB)
):
    user = await require_author(request, db)

    title = title.strip()
    content = content.strip()

    error = validate_manuscript(category, title, content)

    if error:
        return templates.TemplateResponse(
            request=request,
            name="manuscript_form.html",
            context={
                "mode": "new",
                "categories": CATEGORIES,
                "manuscript": {
                    "title": title,
                    "category": category,
                    "content": content
                },
                "error": error
            },
            status_code=400
        )

    cur = await db.execute(
        """
        INSERT INTO manuscripts
            (author_id, category, title, content, status)
        VALUES (%s, %s, %s, %s, 'editing')
        RETURNING id
        """,
        (user["id"], category, title, content)
    )

    manuscript = await cur.fetchone()
    await db.commit()

    return RedirectResponse(
        f"/manuscripts/{manuscript['id']}",
        status_code=303
    )


# 3. 查看文章內容
@app.get("/manuscripts/{manuscript_id}")
async def view_manuscript(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    user = await require_author(request, db)

    cur = await db.execute(
        """
        SELECT m.*,
            (
                SELECT r.reason
                FROM review_logs r
                WHERE r.manuscript_id = m.id
                  AND r.action = 'returned'
                ORDER BY r.reviewed_at DESC, r.id DESC
                LIMIT 1
            ) AS return_reason
        FROM manuscripts m
        WHERE m.id = %s AND m.author_id = %s
        """,
        (manuscript_id, user["id"])
    )

    manuscript = await cur.fetchone()

    if manuscript is None:
        raise HTTPException(
            status_code=404,
            detail="找不到這篇文章"
        )

    status_names = {
        "editing": "編輯中",
        "under_review": "審查中",
        "approved": "已通過"
    }

    return templates.TemplateResponse(
        request=request,
        name="manuscript_detail.html",
        context={
            "manuscript": manuscript,
            "status_name": status_names[manuscript["status"]]
        }
    )


# 4. 顯示編輯文章頁面
@app.get("/manuscripts/{manuscript_id}/edit")
async def edit_manuscript_page(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    user = await require_author(request, db)

    cur = await db.execute(
        """
        SELECT * FROM manuscripts
        WHERE id = %s
          AND author_id = %s
          AND status = 'editing'
        """,
        (manuscript_id, user["id"])
    )

    manuscript = await cur.fetchone()

    if manuscript is None:
        raise HTTPException(
            status_code=404,
            detail="文章不存在或目前不可編輯"
        )

    return templates.TemplateResponse(
        request=request,
        name="manuscript_form.html",
        context={
            "mode": "edit",
            "categories": CATEGORIES,
            "manuscript": manuscript
        }
    )


# 5. 儲存修改後的文章
@app.post("/manuscripts/{manuscript_id}/edit")
async def update_manuscript(
    manuscript_id: int,
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    db=Depends(getDB)
):
    user = await require_author(request, db)

    title = title.strip()
    content = content.strip()

    error = validate_manuscript(category, title, content)

    if error:
        return templates.TemplateResponse(
            request=request,
            name="manuscript_form.html",
            context={
                "mode": "edit",
                "categories": CATEGORIES,
                "manuscript": {
                    "id": manuscript_id,
                    "title": title,
                    "category": category,
                    "content": content
                },
                "error": error
            },
            status_code=400
        )

    cur = await db.execute(
        """
        UPDATE manuscripts
        SET category = %s,
            title = %s,
            content = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND author_id = %s
          AND status = 'editing'
        RETURNING id
        """,
        (category, title, content, manuscript_id, user["id"])
    )

    updated = await cur.fetchone()

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail="文章不存在或目前不可修改"
        )

    await db.commit()

    return RedirectResponse(
        f"/manuscripts/{manuscript_id}",
        status_code=303
    )


# 6. 刪除編輯中的文章
@app.post("/manuscripts/{manuscript_id}/delete")
async def delete_manuscript(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    user = await require_author(request, db)

    cur = await db.execute(
        """
        DELETE FROM manuscripts
        WHERE id = %s
          AND author_id = %s
          AND status = 'editing'
        RETURNING id
        """,
        (manuscript_id, user["id"])
    )

    deleted = await cur.fetchone()

    if deleted is None:
        raise HTTPException(
            status_code=404,
            detail="文章不存在或目前不可刪除"
        )

    await db.commit()

    return RedirectResponse("/author", status_code=303)


# 7. 送出文章審查
@app.post("/manuscripts/{manuscript_id}/submit")
async def submit_manuscript(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    user = await require_author(request, db)

    cur = await db.execute(
        """
        UPDATE manuscripts
        SET status = 'under_review',
            submitted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            reviewed_at = NULL
        WHERE id = %s
          AND author_id = %s
          AND status = 'editing'
        RETURNING id
        """,
        (manuscript_id, user["id"])
    )

    submitted = await cur.fetchone()

    if submitted is None:
        raise HTTPException(
            status_code=404,
            detail="文章不存在或無法送審"
        )

    await db.commit()

    return RedirectResponse(
        f"/manuscripts/{manuscript_id}",
        status_code=303
    )

# ========================================
# 編輯審查功能
# ========================================

# 確認登入者是編輯
async def require_editor(request, db):
    user = await current_user(request, db)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="請先登入"
        )

    if user["role"] != "editor":
        raise HTTPException(
            status_code=403,
            detail="只有編輯可以審查文章"
        )

    return user


# 1. 查看待審查文章內容
@app.get("/editor/manuscripts/{manuscript_id}")
async def editor_view_manuscript(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    await require_editor(request, db)

    cur = await db.execute(
        """
        SELECT m.*,
               u.username AS author_name,
               TO_CHAR(
                   m.submitted_at AT TIME ZONE 'Asia/Taipei',
                   'YYYY-MM-DD HH24:MI'
               ) AS submitted_time
        FROM manuscripts m
        JOIN users u ON m.author_id = u.id
        WHERE m.id = %s
          AND m.status = 'under_review'
        """,
        (manuscript_id,)
    )

    manuscript = await cur.fetchone()

    if manuscript is None:
        raise HTTPException(
            status_code=404,
            detail="找不到待審查文章"
        )

    return templates.TemplateResponse(
        request=request,
        name="editor_detail.html",
        context={
            "manuscript": manuscript
        }
    )


# 2. 通過文章審查
@app.post("/editor/manuscripts/{manuscript_id}/approve")
async def approve_manuscript(
    manuscript_id: int,
    request: Request,
    db=Depends(getDB)
):
    user = await require_editor(request, db)

    # 只有「審查中」的文章可以通過
    cur = await db.execute(
        """
        UPDATE manuscripts
        SET status = 'approved',
            reviewed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND status = 'under_review'
        RETURNING id
        """,
        (manuscript_id,)
    )

    updated = await cur.fetchone()

    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="文章已被處理，無法重複審查"
        )

    # 新增審查紀錄
    await db.execute(
        """
        INSERT INTO review_logs
            (manuscript_id, reviewer_id, action)
        VALUES (%s, %s, 'approved')
        """,
        (manuscript_id, user["id"])
    )

    await db.commit()

    return RedirectResponse(
        "/editor",
        status_code=303
    )


# 3. 退回稿件並記錄原因
@app.post("/editor/manuscripts/{manuscript_id}/return")
async def return_manuscript(
    manuscript_id: int,
    request: Request,
    reason: str = Form(...),
    db=Depends(getDB)
):
    user = await require_editor(request, db)

    reason = reason.strip()

    # 退稿原因不能空白
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="退稿時必須填寫原因"
        )

    # 將文章退回編輯中
    cur = await db.execute(
        """
        UPDATE manuscripts
        SET status = 'editing',
            reviewed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND status = 'under_review'
        RETURNING id
        """,
        (manuscript_id,)
    )

    updated = await cur.fetchone()

    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="文章已被處理，無法重複審查"
        )

    # 儲存退稿原因與審查者
    await db.execute(
        """
        INSERT INTO review_logs
            (manuscript_id, reviewer_id, action, reason)
        VALUES (%s, %s, 'returned', %s)
        """,
        (manuscript_id, user["id"], reason)
    )

    await db.commit()

    return RedirectResponse(
        "/editor",
        status_code=303
    )
