import sys
from scraper import search_naver_news, filter_articles, extract_article_details
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

    relevant_articles = filter_articles(unique_articles, start_date=start_date, end_date=end_date)
    print(f"검색된 기사: {len(unique_articles)}개 -> 1월 필터링 후: {len(relevant_articles)}개")

    count_new = 0
    count_updated = 0
    
    for i, a in enumerate(relevant_articles):
        link = a['link']
        page_id = get_existing_article_page_id(link)
        
        print(f"[{i+1}/{len(relevant_articles)}] 처리 중: {a['title'][:30]}...")
        details = extract_article_details(link)
        
        # 2차 필터링 (추출된 상세 정보 기반)
        # 본문이나 기사 정보에서 NATV 기자가 확인되면 제외
        exclude_raw = ['natv', 'jinlove48@naver.com', '이소희 기자']
        is_homonym = False
        for ex in exclude_raw:
            if (ex in details['reporter'].lower() or 
                ex in details['company'].lower() or 
                ex in details['content'].lower()):
                # 기사 내용에 '의원' 키워드가 확실히 핵심적으로 쓰이지 않은 경우만 제외
                if '의원' not in a['title']:
                    is_homonym = True
                    break
        
        if is_homonym:
            print(f" -> 동명이인 기자(NATV 등) 기사로 판단되어 건너뜁니다.")
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
