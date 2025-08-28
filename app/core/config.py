import redis

# Docker 포트 충돌 문제를 해결하기 위해 6380 포트를 사용했다면
# 여기도 동일하게 6380으로 맞춰줍니다.
REDIS_HOST = "localhost"
REDIS_PORT = 6380

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

print("✅ Redis 클라이언트가 성공적으로 초기화되었습니다.")