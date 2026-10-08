#property strict
#property version   "2.0"
#property description "GoldMind AI - SIGNAL ONLY. Reads MT5 market data and requests analysis; never sends, modifies, or deletes trades."

input string InpBackendURL      = "http://127.0.0.1:8000/signal";
input ENUM_TIMEFRAMES InpPrimaryTF = PERIOD_M5;
input int    InpCandleCount     = 120;
input int    InpRefreshSeconds  = 60;
input int    InpRequestCooldown = 60;
input int    InpTimeoutMs       = 15000;
input int    InpMaxSpreadPoints = 50;
input double InpMinRR           = 1.5;
input int    InpExpiryMinutes   = 10;
input bool   InpRequireNewBar   = true;

datetime g_last_bar = 0;
datetime g_last_request = 0;

string TfName(ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      default:         return EnumToString(tf);
   }
}

string JsonNumber(double v,int digits)
{
   return DoubleToString(v,digits);
}

string JsonEscape(string s)
{
   StringReplace(s,"\\","\\\\");
   StringReplace(s,"\\\"","\\\\\\\"");
   StringReplace(s,"\r","");
   StringReplace(s,"\n"," ");
   return s;
}

string BuildCandlesJson(ENUM_TIMEFRAMES tf)
{
   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   int n=CopyRates(_Symbol,tf,0,InpCandleCount,rates);
   if(n<=0) return "[]";

   string out="[";
   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   for(int i=n-1;i>=0;i--)
   {
      if(StringLen(out)>1) out+=",";
      out+="{";
      out+="\"time\":\""+TimeToString(rates[i].time,TIME_DATE|TIME_SECONDS)+"Z\",";
      out+="\"open\":"+JsonNumber(rates[i].open,digits)+",";
      out+="\"high\":"+JsonNumber(rates[i].high,digits)+",";
      out+="\"low\":"+JsonNumber(rates[i].low,digits)+",";
      out+="\"close\":"+JsonNumber(rates[i].close,digits)+",";
      out+="\"volume\":"+IntegerToString((long)rates[i].tick_volume);
      out+="}";
   }
   out+="]";
   return out;
}

double CalculateATR(ENUM_TIMEFRAMES tf,int period=14)
{
   MqlRates r[];
   ArraySetAsSeries(r,true);
   int n=CopyRates(_Symbol,tf,0,period+1,r);
   if(n<2) return 0.0;
   double sum=0.0;
   int used=0;
   for(int i=n-1;i>0;i--)
   {
      double tr=MathMax(r[i-1].high-r[i-1].low,
               MathMax(MathAbs(r[i-1].high-r[i].close),
                       MathAbs(r[i-1].low-r[i].close)));
      sum+=tr;
      used++;
   }
   return used>0 ? sum/used : 0.0;
}

string BuildRequest()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return "";

   int digits=(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS);
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   int spread=(int)MathRound((tick.ask-tick.bid)/point);

   string j="{";
   j+="\"account_id\":\"signal-only\",";
   j+="\"symbol\":\""+JsonEscape(_Symbol)+"\",";
   j+="\"timeframe\":\""+TfName(InpPrimaryTF)+"\",";
   j+="\"server_time_utc\":\""+TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS)+"Z\",";
   j+="\"bid\":"+JsonNumber(tick.bid,digits)+",";
   j+="\"ask\":"+JsonNumber(tick.ask,digits)+",";
   j+="\"spread_points\":"+IntegerToString(spread)+",";
   j+="\"digits\":"+IntegerToString(digits)+",";
   j+="\"point\":"+DoubleToString(point,8)+",";
   j+="\"candles\":{";
   j+="\"M1\":"+BuildCandlesJson(PERIOD_M1)+",";
   j+="\"M5\":"+BuildCandlesJson(PERIOD_M5)+",";
   j+="\"M15\":"+BuildCandlesJson(PERIOD_M15)+",";
   j+="\"M30\":"+BuildCandlesJson(PERIOD_M30)+",";
   j+="\"H1\":"+BuildCandlesJson(PERIOD_H1)+",";
   j+="\"H4\":"+BuildCandlesJson(PERIOD_H4);
   j+="},";
   j+="\"atr\":"+DoubleToString(CalculateATR(InpPrimaryTF),8)+",";
   j+="\"constraints\":{";
   j+="\"max_spread_points\":"+IntegerToString(InpMaxSpreadPoints)+",";
   j+="\"risk_percent\":0.0,";
   j+="\"min_rr\":"+DoubleToString(InpMinRR,2)+",";
   j+="\"expiry_minutes\":"+IntegerToString(InpExpiryMinutes);
   j+="}}";
   return j;
}

