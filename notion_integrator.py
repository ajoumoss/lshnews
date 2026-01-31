import os
import httpx
from dotenv import load_dotenv
from datetime import datetime
import html

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def clean_text(text):
    if not text: return ""
    # HTML 태그 제거 및 엔티티 변환
    text = text.replace('<b>', '').replace('</b>', '')
    return html.unescape(text)

def parse_naver_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d")

def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

def add_article_to_notion(title, link, date, description, company="정보 없음", reporter="정보 없음", full_content="", mentions=""):
    try:
        formatted_date = parse_naver_date(date)
        url = "https://api.notion.com/v1/pages"
        
        properties = {
            "기사내용": {"title": [{"text": {"content": clean_text(title)}}]},
            "URL": {"url": link},
            "날짜": {"date": {"start": formatted_date}},
            "언론사": {"rich_text": [{"text": {"content": clean_text(company)}}]},
            "기자": {"rich_text": [{"text": {"content": clean_text(reporter)}}]}
        }
        
        children = generate_children_blocks(description, link, mentions) # link를 전달

        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": properties, "children": children
        }
        
        with httpx.Client() as client:
            response = client.post(url, headers=get_headers(), json=payload)
            return response.status_code == 200
    except Exception as e:
        print(f"Error adding to Notion: {e}")
        return False

def update_article_in_notion(page_id, title, link, date, company, reporter, full_content, mentions=""):
    try:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        properties = {
            "기사내용": {"title": [{"text": {"content": clean_text(title)}}]},
            "언론사": {"rich_text": [{"text": {"content": clean_text(company)}}]},
            "기자": {"rich_text": [{"text": {"content": clean_text(reporter)}}]}
        }
        
        with httpx.Client() as client:
            client.patch(url, headers=get_headers(), json={"properties": properties})
            
            content_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            children = generate_children_blocks("", link, mentions) # link를 전달
            client.patch(content_url, headers=get_headers(), json={"children": children})
            
        return True
    except Exception as e:
        print(f"Error updating Notion: {e}")
        return False

def generate_children_blocks(description, article_url, mentions):
    children = []
    
    # 1. 이소희 의원 언급부분 (기존 기사 요약 섹션을 활용)
    if description:
        children.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "이소희 의원 언급부분"}}]}
        })
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": clean_text(description)}}]}
        })
    
    # 2. 본문 링크 (URL 주소 직접 표시)
    if article_url:
        children.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🔗 기사 원문 URL"}}]}
        })
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": article_url,
                            "link": {"url": article_url}
                        }
                    }
                ]
            }
        })
            
    return children
            
    return children

def get_existing_article_page_id(link):
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
        payload = {"filter": {"property": "URL", "url": {"equals": link}}}
        with httpx.Client() as client:
            response = client.post(url, headers=get_headers(), json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results: return results[0]["id"]
        return None
    except: return None

def check_database_exists():
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
        with httpx.Client() as client:
            response = client.get(url, headers=get_headers())
            return response.status_code == 200
    except: return False
