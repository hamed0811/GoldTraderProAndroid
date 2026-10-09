package com.goldtraderpro;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.text.InputType;
import android.util.Base64;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Toast;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.KeyStore;
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
import java.time.OffsetDateTime;

public class MainActivity extends Activity {
    private static final int DISCOVERY_PORT = 8766;
    private static final String DISCOVERY_MESSAGE = "GOLDTRADER_DISCOVER";
    private static final String CLOUD_BASE = "https://ai-cloud-workspace-api.onrender.com";
    private final OkHttpClient client = new OkHttpClient.Builder().retryOnConnectionFailure(true).build();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView health, price, signal, entry, sl, tp, reasons, protection, server;
    private Button aiSettingsButton;
    private static final String AI_PREFS = "goldtrader_ai_settings";
    private static final String AI_KEY_ALIAS = "GoldTraderProApiKeyV1";
    private String base = null;
    private boolean discovering = false;
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
        aiSettingsButton=findViewById(R.id.aiSettings);
        aiSettingsButton.setOnClickListener(v -> showAiSettings());
        base=CLOUD_BASE;
        server.setText("Server: Cloud "+base);
        createChannels();
        ui("● CONNECTING TO CLOUD...");
        schedulePoll(0);
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
                // Try global broadcast first, then the directed broadcast of
                // every IPv4 interface. This is more reliable on home routers.
                sendDiscovery(socket, InetAddress.getByName("255.255.255.255"), data);
                for(NetworkInterface ni : java.util.Collections.list(NetworkInterface.getNetworkInterfaces())){
                    if(!ni.isUp() || ni.isLoopback()) continue;
                    for(java.net.InterfaceAddress ia : ni.getInterfaceAddresses()){
                        java.net.InetAddress bc=ia.getBroadcast();
                        if(bc!=null) sendDiscovery(socket, bc, data);
                    }
                }

