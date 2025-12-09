import os
import re
import random
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Bright Data credentials (set in Cloud Run environment variables)
BRIGHTDATA_API_KEY = os.environ.get('BRIGHTDATA_API_KEY', '')
BRIGHTDATA_ZONE = os.environ.get('BRIGHTDATA_ZONE', '')  # e.g., "web_unlocker1"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Domains that need JavaScript rendering
JS_RENDER_DOMAINS = [
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
    'adp.com',
    'successfactors.com',
    'taleo.net',
    'brassring.com',
    'linkedin.com',
    'indeed.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'angel.co',
    'wellfound.com',
    'swooped.co',
    'ashbyhq.com',
    'bamboohr.com',
    'recruitee.com',
    'personio.com',
    'workable.com',
]


def needs_js_render(url):
    """Check if URL needs JavaScript rendering"""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    return any(js_domain in domain for js_domain in JS_RENDER_DOMAINS)


def is_garbage_text(text):
    """Check if extracted text is garbage/unusable"""
    if not text or len(text) < 50:
        return True
    
    # Check for binary/control characters
    control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
    null_chars = text.count('\x00')
    if null_chars > 0 or (len(text) > 0 and control_chars / len(text) > 0.05):
        return True
    
    # Check for meaningful words
    words = re.findall(r'[a-zA-Z]{3,}', text)
    if len(words) < 10:
        return True
    
    # Check for common "empty page" indicators
    lower_text = text.lower()
    empty_indicators = [
        'please enable javascript',
        'javascript is required',
        'browser does not support',
        'loading...',
        'please wait',
        'redirecting',
    ]
    if any(indicator in lower_text for indicator in empty_indicators):
        # Only flag as garbage if text is short
        if len(text) < 500:
            return True
    
    return False


def clean_text(text):
    """Clean extracted text"""
    if not text:
        return ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def extract_text_from_html(html):
    """Extract readable text from HTML"""
    soup = BeautifulSoup(html, "html.parser")
    
    # Remove non-content elements
    for tag in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe', 'svg', 'meta', 'link']:
        for el in soup.find_all(tag):
            el.decompose()
    
    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r'job|posting|description|content', re.I)) or soup.find("body") or soup
    
    return clean_text(main.get_text(separator='\n', strip=True))


def scrape_direct(url):
    """Direct scraping without proxy"""
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    session = requests.Session()
    response = session.get(url, headers=headers, timeout=15, allow_redirects=True)
    response.raise_for_status()
    
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    
    return extract_text_from_html(response.text)


def scrape_with_brightdata(url, use_render=False):
    """Scrape using Bright Data Web Unlocker API"""
    if not BRIGHTDATA_API_KEY:
        raise ValueError("BRIGHTDATA_API_KEY not configured")
    if not BRIGHTDATA_ZONE:
        raise ValueError("BRIGHTDATA_ZONE not configured")
    
    api_url = "https://api.brightdata.com/request"
    
    headers = {
        'Authorization': f'Bearer {BRIGHTDATA_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # Build payload
    payload = {
        'zone': BRIGHTDATA_ZONE,
        'url': url,
        'format': 'raw'
    }
    
    # Add JavaScript rendering if needed
    if use_render:
        payload['js_render'] = True
        payload['wait'] = 5  # Wait 5 seconds for JS to load
    
    response = requests.post(api_url, headers=headers, json=payload, timeout=90)
    response.raise_for_status()
    
    return extract_text_from_html(response.text), response.text


def scrape(url, force_render=False):
    """Main scraping function with fallback logic"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    use_render = force_render or needs_js_render(url)
    
    # Try direct scraping first for non-JS sites
    if not use_render:
        try:
            text = scrape_direct(url)
            if not is_garbage_text(text) and len(text) >= 100:
                return text, "direct"
        except Exception as e:
            pass  # Fall through to Bright Data
    
    # Use Bright Data
    if BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE:
        # First try without JS render (faster, cheaper)
        if not use_render:
            try:
                text, raw_html = scrape_with_brightdata(url, use_render=False)
                if not is_garbage_text(text) and len(text) >= 100:
                    return text, "brightdata"
            except Exception as e:
                pass  # Try with render
        
        # Try with JS rendering
        text, raw_html = scrape_with_brightdata(url, use_render=True)
        if not is_garbage_text(text) and len(text) >= 100:
            return text, "brightdata_render"
        
        # If still garbage, return what we got with a warning
        if len(text) >= 50:
            return text, "brightdata_partial"
        
        raise ValueError(f"Bright Data returned unreadable content ({len(text)} chars)")
    else:
        raise ValueError("Site requires JavaScript - configure BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "version": "3.2-brightdata-render",
        "brightdata_configured": bool(BRIGHTDATA_API_KEY and BRIGHTDATA_ZONE),
        "zone": BRIGHTDATA_ZONE or "not set",
        "js_render_domains": len(JS_RENDER_DOMAINS)
    })


@app.route("/", methods=["POST"])
def handle():
    data = {}
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        force_render = data.get("force_render", False)
        
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        
        text, method = scrape(url, force_render=force_render)
        
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
            "error": "ERROR_JAVASCRIPT_REQUIRED",
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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
