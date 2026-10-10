"""خبرخوان RSS رایگان با فیلتر طلا و شناسایی خبرهای تازه پرریسک."""
from datetime import datetime,timezone
import feedparser
FEEDS=["https://www.fxstreet.com/rss/news","https://www.dailyfx.com/feeds/market-news","https://www.investing.com/rss/news_11.rss"]
KEYWORDS=("gold","xau","fed","federal reserve","dollar","dxy","inflation","cpi","nfp","fomc","rate decision","bullion")
BULL=("rate cut","dovish","weaker dollar","gold rally","gold rises","gold surge")
BEAR=("rate hike","hawkish","stronger dollar","gold falls","gold drops","gold selloff")
CRITICAL=("fomc","rate decision","nonfarm payroll","nfp","cpi","inflation report")
HIGH=("fed","federal reserve","dxy","recession","gold","bullion")
def fetch_news(max_items=40):
    items=[];errors=[]
    for url in FEEDS:
        try:
            feed=feedparser.parse(url)
            if getattr(feed,"bozo",False) and not feed.entries:errors.append(url);continue
            for e in feed.entries[:max_items]:
                title=str(e.get("title","")).strip();summary=str(e.get("summary","")).strip();text=(title+" "+summary).lower()
                if not title or not any(k in text for k in KEYWORDS):continue
                sentiment="خنثی"
                if any(k in text for k in BULL):sentiment="صعودی"
                elif any(k in text for k in BEAR):sentiment="نزولی"
                importance="CRITICAL" if any(k in text for k in CRITICAL) else "HIGH" if any(k in text for k in HIGH) else "MEDIUM"
                published_at="";parsed=e.get("published_parsed") or e.get("updated_parsed")
                if parsed:
                    try:published_at=datetime(*parsed[:6],tzinfo=timezone.utc).isoformat()
                    except Exception:pass
                items.append({"title":title,"summary":summary[:350],"source":url,"published":e.get("published","نامشخص"),"published_at":published_at,"sentiment":sentiment,"importance":importance,"gold_relevant":True})
        except Exception:errors.append(url)
    seen=set();unique=[]
    for item in items:
        if item["title"] not in seen:seen.add(item["title"]);unique.append(item)
    return {"status":"OK" if unique else "NO DATA","items":unique[:max_items],"checked_at":datetime.now(timezone.utc).isoformat(),"errors":errors}
def blocking_news(items,after_minutes=15,now=None):
    now=now or datetime.now(timezone.utc);blocked=[]
    for item in items or []:
        if item.get("importance") not in ("CRITICAL","HIGH") or not item.get("gold_relevant"):continue
        stamp=item.get("published_at")
        if not stamp:continue
        try:
            dt=datetime.fromisoformat(stamp.replace("Z","+00:00"))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            age=(now-dt).total_seconds()/60
            if 0<=age<=after_minutes:blocked.append(item)
        except (ValueError,TypeError):continue
    return blocked
