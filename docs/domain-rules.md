# 도메인 규칙 출처 (외부 기준 — 기억으로 단정하지 않고 출처를 남긴다)

조사일: 2026-11-03 · 대상: 회원 탈퇴 전 3단계(`AUTH-F09`)와 데이터 보존·파기
확인 상태: **[원문 확인]** 원문 페이지에서 문장을 읽음 · **[발췌만]** 검색 결과 발췌만 봄(원문 못 읽음) · **[2차]** 블로그 등 비공식

## 1. 법령

| 기준 | 내용 | 상태 | 출처 |
|---|---|---|---|
| 전자금융거래법 제22조 ①② | 금융회사등은 전자금융거래기록을 생성해 **5년의 범위 안에서 대통령령이 정하는 기간** 보존. 보존 기간이 지나고 거래 관계가 끝나면 **5년 이내**에 파기(신용정보는 제외) | [원문 확인] | https://www.law.go.kr/LSW//lsInfoP.do?lsId=010199&ancYnChk=0 |
| 전자금융거래법 시행령 제12조 ① | **5년**: 거래 신청·조건 변경, 전자적 장치 접속기록, 건당 1만원 초과 거래 기록 등 / **1년**: 건당 1만원 이하 거래 기록, 거래승인 기록, 금융위 고시 기록 / 전자금융보조업자는 3년 | [원문 확인] 단, 이 조문 표시가 "개정 2015. 4. 14." 까지라 **2026-11-03 현행인지는 확인 못 함** | https://www.law.go.kr/LSW//lsLinkCommonInfo.do?lspttninfSeq=118989&chrClsCd=010202 |
| 개인정보 보호법 제21조 ① | 개인정보가 불필요하게 되면 **지체 없이 파기**. 다만 다른 법령에 따라 보존해야 하면 예외 (시행 2026. 9. 11. 기준 조문) | [원문 확인] | https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1027063705 |
| 개인정보 보호법 제21조 ③ | 예외로 보존할 때는 **다른 개인정보와 분리해서 저장·관리** | [발췌만] 문장이 중간에 잘려 있음 | http://www.law.go.kr/LSW/lsLinkProc.do?lsNm=%EA%B0%9C%EC%9D%B8%EC%A0%95%EB%B3%B4%EB%B3%B4%ED%98%B8%EB%B2%95&lsId=2073298&chrClsCd=010202&joNo=002100000%5E003700004&mode=10&gubun=admRul&datClsCd=010102 |

**아직 안 찾아본 법령**: 신용정보법상 신용정보 보존, 금융실명법, 특정금융거래정보법(고객확인 기록 보존). 실제 금융 서비스라면 확인해야 한다.

## 2. 실제 서비스의 탈퇴 전 조건 (우리 3단계 설계와 비교용)

| 서비스 | 탈퇴 전에 요구하는 것 | 상태 | 출처 |
|---|---|---|---|
| 토스 | 토스머니·포인트 잔액 0원, 토스유스카드 해지, 토스프라임 해지, 등록된 자동이체 삭제 (뒷부분 잘림) | [발췌만] 원문 열람 실패 | https://support.toss.im/faq/218 |
| 토스증권 계좌 해지 | 주식 전부 매도 또는 타 증권사로 출고, 잔액 비우기, 지연이체 해지 | [발췌만] | https://support.toss.im/faq/3337 |
| 토스 개인정보처리방침 | 탈퇴 후 **1개월** 간 이름·휴대전화·계좌번호·금융거래내역을 부정거래·자금세탁 방지, 결제취소 환급 확인 목적으로 이용. 전자금융거래 기록 5년, 계약·대금결제 기록 5년, 소비자 불만·분쟁 3년, 부정 이용 기록 10년 | [원문 확인] | https://toss.im/docs/53/11413 |
| 카카오페이 | 페이머니 잔액, 증권 계좌, 페이 카드 사용, 친구송금 거래, 진행 중 충전/송금이 있으면 서비스 해지 불가. **페이신용카드를 해지해야 탈퇴 가능**. 자동·정기결제는 **탈퇴 시 모두 해지 처리**. 카카오T 미수금·예약 중 티켓이 있으면 탈퇴 제한. 포인트 소멸·복구 불가. 금융거래 개인신용정보 5년 보관 | [원문 확인] | https://support.kakaopay.com/web/faq-result?gubun=03&data=%ED%83%88%ED%87%B4 |
| 카카오뱅크 | 보유 계좌 전부 해지, OTP 해지, 체크카드 해지 후 탈퇴 | **[2차]** 블로그 요약만. 공식 약관·고객센터는 읽지 않음 | (블로그 다수) |

## 3. 정지된 계좌를 해지할 수 있는가 (`AUTH-F09` 일괄 해지의 "일시정지 계좌" 문제)

조사일: 2026-11-03. 실제 은행에는 "정지"가 **두 종류**라서 따로 본다.

