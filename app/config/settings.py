from pydantic_settings import BaseSettings

class Settings(BaseSettings):
	DATABASE_URL: str
	GITHUB_AUTHORIZE_URL: str = "https://github.com/login/oauth/authorize"
	GITHUB_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
	GITHUB_USER_URL: str = "https://api.github.com/user"
	GITHUB_CLIENT_ID: str
	GITHUB_CLIENT_SECRET: str
	GITHUB_CLIENT_ID_CLI: str
	GITHUB_CLIENT_SECRET_CLI: str
	GITHUB_REDIRECT_URI: str

	JWT_SECRET: str
	JWT_ALGORITHM: str
	ACCESS_TOKEN_EXPIRE_MINUTES: int
	REFRESH_TOKEN_EXPIRE_MINUTES: int

	WEB_ORIGIN: str = "http://localhost:8000"

	class Config:
		env_file = ".env"


settings = Settings()