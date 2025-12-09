import os
import re
import random
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Method 1: Bright Data Web Unlocker - API method
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY', '')
BRIGHTDATA_ZONE = os.environ.get('BRIGHTDATA_ZONE', '')

# Method 2: Bright Data Web Unlocker - Proxy method
BRIGHTDATA_USERNAME = os.environ.get('BRIGHTDATA_USERNAME', '')
BRIGHTDATA_PASSWORD = os.environ.get('BRIGHTDATA_PASSWORD', '')
BRIGHTDATA_HOST = os.environ.get('BRIGHTDATA_HOST', 'brd.superproxy.io')
BRIGHTDATA_PORT = os.environ.get('BRIGHTDATA_PORT', '33335')

# Method 3: Browserless.io - For JS-heavy sites
BROWSERLESS_API_KEY = os.environ.get('BROWSERLESS_API_KEY', '')

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Sites that REQUIRE JavaScript rendering - MUST use Browserless
JS_REQUIRED_DOMAINS = [
    'myworkdayjobs.com',
    'workday.com',
    'icims.com',
    'hiringtoday.com',
    'pepsicojobs.com',
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
    'workable.com',
]

# Sites with anti-bot that Web Unlocker CAN handle (server-rendered)
UNLOCKER_DOMAINS = [
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


def check_js_required(url):
    """Check if URL requires JavaScript rendering"""
    domain = get_domain(url)
    for js_domain in JS_REQUIRED_DOMAINS:
        if js_domain in domain:
            return js_domain
    return None


def check_unlocker_required(url):
    """Check if URL needs Web Unlocker"""
    domain = get_domain(url)
    for d in UNLOCKER_DOMAINS:
        if d in domain:
            return d
    return None


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
    
    return False


def is_shell_only(text):
    """Detect if we only got page shell without actual job content"""
    if not text:
        return True
    
    lower_text = text.lower()
    
    shell_indicators = [
        'toggle navigation',
        'candidate dashboard',
        'sign up and add your profile',
        'join today',
        'terms of use',
        'privacy policy',
        'cookie policy',
        'career areas',
        'featured awards',
    ]
    
    content_indicators = [
        'responsibilities',
        'requirements',
        'qualifications',
        'experience required',
        'what you\'ll do',
        'about the role',
        'key accountabilities',
        'primary accountabilities',
        'job duties',
        'position summary',
        'basic qualifications',
        'preferred qualifications',
    ]
    
    shell_count = sum(1 for ind in shell_indicators if ind in lower_text)
    content_count = sum(1 for ind in content_indicators if ind in lower_text)
    
    if shell_count >= 2 and content_count < 1:
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
    """Scrape using Bright Data Web Unlocker API"""
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
    """Scrape using Bright Data Web Unlocker proxy"""
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


def scrape_with_browserless(url):
    """Scrape using Browserless.io (renders JavaScript)"""
    if not BROWSERLESS_API_KEY:
        raise ValueError("BROWSERLESS_API_KEY not configured")
    
    # Browserless /content API - correct format
    response = requests.post(
        f"https://chrome.browserless.io/content?token={BROWSERLESS_API_KEY}",
        json={
            "url": url,
            "gotoOptions": {
                "waitUntil": "networkidle2",
                "timeout": 30000
            }
        },
        timeout=90,
        headers={
            'Content-Type': 'application/json'
        }
    )
    response.raise_for_status()
    
    return extract_text_from_html(response.text)


def scrape(url, force_browserless=False):
    """Main scraping function with intelligent routing"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = get_domain(url)
    
    # Check what type of site this is
    js_match = check_js_required(url)
    unlocker_match = check_unlocker_required(url)
    
    api_configured = bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE)
    proxy_configured = bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD)
    browserless_configured = bool(BROWSERLESS_API_KEY)
    
    errors = []
    
    # ============================================
    # ROUTE 1: JS-REQUIRED SITES → BROWSERLESS ONLY
    # ============================================
    if js_match or force_browserless:
        if not browserless_configured:
            return None, None, f"ERROR_JS_REQUIRED: Site '{js_match or domain}' requires JavaScript rendering. Add BROWSERLESS_API_KEY to scrape this site."
        
        try:
            text = scrape_with_browserless(url)
            if not is_garbage_text(text) and not is_shell_only(text):
                return text, "browserless", None
            errors.append("Browserless returned incomplete content")
        except Exception as e:
            errors.append(f"Browserless error: {str(e)}")
        
        return None, None, f"Could not scrape JS site {domain}: {'; '.join(errors)}"
    
    # ============================================
    # ROUTE 2: ANTI-BOT SITES → WEB UNLOCKER
    # ============================================
    if unlocker_match:
        if api_configured:
            try:
                text = scrape_with_api(url)
                if not is_garbage_text(text) and not is_shell_only(text):
                    return text, "api", None
                errors.append("API returned incomplete content")
            except Exception as e:
                errors.append(f"API error: {str(e)}")
        
        if proxy_configured:
            try:
                text = scrape_with_proxy(url)
                if not is_garbage_text(text) and not is_shell_only(text):
                    return text, "proxy", None
                errors.append("Proxy returned incomplete content")
            except Exception as e:
                errors.append(f"Proxy error: {str(e)}")
        
        if browserless_configured:
            try:
                text = scrape_with_browserless(url)
                if not is_garbage_text(text) and not is_shell_only(text):
                    return text, "browserless", None
            except Exception as e:
                errors.append(f"Browserless error: {str(e)}")
        
        return None, None, f"Could not scrape {domain}: {'; '.join(errors)}"
    
    # ============================================
    # ROUTE 3: NORMAL SITES → TRY DIRECT FIRST
    # ============================================
    try:
        text = scrape_direct(url)
        if not is_garbage_text(text) and not is_shell_only(text) and len(text) >= 100:
            return text, "direct", None
        errors.append("Direct returned incomplete content")
    except Exception as e:
        errors.append(f"Direct error: {str(e)}")
    
    if api_configured:
        try:
            text = scrape_with_api(url)
            if not is_garbage_text(text) and not is_shell_only(text):
                return text, "api", None
        except Exception as e:
            errors.append(f"API error: {str(e)}")
    
    if proxy_configured:
        try:
            text = scrape_with_proxy(url)
            if not is_garbage_text(text) and not is_shell_only(text):
                return text, "proxy", None
        except Exception as e:
            errors.append(f"Proxy error: {str(e)}")
    
    if browserless_configured:
        try:
            text = scrape_with_browserless(url)
            if not is_garbage_text(text) and not is_shell_only(text):
                return text, "browserless", None
        except Exception as e:
            errors.append(f"Browserless error: {str(e)}")
    
    return None, None, f"Could not scrape {domain}: {'; '.join(errors)}"


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "version": "4.2-fixed-browserless",
        "api_configured": bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE),
        "proxy_configured": bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD),
        "browserless_configured": bool(BROWSERLESS_API_KEY),
    })


@app.route("/", methods=["POST"])
def handle():
    data = {}
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        force_browserless = data.get("force_browserless", False)
        
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        
        text, method, error = scrape(url, force_browserless=force_browserless)
        
        if error:
            error_code = "ERROR_SCRAPING_FAILED"
            if "ERROR_JS_REQUIRED" in error:
                error_code = "ERROR_JS_REQUIRED"
            
            return jsonify({
                "success": False,
                "error": error_code,
                "message": error,
                "url": url
            }), 422
        
        if not text or len(text) < 100:
            return jsonify({
                "success": False,
                "error": "ERROR_MINIMAL_CONTENT",
                "text_length": len(text) if text else 0,
                "url": url
            }), 422
        
        return jsonify({
            "success": True,
            "text": text,
            "text_length": len(text),
            "url": url,
            "method": method
        })
    
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
