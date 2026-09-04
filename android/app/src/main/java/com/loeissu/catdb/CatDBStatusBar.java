package com.loeissu.catdb;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.view.View;
import android.view.Window;

import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * 原生状态栏控制（绕开 @capacitor/status-bar 在 Android 15 上的兼容缺陷）。
 * 通过 WindowInsetsControllerCompat 直接控制状态栏/导航栏图标明暗与背景色，
 * 这是 Android 15 上唯一可靠的途径。
 */
@CapacitorPlugin(name = "CatDBStatusBar")
public class CatDBStatusBar extends Plugin {

    /** 浅色主题背景（与 www/index.html 浅色主题一致） */
    private static final int BG_LIGHT = 0xFFF9F5F0;
    /** 深色主题背景（与 www/index.html 深色主题一致） */
    private static final int BG_DARK = 0xFF14100D;

    @PluginMethod
    public void setTheme(PluginCall call) {
        Boolean dark = call.getBoolean("dark");
        if (dark == null) {
            call.reject("dark is required");
            return;
        }
        applyStatusBar(dark.booleanValue());
        call.resolve(new JSObject().put("ok", true));
    }

    /** 冷启动时按系统夜间模式设置一次状态栏（styles.xml 的兜底之外的保险） */
    public void applyForSystemTheme(Activity activity) {
        if (activity == null) {
            return;
        }
        int mode = activity.getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK;
        boolean dark = (mode == Configuration.UI_MODE_NIGHT_YES);
        applyStatusBar(dark);
    }

    private void applyStatusBar(boolean dark) {
        Activity activity = getActivity();
        if (activity == null || activity.isFinishing()) {
            return;
        }
        final Window window = activity.getWindow();
        final View decor = window.getDecorView();
        final int bg = dark ? BG_DARK : BG_LIGHT;

        // 图标明暗：浅色主题 -> 深色图标（light=true），深色主题 -> 浅色图标
        WindowInsetsControllerCompat controller =
                WindowCompat.getInsetsController(window, decor);
        if (controller != null) {
            controller.setAppearanceLightStatusBars(!dark);
            controller.setAppearanceLightNavigationBars(!dark);
        }
        // 背景色与页面主题保持一致
        window.setStatusBarColor(bg);
        window.setNavigationBarColor(bg);
    }
}