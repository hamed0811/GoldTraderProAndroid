"""نمای تجمیعی موتورهای تحلیل."""
from .confluence_engine import analyze as analyze_confluence
from .smc import analyze_smc
from .lct_strategy import analyze_lct
from .whale_tracker import analyze_volume
from .level_finder import find_levels
def analyze_market(df_m5,df_m15=None,df_h1=None,price=None):
    base=analyze_confluence(df_m5,df_m15,df_h1)
    if df_m5 is None or len(df_m5)<30:return base
    base["smc"]=analyze_smc(df_m5);base["lct"]=analyze_lct(df_m15 if df_m15 is not None and len(df_m15)>0 else df_m5)
    base["volume_proxy"]=analyze_volume(df_m5);base["levels"]=find_levels(df_m5,price)
    return base
