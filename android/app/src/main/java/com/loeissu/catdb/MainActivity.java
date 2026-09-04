package com.loeissu.catdb;

import android.os.Bundle;
import android.util.Log;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "CatDBMain";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // 必须在 bridge 创建前注册（Capacitor 6：registerPlugin 加入 bridgeBuilder，super 后统一创建）
        registerPlugin(CatDBStatusBar.class);
        super.onCreate(savedInstanceState);
        // 冷启动：等窗口就绪后按系统夜间模式用原生 API 设置状态栏。
        // 整段 try/catch 兜底——任何机型异常都不允许影响 Activity 启动。
        try {
            getWindow().getDecorView().post(new Runnable() {
                @Override
                public void run() {
                    try {
                        new CatDBStatusBar().applyForSystemTheme(MainActivity.this);
                    } catch (Throwable t) {
                        Log.w(TAG, "applyForSystemTheme failed: " + t);
                    }
                }
            });
        } catch (Throwable t) {
            Log.w(TAG, "decorView post failed: " + t);
        }
    }
}