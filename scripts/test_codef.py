import json
import requests
from urllib.parse import quote, unquote_plus
from easycodefpy import Codef, ServiceType

# SDK에 내장된 샌드박스 인증 정보로 토큰 발급 (개인 키·공개키 불필요, 샌드박스 전용)
codef = Codef()
token = codef.request_token(ServiceType.SANDBOX)

# 더미 카드 목록 조회
response = requests.post(
    "https://sandbox.codef.io/v1/kr/card/p/account/card-list",
    headers={"Authorization": f"Bearer {token}"},
    data=quote(json.dumps({
        "organization": "0309",
        "connectedId": "sandbox-test",
        "inquiryType": "0"
    })),
    timeout=30
)
response.raise_for_status()

result = json.loads(unquote_plus(response.text))
print(json.dumps(result, ensure_ascii=False, indent=2))
