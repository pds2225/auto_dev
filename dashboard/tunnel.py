"""ngrok 터널 실행기 — 외부에서 Streamlit 접속"""
from __future__ import annotations

import os
import re
import sys

# Windows cp949 터미널에서도 유니코드 출력이 가능하도록 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

try:
    from pyngrok import ngrok
except ImportError:
    print("❌ pyngrok이 설치되지 않았습니다.")
    print("   python -m pip install -r .\\dashboard\\requirements.txt")
    sys.exit(1)

# ngrok authtoken: 영숫자·언더스코어로 구성된 30자 이상 문자열
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_]{30,}$")
# authtoken이 아닌 것으로 알려진 접두사
_NON_TOKEN_PREFIXES = ("cr_",)


def _validate_auth_token(token: str) -> None:
    """토큰 형식 검증 — 문제가 있으면 안내 메시지를 출력하고 즉시 종료합니다.
    실제 토큰 값은 절대 출력하지 않습니다."""
    if not token:
        print("❌ NGROK_AUTHTOKEN이 설정되지 않았습니다.")
        print("   https://dashboard.ngrok.com/get-started/your-authtoken 에서")
        print("   authtoken을 복사해 입력하세요.")
        sys.exit(1)

    for prefix in _NON_TOKEN_PREFIXES:
        if token.startswith(prefix):
            print("❌ 입력값이 ngrok authtoken 형식이 아닙니다.")
            print("   ngrok dashboard의 Your Authtoken 값을 그대로 복사하세요.")
            print(f"   {prefix}... 로 시작하는 값은 일반적으로 authtoken이 아닙니다.")
            sys.exit(1)

    if not _TOKEN_RE.match(token):
        print("❌ 입력값이 ngrok authtoken 형식이 아닙니다.")
        print("   ngrok dashboard의 Your Authtoken 값을 그대로 복사하세요.")
        sys.exit(1)


def configure_auth_token() -> None:
    """NGROK_AUTHTOKEN 환경변수를 검증하고 pyngrok에 적용합니다."""
    token = os.environ.get("NGROK_AUTHTOKEN", "").strip()
    _validate_auth_token(token)
    ngrok.set_auth_token(token)


def start_tunnel(port: int = 8501) -> str:
    """Streamlit 포트를 외부에 공개"""
    try:
        configure_auth_token()
        public_url = ngrok.connect(port, "http")
        print(f"🌐 외부 접속 주소: {public_url}")
        print("📱 핸드폰/다른 PC에서 위 주소로 접속하세요")
        print("⚠️  이 창을 닫으면 터널도 종료됩니다")
        print("-" * 50)
        input("⏹️  종료하려면 엔터를 누르세요...")
        return public_url
    except Exception as e:
        msg = str(e)
        if "ERR_NGROK_105" in msg or "authtoken" in msg.lower():
            print("❌ ngrok 인증 오류입니다. (ERR_NGROK_105)")
            print("   https://dashboard.ngrok.com/get-started/your-authtoken 에서")
            print("   올바른 authtoken을 복사해 다시 시도하세요.")
        elif any(kw in msg.lower() for kw in ("install", "download", "binary", "not found")):
            print("❌ ngrok 바이너리를 설치할 수 없습니다.")
            print("   인터넷 연결을 확인하거나 pyngrok을 재설치하세요:")
            print("   python -m pip install -r .\\dashboard\\requirements.txt")
        else:
            print(f"❌ 터널 생성 실패: {e}")
        sys.exit(1)


def stop_tunnel(url: str) -> None:
    ngrok.disconnect(url)
    print("✅ 터널 종료 완료")


if __name__ == "__main__":
    url = start_tunnel()
    stop_tunnel(url)
