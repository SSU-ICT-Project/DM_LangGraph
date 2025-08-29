# app/services.py

from typing import TypedDict, Optional
import os
import requests
from datetime import datetime
import dateutil.parser
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
import concurrent.futures
import json
import time
# app/services.py 상단
from langchain_openai import ChatOpenAI  # 이렇게 되어 있어야 합니다.
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.schema import HumanMessage

# (다른 파일에서 import)
from .schemas import AgentRequest, AgentResponse

# 1. .env 파일 로드
load_dotenv()

# --- ❗️ 진단용 코드 시작 ❗️ ---
print("--- .env 파일 진단 시작 ---")
openweathermap_key = os.getenv("OPENWEATHERMAP_API_KEY")
google_maps_key = os.getenv("GOOGLE_MAPS_API_KEY")

print(f"Loaded OPENWEATHERMAP_API_KEY: {openweathermap_key}")
print(f"Loaded GOOGLE_MAPS_API_KEY: {google_maps_key}")

if not openweathermap_key or not google_maps_key:
    print("❗️ 경고: 하나 이상의 API 키를 .env 파일에서 찾을 수 없습니다.")
    print("❗️ .env 파일의 위치와 키 이름(OPENWEATHERMAP_API_KEY, GOOGLE_MAPS_API_KEY)을 다시 확인해주세요.")
print("--- .env 파일 진단 끝 ---")


# --- ❗️ 진단용 코드 끝 ---


# --- 도구(Tools) 정의 ---

@tool
def get_weather_forecast(location_name: str, date: str, latitude: float, longitude: float, test_mode: Optional[str] = None) -> dict:
    """특정 장소와 날짜의 날씨 예보를 OpenWeatherMap '5일 예보' API로 가져옵니다."""
    if test_mode == "rainy_day":
        print("🌧️ [Test Mode] '비 오는 날' 시나리오 실행")
        return {"weather": "테스트용 폭우", "condition": "bad"}

    print(f"✅ [Tool] OpenWeatherMap '5일 예보' API 호출 시작: 장소({location_name}), 날짜({date})")

    api_key = os.getenv("OPENWEATHERMAP_API_KEY")  # <-- 이 부분을 수정했습니다!
    if not api_key:
        return {"weather": "API 키 없음", "condition": "error"}

    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={api_key}&units=metric&lang=kr"

    try:
        target_dt = dateutil.parser.isoparse(date)
        target_date_str = target_dt.strftime('%Y-%m-%d')
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        found_forecast = None
        for forecast in data['list']:
            forecast_dt_utc = datetime.utcfromtimestamp(forecast['dt'])
            if forecast_dt_utc.strftime('%Y-%m-%d') == target_date_str and 14 <= forecast_dt_utc.hour <= 17:
                found_forecast = forecast
                break
        if not found_forecast:
            for forecast in data['list']:
                if datetime.utcfromtimestamp(forecast['dt']).strftime('%Y-%m-%d') == target_date_str:
                    found_forecast = forecast
                    break
        if found_forecast:
            weather_description = found_forecast["weather"][0]["description"]
            weather_id = found_forecast["weather"][0]["id"]
            condition = "good"
            if 200 <= weather_id < 700:
                condition = "bad"
            return {"weather": weather_description, "condition": condition}
        else:
            return {"weather": "5일 이내의 날씨만 예측 가능", "condition": "good"}
    except requests.exceptions.RequestException as e:
        print(f"❗️ [Error] 날씨 API 호출 실패: {e}")
        return {"weather": "API 호출 실패", "condition": "error"}
    except Exception as e:
        print(f"❗️ [Error] 날짜 처리 중 오류 발생: {e}")
        return {"weather": "날짜 형식 오류", "condition": "error"}


