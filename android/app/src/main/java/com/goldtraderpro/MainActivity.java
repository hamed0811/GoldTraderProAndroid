package com.goldtraderpro;

import android.app.Activity;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.TextView;
import okhttp3.*;
import org.json.*;

public class MainActivity extends Activity {
    private static final String BASE = "http://SERVER_IP:8765";
    private static final String WS = "ws://SERVER_IP:8765/ws";
    private final OkHttpClient client = new OkHttpClient.Builder().retryOnConnectionFailure(true).build();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView health, price, signal, entry, sl, tp, reasons, protection, server;
    private WebSocket socket;
    @Override public void onCreate(Bundle b) { super.onCreate(b); setContentView(R.layout.activity_main);
        health=findViewById(R.id.health); price=findViewById(R.id.price); signal=findViewById(R.id.signal); entry=findViewById(R.id.entry); sl=findViewById(R.id.sl); tp=findViewById(R.id.tp); reasons=findViewById(R.id.reasons); protection=findViewById(R.id.protection); server=findViewById(R.id.server);
        server.setText("Server: "+BASE); createChannels(); connectWebSocket(); poll();
    }
    private void createChannels(){ NotificationManager nm=getSystemService(NotificationManager.class); nm.createNotificationChannel(new NotificationChannel("gold_entry","GoldTrader Entry",NotificationManager.IMPORTANCE_HIGH)); nm.createNotificationChannel(new NotificationChannel("gold_watch","GoldTrader Watch",NotificationManager.IMPORTANCE_DEFAULT)); }
    private void connectWebSocket(){ Request r=new Request.Builder().url(WS).build(); socket=client.newWebSocket(r,new WebSocketListener(){ public void onOpen(WebSocket w,Response r){ ui("● CONNECTED"); } public void onMessage(WebSocket w,String s){ parse(s); } public void onFailure(WebSocket w,Throwable t,Response r){ ui("● NO DATA / WAIT"); handler.postDelayed(()->connectWebSocket(),5000); }}); }
    private void poll(){ Request r=new Request.Builder().url(BASE+"/api/state").build(); client.newCall(r).enqueue(new Callback(){ public void onFailure(Call c,java.io.IOException e){ui("● NO DATA / WAIT");} public void onResponse(Call c,Response r)throws java.io.IOException{ if(r.isSuccessful()) parse(r.body().string()); else ui("● NO DATA / WAIT"); }}); handler.postDelayed(this::poll,5000); }
    private void parse(String raw){ try{ JSONObject o=new JSONObject(raw); JSONObject s=o.optJSONObject("signal"); String p=o.optString("price",o.optString("xauusd_price","")); ui(p.isEmpty()?"NO DATA":p); if(s==null){ setSignal("WAIT — منتظر داده معتبر"); return; } String state=s.optString("state","WAIT"); setSignal(state+"  |  "+s.optString("side","—")); set(entry,"ENTRY\n"+s.optString("entry","—")); set(sl,"SL\n"+s.optString("sl","—")); set(tp,"TP1\n"+s.optString("tp1","—")); set(reasons,"دلایل سیگنال\n"+s.optString("reasons","—")); JSONObject pr=o.optJSONObject("protection"); set(protection,"Smart Protection: "+(pr==null?"OFF":pr.optString("mode","OFF"))); }catch(Exception e){ ui("NO DATA"); } }
    private void set(TextView v,String s){runOnUiThread(()->v.setText(s));} private void ui(String s){runOnUiThread(()->health.setText(s));} private void setSignal(String s){runOnUiThread(()->signal.setText(s));}
    @Override protected void onDestroy(){ if(socket!=null)socket.close(1000,"closed"); handler.removeCallbacksAndMessages(null); client.dispatcher().executorService().shutdown(); super.onDestroy(); }
}
