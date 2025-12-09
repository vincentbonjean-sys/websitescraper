import os
import re
import random
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Method 1: Bright Data Web Unlocker - API method (was working for swooped.co)
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY', '')
BRIGHTDATA_ZONE = os.environ.get('BRIGHTDATA_ZONE', '')  # e.g., "web_unlocker1"

# Method 2: Bright Data Web Unlocker - Proxy method (additional coverage)
BRIGHTDATA_USERNAME = os.environ.get('BRIGHTDATA_USERNAME', '')
BRIGHTDATA_PASSWORD = os.environ.get('BRIGHTDATA_PASSWORD', '')
BRIGHTDATA_HOST = os.environ.get('BRIGHTDATA_HOST', 'brd.superproxy.io')
BRIGHTDATA_PORT = os.environ.get('BRIGHTDATA_PORT', '33335')

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Domains that need Bright Data (anti-bot or JS-heavy)
BRIGHTDATA_DOMAINS = [
    # JS-heavy SPAs
    'myworkdayjobs.com',
    'workday.com',
    'icims.com',
    'hiringtoday.com',
    'lever.co',
    'jobs.lever.co',
    'greenhouse.io',
    'boards.greenhouse.io',
    'smartrecruiters.com',
    'jobvite.com',
    'ultipro.com',
    'paylocity.com',
    'paycomonline.net',
    'successfactors.com',
    'taleo.net',
    'brassring.com',
    'ashbyhq.com',
    'personio.com',
    'bamboohr.com',
    'recruitee.com',
    # Anti-bot sites
    'swooped.co',
    'linkedin.com',
    'indeed.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'angel.co',
    'wellfound.com',
]


def get_domain(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def needs_brightdata(url):
    domain = get_domain(url)
    return any(d in domain for d in BRIGHTDATA_DOMAINS)


def is_garbage_text(text):
    if not text or len(text) < 50:
        return True
    
    control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
    null_chars = text.count('\x00')
    if null_chars > 0 or (len(text) > 0 and control_chars / len(text) > 0.05):
        return True
    
    words = re.findall(r'[a-zA-Z]{3,}', text)
    if len(words) < 10:
        return True
    
    lower_text = text.lower()
    empty_indicators = [
        'please enable javascript',
        'javascript is required',
        'browser does not support',
        'loading...',
        'please wait while',
        'redirecting...',
        'just a moment',
        'checking your browser',
    ]
    if any(indicator in lower_text for indicator in empty_indicators):
        if len(text) < 500:
            return True
    
    return False


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
    
    for tag in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe', 'svg', 'meta', 'link']:
        for el in soup.find_all(tag):
            el.decompose()
    
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r'job|posting|description|content', re.I)) or soup.find("body") or soup
    
    return clean_text(main.get_text(separator='\n', strip=True))


def scrape_direct(url):
    """Direct scraping without any proxy"""
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


def scrape_with_api(url):
    """Scrape using Bright Data Web Unlocker API method"""
    if not BRIGHTDATA_API_KEY or not BRIGHTDATA_ZONE:
        raise ValueError("API credentials not configured")
    
    headers = {
        'Authorization': f'Bearer {BRIGHTDATA_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'zone': BRIGHTDATA_ZONE,
        'url': url,
        'format': 'raw'
    }
    
    response = requests.post(
        "https://api.brightdata.com/request",
        headers=headers,
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    
    return extract_text_from_html(response.text)


def scrape_with_proxy(url):
    """Scrape using Bright Data Web Unlocker proxy method"""
    if not BRIGHTDATA_USERNAME or not BRIGHTDATA_PASSWORD:
        raise ValueError("Proxy credentials not configured")
    
    proxy_url = f"http://{BRIGHTDATA_USERNAME}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_HOST}:{BRIGHTDATA_PORT}"
    
    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }
    
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    response = requests.get(
        url,
        headers=headers,
        proxies=proxies,
        timeout=90,
        verify=False
    )
    response.raise_for_status()
    
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    
    return extract_text_from_html(response.text)


def scrape(url, force_proxy=False):
    """Main scraping function with fallback chain"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = get_domain(url)
    use_brightdata = needs_brightdata(url) or force_proxy
    
    api_configured = bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE)
    proxy_configured = bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD)
    
    errors = []
    
    # Route 1: Sites that need Bright Data
    if use_brightdata:
        # Try API method first (was working for swooped.co)
        if api_configured:
            try:
                text = scrape_with_api(url)
                if not is_garbage_text(text):
                    return text, "api"
                errors.append("API returned unreadable content")
            except Exception as e:
                errors.append(f"API error: {str(e)}")
        
        # Try proxy method as fallback
        if proxy_configured:
            try:
                text = scrape_with_proxy(url)
                if not is_garbage_text(text):
                    return text, "proxy"
                errors.append("Proxy returned unreadable content")
            except Exception as e:
                errors.append(f"Proxy error: {str(e)}")
        
        if errors:
            raise ValueError(f"Could not scrape {domain}: {'; '.join(errors)}")
        else:
            raise ValueError(f"No Bright Data credentials configured for {domain}")
    
    # Route 2: Normal sites - try direct first
    try:
        text = scrape_direct(url)
        if not is_garbage_text(text) and len(text) >= 100:
            return text, "direct"
        errors.append("Direct returned unreadable content")
    except Exception as e:
        errors.append(f"Direct error: {str(e)}")
    
    # Route 3: Direct failed - try API
    if api_configured:
        try:
            text = scrape_with_api(url)
            if not is_garbage_text(text):
                return text, "api"
            errors.append("API returned unreadable content")
        except Exception as e:
            errors.append(f"API error: {str(e)}")
    
    # Route 4: API failed - try proxy
    if proxy_configured:
        try:
            text = scrape_with_proxy(url)
            if not is_garbage_text(text):
                return text, "proxy"
            errors.append("Proxy returned unreadable content")
        except Exception as e:
            errors.append(f"Proxy error: {str(e)}")
    
    raise ValueError(f"Could not scrape {domain}: {'; '.join(errors)}")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "version": "3.7-dual-method",
        "api_configured": bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE),
        "proxy_configured": bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD),
        "zone": BRIGHTDATA_ZONE or "not set",
        "proxy_port": BRIGHTDATA_PORT
    })


@app.route("/", methods=["POST"])
def handle():
    data = {}
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        force_proxy = data.get("force_proxy", False)
        
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        
        text, method = scrape(url, force_proxy=force_proxy)
        
        if len(text) < 100:
            return jsonify({
                "success": False,
                "error": "ERROR_MINIMAL_CONTENT",
                "text_length": len(text),
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
            "error": "ERROR_SCRAPING_FAILED",
            "message": str(e),
            "url": data.get("website") or data.get("url")
        }), 422
    
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        error_body = ""
        try:
            error_body = e.response.text[:500] if e.response else ""
        except:
            pass
        return jsonify({
            "success": False,
            "error": f"ERROR_HTTP_{status}",
            "details": error_body,
            "url": data.get("website") or data.get("url")
        }), 422
    
    except requests.exceptions.Timeout:
        return jsonify({
            "success": False,
            "error": "ERROR_TIMEOUT",
            "url": data.get("website") or data.get("url")
        }), 422
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "ERROR_UNKNOWN",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