### 3.1 시스템이 거는 정지 — 거래중지계좌 (오래 안 쓴 소액 계좌, 대포통장 방지)
| 기준 | 내용 | 상태 | 출처 |
|---|---|---|---|
| 카카오뱅크 | 거래중지계좌로 편입되면 입출금·카드결제·대출약정을 할 수 없다. **"모바일앱을 통한 예금잔액 확인 및 계좌 해지는 가능"**. 편입 조건: 잔액 1만원 미만+1년 미거래 / 1만~5만원 미만+2년 / 5만~10만원 미만+3년 | [원문 확인] | https://kakaobank.com/Corp/News/Notices/view/16136 |
| 카카오뱅크 | 거래를 다시 하려면(해제) 금융거래목적 확인 증빙서류 제출 | [발췌만] | https://www.kakaobank.com/Corp/News/Notices/view/9558 |
| 하나은행 | 편입 조건은 위와 같고, 해제하려면 영업점에서 금융거래목적확인서와 증빙서류 제출. 해지는 인터넷뱅킹·앱·고객센터·영업점에서 가능 | 해제 방법은 [원문 확인], **해지 채널은 [발췌만]** | https://biz.kebhana.com/cont/customer/customer07/1508765_135643.jsp |
| 씨티은행 | 중지계좌로 편입된 계좌는 영업점·인터넷/모바일뱅킹으로 해지해 잔액을 찾을 수 있다 | [발췌만] | https://www.citibank.co.kr/CusConsCnts0102.act?FAQ_ID=KNOW0000000065&IDX=3 |

→ **시스템이 건 정지는 해제하지 않고도 해지할 수 있다.** 해제(재사용)가 해지보다 까다롭다.

### 3.2 고객이 직접 거는 정지 — 본인계좌 일괄지급정지 (금융사기 예방)
| 기준 | 내용 | 상태 | 출처 |
|---|---|---|---|
| 우리은행 약관 | **"지급정지, 압류가 등록된 계좌 등 일부 계좌의 경우에는 잔고이전·해지가 되지 않을 수 있습니다."** 지급정지 시 연결된 직불·체크카드 이용이 제한된다. 지급정지의 해지(해제)는 금융회사를 통해 가능하고 절차는 금융회사마다 다르다 | [원문 확인] | https://spot.wooribank.com/pot/Dream?withyou=CQCCS0100 |
| 신한투자증권 안내문 | 지급정지 시 **자동이체를 포함한 모든 출금·출고 거래가 정지**되고 체크카드 이용도 제한된다(증권 매매는 가능). 해제는 개별 금융회사 또는 참여 금융회사 창구에서 일괄 해제. 지급정지로 자동이체가 멈춰 생기는 연체 피해는 금융회사가 책임지지 않는다 | [원문 확인] | https://file.shinhaninvest.com/filedoc/clause/k_131.pdf |
| 토스뱅크 FAQ | 본인 계좌 일괄 지급정지 서비스 설명 | [발췌만] 원문 열람 실패 | https://support.toss.im/faq/tossbank/19207?from=23&page=5 |

→ **고객이 직접 건 정지(지급정지)는 해지가 안 될 수 있어서, 해제 후 해지가 기본이다.** 우리 `SUSPENDED`(사용자가 거는 일시정지)는 이쪽과 닮았다.

**아직 안 찾아본 것**: 압류·사기이용계좌 지급정지처럼 법에 따른 정지(통신사기피해환급법 등)는 사용자가 풀 수 없고 해지도 막힌다. 우리 모델에는 아직 없는 상태다. 토스뱅크·카카오뱅크의 "고객이 직접 거는 일시정지" 전용 기능의 공식 안내는 찾지 못했다.

## 4. 토스 기준 (이 프로젝트는 토스 클론 — 사용자 말 2026-11-03)

조사일: 2026-11-03. 토스 공식 페이지 위주. 열리지 않은 페이지는 검색 결과 발췌만 봤다.