@tool
def get_travel_time(start_location: dict, end_location: dict, departure_time: str) -> dict:
    """requests 라이브러리로 Google Distance Matrix API를 직접 호출합니다."""
    print(f"✅ [Tool] Google API 직접 호출 시작: {start_location['placeName']} -> {end_location['placeName']}")

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"minutes": 30, "error": "Google Maps API 키가 없습니다."}

    # 1. URL과 파라미터를 직접 정의
    origin_str = f"{start_location['latitude']},{start_location['longitude']}".strip()
    dest_str = f"{end_location['latitude']},{end_location['longitude']}".strip()
    base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"

    params = {
        "origins": origin_str,
        "destinations": dest_str,
        "mode": "transit",
        "arrival_time": int(time.time()),  # 현재 시각을 epoch seconds로 전달
        "language": "ko",
        "key": api_key
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        result = response.json()

        print("--- Google Maps API 응답 원본 (직접 호출) ---")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("--- Google Maps API 응답 원본 끝 ---")

        if result['status'] == 'OK' and result['rows'][0]['elements'][0]['status'] == 'OK':
            duration_seconds = result['rows'][0]['elements'][0]['duration']['value']
            duration_minutes = round(duration_seconds / 60)
            return {"minutes": duration_minutes}
        else:
            error_status = result.get('status', '알 수 없는 상태')
            element_status = result['rows'][0]['elements'][0].get('status', '알 수 없는 상태')
            return {"minutes": 30, "error": f"API Status: {error_status}, Element Status: {element_status}"}
    except requests.exceptions.RequestException as e:
        print(f"❗️ [Error] Google Maps API 직접 호출 실패: {e}")
        return {"minutes": 30, "error": f"API 호출 중 예외 발생: {e}"}


# --- LangGraph 상태(State) 정의 ---
class GraphState(TypedDict):
    request: AgentRequest
    weather_forecast: Optional[dict]
    travel_time_minutes: Optional[int]
    final_recommendation: Optional[str]
    weather_text: Optional[str]
    travel_time: Optional[int]
    buffer_time: Optional[int]
    total_time: Optional[int]
    appointment_title: Optional[str]


# --- LangGraph 노드(Node) 정의 ---
def call_tools(state: GraphState):
    """필요한 모든 도구를 ✨병렬로✨ 호출하여 정보를 수집합니다."""
    print("➡️ [Node] call_tools 진입 (병렬 처리)")
    request = state['request']

    with concurrent.futures.ThreadPoolExecutor() as executor:
        weather_future = executor.submit(
            get_weather_forecast.invoke,
            {
                "location_name": request.ArrivalLocation.placeName,
                "date": request.scheduleStartTime,
                "latitude": request.ArrivalLocation.latitude,
                "longitude": request.ArrivalLocation.longitude,
                "test_mode": request.test_mode  # 테스트 모드 전달
            }
        )
        travel_time_future = executor.submit(
            get_travel_time.invoke,
            {
                "start_location": {
                    "placeName": request.DepartureLocation.placeName,
                    "latitude": request.DepartureLocation.latitude,
                    "longitude": request.DepartureLocation.longitude
                },
                "end_location": {
                    "placeName": request.ArrivalLocation.placeName,
                    "latitude": request.ArrivalLocation.latitude,
                    "longitude": request.ArrivalLocation.longitude
                },
                "departure_time": request.scheduleStartTime
            }
        )
        weather_result = weather_future.result()
        travel_time_result = travel_time_future.result()

    return {
        "weather_forecast": weather_result,
        "travel_time_minutes": travel_time_result.get("minutes", 30),  # .get()으로 안전하게 접근
        "appointment_title": request.scheduleName
    }


def generate_recommendation(state: GraphState):
    """수집된 정보로 최종 추천 메시지를 생성합니다."""
    print("➡️ [Node] generate_recommendation 진입")
    weather_info = state["weather_forecast"]
    travel_time = state["travel_time_minutes"]
    buffer_time = 0

    if weather_info and weather_info.get("condition") == "bad":  # .get()으로 안전하게 접근
        buffer_time = 30

    total_time = travel_time + buffer_time
    weather_text = weather_info.get('weather', '알 수 없음') if weather_info else '알 수 없음'

    return {
        "weather_text": weather_text,
        "travel_time": travel_time,
        "buffer_time": buffer_time,
        "total_time": total_time
    }


def find_alternative_plan(state: GraphState):
    """악천후 시 대체 계획 추천 메시지를 생성합니다."""
    print("➡️ [Node] find_alternative_plan 진입")
    weather_info = state.get("weather_forecast")
    weather_text = weather_info.get('weather', '알 수 없음') if weather_info else '알 수 없음'
    buffer_time = 30
    travel_time = state.get("travel_time_minutes", 30)
    total_time = travel_time + buffer_time

    return {
        "weather_text": weather_text,
        "travel_time": travel_time,
        "buffer_time": buffer_time,
        "total_time": total_time
    }


def llm_formatter(state: GraphState):
    """LLM을 사용하여 자연스러운 최종 추천 메시지를 생성합니다."""
    print("➡️ [Node] llm_formatter 진입")

    # 1. Google API 키가 있는지 먼저 확인합니다.
    if not os.getenv("GEMINI_API_KEY"):
        print("❗️ [Error] GEMINI_API_KEY가 설정되어 있지 않습니다.")
        return {"final_recommendation": "Google Gemini API 키가 설정되어 있지 않습니다."}

    # 2. 프롬프트에 사용할 변수들을 상태(state)에서 가져옵니다.
    appointment_title = state.get("appointment_title", "알 수 없는 일정")
    weather_text = state.get("weather_text", "알 수 없음")
    travel_time = state.get("travel_time", 30)
    buffer_time = state.get("buffer_time", 0)
    total_time = state.get("total_time", travel_time + buffer_time)
    destination_name = state['request'].ArrivalLocation.placeName if ('request' in state and hasattr(state['request'], 'ArrivalLocation')
                                                             and hasattr(state['request'].ArrivalLocation, 'placeName')) else "알 수 없는 목적지"

    def format_time(minutes: int) -> str:
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}시간 {mins}분"
        else:
            return f"{mins}분"

    # 3. PCTF 구조의 프롬프트 문자열을 생성합니다.
    prompt = (
        "Persona: 당신은 일정 안내와 이동 계획을 전문으로 안내하는 AI입니다.\n"
        f"Context: 일정 제목은 '{appointment_title}'이며, 목적지는 '{destination_name}'입니다.\n"
        "Task: 해당 일정의 제목, 목적지, 이동 시간, 날씨를 자연스럽게 두 문장으로만 안내하세요. "
        "날씨는 누구나 이해할 수 있는 쉬운 표현으로 설명하고 예를 들어 약한비는 약한비로 대체하고 , 마지막에는 준비를 권유하는 말투로 끝내세요. 날씨 설명은 반드시 사람들이 자주 쓰는 단순 용어(예: 맑음, 흐림, 비, 폭우, 폭설) 중 하나로 바꿔서 표현하세요.\n"
        "Format: 무조건 2문장으로 작성하세요. 표식이나 괄호는 쓰지 마세요. 항상 공손한 말투를 유지하세요. 마지막 문장 끝에 [이동 시간: 00:00] 형식으로 (시:분)을 표시하세요. \n\n"
        f"날씨: {weather_text}\n"
        f"이동 시간: {format_time(travel_time)}\n"
    )
    if buffer_time > 0:
        prompt += f"날씨 때문에 이동 시간이 조금 더 걸릴 수 있어 {format_time(buffer_time)} 정도 더 일찍 준비하시는 게 좋습니다.\n"
    prompt += f"총 소요 시간: {format_time(total_time)}\n"

    # 4. ChatGoogleGenerativeAI를 올바르게 초기화합니다. (model 파라미터 포함)
    api_key = os.getenv("GEMINI_API_KEY")
    llm = ChatGoogleGenerativeAI(api_key=api_key, model="gemini-1.5-pro-latest", temperature=0.7)

    # 5. LLM을 호출하여 최종 추천 메시지를 생성합니다.
    response = llm.invoke(prompt)
    text = response.content.strip()  # 불필요한 공백 제거

    return {"final_recommendation": text}

