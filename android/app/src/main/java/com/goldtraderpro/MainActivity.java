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
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_MESSAGE = "GOLDTRADER_DISCOVER";
    private final OkHttpClient client = new OkHttpClient.Builder().retryOnConnectionFailure(true).build();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView health, price, signal, entry, sl, tp, reasons, protection, server;
    private String base = null;
    private boolean discovering = false;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_main);
        health=findViewById(R.id.health);
        price=findViewById(R.id.price);
        signal=findViewById(R.id.signal);
        entry=findViewById(R.id.entry);
        sl=findViewById(R.id.sl);
        tp=findViewById(R.id.tp);
        reasons=findViewById(R.id.reasons);
        protection=findViewById(R.id.protection);
        server=findViewById(R.id.server);
        server.setText("Server: در حال جستجوی سرور...");
        createChannels();
        discoverServer();
    }

    private void createChannels(){
        NotificationManager nm=getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("gold_entry","GoldTrader Entry",NotificationManager.IMPORTANCE_HIGH));
        nm.createNotificationChannel(new NotificationChannel("gold_watch","GoldTrader Watch",NotificationManager.IMPORTANCE_DEFAULT));
    }

    private void discoverServer(){
        if(discovering) return;
        discovering=true;
        ui("● در حال جستجوی سرور...");
        new Thread(() -> {
            DatagramSocket socket=null;
            try {
                socket=new DatagramSocket();
                socket.setBroadcast(true);
                socket.setSoTimeout(1200);
                byte[] data=DISCOVERY_MESSAGE.getBytes(StandardCharsets.UTF_8);
                DatagramPacket request=new DatagramPacket(
                    data, data.length,
                    InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT);
                socket.send(request);

                byte[] buffer=new byte[256];
                DatagramPacket response=new DatagramPacket(buffer, buffer.length);
                socket.receive(response);
                String answer=new String(response.getData(), response.getOffset(), response.getLength(), StandardCharsets.UTF_8).trim();
                if(answer.startsWith("GOLDTRADER_SERVER|")){
                    String[] p=answer.split("\\|");
                    if(p.length>=2){
                        String host=p[1];
                        int port=p.length>=3 ? Integer.parseInt(p[2]) : 8000;
                        base="http://"+host+":"+port;
                    }
                }
            } catch(Exception ignored) {
                // Discovery may be blocked by the Wi-Fi/router. Polling will retry discovery.
            } finally {
                if(socket!=null) socket.close();
                discovering=false;
            }
            runOnUiThread(() -> {
                if(base!=null){
                    server.setText("Server: "+base);
                    ui("● CONNECTED");
                    poll();
                } else {
                    ui("● SERVER NOT FOUND");
                    server.setText("Server: سرور GoldMind پیدا نشد");
                    handler.postDelayed(this::discoverServer, 5000);
                }
            });
        }).start();
    }

    private void poll(){
        if(base==null) return;
        Request r=new Request.Builder().url(base+"/api/state").build();
        client.newCall(r).enqueue(new Callback(){
            public void onFailure(Call c,java.io.IOException e){
                ui("● NO DATA / SERVER");
                handler.postDelayed(MainActivity.this::discoverServer,3000);
            }
            public void onResponse(Call c,Response r)throws java.io.IOException{
                try {
                    if(r.isSuccessful() && r.body()!=null) {
                        parse(r.body().string());
                    } else {
                        ui("● NO DATA / SERVER");
                    }
                } finally {
                    r.close();
                }
            }
        });
        handler.postDelayed(this::poll,5000);
    }

    private void parse(String raw){
        try{
            JSONObject o=new JSONObject(raw);
            JSONObject s=o.optJSONObject("signal");
            String p=o.optString("price","");
            ui(p.isEmpty()?"● WAITING FOR MT5":("● LIVE  "+p));
            if(s==null){
                setSignal("WAIT — منتظر داده MT5");
                return;
            }
            String state=s.optString("state","WAIT");
            setSignal(state+"  |  "+s.optString("side","—"));
            set(entry,"ENTRY\n"+s.optString("entry","—"));
            set(sl,"SL\n"+s.optString("sl","—"));
            set(tp,"TP1\n"+s.optString("tp1","—"));
            set(reasons,"دلایل سیگنال\n"+s.optString("reasons","—"));
            JSONObject pr=o.optJSONObject("protection");
            set(protection,"Smart Protection: "+(pr==null?"OFF":pr.optString("mode","OFF")));
        }catch(Exception e){
            ui("● BAD DATA");
        }
    }

    private void set(TextView v,String s){runOnUiThread(()->v.setText(s));}
    private void ui(String s){runOnUiThread(()->health.setText(s));}
    private void setSignal(String s){runOnUiThread(()->signal.setText(s);}

    @Override protected void onDestroy(){
        handler.removeCallbacksAndMessages(null);
        client.dispatcher().executorService().shutdown();
        super.onDestroy();
    }
}