| 주제 | 토스가 하는 것 | 상태 | 출처 |
|---|---|---|---|
| 탈퇴 전 조건 | 토스머니·포인트 잔액 0원, 토스유스카드 해지, 토스프라임 해지, **등록된 자동이체 모두 삭제** | [발췌만] 원문 열람 실패 | https://support.toss.im/faq/218 |
| 탈퇴 뒤 거래기록 | 탈퇴하면 개인정보처리방침에 따라 **기존 거래기록은 삭제되고 재가입해도 확인할 수 없다**. 단 금융거래정보는 관련 법에 따라 5년간 (보관, 문장 뒤가 잘림) | [발췌만] | https://support.toss.im/faq/218 |
| 탈퇴 뒤 정보 이용 | 탈퇴 후 **1개월** 동안 이름·휴대전화·계좌번호·거래내역을 부정거래·자금세탁 방지, 결제취소 환급 확인에 이용 | [원문 확인] | https://toss.im/docs/53/11413 |
| 동의 철회 | 회원 탈퇴를 하면 필수 동의를 포함해 **모든 동의가 자동으로 철회** | [발췌만] | https://toss.im/privacy-policy |
| 연결 서비스 해지 위치 | 자동납부 해지: 앱 → 토스뱅크 → 통장 → 관리 → 자동 납부 → 해지. 카드 해지: 앱 → 토스뱅크 → 카드 → 관리 → 카드 해지하기 (앱 안에서 직접) | [발췌만] | https://support.toss.im/faq/tossbank/5365 · https://support.toss.im/faq/5283 |
| 남은 돈 옮기며 해지 (휴면계좌) | 앱에서 휴면계좌(최근 1년 입출금 없음) 조회 → **잔액을 옮길 계좌(또는 기부) 선택 → 즉시 이체 → 해지**. "해지가 불가한 경우 해당 은행 방문이 필요할 수 있다" | [원문 확인] | https://toss.im/tossfeed/article/toss-guide-dormant-account |
| 계좌 해지가 막히는 경우 | 모임통장 약관: 결제성 거래(카드 결제계좌 등)가 모두 해지된 경우에만 해지 가능. **압류 등 출금제한 사고신고가 등록되면 해지 불가** | [발췌만] 모임통장 상품 약관이며 일반 입출금통장은 못 봄 | https://www.tossbank.com/product-service/savings/moim-account |
| 이용제한(정지) | 모임통장은 ① 거래중지·휴면 전환 ② **공동명의자가 고객센터 등을 통해 이용제한을 직접 신청** ③ 압류일 때 이용이 일시 중단될 수 있다. 본인 계좌 일괄 지급정지도 고객센터 유선 본인확인 뒤 즉시 | [발췌만] | 위 모임통장 주소 · https://support.toss.im/faq/tossbank/19207?from=23&page=5 |

**알 수 있는 것**: 토스는 ① 잔액 0원 ② 자동이체·카드 해지 ③ 탈퇴 후 1개월 유예 ④ 압류 등 출금제한 계좌만 해지 불가. 정지·휴면 계좌는 앱에서 해지한다.

**못 찾은 것**: 토스 앱에 "계좌 일시정지" 버튼이 따로 있다는 안내는 찾지 못했다(고객센터를 통한 이용제한만 확인). 우리 `ACCT-F05` 일시정지는 토스에 똑같은 기능이 확인되지 않는다. `toss.im/suspend` 페이지는 내용을 확인하지 못했다.

## 5. 예금·적금 상품 금리 (더미 `data/dummy/products/products.json` 근거)

조사일: 2026-11-04. 공식 상품 페이지에서 금리표를 읽었다.

| 상품 | 내용 | 상태 | 출처 |
|---|---|---|---|
| 토스뱅크 원하는 날 만기되는 정기예금 | 기준일 2026-11-03, 세전. 1~3개월 미만 1.8% / 3~6 미만 3.3% / 6~9 미만 3.4% / 9~12 미만 3.5% / 12~24 미만 3.8% / 24~36 미만 3.0% / 36개월 3.0%. 100만~10억 원(만 원 단위), 1~36개월 | [원문 확인] | https://www.tossbank.com/product-service/savings/dday-deposit |
| 토스뱅크 자유적금 | 기준일 2026-11-03. 3~5개월 2.60% / 6~11 2.90% / 12~23 3.25% / 24~35 2.50% / 36개월 2.50%. 월 최대 300만 원. 우대 연 0.5%(계약월수 1/2 이상 자동이체 성공) | [원문 확인] | https://www.tossbank.com/product-service/savings/savings-freedom |
| 우리은행 예금·적금 30개 (더미에서는 "두린은행") | 아래 5-1 표. 2026-11-04 공식 페이지에서 직접 읽음 | [원문 확인] | 5-1 표 |

토스뱅크 상품은 위 조사 기록으로만 남기고 더미 데이터(`products.json`)에서는 뺐다(사용자 결정, 2026-11-04).

### 5-1. 두린은행 상품 30개의 출처 (원본: 우리은행, 확인일 2026-11-04)

방법: 상품 목록 페이지(목돈굴리기 11개 + 목돈모으기 19개)에서 상품 코드를 얻고, 상품별 '미리보기'(가입대상·기간·금액)와 '금리표' 조각 페이지를 읽었다. 금리 기준일은 상품마다 달라 `products.json` 의 `effective_from` 에 있다. 금리표가 비어 있는 4개(CD plus예금·두루두루정기예금·미소드림적금·희망드림적금)는 금리 행이 없다. 더미의 `source_url` 은 모의 프로젝트용으로 비웠다.

