#!/bin/sh
# 컨테이너 첫 기동 때 한 번 실행된다(빈 볼륨일 때만).
# 기획서 스키마 docs/sql/00~07 (docker-compose.yml 이 /schema 에 붙임)을 번호 순서로 midproject 에 만든다.
# midproject_test 는 테스트(tests/conftest.py)가 실행할 때마다 같은 docs/sql 로 새로 만들므로 건드리지 않는다.
# 실행 권한이 없으면 entrypoint 가 이 파일을 source 하므로 set -u 는 쓰지 않는다(entrypoint 변수에 영향).
set -e

ls /schema/0*.sql >/dev/null 2>&1 || { echo "02_schema.sh: /schema 에 0*.sql 이 없음 (../docs/sql 마운트 확인)" >&2; exit 1; }

for f in /schema/0*.sql; do
  echo "02_schema.sh: $f"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -q -f "$f"
done
