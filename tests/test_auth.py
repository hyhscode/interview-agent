"""认证接口的测试。"""


def _register_and_login(client, email="alice@test.com", password="12345678"):
    """小工具：注册 + 登录，返回 token。下划线开头表示"仅供本文件内部使用"。"""
    client.post("/auth/register", json={"email": email, "password": password})
    response = client.post("/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


# ---------- 注册 ----------

def test_register_success(client):
    response = client.post(
        "/auth/register",
        json={"email": "new@test.com", "password": "12345678"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@test.com"
    assert "id" in body
    # ★ 关键断言：返回体里不能有密码相关字段
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_duplicate_email(client):
    payload = {"email": "dup@test.com", "password": "12345678"}
    client.post("/auth/register", json=payload)          # 第一次成功
    response = client.post("/auth/register", json=payload)  # 第二次应失败
    assert response.status_code == 400
    assert response.json()["detail"] == "该邮箱已注册"


def test_register_password_too_short(client):
    response = client.post(
        "/auth/register",
        json={"email": "short@test.com", "password": "123"},
    )
    assert response.status_code == 422
    # ↑ 422 是 Pydantic 的校验失败，在进业务逻辑之前就被拦住了


# ---------- 登录 ----------

def test_login_success(client):
    client.post("/auth/register", json={"email": "login@test.com", "password": "12345678"})
    response = client.post("/auth/login", json={"email": "login@test.com", "password": "12345678"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2
    # ↑ JWT 是三段、两个点。这个断言能挡住"返回了个空字符串"这种情况


def test_login_wrong_password(client):
    client.post("/auth/register", json={"email": "wp@test.com", "password": "12345678"})
    response = client.post("/auth/login", json={"email": "wp@test.com", "password": "wrong-password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"
    # ↑ 注意提示语是统一的，不说"密码错"还是"用户不存在" —— 防用户名枚举


def test_login_unknown_email(client):
    response = client.post("/auth/login", json={"email": "nobody@test.com", "password": "12345678"})
    assert response.status_code == 401
    # ↑ 和"密码错"返回完全一样，这就是防枚举的证据


# ---------- 当前用户 ----------

def test_me_with_token(client):
    token = _register_and_login(client, email="me@test.com")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "me@test.com"


def test_me_without_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "未登录"


def test_me_with_tampered_token(client):
    token = _register_and_login(client, email="tamper@test.com")

    head, payload, signature = token.split(".")
    broken = f"{head}.{payload}x.{signature}"
    # ↑ 在 payload 后面加一个字符 → 签名就对不上了

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {broken}"})
    assert response.status_code == 401
    assert "失效" in response.json()["detail"]
    # ↑ 只断言关键词，不断言完整文案：
    #   状态码（401）和"哪一类 401"是契约，文案措辞不是。
    #   否则哪天改个标点，测试就红，但功能其实没坏