def weather_condition_branch(state: GraphState) -> str:
    """날씨 상태에 따라 분기합니다."""
    weather_info = state.get("weather_forecast")
    if weather_info and weather_info.get("condition") == "bad":
        return "bad_weather"
    else:
        return "good_weather"


# --- 그래프 워크플로우(Workflow) 조립 ---
workflow = StateGraph(GraphState)
workflow.add_node("tool_caller", call_tools)
workflow.add_node("recommender", generate_recommendation)
workflow.add_node("find_alternative_plan", find_alternative_plan)
workflow.add_node("llm_formatter", llm_formatter)

workflow.set_entry_point("tool_caller")
workflow.add_conditional_edges("tool_caller", weather_condition_branch, {
    "bad_weather": "find_alternative_plan",
    "good_weather": "recommender"
})
workflow.add_edge("recommender", "llm_formatter")
workflow.add_edge("find_alternative_plan", "llm_formatter")
workflow.add_edge("llm_formatter", END)

app_graph = workflow.compile()


# --- FastAPI에서 호출할 메인 함수 ---
def get_lang_graph_recommendation(request: AgentRequest) -> AgentResponse:
    """AgentRequest를 받아 LangGraph를 실행하고 AgentResponse를 반환합니다."""
    inputs = {"request": request}
    final_state = app_graph.invoke(inputs)
    return AgentResponse(recommendation=final_state['final_recommendation'])