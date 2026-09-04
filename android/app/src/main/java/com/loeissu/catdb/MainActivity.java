package com.loeissu.catdb;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(CatDBStatusBar.class);
        super.onCreate(savedInstanceState);
        // 冷启动：styles.xml 双主题兜底之外，再按系统夜间模式用原生 API 设置一次状态栏
        getWindow().getDecorView().post(new Runnable() {
            @Override
            public void run() {
                new CatDBStatusBar().applyForSystemTheme(MainActivity.this);
            }
        });
    }
}