| 상품 번호 | 두린은행 상품 | 원본 상품명 | 상품 코드 | 출처 |
|---|---|---|---|---|
| prod_003 | 두린플러스 예금 | WON플러스 예금 | P010002491 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002491&PRD_YN=Y |
| prod_004 | 두린 적금 | WON 적금 | P010002353 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002353&PRD_YN=Y |
| prod_005 | 두린 369 정기예금 | 우리 369 정기예금 | P010002605 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002605&PRD_YN=Y |
| prod_006 | 두린 첫거래우대 정기예금 | 우리 첫거래우대 정기예금 | P010002487 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002487&PRD_YN=Y |
| prod_007 | 두린 SUPER 정기예금 | 우리 SUPER 정기예금 | P010002402 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002402&PRD_YN=Y |
| prod_008 | 두린 기업정기예금 | WON 기업정기예금 | P010002385 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002385&PRD_YN=Y |
| prod_009 | ISA정기예금 | ISA정기예금 | P010000002 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000002&PRD_YN=Y |
| prod_010 | CD plus예금 | CD plus예금 | P010000364 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000364&PRD_YN=Y |
| prod_011 | 정기예금 | 정기예금 | P010000196 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000196&PRD_YN=Y |
| prod_012 | 표지어음 | 표지어음 | P010000344 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000344&PRD_YN=Y |
| prod_013 | 양도성예금증서(CD) | 양도성예금증서(CD) | P010000343 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000343&PRD_YN=Y |
| prod_014 | 두루두루정기예금 | 두루두루정기예금 | P010000361 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000361&PRD_YN=Y |
| prod_015 | 두린 SUPER주거래 적금 | 우리 SUPER주거래 적금 | P010000109 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000109&PRD_YN=Y |
| prod_016 | 두린 SUPER주거래 자유적금 | 우리 SUPER주거래 자유적금 | P010000110 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000110&PRD_YN=Y |
| prod_017 | 두린금융 다함께 적금 2 | 우리금융 다함께 적금 2 | P010002603 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002603&PRD_YN=Y |
| prod_018 | 두린 청년미래적금 | 우리 청년미래적금 | P010002592 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002592&PRD_YN=Y |
| prod_019 | 두린 사장님 성장 적금 | 우리 사장님 성장 적금 | P010002588 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002588&PRD_YN=Y |
| prod_020 | 두린 두근두근 행운적금 | 우리 두근두근 행운적금 | P010002582 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002582&PRD_YN=Y |
| prod_021 | 삼성월렛머니 두린 적금 | 삼성월렛머니 우리 적금 | P010002576 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002576&PRD_YN=Y |
| prod_022 | Npay 두린 적금 | Npay 우리 적금 | P010002570 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002570&PRD_YN=Y |
| prod_023 | 두린모바일 적금 | 우리WON모바일 적금 | P010002566 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002566&PRD_YN=Y |
| prod_024 | N일 적금(31일) | N일 적금(31일) | P010002514 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002514&PRD_YN=Y |
| prod_025 | N일 적금(100일) | N일 적금(100일) | P010002515 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002515&PRD_YN=Y |
| prod_026 | N일 적금(200일) | N일 적금(200일) | P010002516 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002516&PRD_YN=Y |
| prod_027 | 두린 아이행복 적금2 | 우리 아이행복 적금2 | P010002494 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002494&PRD_YN=Y |
| prod_028 | 두린 (영업점명) 적금 | 우리 (영업점명) 적금 | P010002482 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002482&PRD_YN=Y |
| prod_029 | 두린 (업체명 임직원) 적금 | 우리 (업체명 임직원) 적금 | P010002373 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002373&PRD_YN=Y |
| prod_030 | 두린 장병내일준비적금 | 우리은행 장병내일준비적금 | P010002283 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010002283&PRD_YN=Y |
| prod_031 | 두린미소드림적금 | 우리미소드림적금 | P010000016 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000016&PRD_YN=Y |
| prod_032 | 두린희망드림적금 | 우리희망드림적금 | P010000136 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0001&cc=c011240:c009166;c012263:c012399&PRD_CD=P010000136&PRD_YN=Y |

### 5-2. 챗봇 RAG 문서 `data/rag/` 의 출처 (원본: 우리은행, 받은 날 2026-11-04)

원본 PDF 를 그대로 저장했다(글자 변환·이름 바꾸기 안 함 — PDF 안에는 "우리은행" 이 그대로 있다). 받는 주소는 모두
`https://spot.wooribank.com/pot/pot/mall/comm/download.jsp?PLM_BIZ_DSCD=<구분>&PLM_ANX_SAVE_FILE_NM=<파일코드>` 이고, 상품 설명서 링크는 각 상품 상세 페이지(5-1 표의 URL)에 걸려 있다.

