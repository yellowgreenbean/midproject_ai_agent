from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5433/midproject"

    # CORS: 이 API 를 부를 수 있는 화면(프런트엔드) 주소. 쉼표로 구분, 주소는 정확히(scheme://host:port).
    # 로그인 쿠키를 주고받으므로 "*" 는 쓸 수 없다. 기본값: Vite(5173) · Next/CRA(3000), localhost 와 127.0.0.1 둘 다
    # (브라우저는 localhost 와 127.0.0.1 을 다른 주소로 본다)
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"
    )

    # 로그인 쿠키에 Secure 를 붙일지. https 로 배포할 때 true. 내 PC(http)에서는 false 라야 쿠키가 저장된다
    cookie_secure: bool = False

    # 개발용: true 면 로그인 쿠키가 없을 때 X-User-Id 헤더로 회원을 정한다(Swagger·curl 시험용).
    # 헤더만 바꾸면 누구든 다른 회원 행세를 할 수 있으므로 기본값은 false — 배포 환경에서 켜지 말 것
    auth_dev_header: bool = False

    # 챗봇 (POST /agent/chat, app/agent.py) — 키가 없으면 챗봇만 503 으로 답하고 나머지 API 는 그대로 돈다
    gemini_api_key: str = ""
    chat_model: str = "gemini-2.5-flash"
    rag_experiment: str = "pc-1000"  # scripts/rag_ingest.py --save 로 채운 청킹 실험 이름

    # 이메일 인증번호 메일 (app/mailer.py). SMTP_HOST 가 비면 메일 대신 서버 콘솔에 번호를 찍는다.
    # Gmail 은 계정 비밀번호가 아니라 「앱 비밀번호」(2단계 인증 필요)를 SMTP_PASSWORD 에 넣는다. 커밋 금지(.env)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""  # 보내는 주소. 비면 SMTP_USER

    # 테스트 전용: true 면 인증번호 발송 응답에 dev_code 로 번호를 같이 준다(tests/conftest.py 가 켠다).
    # 켜 두면 메일을 안 받아도 누구나 인증할 수 있으므로 앱을 돌릴 때는 false
    email_dev_code: bool = False

    # 서버 안 1분 스케줄러(예약 송금 실행 등, app/jobs.py run_minutely). 테스트는 끈다(tests/conftest.py)
    scheduler_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
