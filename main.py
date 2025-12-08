import os
import re
import random
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

# Multiple user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

def get_headers(url):
    """Generate browser-like headers"""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Host': domain,
        'Referer': f'https://www.google.com/search?q={domain}',
    }

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def scrape(url, retries=2):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    last_error = None
    
    for attempt in range(retries + 1):
        try:
            headers = get_headers(url)
            
            # Create session for cookie handling
            session = requests.Session()
            
            response = session.get(
                url, 
                headers=headers, 
                timeout=20, 
                allow_redirects=True,
                verify=True
            )
            response.raise_for_status()
            
            if response.encoding is None or response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            for tag in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe', 'svg']:
                for el in soup.find_all(tag):
                    el.decompose()
            
            main = soup.find("main") or soup.find("article") or soup.find("body") or soup
            return clean_text(main.get_text(separator='\n', strip=True))
            
        except requests.exceptions.HTTPError as e:
            last_error = e
            if e.response.status_code == 403 and attempt < retries:
                # Retry with different user agent
                continue
            raise
        except Exception as e:
            last_error = e
            if attempt < retries:
                continue
            raise

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "version": "2.0"})

@app.route("/", methods=["POST"])
def handle():
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        
        text = scrape(url)
        
        if len(text) < 50:
            return jsonify({
                "success": False, 
                "error": "Minimal content extracted - site may require JavaScript",
                "text": text,
                "url": url
            }), 422
        
        return jsonify({
            "success": True, 
            "text": text, 
            "text_length": len(text),
            "url": url
        })
    
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        return jsonify({
            "success": False, 
            "error": f"HTTP {status}: Site blocked the request or page not found",
            "url": data.get("website") or data.get("url"),
            "blocked": status == 403
        }), 422
    
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 422
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
