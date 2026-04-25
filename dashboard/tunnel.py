tunnel.py

"""ngrok 터널 실행기 — 외부에서 Streamlit 접속"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from pyngrok import ngrok
except ImportError:
    print("❌ pyngrok이 설치되지 않았습니다.")
    print("   pip install pyngrok")
    sys.exit(1)


def start_tunnel(port: int = 8501) -> str:
    """Streamlit 포트를 외부에 공개"""
    try:
        public_url = ngrok.connect(port, "http")
        print(f"🌐 외부 접속 주소: {public_url}")
        print(f"📱 핸드폰/다른 PC에서 위 주소로 접속하세요")
        print(f"⚠️  이 창을 닫으면 터널도 종료됩니다")
        print("-" * 50)
        input("⏹️  종료하려면 엔터를 누르세요...")
        return public_url
    except Exception as e:
        print(f"❌ 터널 생성 실패: {e}")
        sys.exit(1)


def stop_tunnel(url: str) -> None:
    ngrok.disconnect(url)
    print("✅ 터널 종료 완료")


if __name__ == "__main__":
    url = start_tunnel()
    stop_tunnel(url)