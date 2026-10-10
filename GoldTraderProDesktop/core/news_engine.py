"""خبرخوان RSS رایگان؛ اگر اینترنت/فید موجود نباشد وضعیت NO DATA است."""
from datetime import datetime, timezone, timedelta
import feedparser
FEEDS=["https://www.fxstreet.com/rss/news","https://www.dailyfx.com/feeds/market-news","https://www.investing.com/rss/news_11.rss"]
KEYWORDS=("gold","xau","fed","federal reserve","dollar","dxy","inflation","cpi","nfp","fomc","rate decision","bullion")
BULL=("rate cut","dovish","weaker dollar","gold rally","gold rises","gold surge")
BEAR=("rate hike","hawkish","stronger dollar","gold falls","gold drops","gold selloff")
def fetch_news(max_items=40):
    items=[]; errors=[]
    for url in FEEDS:
        try:
            feed=feedparser.parse(url)
            if getattr(feed,"bozo",False) and not feed.entries: errors.append(url);continue
            for e in feed.entries[:max_items]:
                title=str(e.get("title","")).strip(); summary=str(e.get("summary","")).strip()
                text=(title+" "+summary).lower()
                if not title or not any(k in text for k in KEYWORDS):continue
                sentiment="خنثی"
                if any(k in text for k in BULL):sentiment="صعودی"
                elif any(k in text for k in BEAR):sentiment="نزولی"
                items.append({"title":title,"summary":summary[:350],"source":url,"published":e.get("published","نامشخص"),"sentiment":sentiment,"gold_relevant":True})
        except Exception:errors.append(url)
    seen=set(); unique=[]
    for item in items:
        if item["title"] not in seen:seen.add(item["title"]);unique.append(item)
    return {"status":"OK" if unique else "NO DATA","items":unique[:max_items],"checked_at":datetime.now(timezone.utc).isoformat(),"errors":errors}
