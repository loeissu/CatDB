package com.loeissu.catdb;

import android.content.res.Configuration;
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
                        CatDBStatusBar.applyForSystemTheme(MainActivity.this);
                    } catch (Throwable t) {
                        Log.w(TAG, "applyForSystemTheme failed: " + t);
                    }
                }
            });
        } catch (Throwable t) {
            Log.w(TAG, "decorView post failed: " + t);
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        // 回到前台：重放「用户最近一次主题」（未设置过则跟随系统），
        // 与 JS visibilitychange 的同步幂等互补，保证状态栏始终与页面一致。
        try {
            getWindow().getDecorView().post(new Runnable() {
                @Override
                public void run() {
                    try {
                        CatDBStatusBar.applyLastOrSystemTheme(MainActivity.this);
                    } catch (Throwable t) {
                        Log.w(TAG, "resume statusbar failed: " + t);
                    }
                }
            });
        } catch (Throwable t) {
            Log.w(TAG, "resume decor post failed: " + t);
        }
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // 系统深浅色切换（uiMode 已声明在 manifest configChanges，Activity 不重建）：
        // 稍后重放用户主题（或系统主题）。JS 的 matchMedia 若同步了则两者幂等一致。
        try {
            getWindow().getDecorView().postDelayed(new Runnable() {
                @Override
                public void run() {
                    try {
                        CatDBStatusBar.applyLastOrSystemTheme(MainActivity.this);
                    } catch (Throwable t) {
                        Log.w(TAG, "config statusbar failed: " + t);
                    }
                }
            }, 150);
        } catch (Throwable t) {
            Log.w(TAG, "config decor post failed: " + t);
        }
    }
}