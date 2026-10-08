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
import java.net.Inet4Address;
import java.net.NetworkInterface;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Enumeration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_MESSAGE = "GOLDTRADER_DISCOVER";
    private final OkHttpClient client = new OkHttpClient.Builder().retryOnConnectionFailure(true).build();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView health, price, signal, entry, sl, tp, reasons, protection, server;
    private volatile String base = null;
    private volatile boolean discovering = false;
    private boolean pollScheduled = false;

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
        base=null;
        ui("● در حال جستجوی سرور...");
        new Thread(() -> {
            String found = discoverByUdp();
            if(found == null) found = scanLocalSubnets();
            final String result = found;
            runOnUiThread(() -> {
                discovering=false;
                if(result!=null){
                    base=result;
                    server.setText("Server: "+base);
                    ui("● CONNECTED");
                    schedulePoll(0);
                } else {
                    ui("● SERVER NOT FOUND");
                    server.setText("Server: سرور GoldMind پیدا نشد");
                    handler.postDelayed(this::discoverServer, 5000);
                }
            });
        }, "goldtrader-discovery").start();
    }

    private String discoverByUdp(){
        DatagramSocket socket=null;
        try {
            socket=new DatagramSocket();
            socket.setBroadcast(true);
            socket.setSoTimeout(450);
            byte[] data=DISCOVERY_MESSAGE.getBytes(StandardCharsets.UTF_8);

            sendDiscovery(socket, InetAddress.getByName("255.255.255.255"), data);
            for(NetworkInterface ni : java.util.Collections.list(NetworkInterface.getNetworkInterfaces())){
                if(!ni.isUp() || ni.isLoopback()) continue;
                for(java.net.InterfaceAddress ia : ni.getInterfaceAddresses()){
                    InetAddress bc=ia.getBroadcast();
                    if(bc!=null) sendDiscovery(socket, bc, data);
                }
            }

            long deadline=System.currentTimeMillis()+1800;
            while(System.currentTimeMillis()<deadline){
                try{
                    byte[] buffer=new byte[256];
                    DatagramPacket response=new DatagramPacket(buffer, buffer.length);
                    socket.receive(response);
                    String answer=new String(response.getData(), response.getOffset(), response.getLength(), StandardCharsets.UTF_8).trim();
                    if(answer.startsWith("GOLDTRADER_SERVER|")){
                        String[] p=answer.split("\\|");
                        if(p.length>=2){
                            String host=p[1].trim();
                            int port=p.length>=3 ? Integer.parseInt(p[2].trim()) : 8000;
                            String candidate="http://"+host+":"+port;
                            if(isHealthy(candidate)) return candidate;
                        }
                    }
                }catch(java.net.SocketTimeoutException ignored){}
                catch(Exception ignored){}
            }
        }catch(Exception ignored){} finally {
            if(socket!=null) socket.close();
        }
        return null;
    }

    private void sendDiscovery(DatagramSocket socket, InetAddress address, byte[] data){
        try{
            socket.send(new DatagramPacket(data,data.length,address,DISCOVERY_PORT));
        }catch(Exception ignored){}
    }

    /*
     * Uses the actual IPv4 prefix advertised by Android instead of assuming
     * every LAN is a /24. This fixes discovery on routers/VLANs using another
     * subnet size while keeping the probe bounded.
     */
    private String scanLocalSubnets(){
        try{
            for(NetworkInterface ni : java.util.Collections.list(NetworkInterface.getNetworkInterfaces())){
                if(!ni.isUp() || ni.isLoopback()) continue;
                for(java.net.InterfaceAddress ia : ni.getInterfaceAddresses()){
                    InetAddress addr=ia.getAddress();
                    if(!(addr instanceof Inet4Address) || addr.isLoopbackAddress()) continue;
                    int prefix=ia.getNetworkPrefixLength();
                    if(prefix<16 || prefix>30) continue;

                    byte[] raw=addr.getAddress();
                    int ip=((raw[0]&255)<<24)|((raw[1]&255)<<16)|((raw[2]&255)<<8)|(raw[3]&255);
                    int mask=prefix==0 ? 0 : (int)(0xFFFFFFFFL << (32-prefix));
                    int network=ip & mask;
                    long hosts=(1L << (32-prefix))-2;
                    if(hosts<=0) continue;

                    // Full scan only for reasonably sized LANs. For larger
                    // networks probe the /24 containing the phone first.
                    int start, end;
                    if(hosts<=1022){
                        start=network+1; end=network+(int)hosts;
                    }else{
                        int localStart=ip & 0xFFFFFF00;
                        start=localStart+1; end=localStart+254;
                    }

                    String found=probeRange(start,end);
                    if(found!=null) return found;
                }
            }
        }catch(Exception ignored){}
        return null;
    }

    private String probeRange(int start, int end){
        ExecutorService pool=Executors.newFixedThreadPool(32);
        AtomicReference<String> found=new AtomicReference<>(null);
        for(int n=start;n<=end;n++){
            final String host=((n>>>24)&255)+"."+((n>>>16)&255)+"."+((n>>>8)&255)+"."+(n&255);
            pool.submit(() -> {
                if(found.get()!=null) return;
                HttpURLConnection conn=null;
                try{
                    URL u=new URL("http://"+host+":8000/health");
                    conn=(HttpURLConnection)u.openConnection();
                    conn.setConnectTimeout(250);
                    conn.setReadTimeout(350);
                    conn.setUseCaches(false);
                    conn.setRequestMethod("GET");
                    if(conn.getResponseCode()==200 && found.compareAndSet(null,"http://"+host+":8000")){
                        // Found the GoldMind health endpoint.
                    }
                }catch(Exception ignored){} finally {
                    if(conn!=null) conn.disconnect();
                }
            });
        }
        pool.shutdown();
        long deadline=System.currentTimeMillis()+5000;
        while(System.currentTimeMillis()<deadline && found.get()==null){
            try{ Thread.sleep(50); }catch(InterruptedException e){ Thread.currentThread().interrupt(); break; }
        }
        pool.shutdownNow();
        return found.get();
    }

    private boolean isHealthy(String candidate){
        HttpURLConnection conn=null;
        try{
            URL u=new URL(candidate+"/health");
            conn=(HttpURLConnection)u.openConnection();
            conn.setConnectTimeout(800);
            conn.setReadTimeout(1000);
            conn.setUseCaches(false);
            return conn.getResponseCode()==200;
        }catch(Exception ignored){
            return false;
        }finally{
            if(conn!=null) conn.disconnect();
        }
    }

    private void schedulePoll(long delayMs){
        if(pollScheduled) return;
        pollScheduled=true;
        handler.postDelayed(() -> {
            pollScheduled=false;
            poll();
        }, delayMs);
    }

    private void poll(){
        if(base==null){
            discoverServer();
            return;
        }
        Request r=new Request.Builder().url(base+"/api/state").build();
        client.newCall(r).enqueue(new Callback(){
            public void onFailure(Call c,java.io.IOException e){
                ui("● NO DATA / SERVER");
                base=null;
                schedulePoll(3000);
                handler.postDelayed(MainActivity.this::discoverServer,3000);
            }
            public void onResponse(Call c,Response r)throws java.io.IOException{
                try {
                    if(r.isSuccessful() && r.body()!=null) {
                        parse(r.body().string());
                        schedulePoll(5000);
                    } else {
                        base=null;
                        ui("● NO DATA / SERVER");
                        handler.postDelayed(MainActivity.this::discoverServer,1000);
                    }
                } finally {
                    r.close();
                }
            }
        });
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
    private void setSignal(String s){runOnUiThread(()->signal.setText(s));}

    @Override protected void onDestroy(){
        handler.removeCallbacksAndMessages(null);
        client.dispatcher().executorService().shutdown();
        super.onDestroy();
    }
}