| 파일 | 원본 | 구분 · 파일코드 |
|---|---|---|
| `terms/deposit_basic_terms.pdf` | 예금거래기본약관 (2025-01-17 개정) | 00 · `PLM_P00XXXXXXX_A0101_20250118235506000274.pdf` |
| `terms/time_deposit_terms.pdf` | 거치식예금약관 (파일명 정기예금약관) | 00 · `PLM_P00XXXXXXX_A0102_20211213142401000408.pdf` |
| `terms/installment_savings_terms.pdf` | 적립식예금 약관 (2017-01-01) | 00 · `PLM_P00XXXXXXX_A0104_20211213142420000077.pdf` |
| `terms/checking_account_terms.pdf` | 입출금이 자유로운 예금 약관 | 00 · `PLM_P00XXXXXXX_A0103_20240402180359000397.pdf` |
| `terms/auto_transfer_terms.pdf` | 계좌간 자동이체 약관 (개정 후) | 00 · `PLM_P00XXXXXXX_A0105_20230313162334000064.pdf` |
| `terms/tax_free_savings_rider.pdf` | 비과세종합저축 특약 | 00 · `PLM_P00XXXXXXX_A0196_20260102092526000492.pdf` |
| `terms/auto_renewal_rider.pdf` | 「만기자금 자동재예치」 특약 | 00 · `PLM_P00XXXXXXX_A0197_20260330155556000223.pdf` |
| `products/prod_XXX.pdf` (27개) | 상품설명서 (5-1 표의 상품번호와 같음) | 01 · `PLM_<상품코드>_DA001_<날짜>.pdf` |
| `riders/prod_XXX.pdf` (27개) | 상품별 특약 (5-1 표의 상품번호와 같음, prod_015 는 상품코드 P010000109) | 01 · `PLM_<상품코드>_DF003_<날짜>.pdf` |
| `consents/npay_savings_*.pdf` (2) | Npay 적금(prod_022) 개인(신용)정보 제3자 제공 동의서 · 금융거래정보 이용·제공 동의서 | 00 · `A05KA_20250701123307000371` · `A05KC_20250701123502000760` |
| `consents/cjpay_account_*.pdf` (2) | CJ PAY 통장(입출금, 더미에 없음) 같은 두 동의서 | 00 · `A05K8_20250410165411000058` · `A05K0_20250410165458000681` |
| `consents/nonface_account_block_check_consent.pdf` | 비대면 계좌개설 안심차단 등록 여부 조회용 개인(신용)정보 동의서 | 00 · `A05L6_20250205100456000079` |

- 상품 설명서가 없는 상품: `prod_009` ISA정기예금(페이지에 공통 약관만), `prod_013` 양도성예금증서(CD)(내려받기 링크 없음). 특약이 없는 상품: `prod_009`·`prod_011`(정기예금)·`prod_013`.
- 카드 약관 `cards/*.pdf` 2개(우리카드 「신용카드 개인회원 약관 전문(20260408개정 20260512시행)」 · 「체크카드 개인회원 약관」 전문)는 pc.wooricard.com 상품공시실 > 약관(`H1CCT211S09.do`)에서 받았다. 바로 받는 링크가 없고 업로드 위젯(RAONK)으로만 내려준다. 이 페이지는 목록 요청(`getMainDataList.pwkjson`)을 두 번 보내고 두 번째가 "동일한 거래 요청" 오류로 실패해 버튼이 안 그려지므로, Playwright 로 두 번째 요청에 첫 응답을 돌려준 뒤 「신용카드/체크카드 약관 다운로드」 버튼을 눌렀다.
- 카드 부가 약관 31개(`cards/` 의 한글 파일명)는 우리카드 상품공시실 > 기타 약관 게시판(`H1CCT211S12.do`, 게시판 코드 1026, 글 212개)에서 받았다. 2022년 이후 글 중 같은 약관은 가장 새 버전 하나만 골랐다(36개). 목록 요청의 `pageSize` 를 300 으로 바꿔 한 화면에 띄우고, 상세 요청(`searchBbsDetail.pwkjson`)도 두 번 나가므로 첫 응답을 돌려준 뒤 첨부파일 버튼을 눌렀다. 빠진 것: 암호(DRM)가 걸려 열리지 않는 4개(자동차 리스 약정서 · 자동차 할부금융 약정서 · 포인트 바로지급 서비스 약관 · 자동차 시설대여(리스) 약관), 이미 받은 2026년판의 옛 버전인 「신용카드 개인회원 약관」(2022). 4개는 원본이 한글(HWP) 파일이라 그대로 두었다(글자는 olefile 로 뽑힌다). `자동차할부금융약관.hwp` 는 전문이 아니라 신·구조문 대비표뿐이다.

