import os
import re
import random
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Bright Data API key (set in Cloud Run environment variables)
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY', '')

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

JS_REQUIRED_DOMAINS = [
    'swooped.co',
    'lever.co',
    'jobs.lever.co',
    'greenhouse.io',
    'boards.greenhouse.io',
    'linkedin.com',
    'indeed.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'angel.co',
    'wellfound.com',
]


def needs_javascript(url):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    return any(js_domain in domain for js_domain in JS_REQUIRED_DOMAINS)


def is_garbage_text(text):
    if not text or len(text) < 50:
        return True
    control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
    null_chars = text.count('\x00')
    if null_chars > 0 or (len(text) > 0 and control_chars / len(text) > 0.05):
        return True
    words = re.findall(r'[a-zA-Z]{3,}', text)
    return len(words) < 10


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def extract_text_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe', 'svg']:
        for el in soup.find_all(tag):
            el.decompose()
    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    return clean_text(main.get_text(separator='\n', strip=True))


def scrape_direct(url):
    """Direct scraping without JavaScript rendering"""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
    response.raise_for_status()
    
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    
    return extract_text_from_html(response.text)


def scrape_with_brightdata(url):
    """Scrape using Bright Data Web Scraper API"""
    if not BRIGHTDATA_API_KEY:
        raise ValueError("BRIGHTDATA_API_KEY not configured")
    
    api_url = "https://api.brightdata.com/request"
    
    headers = {
        'Authorization': f'Bearer {BRIGHTDATA_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'url': url,
        'format': 'raw'  # Get raw HTML
    }
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    
    # Bright Data returns the HTML content
    return extract_text_from_html(response.text)


def scrape(url, force_js=False):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Try direct scraping first unless we know it needs JS
    if not force_js and not needs_javascript(url):
        try:
            text = scrape_direct(url)
            if not is_garbage_text(text) and len(text) >= 100:
                return text, "direct"
        except:
            pass
    
    # Fall back to Bright Data for JS rendering
    if BRIGHTDATA_API_KEY:
        text = scrape_with_brightdata(url)
        if not is_garbage_text(text):
            return text, "brightdata"
        raise ValueError("Bright Data returned unreadable content")
    else:
        raise ValueError("Site requires JavaScript - configure BRIGHTDATA_API_KEY")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "version": "3.0-brightdata",
        "brightdata_configured": bool(BRIGHTDATA_API_KEY)
    })


@app.route("/", methods=["POST"])
def handle():
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        force_js = data.get("force_js", False)
        
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        
        text, method = scrape(url, force_js=force_js)
        
        if len(text) < 100:
            return jsonify({
                "success": False,
                "error": "ERROR_MINIMAL_CONTENT",
                "url": url
            }), 422
        
        return jsonify({
            "success": True,
            "text": text,
            "text_length": len(text),
            "url": url,
            "method": method
        })
    
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": "ERROR_JAVASCRIPT_REQUIRED",
            "message": str(e),
            "url": data.get("website") or data.get("url")
        }), 422
    
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        return jsonify({
            "success": False,
            "error": f"ERROR_HTTP_{status}",
            "url": data.get("website") or data.get("url")
        }), 422
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "ERROR_UNKNOWN",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