                long deadline=System.currentTimeMillis()+1800;
                while(base==null && System.currentTimeMillis()<deadline){
                    try{
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
                    }catch(java.net.SocketTimeoutException ignored){ break; }
                }
            } catch(Exception ignored) {
                // Broadcast/discovery can be blocked by the router or Windows firewall.
                // Always fall through to the direct subnet scan below.
            } finally {
                if(socket!=null) socket.close();
                discovering=false;
            }
            runOnUiThread(() -> {
                // UDP discovery may time out without throwing. In that case,
                // the old code skipped the subnet scan entirely. Always use the scan
                // as the deterministic LAN fallback.
                if(base==null) base=scanLocalSubnet();
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

    private void sendDiscovery(DatagramSocket socket, InetAddress address, byte[] data){
        try{
            DatagramPacket packet=new DatagramPacket(data,data.length,address,DISCOVERY_PORT);
            socket.send(packet);
        }catch(Exception ignored){}
    }

    private String scanLocalSubnet(){
        try{
            Enumeration<NetworkInterface> interfaces=NetworkInterface.getNetworkInterfaces();
            while(interfaces.hasMoreElements()){
                NetworkInterface ni=interfaces.nextElement();
                if(!ni.isUp() || ni.isLoopback()) continue;
                Enumeration<java.net.InetAddress> addrs=ni.getInetAddresses();
                while(addrs.hasMoreElements()){
                    java.net.InetAddress addr=addrs.nextElement();
                    if(!(addr instanceof Inet4Address) || addr.isLoopbackAddress()) continue;
                    String ip=addr.getHostAddress();
                    int dot=ip.lastIndexOf('.');
                    if(dot<0) continue;
                    String prefix=ip.substring(0,dot+1);

                    ExecutorService pool=Executors.newFixedThreadPool(32);
                    AtomicReference<String> found=new AtomicReference<>(null);
                    for(int i=1;i<=254;i++){
                        final String host=prefix+i;
                        pool.submit(() -> {
                            if(found.get()!=null) return;
                            HttpURLConnection conn=null;
                            try{
                                URL u=new URL("http://"+host+":8000/health");
                                conn=(HttpURLConnection)u.openConnection();
                                conn.setConnectTimeout(180);
                                conn.setReadTimeout(180);
                                conn.setRequestMethod("GET");
                                if(conn.getResponseCode()==200 && found.compareAndSet(null,"http://"+host+":8000")){
                                    // First valid GoldMind health endpoint wins.
                                }
                            }catch(Exception ignored){} finally{
                                if(conn!=null) conn.disconnect();
                            }
                        });
                    }
                    pool.shutdown();
                    long deadline=System.currentTimeMillis()+2500;
                    while(System.currentTimeMillis()<deadline && found.get()==null){
                        Thread.sleep(50);
                    }
                    pool.shutdownNow();
                    if(found.get()!=null) return found.get();
                }
            }
        }catch(Exception ignored){}
        return null;
    }

    private void schedulePoll(long delayMs){
        if(pollScheduled) return;
        pollScheduled=true;
        handler.postDelayed(() -> {
            pollScheduled=false;
            poll();
        }, delayMs);
    }

    private boolean isCloudBase(){
        return base!=null && base.startsWith(CLOUD_BASE);
    }

    private void poll(){
        if(base==null) base=CLOUD_BASE;
        Request request=new Request.Builder().url(base+"/api/state").build();
        client.newCall(request).enqueue(new Callback(){
            public void onFailure(Call call,java.io.IOException e){
                // Do not leave an old price or signal on screen as if it were live.
                set(price, "XAUUSD\nNO DATA");
                clearSignal("WAIT — اتصال قطع است؛ داده قبلی معتبر نیست");
                if(isCloudBase()){
                    ui("● CLOUD OFFLINE / RETRYING");
                    schedulePoll(5000);
                } else {
                    base=CLOUD_BASE;
                    server.setText("Server: Cloud "+base);
                    ui("● SWITCHING TO CLOUD");
                    schedulePoll(0);
                }
            }
            public void onResponse(Call call,Response response)throws java.io.IOException{
                try {
                    if(response.isSuccessful() && response.body()!=null) {
                        parse(response.body().string());
                        schedulePoll(5000);
                    } else if(isCloudBase()) {
                        set(price, "XAUUSD\nNO DATA");
                        clearSignal("WAIT — سرور پاسخ معتبر نداد");
                        ui("● CLOUD HTTP "+response.code()+" / RETRYING");
                        schedulePoll(5000);
                    } else {
                        base=CLOUD_BASE;
                        server.setText("Server: Cloud "+base);
                        ui("● LOCAL SERVER FAILED / SWITCHING TO CLOUD");
                        schedulePoll(0);
                    }
                } finally {
                    response.close();
                }
            }
        });
    }

    private static final long MAX_DATA_AGE_MS = 15_000L;
    private static final long MAX_FUTURE_SKEW_MS = 5_000L;

    private boolean isFreshLiveData(JSONObject o) {
        String status = o.optString("data_status", "");
        String timestamp = o.optString("updated_at_utc", "");
        if (!"LIVE".equalsIgnoreCase(status) || timestamp.isEmpty()) return false;
        try {
            long age = System.currentTimeMillis() - OffsetDateTime.parse(timestamp).toInstant().toEpochMilli();
            return age <= MAX_DATA_AGE_MS && age >= -MAX_FUTURE_SKEW_MS;
        } catch (Exception ignored) {
            return false;
        }
    }

    private void clearSignal(String message) {
        setSignal(message);
        set(entry, "ENTRY\n—");
        set(sl, "SL\n—");
        set(tp, "TP1\n—");
        set(reasons, "وضعیت\n" + message);
    }

    private void parse(String raw){
        try{
            JSONObject o=new JSONObject(raw);
            JSONObject s=o.optJSONObject("signal");
            String p=o.optString("price","");
            String source=o.optString("source","");
            String dataStatus=o.optString("data_status","");
            JSONObject pr=o.optJSONObject("protection");
            set(protection,"Smart Protection: "+(pr==null?"OFF":pr.optString("mode","OFF")));

            // Fail closed: a price without a fresh UTC timestamp is never labelled LIVE.
            if (!isFreshLiveData(o) || p.isEmpty()) {
                set(price, "XAUUSD\nNO DATA");
                ui("● " + (dataStatus.isEmpty() ? "NO DATA" : dataStatus) + " / STALE OR UNVERIFIED");
                clearSignal("WAIT — داده تازه و معتبر در دسترس نیست؛ معامله نکنید");
                return;
            }

            set(price, "XAUUSD\n" + p);
            ui("● LIVE  " + p + (source.isEmpty() ? "" : "  |  " + source));
            if(s==null){
                clearSignal("WAIT — قیمت دریافت شد؛ سیگنال معتبر موجود نیست");
                return;
            }
            String state=s.optString("state","WAIT");
            setSignal(state+"  |  "+s.optString("side","—"));
            set(entry,"ENTRY\n"+s.optString("entry","—"));
            set(sl,"SL\n"+s.optString("sl","—"));
            set(tp,"TP1\n"+s.optString("tp1","—"));
            set(reasons,"دلایل سیگنال\n"+s.optString("reasons","—"));
        }catch(Exception e){
            set(price, "XAUUSD\nNO DATA");
            clearSignal("WAIT — پاسخ سرور قابل‌اعتماد نیست");
            ui("● BAD DATA");
        }
    }


    // API configuration is prepared for a future server-side provider connection.
    // The app does not send this key anywhere in this version.
    private void showAiSettings() {
        SharedPreferences prefs = getSharedPreferences(AI_PREFS, MODE_PRIVATE);
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        int pad = (int)(16 * getResources().getDisplayMetrics().density);
        form.setPadding(pad, pad / 2, pad, 0);

        EditText provider = field("ارائه‌دهنده (مثلاً OpenAI، Gemini یا سازگار با OpenAI)");
        provider.setText(prefs.getString("provider", ""));
        form.addView(provider);

        EditText endpoint = field("آدرس API / Base URL");
        endpoint.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        endpoint.setText(prefs.getString("endpoint", ""));
        form.addView(endpoint);

        EditText model = field("نام مدل");
        model.setText(prefs.getString("model", ""));
        form.addView(model);

        EditText apiKey = field("API Key");
        apiKey.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        try {
            String encrypted = prefs.getString("api_key_enc", "");
            if (!encrypted.isEmpty()) apiKey.setText(decryptApiKey(encrypted));
        } catch (Exception e) {
            Toast.makeText(this, "کلید ذخیره‌شده قابل خواندن نیست؛ لطفاً دوباره وارد کنید", Toast.LENGTH_LONG).show();
        }
        form.addView(apiKey);

        new AlertDialog.Builder(this)
            .setTitle("تنظیمات اتصال هوش مصنوعی")
            .setMessage("این بخش برای اتصال آینده آماده شده است. در نسخه فعلی، تنظیمات فقط ذخیره می‌شوند و API فراخوانی نمی‌شود.")
            .setView(form)
            .setPositiveButton("ذخیره", (dialog, which) -> {
                try {
                    SharedPreferences.Editor edit = prefs.edit()
                        .putString("provider", provider.getText().toString().trim())
                        .putString("endpoint", endpoint.getText().toString().trim())
                        .putString("model", model.getText().toString().trim());
                    String key = apiKey.getText().toString();
                    if (!key.isEmpty()) edit.putString("api_key_enc", encryptApiKey(key));
                    edit.apply();
                    Toast.makeText(this, "تنظیمات روی همین دستگاه ذخیره شد؛ اتصال هنوز فعال نیست", Toast.LENGTH_LONG).show();
                } catch (Exception e) {
                    Toast.makeText(this, "ذخیره امن API Key انجام نشد", Toast.LENGTH_LONG).show();
                }
            })
            .setNegativeButton("انصراف", null)
            .setNeutralButton("پاک‌کردن API Key", (dialog, which) -> {
                prefs.edit().remove("api_key_enc").apply();
                Toast.makeText(this, "API Key ذخیره‌شده پاک شد", Toast.LENGTH_SHORT).show();
            })
            .show();
    }

    private EditText field(String hint) {
        EditText edit = new EditText(this);
        edit.setSingleLine(true);
        edit.setHint(hint);
        edit.setTextSize(14);
        return edit;
    }

    private SecretKey getApiEncryptionKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        java.security.Key existing = keyStore.getKey(AI_KEY_ALIAS, null);
        if (existing instanceof SecretKey) return (SecretKey) existing;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(AI_KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true)
            .build());
        return generator.generateKey();
    }

    private String encryptApiKey(String plainText) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getApiEncryptionKey());
        byte[] encrypted = cipher.doFinal(plainText.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] combined = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, combined, 0, iv.length);
        System.arraycopy(encrypted, 0, combined, iv.length, encrypted.length);
        return Base64.encodeToString(combined, Base64.NO_WRAP);
    }

    private String decryptApiKey(String encoded) throws Exception {
        byte[] combined = Base64.decode(encoded, Base64.NO_WRAP);
        if (combined.length <= 12) throw new IllegalArgumentException("Invalid encrypted API key");
        byte[] iv = java.util.Arrays.copyOfRange(combined, 0, 12);
        byte[] encrypted = java.util.Arrays.copyOfRange(combined, 12, combined.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, getApiEncryptionKey(), new GCMParameterSpec(128, iv));
        return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
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
