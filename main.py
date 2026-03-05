import sys
from scraper import search_naver_news, is_relevant_article, extract_article_details
from notion_integrator import add_article_to_notion, update_article_in_notion, get_existing_article_page_id, check_database_exists
import time
from datetime import datetime, timezone, timedelta

def main():
    print("이소희 의원 뉴스 크롤러 (v4: 언론사 확장 & 언급 요약) 시작합니다...")
    # KST 설정
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    # 매일 실행되므로 최근 1일(24시간) 이내의 기사만 수집
    start_date = now - timedelta(days=1)
    end_date = now

    if not check_database_exists():
        print("Notion 데이터베이스 연결 실패")
        return

    queries = ["이소희 의원", "국민의힘 이소희", "22대 국회의원 이소희"]
    all_articles = []
    for q in queries:
        print(f"'{q}' 검색 중...")
        for start_idx in range(1, 201, 100):
            articles = search_naver_news(q, start=start_idx)
            if not articles: break
            all_articles.extend(articles)
            time.sleep(0.3)

    seen_links = set()
    unique_articles = []
    for a in all_articles:
        if a['link'] not in seen_links:
            seen_links.add(a['link'])
            unique_articles.append(a)

    # 1. 날짜 필터링만 우선 수행 (24시간 이내)
    recent_articles = []
    for a in unique_articles:
        try:
            pub_dt = datetime.strptime(a.get('pubDate', ''), "%a, %d %b %Y %H:%M:%S %z")
            if pub_dt >= start_date:
                recent_articles.append(a)
        except:
            pass
            
    print(f"검색된 기사: {len(unique_articles)}개 -> 24시간 이내: {len(recent_articles)}개")

    count_new = 0
    count_updated = 0
    
    for i, a in enumerate(recent_articles):
        link = a['link']
        
        # [변경] 상세 내용을 먼저 추출
        print(f"[{i+1}/{len(recent_articles)}] 분석 중: {a['title'][:30]}...")
        details = extract_article_details(link)
        
        # [변경] 본문 포함하여 관련성 검사 (is_relevant_article 수정됨)
        # 이제 title, description, content 전체를 보고 판단
        if not is_relevant_article(a, content=details['content']):
            print(" -> 관련 없는 기사로 판단되어 건너뜁니다.")
            continue
            
        page_id = get_existing_article_page_id(link)
        
        # 2차 필터링 (추가적인 동명이인/NATV 체크 - 기존 로직 유지하되 중복 확인)
        # 이미 is_relevant_article 안에서도 체크하지만, extract_article_details에서 나온 
        # reporter/company 정보를 더 확실히 쓰고 싶다면 여기서 한 번 더 체크 가능.
        # 하지만 위에서 is_relevant_article(content=...)로 대부분 걸러짐.
        # 여기선 '기자' 필드나 '언론사' 필드에 명시적으로 들어간 경우를 재확인.
        
        exclude_raw = ['natv', 'jinlove48@naver.com', '이소희 기자']
        is_homonym = False
        for ex in exclude_raw:
            # NoneType 에러를 방지하기 위해 빈 값이면 빈 문자열("")로 대체
            reporter_text = details.get('reporter') or ""
            company_text = details.get('company') or ""
            
            if (ex in reporter_text.lower() or 
                ex in company_text.lower()):
                if '의원' not in a['title']:
                    is_homonym = True
                    break

        
        if is_homonym:
            print(f" -> 동명이인 기자/매체(NATV 등)로 판단되어 건너뜁니다.")
            continue

        if not page_id:
            success = add_article_to_notion(
                title=a['title'], link=link, date=a['pubDate'], description=a['description'],
                company=details['company'], reporter=details['reporter'], 
                full_content=details['content'], mentions=details['mentions']
            )
            if success: count_new += 1
        else:
            success = update_article_in_notion(
                page_id=page_id, title=a['title'], link=link, date=a['pubDate'],
                company=details['company'], reporter=details['reporter'], 
                full_content=details['content'], mentions=details['mentions']
            )
            if success: count_updated += 1
            
        time.sleep(0.5)
            
    print(f"\n작업 완료! 신규: {count_new}개, 업데이트: {count_updated}개")

if __name__ == "__main__":
    main()
