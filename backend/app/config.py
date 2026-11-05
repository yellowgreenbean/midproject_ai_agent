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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
