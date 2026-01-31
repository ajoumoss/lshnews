import os
import httpx
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

def find_and_archive_homonyms():
    print("노션 데이터베이스에서 동명이인(NATV 기자 등) 기사 청소를 시작합니다...")
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    
    # 간단한 검색 (제목에 NATV가 포함된 경우 등)
    # 실제로는 모든 기사를 가져와서 새로운 필터링 로직으로 체크하는 것이 정확함
    with httpx.Client() as client:
        response = client.post(url, headers=get_headers())
        if response.status_code != 200:
            print("데이터베이스 조회 실패")
            return

        results = response.json().get("results", [])
        count = 0
        for page in results:
            page_id = page["id"]
            title = ""
            # '기사내용'이 title 속성임
            title_props = page["properties"].get("기사내용", {}).get("title", [])
            if title_props:
                title = title_props[0]["text"]["content"]
            
            reporter_props = page["properties"].get("기자", {}).get("rich_text", [])
            reporter = reporter_props[0]["text"]["content"] if reporter_props else ""
            
            company_props = page["properties"].get("언론사", {}).get("rich_text", [])
            company = company_props[0]["text"]["content"] if company_props else ""

            # 필터링 조건 (NATV 기자)
            target_keywords = ["NATV", "jinlove48@naver.com", "이소희 기자"]
            is_homonym = False
            for kw in target_keywords:
                if kw in title or kw in reporter or kw in company:
                    # 제목에 '의원'이 확실히 있는 경우는 제외 (안전장치)
                    if "의원" not in title:
                        is_homonym = True
                        break

            if is_homonym:
                print(f" -> 삭제 대상 발견: {title} (기자: {reporter}, 언론사: {company})")
                archive_url = f"https://api.notion.com/v1/pages/{page_id}"
                arch_res = client.patch(archive_url, headers=get_headers(), json={"archived": True})
                if arch_res.status_code == 200:
                    print("    [성공] 아카이브 완료")
                    count += 1
                else:
                    print(f"    [실패] {arch_res.status_code}")

        print(f"\n총 {count}개의 부적절한 기사를 정리했습니다.")

if __name__ == "__main__":
    find_and_archive_homonyms()
