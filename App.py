import os
import re

from flask import Flask, jsonify, request
from deep_translator import GoogleTranslator
import requests

app = Flask(__name__)

# ===== مفتاح الحماية =====
# غيّر القيمة الافتراضية هنا لنفس القيمة اللي حطيتها بـ Secrets على
# Creator Dashboard تبع روبلوكس (اسم السر: DOOR_API_KEY).
# الأفضل أمنياً إنك تحطها كـ Environment Variable من إعدادات الـ Web App
# بـ PythonAnywhere بدل ما تكتبها هنا مباشرة، لكن للتجربة السريعة تقدر
# تكتبها هنا مؤقتاً.
API_SECRET = os.environ.get("DOOR_API_KEY", "NETRO1122@")


@app.before_request
def check_api_key():
    # اسمح بمرور فحص الصحة بدون مفتاح، عشان تقدر تتأكد إن السيرفر شغّال
    if request.path == "/health":
        return
    provided_key = request.headers.get("X-Api-Key")
    if not provided_key or provided_key != API_SECRET:
        return jsonify({"error": "unauthorized"}), 401


KEYWORD_EFFECTS = [
    {"words": ["gothic", "pointed arch", "cathedral"],
     "effect": {"frameStyle": "pointed_arch", "archRise": 0.15, "ornament": 0.2}},
    {"words": ["arch", "arched", "archway", "romanesque"],
     "effect": {"frameStyle": "segmental_arch", "archRise": 0.1}},
    {"words": ["glass", "window pane", "glazed", "glazing"],
     "effect": {"glassRatio": 0.3}},
    {"words": ["carved", "ornate", "relief", "baroque", "rococo", "decorative molding"],
     "effect": {"ornament": 0.35}},
    {"words": ["wrought iron", "iron strap", "iron banding"],
     "effect": {"hingeMaterial": "WroughtIron", "material": "Wood", "ornament": 0.15}},
    {"words": ["steel", "industrial", "riveted", "metal plate"],
     "effect": {"material": "DiamondPlate", "hingeMaterial": "Steel"}},
    {"words": ["brass", "bronze"], "effect": {"hingeMaterial": "Brass"}},
    {"words": ["double door", "double doors", "french door"], "effect": {"isDouble": True}},
    {"words": ["minimalist", "flush door", "flat panel"],
     "effect": {"ornament": -0.2, "glassRatio": -0.1}},
    {"words": ["oak", "walnut", "mahogany", "timber"], "effect": {"material": "Wood"}},
]


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def search_wikipedia(query, limit=3, lang="en"):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srlimit": limit,
        "srsearch": query,
    }
    headers = {"User-Agent": "RobloxDoorGen/1.0 (educational project)"}
    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = data.get("query", {}).get("search", [])
    return [
        {"title": item["title"], "snippet": strip_html(item.get("snippet", ""))}
        for item in results
    ]


def extract_style_hints(snippets):
    text = " ".join(f"{s['title']} {s['snippet']}" for s in snippets).lower()

    bias = {"archRise": 0.0, "glassRatio": 0.0, "ornament": 0.0}
    found_words = []
    frame_style_vote = None
    material_vote = None
    hinge_vote = None
    is_double_vote = False

    for entry in KEYWORD_EFFECTS:
        for w in entry["words"]:
            if w in text:
                found_words.append(w)
                e = entry["effect"]
                bias["archRise"] += e.get("archRise", 0)
                bias["glassRatio"] += e.get("glassRatio", 0)
                bias["ornament"] += e.get("ornament", 0)
                if "frameStyle" in e:
                    frame_style_vote = e["frameStyle"]
                if "material" in e:
                    material_vote = e["material"]
                if "hingeMaterial" in e:
                    hinge_vote = e["hingeMaterial"]
                if e.get("isDouble"):
                    is_double_vote = True
                break

    return {
        "archRiseBias": clamp(bias["archRise"], 0, 0.3),
        "glassRatioBias": clamp(bias["glassRatio"], -0.3, 0.5),
        "ornamentBias": clamp(bias["ornament"], -0.3, 0.5),
        "frameStyleHint": frame_style_vote,
        "materialHint": material_vote,
        "hingeMaterialHint": hinge_vote,
        "isDoubleHint": is_double_vote,
        "keywordsFound": found_words,
        "hasSignal": len(found_words) > 0,
    }


@app.route("/inspiration", methods=["GET"])
def inspiration():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"error": "query_too_short"}), 400
    if len(query) > 200:
        query = query[:200]

    try:
        translated = GoogleTranslator(source="auto", target="en").translate(query)
        if not translated:
            translated = query
    except Exception:
        translated = query

    try:
        snippets = search_wikipedia(translated, limit=3, lang="en")
    except Exception:
        return jsonify({"error": "search_failed"}), 502

    if not snippets:
        return jsonify({"error": "no_results"}), 404

    hints = extract_style_hints(snippets)
    hints["query"] = query
    hints["translatedQuery"] = translated
    hints["sourceTitles"] = [s["title"] for s in snippets]

    return jsonify(hints)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

