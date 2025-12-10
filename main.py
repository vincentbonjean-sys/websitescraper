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

# Method 4: Bright Data Scraping Browser - For Cloudflare/heavy protection
SCRAPING_BROWSER_USERNAME = os.environ.get('SCRAPING_BROWSER_USERNAME', '')
SCRAPING_BROWSER_PASSWORD = os.environ.get('SCRAPING_BROWSER_PASSWORD', '')

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Sites that REQUIRE JavaScript rendering
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

# Sites with anti-bot protection (use Web Unlocker or Scraping Browser)
PROTECTED_DOMAINS = [
    'swooped.co',
    'linkedin.com',
    'indeed.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'angel.co',
    'wellfound.com',
    'tealhq.com',
    'builtin.com',
    'dice.com',
    'careerbuilder.com',
]


def get_domain(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc.lower()


def check_js_required(url):
    domain = get_domain(url)
    for js_domain in JS_REQUIRED_DOMAINS:
        if js_domain in domain:
            return js_domain
    return None


def check_protected(url):
    domain = get_domain(url)
    for d in PROTECTED_DOMAINS:
        if d in domain:
            return d
    return None


def is_blocked(text):
    """Detect if response is a security block page"""
    if not text:
        return False
    
    lower_text = text.lower()
    
    block_indicators = [
        'you have been blocked',
        'cloudflare ray id',
        'please enable cookies',
        'security service to protect itself',
        'why have i been blocked',
        'attention required',
        'checking your browser',
        'please wait while we verify',
        'just a moment...',
        'enable javascript and cookies',
        'access denied',
        'access to this page has been denied',
        'please verify you are human',
        'complete the captcha',
        'prove you are not a robot',
        'bot detection',
        'suspicious activity',
        'too many requests',
        'rate limit exceeded',
        'are you a robot',
        'human verification',
        'ddos protection',
        'security check',
        'incapsula',
        'perimeterx',
        'datadome',
    ]
    
    matches = sum(1 for ind in block_indicators if ind in lower_text)
    
    if matches >= 2:
        return True
    if matches >= 1 and len(text) < 2000:
        return True
    
    return False


def is_garbage_text(text):
    if not text or len(text) < 50:
        return True
    
    control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
    if text.count('\x00') > 0 or (len(text) > 0 and control_chars / len(text) > 0.05):
        return True
    
    words = re.findall(r'[a-zA-Z]{3,}', text)
    if len(words) < 10:
        return True
    
    return False


def is_shell_only(text):
    if not text:
        return True
    
    lower_text = text.lower()
    
    shell_indicators = ['toggle navigation', 'candidate dashboard', 'join today', 'privacy policy', 'cookie policy']
    content_indicators = ['responsibilities', 'requirements', 'qualifications', 'what you\'ll do', 'about the role']
    
    shell_count = sum(1 for ind in shell_indicators if ind in lower_text)
    content_count = sum(1 for ind in content_indicators if ind in lower_text)
    
    return shell_count >= 2 and content_count < 1


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


def validate_content(text):
    """Returns (is_valid, error_type, message)"""
    if not text:
        return False, "empty", "No content"
    if is_blocked(text):
        return False, "blocked", "Security block detected"
    if is_garbage_text(text):
        return False, "garbage", "Unreadable content"
    if is_shell_only(text):
        return False, "shell", "Only page shell, no job content"
    if len(text) < 100:
        return False, "minimal", f"Too short ({len(text)} chars)"
    return True, None, None


# ============================================
# SCRAPING METHODS
# ============================================

def scrape_direct(url):
    """Direct scraping - no proxy"""
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


def scrape_with_web_unlocker_api(url):
    """Bright Data Web Unlocker - API method"""
    if not BRIGHTDATA_API_KEY or not BRIGHTDATA_ZONE:
        raise ValueError("Web Unlocker API not configured")
    
    response = requests.post(
        "https://api.brightdata.com/request",
        headers={
            'Authorization': f'Bearer {BRIGHTDATA_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={'zone': BRIGHTDATA_ZONE, 'url': url, 'format': 'raw'},
        timeout=60
    )
    response.raise_for_status()
    return extract_text_from_html(response.text)


def scrape_with_web_unlocker_proxy(url):
    """Bright Data Web Unlocker - Proxy method"""
    if not BRIGHTDATA_USERNAME or not BRIGHTDATA_PASSWORD:
        raise ValueError("Web Unlocker proxy not configured")
    
    proxy_url = f"http://{BRIGHTDATA_USERNAME}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_HOST}:{BRIGHTDATA_PORT}"
    
    response = requests.get(
        url,
        headers={'User-Agent': random.choice(USER_AGENTS)},
        proxies={'http': proxy_url, 'https': proxy_url},
        timeout=90,
        verify=False
    )
    response.raise_for_status()
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    return extract_text_from_html(response.text)


def scrape_with_scraping_browser(url):
    """
    Bright Data Scraping Browser - BEST for Cloudflare
    Uses real Chrome browser with undetectable fingerprints
    """
    if not SCRAPING_BROWSER_USERNAME or not SCRAPING_BROWSER_PASSWORD:
        raise ValueError("Scraping Browser not configured")
    
    # Scraping Browser uses port 22225
    proxy_url = f"http://{SCRAPING_BROWSER_USERNAME}:{SCRAPING_BROWSER_PASSWORD}@brd.superproxy.io:22225"
    
    response = requests.get(
        url,
        headers={
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        proxies={'http': proxy_url, 'https': proxy_url},
        timeout=120,  # Scraping Browser is slower but more reliable
        verify=False
    )
    response.raise_for_status()
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    return extract_text_from_html(response.text)


def scrape_with_browserless(url, stealth=False):
    """Browserless.io - JS rendering"""
    if not BROWSERLESS_API_KEY:
        raise ValueError("Browserless not configured")
    
    # Add stealth parameter for better bot evasion
    endpoint = f"https://chrome.browserless.io/content?token={BROWSERLESS_API_KEY}"
    if stealth:
        endpoint += "&stealth"
    
    response = requests.post(
        endpoint,
        json={
            "url": url,
            "gotoOptions": {
                "waitUntil": "networkidle2",
                "timeout": 30000
            }
        },
        timeout=90,
        headers={'Content-Type': 'application/json'}
    )
    response.raise_for_status()
    return extract_text_from_html(response.text)


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def scrape(url, force_browserless=False):
    """Main scraping function with intelligent routing and fallbacks"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    domain = get_domain(url)
    js_required = check_js_required(url)
    is_protected = check_protected(url)
    
    # Check what's configured
    web_unlocker_api = bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE)
    web_unlocker_proxy = bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD)
    scraping_browser = bool(SCRAPING_BROWSER_USERNAME and SCRAPING_BROWSER_PASSWORD)
    browserless = bool(BROWSERLESS_API_KEY)
    
    errors = []
    
    # ============================================
    # ROUTE 1: JS-REQUIRED SITES
    # Try: Browserless → Scraping Browser
    # ============================================
    if js_required or force_browserless:
        # Try Browserless with stealth first
        if browserless:
            try:
                text = scrape_with_browserless(url, stealth=True)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "browserless_stealth", None, None
                if err_type == "blocked":
                    errors.append(f"Browserless stealth: blocked")
                else:
                    errors.append(f"Browserless stealth: {err_msg}")
            except Exception as e:
                errors.append(f"Browserless stealth: {str(e)}")
        
        # Try Scraping Browser (better Cloudflare bypass)
        if scraping_browser:
            try:
                text = scrape_with_scraping_browser(url)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "scraping_browser", None, None
                errors.append(f"Scraping Browser: {err_msg}")
            except Exception as e:
                errors.append(f"Scraping Browser: {str(e)}")
        
        if not browserless and not scraping_browser:
            return None, None, "ERROR_JS_REQUIRED", f"Site requires JS. Configure BROWSERLESS_API_KEY or SCRAPING_BROWSER credentials."
        
        return None, None, "ERROR_SCRAPING_FAILED", f"JS site {domain}: {'; '.join(errors)}"
    
    # ============================================
    # ROUTE 2: PROTECTED SITES (Cloudflare etc)
    # Try: Scraping Browser → Web Unlocker → Browserless
    # ============================================
    if is_protected:
        # Scraping Browser is BEST for protected sites
        if scraping_browser:
            try:
                text = scrape_with_scraping_browser(url)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "scraping_browser", None, None
                errors.append(f"Scraping Browser: {err_msg}")
            except Exception as e:
                errors.append(f"Scraping Browser: {str(e)}")
        
        # Try Web Unlocker API
        if web_unlocker_api:
            try:
                text = scrape_with_web_unlocker_api(url)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "web_unlocker_api", None, None
                errors.append(f"Web Unlocker API: {err_msg}")
            except Exception as e:
                errors.append(f"Web Unlocker API: {str(e)}")
        
        # Try Web Unlocker Proxy
        if web_unlocker_proxy:
            try:
                text = scrape_with_web_unlocker_proxy(url)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "web_unlocker_proxy", None, None
                errors.append(f"Web Unlocker Proxy: {err_msg}")
            except Exception as e:
                errors.append(f"Web Unlocker Proxy: {str(e)}")
        
        # Try Browserless with stealth
        if browserless:
            try:
                text = scrape_with_browserless(url, stealth=True)
                is_valid, err_type, err_msg = validate_content(text)
                if is_valid:
                    return text, "browserless_stealth", None, None
                errors.append(f"Browserless stealth: {err_msg}")
            except Exception as e:
                errors.append(f"Browserless stealth: {str(e)}")
        
        # All failed
        if any("block" in e.lower() for e in errors):
            return None, None, "ERROR_BLOCKED", f"All methods blocked by {domain}"
        return None, None, "ERROR_SCRAPING_FAILED", f"Protected site {domain}: {'; '.join(errors)}"
    
    # ============================================
    # ROUTE 3: NORMAL SITES
    # Try: Direct → Web Unlocker → Browserless
    # ============================================
    
    # Try direct first
    try:
        text = scrape_direct(url)
        is_valid, err_type, err_msg = validate_content(text)
        if is_valid:
            return text, "direct", None, None
        if err_type == "blocked":
            errors.append(f"Direct: blocked")
        else:
            errors.append(f"Direct: {err_msg}")
    except Exception as e:
        errors.append(f"Direct: {str(e)}")
    
    # Try Web Unlocker API
    if web_unlocker_api:
        try:
            text = scrape_with_web_unlocker_api(url)
            is_valid, err_type, err_msg = validate_content(text)
            if is_valid:
                return text, "web_unlocker_api", None, None
            errors.append(f"Web Unlocker API: {err_msg}")
        except Exception as e:
            errors.append(f"Web Unlocker API: {str(e)}")
    
    # Try Web Unlocker Proxy
    if web_unlocker_proxy:
        try:
            text = scrape_with_web_unlocker_proxy(url)
            is_valid, err_type, err_msg = validate_content(text)
            if is_valid:
                return text, "web_unlocker_proxy", None, None
            errors.append(f"Web Unlocker Proxy: {err_msg}")
        except Exception as e:
            errors.append(f"Web Unlocker Proxy: {str(e)}")
    
    # Try Scraping Browser
    if scraping_browser:
        try:
            text = scrape_with_scraping_browser(url)
            is_valid, err_type, err_msg = validate_content(text)
            if is_valid:
                return text, "scraping_browser", None, None
            errors.append(f"Scraping Browser: {err_msg}")
        except Exception as e:
            errors.append(f"Scraping Browser: {str(e)}")
    
    # Try Browserless
    if browserless:
        try:
            text = scrape_with_browserless(url)
            is_valid, err_type, err_msg = validate_content(text)
            if is_valid:
                return text, "browserless", None, None
            errors.append(f"Browserless: {err_msg}")
        except Exception as e:
            errors.append(f"Browserless: {str(e)}")
    
    # All methods failed
    if any("block" in e.lower() for e in errors):
        return None, None, "ERROR_BLOCKED", f"Blocked: {'; '.join(errors)}"
    
    return None, None, "ERROR_SCRAPING_FAILED", f"{domain}: {'; '.join(errors)}"


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "version": "5.0-scraping-browser",
        "methods": {
            "web_unlocker_api": bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE),
            "web_unlocker_proxy": bool(BRIGHTDATA_USERNAME and BRIGHTDATA_PASSWORD),
            "scraping_browser": bool(SCRAPING_BROWSER_USERNAME and SCRAPING_BROWSER_PASSWORD),
            "browserless": bool(BROWSERLESS_API_KEY),
        }
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
        
        text, method, error_code, error_message = scrape(url, force_browserless=force_browserless)
        
        if error_code:
            return jsonify({
                "success": False,
                "error": error_code,
                "message": error_message,
                "url": url,
                "method": method
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
