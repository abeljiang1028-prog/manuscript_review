# 投稿審查系統

使用 FastAPI、PostgreSQL、HTML、CSS 和 JavaScript
開發的文章投稿與審查管理系統。

## 一、專題介紹

本系統提供作者投稿及編輯審查的功能。

作者可以新增、修改、刪除與送出文章，
編輯則負責審查文章，決定通過或退回。

## 二、系統角色

### 作者 Author
- 註冊及登入帳號
- 查看自己的投稿清單
- 新增文章
- 修改編輯中的文章
- 刪除編輯中的文章
- 送出文章審查
- 查看審查狀態及退稿原因

### 編輯 Editor
- 登入編輯帳號
- 查看待審查文章
- 依送審時間排序
- 閱讀文章內容
- 通過文章
- 退回文章並填寫原因
- 記錄審查結果

## 三、文章狀態

| 狀態 | 說明 |
|---|---|
| editing | 編輯中 |
| under_review | 審查中 |
| approved | 已通過 |

狀態轉換：

編輯中 → 審查中 → 已通過

如果編輯退稿：

審查中 → 編輯中

作者可以修改文章後重新送審。

## 四、使用技術

- Python
- FastAPI
- PostgreSQL
- HTML
- CSS
- JavaScript
- Jinja2
- Git / GitHub

## 五、資料庫

使用三張主要資料表：

- users：使用者及角色資料
- manuscripts：文章資料及審查狀態
- review_logs：審查結果及退稿原因

建表 SQL 請參考 schema.sql。

## 六、安裝與執行

### 1. 建立虛擬環境

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安裝套件

```powershell
python -m pip install -r requirements.txt
```

### 3. 建立 PostgreSQL 資料庫

建立名為 manuscript_review 的資料庫。

在新建立的空白資料庫中，
執行 schema.sql 建立資料表。

### 4. 設定環境變數

參考 .env.example，在專案根目錄建立 .env，
填入自己的 PostgreSQL 連線資訊及 SESSION_SECRET。

### 5. 啟動 FastAPI

```powershell
python -m uvicorn main:app --reload
```

瀏覽器開啟：

http://127.0.0.1:8000/

## 七、測試帳號

透過註冊功能建立的帳號預設為 author。

若需建立測試編輯帳號，
可以先註冊帳號，再由資料庫管理者執行：

```sql
UPDATE users
SET role = 'editor'
WHERE username = '你的測試編輯帳號';
```

## 八、注意事項

- 本專題目前主要供本機開發與課堂展示使用。
- .env 不會上傳到 GitHub。
- GitHub 不包含本機 PostgreSQL 的實際資料。
- 正式公開部署前需另外進行安全性設定。
