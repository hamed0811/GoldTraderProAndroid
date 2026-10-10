"""سطوح تقریبی حمایت/مقاومت از swing، اعداد رند و EMA."""
from .indicators import ema
def find_levels(df,price=None,tolerance=2.0):
    if df is None or len(df)<30:return {"support":[],"resistance":[]}
    h=df.high.astype(float).to_numpy();l=df.low.astype(float).to_numpy();c=df.close.astype(float).to_numpy();price=float(price if price is not None else c[-1])
    candidates=[]
    start=max(2,len(df)-250)
    for i in range(start,len(df)-2):
        if h[i]>=max(h[i-2:i+3]):candidates.append((float(h[i]),"سقف محلی"))
        if l[i]<=min(l[i-2:i+3]):candidates.append((float(l[i]),"کف محلی"))
    for p in (9,21,50,200):
        v=ema(c,p)[-1]
        if v==v:candidates.append((float(v),f"EMA{p}"))
    rounded=round(price/5)*5
    for delta in range(-5,6):candidates.append((rounded+delta*5,"عدد رند"))
    groups=[]
    for value,source in sorted(candidates,key=lambda x:x[0]):
        match=next((g for g in groups if abs(g["price"]-value)<=tolerance),None)
        if match:match["values"].append(value);match["sources"].append(source);match["price"]=sum(match["values"])/len(match["values"])
        else:groups.append({"price":value,"values":[value],"sources":[source]})
    levels=[{"price":round(g["price"],2),"sources":sorted(set(g["sources"])),"count":len(set(g["sources"]))} for g in groups if len(set(g["sources"]))>=2]
    return {"support":sorted([x for x in levels if x["price"]<price],key=lambda x:price-x["price"])[:8],"resistance":sorted([x for x in levels if x["price"]>price],key=lambda x:x["price"]-price)[:8]}
