from fastapi import FastAPI
from .schemas import AgentRequest, AgentResponse
from .services import get_lang_graph_recommendation  # services.py에서 메인 함수를 가져옵니다.
from .core.config import redis_client  # Redis 연결 설정을 가져옵니다.
import json

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "LangGraph 기반 추천 에이전트 API"}


@app.post("/recommend", response_model=AgentResponse)
def get_recommendation(request: AgentRequest):
    """
    출발지, 도착지, 약속 시간 정보를 받아 최적 출발 시간을 추천합니다.
    Redis 캐시를 먼저 확인합니다.
    """
    # 1. 캐시 키 생성 (요청 내용 전체를 기반으로 고유한 키 생성)
    # sort_keys=True를 사용해 딕셔너리 순서가 달라도 항상 같은 키가 만들어지도록 합니다.
    cache_key = f"recommendation:{json.dumps(request.dict(), sort_keys=True)}"

    # 2. Redis에서 캐시 확인
    try:
        cached_result = redis_client.get(cache_key)
        if cached_result:
            print("✅ Cache Hit! Redis에서 결과를 바로 반환합니다.")
            # JSON 문자열을 AgentResponse 객체로 변환하여 반환
            return AgentResponse.parse_raw(cached_result)
    except Exception as e:
        print(f"❗️ Redis 연결 오류: {e}")
        # Redis에 문제가 생겨도 핵심 기능은 동작해야 하므로, 캐시를 건너뛰고 계속 진행합니다.
        pass

    # 3. 캐시가 없으면 실제 LangGraph 에이전트 실행
    print("❌ Cache Miss! LangGraph 에이전트를 실행합니다...")
    result = get_lang_graph_recommendation(request)

    # 4. 결과를 Redis에 저장 (유효기간: 1시간 = 3600초)
    try:
        # AgentResponse 객체를 JSON 문자열로 변환하여 저장
        redis_client.setex(cache_key, 3600, result.json())
        print("📝 Cache Saved! 결과를 Redis에 1시간 동안 저장합니다.")
    except Exception as e:
        print(f"❗️ Redis 저장 오류: {e}")
        # 캐시 저장을 못하더라도 결과는 정상적으로 반환해야 합니다.
        pass

    return result