string JsonStringValue(string json,string key)
{
   string needle="\""+key+"\":\"";
   int p=StringFind(json,needle);
   if(p<0) return "";
   p+=StringLen(needle);
   int e=StringFind(json,"\"",p);
   if(e<0) return "";
   return StringSubstr(json,p,e-p);
}

double JsonNumberValue(string json,string key)
{
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return 0.0;
   p+=StringLen(needle);
   int e=p;
   int len=StringLen(json);
   while(e<len)
   {
      ushort c=StringGetCharacter(json,e);
      if((c>='0' && c<='9') || c=='-' || c=='+' || c=='.' || c=='e' || c=='E') e++;
      else break;
   }
   return StringToDouble(StringSubstr(json,p,e-p));
}

bool JsonBoolValue(string json,string key)
{
   string needle="\""+key+"\":";
   int p=StringFind(json,needle);
   if(p<0) return false;
   p+=StringLen(needle);
   return StringSubstr(json,p,4)=="true";
}

void PrintSignal(string body)
{
   string symbol=JsonStringValue(body,"symbol");
   string bias=JsonStringValue(body,"bias");
   string type=JsonStringValue(body,"type");
   string comment=JsonStringValue(body,"comment");
   double confidence=JsonNumberValue(body,"confidence");
   double entry=JsonNumberValue(body,"entry");
   double sl=JsonNumberValue(body,"sl");
   double tp=JsonNumberValue(body,"tp");
   bool veto=JsonBoolValue(body,"veto");
   string reason=JsonStringValue(body,"veto_reason");

   Print("========== GOLDMIND SIGNAL ONLY ==========");
   Print("Symbol: ",symbol," | Bias: ",bias," | Confidence: ",DoubleToString(confidence*100.0,1),"%");
   if(veto || type=="none")
      Print("SIGNAL: WAIT | Reason: ",reason);
   else
   {
      string signal_type=type;\n      StringToUpper(signal_type);\n      Print("SIGNAL: ",signal_type);
      Print("Entry: ",DoubleToString(entry,(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS)),
            " | SL: ",DoubleToString(sl,(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS)),
            " | TP: ",DoubleToString(tp,(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS)));
      Print("Comment: ",comment);
   }
   Print("==========================================");
}

bool RequestSignal()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) { Print("NO DATA: SymbolInfoTick failed"); return false; }

   int spread=(int)MathRound((tick.ask-tick.bid)/SymbolInfoDouble(_Symbol,SYMBOL_POINT));
   if(spread>InpMaxSpreadPoints)
   {
      Print("WAIT: spread ",spread," > max ",InpMaxSpreadPoints);
      return false;
   }

   string payload=BuildRequest();
   if(payload=="") { Print("NO DATA: request payload unavailable"); return false; }

   char data[];
   int bytes=StringToCharArray(payload,data,0,WHOLE_ARRAY,CP_UTF8);
   if(bytes<=0) { Print("NO DATA: UTF-8 encoding failed"); return false; }
   ArrayResize(data,bytes-1);

   char result[];
   string response_headers="";
   string headers="Content-Type: application/json\r\n";
   ResetLastError();
   int status=WebRequest("POST",InpBackendURL,headers,InpTimeoutMs,data,result,response_headers);
   int err=GetLastError();
   if(status<200 || status>=300)
   {
      Print("NO DATA: backend HTTP=",status," error=",err);
      return false;
   }

   string body=CharArrayToString(result,0,-1,CP_UTF8);
   if(StringLen(body)<20)
   {
      Print("NO DATA: empty/invalid backend response");
      return false;
   }
   PrintSignal(body);
   return true;
}

int OnInit()
{
   EventSetTimer(MathMax(10,InpRefreshSeconds));
   Print("GoldMind AI SIGNAL-ONLY initialized.");
   Print("NO order execution is compiled into this EA.");
   Print("Backend: ",InpBackendURL);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   datetime bar=iTime(_Symbol,InpPrimaryTF,0);
   if(bar<=0) { Print("NO DATA: no primary timeframe bar"); return; }

   bool newbar=(bar!=g_last_bar);
   if(InpRequireNewBar && !newbar) return;
   if((TimeCurrent()-g_last_request)<InpRequestCooldown) return;

   g_last_bar=bar;
   g_last_request=TimeCurrent();
   RequestSignal();
}
