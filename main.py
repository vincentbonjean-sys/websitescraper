import os
import re
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def scrape(url):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
    response.raise_for_status()
    if response.encoding is None or response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in ['script', 'style', 'nav', 'footer', 'header', 'noscript', 'iframe']:
        for el in soup.find_all(tag):
            el.decompose()
    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    return clean_text(main.get_text(separator='\n', strip=True))

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running"})

@app.route("/", methods=["POST"])
def handle():
    try:
        data = request.get_json() or {}
        url = data.get("website") or data.get("url")
        if not url:
            return jsonify({"success": False, "error": "website parameter required"}), 400
        text = scrape(url)
        if len(text) < 50:
            return jsonify({"success": False, "error": "Minimal content", "text": text}), 422
        return jsonify({"success": True, "text": text, "text_length": len(text)})
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 422
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