| 파일 | 원본 글 제목 | 올린 날 |
|---|---|---|
| `cards/모바일카드이용약관.hwp` | 우리카드 「모바일카드 이용약관」 (2021.05.28 시행) — 2022년 전이지만 앱 카드 기능에 필요해 따로 받음 | 2021-04-28 |
| `cards/모바일전용카드회원약관.pdf` | 「모바일 전용카드 회원 약관」(2021. 02. 10 시행) — 같은 이유 | 2021-01-08 |
| `cards/해외전자상거래인증시스템이용약관.pdf` | 우리카드 「해외 전자상거래 인증시스템 이용약관」 (2026.09.10 시행) | 2026-07-30 |
| `cards/우리WON멤버스이용약관.pdf` | 우리카드「우리WON멤버스 이용약관」(2026.07.31. 시행) | 2026-06-01 |
| `cards/간편결제서비스이용약관.pdf` | 우리카드 「우리카드 간편결제 서비스 이용약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/오픈뱅킹공동업무금융정보조회약관.pdf` | 우리카드 「오픈뱅킹공동업무 금융정보조회 약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/ID_PW결제서비스이용약관.pdf` | 우리카드 「우리카드 ID/PW결제 서비스 이용약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/오픈뱅킹서비스이용약관.pdf` | 우리카드 「오픈뱅킹 서비스 이용약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/전자금융거래기본약관.pdf` | 우리카드 「전자금융거래 기본약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/삼성페이용앱카드결제이용약관.pdf` | 우리카드 「우리카드 삼성페이용 앱카드 결제 이용 약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/서울시지방세입전자송달서비스이용약관.pdf` | 우리카드 「서울시 지방세입 전자송달 서비스 이용약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/TV간편결제서비스이용약관.pdf` | 우리카드 「TV간편결제서비스 이용약관」 (2026.05.18 시행) | 2026-04-10 |
| `cards/국가간QR결제서비스이용약관.pdf` | 우리카드 국가간 QR결제 서비스 이용약관 | 2025-12-26 |
| `cards/매주자동결제서비스이용약관.pdf` | 우리카드 「매주 자동결제 서비스」 이용약관 (2025.01.22 시행) | 2024-12-13 |
| `cards/자동차할부금융약관.hwp` | 우리카드 「자동차 할부금융 약관」 (2024.10.17 시행) | 2024-10-30 |
| `cards/개인신용대출약관.pdf` | 우리카드 「개인신용대출 약관」 (2024.10.17 시행) | 2024-10-28 |
| `cards/여신거래기본약관.pdf` | 우리카드 「여신거래기본약관」 (2024.10.17 시행) | 2024-10-28 |
| `cards/개인사업자신용대출약관.pdf` | 우리카드 「개인사업자신용대출 약관」 (2024.10.17 시행) | 2024-10-28 |
| `cards/챗봇_톡상담서비스이용약관.pdf` | 우리카드 「챗봇·톡상담 서비스 이용약관」 (2024.09.20 시행) | 2024-09-03 |
| `cards/계좌통합관리서비스이용약관.pdf` | 우리카드 「계좌통합관리서비스(내 카드 한눈에) 이용약관」 (2024.09.26. 시행) | 2024-08-26 |
| `cards/월세카드납부서비스이용약관.hwp` | 우리카드 「월세카드납부 서비스」 이용약관 (2024.07.08 시행) | 2024-07-08 |
| `cards/선불카드이용약관.pdf` | 「선불카드 이용약관」 (2024.3.4. 시행) | 2024-02-07 |
| `cards/휴대폰메시지약관.pdf` | 우리카드 「휴대폰 메시지 약관」 (2023.07.24 시행) | 2023-07-24 |
| `cards/일반금융리스약정서.pdf` | 우리카드 「일반 금융리스 약정서」 (2023.06.13 개정) | 2023-06-13 |
| `cards/대출이동시스템을통한대환대출서비스이용약관.hwp` | 우리카드 「대출이동시스템을 통한 대환대출서비스 이용약관」 (2023.05.31 시행) | 2023-05-30 |
| `cards/삼성페이웨어러블앱카드결제이용약관.pdf` | 우리카드 「삼성페이 웨어러블(Wearable) 앱카드 결제 이용약관」 (2023.02.24 시행) | 2023-02-24 |
| `cards/재고금융약관.pdf` | 우리카드 「재고금융약관」 (2023. 1. 2 시행) | 2022-12-28 |
| `cards/근보증서_자동차시설대여.pdf` | 근보증서[자동차 시설대여(리스)] | 2022-10-24 |
| `cards/근보증서_자동차렌탈_제정.pdf` | 근보증서[자동차 렌탈(대여)] 제정 | 2022-10-24 |
| `cards/통합결제플랫폼머니약관.pdf` | 우리카드 「통합결제플랫폼 머니 약관」(2022.7.12 제정) | 2022-07-12 |
| `cards/온라인서비스이용약관.hwp` | 「온라인 서비스 이용약관」(2022. 6. 20 시행) | 2022-06-10 |
| `cards/매출채권선정산대출관련약관_약정서및채권양도계약서.pdf` | 우리카드 「매출채권 선정산 대출」 관련 약관, 약정서 및 채권양도계약서(2022.4.26 시행) | 2022-05-02 |
| `cards/일반시설대여약관.pdf` | 우리카드 「일반 시설대여(리스) 약관」 ( 2022. 3.29 제정 ) | 2022-03-29 |

### 5-3. 웹페이지를 PDF 로 저장한 것 (`data/rag/guides/` · `terms/electronic_financial_transactions_terms.pdf`, 받은 날 2026-11-04)

원본이 PDF 가 아닌 웹페이지라서 Playwright 로 화면을 PDF 로 인쇄했다. 접힌 FAQ 답은 펼치고, 높이가 고정된 스크롤 상자(약관 상자)는 높이 제한을 풀고 인쇄했다. FAQ 2개는 질문·답을 모아 한 문서로 다시 짰다.

| 파일 | 내용 | 원본 |
|---|---|---|
| `terms/electronic_financial_transactions_terms.pdf` | 우리은행 회원가입 약관 동의 화면(전자금융거래 기본약관 등, 8쪽) | https://spot.wooribank.com/pot/Dream?withyou=CQMEM0014&__STEP=1 |
| `guides/bank_fees_personal.pdf` | 개인뱅킹(인터넷·스마트) 이체수수료 | https://spot.wooribank.com/pot/Dream?withyou=CQIBG0007 |
| `guides/bank_fees_deposit.pdf` | 예금 관련 수수료 | https://spot.wooribank.com/pot/Dream?withyou=PODEP0011 |
| `guides/bank_faq.pdf` | 우리은행 FAQ 108문항(인터넷/스마트뱅킹 · 예금 · 텔레뱅킹 · 자동화기기 · 소득/세액공제 · 기타). 대출·외환·퇴직연금·신탁·펀드·우리틴틴은 앱 범위 밖이라 뺐다 | 목록 `pot/jcc?withyou=CQCCS0002&__ID=c009213&categoryid=…&DetailCategoryid=…&PageNo=…`, 답 `__ID=c009215&questionid=KNOW…` |
| `guides/card_faq.pdf` | 우리카드 FAQ 전체 139문항 | https://pc.wooricard.com/dcpc/yh1/cct/cct03/H1CCT203S07.do (`getFaqList` · `getFaqContentsById`) |
| `guides/deposit_protection_faq_kdic.pdf` | 예금보험공사 예금자보호제도 FAQ (보호한도 1억원 등) | https://www.kdic.or.kr/sp/dpstrprot/ProtSystFaq/selectScrn.do |
| `guides/deposit_protection_easylaw.pdf` | 찾기쉬운 생활법령 「예금자보호제도」 | https://easylaw.go.kr/CSP/CnpClsMainBtr.laf?popMenu=ov&csmSeq=1771&ccfNo=3&cciNo=1&cnpClsNo=1&menuType=onhunqna |
| `guides/bank_service_hours.pdf` | 우리은행 인터넷뱅킹 이용시간 안내(이체·조회 서비스별 시간, 정기점검) | https://spot.wooribank.com/pot/Dream?withyou=CQIBG0008 |
| `guides/bank_transfer_limits.pdf` | 우리은행 이체한도 안내(보안등급별 1회·1일 한도) | https://spot.wooribank.com/pot/Dream?withyou=CQIBG0022 |
| `guides/bank_privacy_policy.pdf` | 우리은행 개인정보처리방침 (9쪽) | https://spot.wooribank.com/pot/Dream?withyou=CQSCT0048 |
| `cards/card_privacy_policy.pdf` | 우리카드 개인정보처리방침 (12쪽) | https://pc.wooricard.com/dcpc/yh1/cct/cct12/psninfprotplcy/H1CCT212S08.do |
| `cards/card_customer_info_policy.pdf` | 우리카드 고객정보 취급방침 (현재판 — 약관 게시판의 2019년판 대신) | https://pc.wooricard.com/dcpc/yh1/cct/cct12/psninfprotplcy/H1CCT212S16.do |
| `guides/mistaken_transfer_kdic_apply.pdf` | 예금보험공사 착오송금반환지원 신청방법 (온라인·방문, 준비물) | https://www.kdic.or.kr/sp/kmrs/kmrsItrdAplyMthd/selectScrn.do |
| `guides/mistaken_transfer_kdic_process.pdf` | 착오송금반환지원 절차 (사전반환 신청 → 채권 매입 → 자진반환 권유 → 지급명령) | https://fins.kdic.or.kr/ir/aplygudn/MtrsGvbkSprtProc/selectScrn.do |
| `guides/mistaken_transfer_kdic_sender_notes.pdf` | 착오송금인 유의사항 (건당 5만원 이상 1억원 이하, 송금일부터 1년 이내 등) | https://fins.kdic.or.kr/ir/msdrpr/MsdrprAttnMttr/selectScrn.do |
| `guides/account_bulk_suspension_fsc.pdf` | 금융위원회 공식 블로그 「본인계좌 일괄지급정지 서비스」 카드뉴스 (2024-05-07 · 만 19세 이상 내국인, 신청 경로). 어카운트인포 서비스 화면은 동의 화면뿐이라 이것으로 대신 | https://m.blog.naver.com/blogfsc/223438936795 |
| `guides/dormant_deposit_kinfa.pdf` | 서민금융진흥원 휴면예금 안내 (휴면예금 찾아줌) | https://www.kinfa.or.kr/financialLife/sleepmoney.do |
| `cards/credit_card_standard_terms.pdf` | 신용카드 개인회원 표준약관 (2022-11-01 일부개정 · 39쪽). 웹페이지가 아니라 원본 PDF 그대로. 금융당국 게시본을 못 찾아 롯데카드가 올린 표준약관 전문을 받음(본문 회사명만 롯데카드). 우리카드 회원약관도 이 표준약관을 바탕으로 함 | https://image.lottecard.co.kr/webapp/pc/download/Standard-terms-for-credit-card-individual-members-1.pdf |
| `terms/mydata_basic_terms.pdf` | 금융감독원이 배포한 「마이데이터 기본약관」(2022-05-03 · 8쪽, 마이데이터 연동 `CARD-F10`용). 원본 PDF 그대로. 회사명은 "○○○○주식회사"로 비어 있음 | 한국신용정보원 마이데이터 종합포털 게시글 https://www.mydatacenter.or.kr:3441/myd/bbsctt/normal1/normal/35efbc61-2c02-4643-b2ef-f813b9922d12/34/bbsctt.do |
- `prod_015_016.pdf` 하나가 SUPER주거래 적금의 정액적립식(prod_015)·자유적립식(prod_016)을 함께 설명한다.
- 전자금융거래 기본약관은 지금 공통 약관 목록에 없다(약관 게시판 링크가 자바스크립트 전용). 2020년에 다른 상품에 붙은 옛 파일만 있어 받지 않았다.
- 법령 `laws/*.pdf` 14개는 국가법령정보센터(law.go.kr)의 「저장 → PDF」 버튼을 Playwright(브라우저 자동 조종, 저장소 밖에 설치)로 눌러 받았다. 바로 받는 링크는 없고, 저장 요청(`LSW/lsPdfPrint.do` POST)을 curl 로 흉내 내면 빈 파일이 온다. 조문 목록이 다 뜨기 전에 누르면 내려받기가 시작되지 않는다(3초 기다림). 본문·부칙이 함께 들어 있다.

| 파일 | 법령 (원본 파일명) |
|---|---|
| `laws/depositor_protection_act.pdf` | 예금자보호법(법률)(제21065호)(20260102) · 22쪽 |
| `laws/financial_consumer_protection_act.pdf` | 금융소비자 보호에 관한 법률(법률)(제21065호)(20260102) · 25쪽 |
| `laws/electronic_financial_transactions_act.pdf` | 전자금융거래법(법률)(제22048호)(20261002) · 31쪽 |
| `laws/depositor_protection_decree.pdf` | 예금자보호법 시행령(대통령령)(제35687호)(20250901) · 15쪽 |
| `laws/financial_consumer_protection_decree.pdf` | 금융소비자 보호에 관한 법률 시행령(대통령령)(제36287호)(20260428) · 28쪽 |
| `laws/electronic_financial_transactions_decree.pdf` | 전자금융거래법 시행령(대통령령)(제36281호)(20260428) · 21쪽 |
| `laws/real_name_financial_transactions_act.pdf` | 금융실명거래 및 비밀보장에 관한 법률(법률)(제20894호)(20250401) · 6쪽 |
| `laws/real_name_financial_transactions_decree.pdf` | 같은 법 시행령(대통령령)(제35038호)(20241227) · 5쪽 |
| `laws/personal_information_protection_act.pdf` | 개인정보 보호법(법률)(제21445호)(20260911) · 47쪽 |
| `laws/credit_information_act.pdf` | 신용정보의 이용 및 보호에 관한 법률(법률)(제21445호)(20260911) · 43쪽 |
| `laws/specialized_credit_finance_business_act.pdf` | 여신전문금융업법(법률)(제21065호)(20251001) · 31쪽 |
| `laws/specialized_credit_finance_business_decree.pdf` | 여신전문금융업법 시행령(대통령령)(제36314호)(20260506) · 25쪽 |
| `laws/telecom_financial_fraud_act.pdf` | 전기통신금융사기 피해 방지 및 피해자산 환급에 관한 특별법(법률)(제22047호)(20261002) · 12쪽 — 예전 이름은 「…피해금 환급에 관한 특별법」 |
| `laws/telecom_financial_fraud_decree.pdf` | 같은 법 시행령(대통령령)(제36729호)(20261001) · 11쪽 |

## 6. 카드 신청을 배송 중에 취소할 수 있는가 (`CARD-F05`·`CARD-F06` 신청 취소)

조사일: 2026-11-04. 결론(우리 기획): **배송 시작 전까지만 앱에서 취소**, 배송 중·배송 완료는 받은 뒤 카드 해지로 안내.

| 기준 | 내용 | 상태 | 출처 |
|---|---|---|---|
| 금융소비자보호법 제46조 | 대출성 상품 등은 계약서류를 받은 날(안 받았으면 계약 체결일)부터 **14일 이내** 청약 철회 가능 | [발췌만] 카드사 약관에 인용된 문장만 봄 | https://www.bccard.com/down/individual/customer/baro_asiana_card_20221001.pdf · https://wikidocs.net/396000 |
| 같은 법 시행령 제37조 | 청약 철회 대상 상품·적용 제외·전자적 철회 방법 | [발췌만] 조문 내용 못 읽음 | https://korea.legal/wiki/%ea%b8%88%ec%9c%b5%ec%86%8c%eb%b9%84%ec%9e%90-%eb%b3%b4%ed%98%b8%ec%97%90-%ea%b4%80%ed%95%9c-%eb%b2%95%eb%a5%a0-%ec%8b%9c%ed%96%89%eb%a0%b9-%ec%a0%9c37%ec%a1%b0/ |
| 카드사 앱의 신청 취소 | 심사 중에는 앱에서 취소, 카드가 만들어져 배송이 시작되면 앱 취소가 없어지고 고객센터·수령 거부·받은 뒤 해지로 처리하는 경우가 많음 | **[2차]** 일반적으로 알려진 방식. 카드사별 공식 안내는 읽지 않음 | — |

**확인 못 한 것**: 신용카드가 제46조 철회 대상인지·연회비 반환 범위(시행령·신용카드 표준약관 원문), 카드사별 배송 중 취소 정책. 14일 청약철회를 만들 때 원문으로 다시 확인한다.
