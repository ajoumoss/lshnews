import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re
import html

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

def search_naver_news(query, display=100, start=1, sort='date'):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {"query": query, "display": display, "start": start, "sort": sort}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        items = response.json().get('items', [])
        # 초기 단계에서 인코딩 수정
        for item in items:
            item['title'] = html.unescape(item['title']).replace('<b>', '').replace('</b>', '')
            item['description'] = html.unescape(item['description']).replace('<b>', '').replace('</b>', '')
        return items
    return []

def extract_article_details(url):
    details = {"content": "", "reporter": "정보 없음", "company": "정보 없음", "mentions": ""}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return details
        
        # HTML 엔티티 변환을 위해 BeautifulSoup 사용 전 unescape 고려 가능하나 soup이 처리해줌
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 네이버 뉴스 전용 고정밀 추출
        if "news.naver.com" in url:
            # 언론사명 추출
            company_tag = soup.select_one('.media_end_head_top_logo img') or soup.select_one('meta[property="og:article:author"]')
            if company_tag:
                details["company"] = company_tag.get('title') or company_tag.get('content')
            
            # 기자명 추출
            journalist_tag = soup.select_one('.media_end_head_journalist_name')
            if journalist_tag:
                details["reporter"] = journalist_tag.get_text().strip()
            else:
                # 기자가 없는 경우 '매일신문 | 네이버' 처럼 섞여 들어가는 것 방지
                # og:description 이나 다른 태그에서 기자명 찾기
                author_tag = soup.select_one('meta[name="author"]')
                if author_tag:
                    author_val = author_tag.get('content', '')
                    if " | 네이버" in author_val:
                        details["reporter"] = "정보 없음" # 언론사 이름이 섞인 것이므로 무시
                    else:
                        details["reporter"] = author_val.strip()

        # 2. 일반 언론사 (범용)
        if details["company"] == "정보 없음":
            company = (soup.select_one('meta[property="og:site_name"]') or 
                       soup.select_one('meta[name="twitter:site"]') or 
                       soup.select_one('meta[name="publisher"]'))
            if company:
                details["company"] = company.get('content', '').strip()
        
        if details["reporter"] == "정보 없음":
            reporter = (soup.select_one('meta[name="author"]') or 
                        soup.select_one('meta[property="og:article:author"]') or 
                        soup.select_one('meta[name="dable:author"]'))
            if reporter:
                rep_val = reporter.get('content', '').strip()
                if " | " not in rep_val and len(rep_val) < 10: 
                    details["reporter"] = rep_val

        # 3. 본문 추출 및 본문 내 기자명 2차 검색
        content_tag = (soup.select_one('#newsct_article') or 
                       soup.select_one('#articleBodyContents') or 
                       soup.select_one('article') or 
                       soup.select_one('.article_body') or 
                       soup.select_one('#article_content'))
        
        if content_tag:
            for s in content_tag(['script', 'style', 'nav', 'footer', 'header']): s.decompose()
            text_content = html.unescape(content_tag.get_text('\n', strip=True))
            details["content"] = text_content
            
            # 본문 내에서 기자명 패턴 찾기 (메타데이터 실패 시)
            if details["reporter"] == "정보 없음":
                # 패턴 1: [서울=뉴스핌] 윤창빈 기자 = ...
                # 패턴 2: 윤창빈 기자 (email)
                # 패턴 3: 기자 = 윤창빈
                # 패턴 4: 윤창빈기자
                patterns = [
                    r'([가-힣]{2,4})\s*기자\s*=',
                    r'([가-힣]{2,4})\s*기자\s*\(',
                    r'기자\s*=\s*([가-힣]{2,4})',
                    r'([가-힣]{2,4})\s*기자(?!\w)',
                    r'\[.*?\]\s*([가-힣]{2,4})\s*기자'
                ]
                # 기사 앞쪽 500자 이내에서 검색
                search_text = text_content[:500]
                for p in patterns:
                    match = re.search(p, search_text)
                    if match:
                        name = match.group(1).strip()
                        if 2 <= len(name) <= 4: # 한국인 이름 길이 체크
                            details["reporter"] = f"{name} 기자"
                            break

        # 4. 이소희 의원 언급 부분 요약
        details["mentions"] = summarize_mentions(details["content"])
            
    except Exception as e:
        print(f"Error extracting details from {url}: {e}")
        
    return details

def summarize_mentions(text):
    if not text: return ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    relevant = []
    for s in sentences:
        if '이소희' in s:
            if '교수' in s and '의원' not in s: continue
            relevant.append(html.unescape(s.strip()))
            
    if not relevant: return "의원님에 대한 직접적인 언급 문장을 찾지 못했습니다."
    return "\n\n".join(relevant[:7])

def is_relevant_article(item, start_date=None, end_date=None, content=None):
    title = item.get('title', '').replace('<b>', '').replace('</b>', '')
    description = item.get('description', '').replace('<b>', '').replace('</b>', '')
    
    # 제목 + 설명 + (선택적) 본문 결합
    combined_text = title + " " + description
    if content:
        combined_text += " " + content
    
    # 1. 교수/기자 동명이인 강력 제외 (NATV 및 특정 기자 패턴 추가)
    exclude_keywords = [
        '이소희 교수', '교수 이소희', 
        '이소희 기자', '기자 이소희', '기자=이소희',
        'NATV', 'jinlove48@naver.com' # 사용자 제보 사례 추가
    ]
    for ekw in exclude_keywords:
        if ekw.lower() in combined_text.lower():
            # 제목에 '의원'이 확실히 있을 때만 예외적으로 허용 (그 외엔 동명이인으로 간주)
            if '의원' not in title:
                return False

    # 2. 국회의원 이소희 관련 핵심 패턴 (정교하게 일치할 때만 통과)
    core_patterns = [
        r'이소희\s*(국회)?의원', 
        r'의원\s*이소희', 
        r'이소희\s*국민의힘', 
        r'비례대표\s*이소희',
        r'인요한.*이소희', # 인요한 위원장과 함께 언급되는 경우 많음
        r'의원직\s*승계.*이소희'
    ]
    is_matched = False
    for pattern in core_patterns:
        if re.search(pattern, combined_text):
            is_matched = True
            break
            
    if not is_matched:
        # 패턴은 없지만 '이소희' 이름과 정치 키워드가 모두 존재할 때
        politics_keywords = ['국회', '국민의힘', '비례대표', '의원직 승계', '입성', '선서']
        if '이소희' in combined_text and any(pkw in combined_text for pkw in politics_keywords):
            # '교수'나 'NATV' 관련 문맥이 없는지 다시 한 번 확인
            if not any(ekw.lower() in combined_text.lower() for ekw in ['교수', 'NATV', '기자 이소희']):
                is_matched = True
            
    if not is_matched: return False

    # 3. 기간 필터링
    try:
        pub_dt = datetime.strptime(item.get('pubDate', ''), "%a, %d %b %Y %H:%M:%S %z")
        if start_date and pub_dt < start_date: return False
        if end_date and pub_dt > end_date: return False
    except: pass
    
    return True

def filter_articles(items, start_date=None, end_date=None):
    return [item for item in items if is_relevant_article(item, start_date, end_date)]
