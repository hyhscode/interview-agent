
from app.schemas.resume import ResumeParsed


def _register_and_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "12345678"})
    r = client.post("/auth/login", json={"email": email, "password": "12345678"})
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_upload_success(client, fake_pipeline):
    token = _register_and_login(client, "up@test.com")

    response = client.post(
        "/resumes",
        files={"file": ("cv.pdf", b"%PDF-fake", "application/pdf")},
        headers=_auth(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "parsed"
    assert body["parsed"]["name"] == "张三"
    assert body["parsed"]["skills"] == ["Python", "FastAPI"]


def test_upload_without_token(client):
    response = client.post(
        "/resumes",
        files={"file": ("cv.pdf", b"%PDF-fake", "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_wrong_type(client):
    token = _register_and_login(client, "wrong@test.com")
    response = client.post(
        "/resumes",
        files={"file": ("cv.txt", b"hello", "text/plain")},
        headers=_auth(token),
    )
    assert response.status_code == 400


def test_upload_not_a_resume(client, monkeypatch):

    token = _register_and_login(client, "notresume@test.com")

    monkeypatch.setattr(
        "app.routers.resumes.pdf_service.extract_text",
        lambda b: ("这是一份产品使用说明书。本产品适用于家庭场景，请在使用前仔细阅读全部内容。第一部分为产品功能介绍，说明各部件的作用与操作方法；第二部分为安装与调试步骤；第三部分为日常维护与清洁建议；第四部分为常见故障排查；最后附有售后服务与联系方式。", 1),
    )
    monkeypatch.setattr(
        "app.routers.resumes.resume_parser.parse_resume",
        lambda t: (ResumeParsed(), 10, 5),   # 全空
    )

    response = client.post(
        "/resumes",
        files={"file": ("doc.pdf", b"%PDF-fake", "application/pdf")},
        headers=_auth(token),
    )
    assert response.status_code == 400
    assert "没有识别出简历信息" in response.json()["detail"]


def test_get_own_resume(client, fake_pipeline):
    token = _register_and_login(client, "own@test.com")
    created = client.post(
        "/resumes",
        files={"file": ("cv.pdf", b"%PDF-fake", "application/pdf")},
        headers=_auth(token),
    ).json()

    response = client.get(f"/resumes/{created['id']}", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_cannot_get_others_resume(client, fake_pipeline):

    token_a = _register_and_login(client, "alice@test.com")
    token_b = _register_and_login(client, "bob@test.com")

    resume_a = client.post(
        "/resumes",
        files={"file": ("alice-cv.pdf", b"%PDF-fake", "application/pdf")},
        headers=_auth(token_a),
    ).json()

    response = client.get(f"/resumes/{resume_a['id']}", headers=_auth(token_b))

    assert response.status_code == 404

    assert response.json()["detail"] == "简历不存在"


def test_get_nonexistent_resume(client):
    token = _register_and_login(client, "ghost@test.com")
    response = client.get("/resumes/99999", headers=_auth(token))
    assert response.status_code == 404
