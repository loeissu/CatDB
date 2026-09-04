package com.loeissu.catdb;

import android.app.Activity;
import android.content.res.Configuration;
import android.util.Log;
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
 *
 * 注意：所有对外入口均 try/catch 兜底——状态栏设置属于"锦上添花"，
 * 任何机型/系统版本上的异常都绝不允许导致 App 崩溃（只记日志降级）。
 */
@CapacitorPlugin(name = "CatDBStatusBar")
public class CatDBStatusBar extends Plugin {

    private static final String TAG = "CatDBStatusBar";

    /** 浅色主题背景（与 www/index.html 浅色主题一致） */
    private static final int BG_LIGHT = 0xFFF9F5F0;
    /** 深色主题背景（与 www/index.html 深色主题一致） */
    private static final int BG_DARK = 0xFF14100D;

    @PluginMethod
    public void setTheme(PluginCall call) {
        try {
            Boolean dark = call.getBoolean("dark");
            if (dark == null) {
                call.reject("dark is required");
                return;
            }
            applyStatusBar(getActivity(), dark.booleanValue());
            call.resolve(new JSObject().put("ok", true));
        } catch (Throwable t) {
            // 状态栏设置失败不影响 App 运行
            Log.w(TAG, "setTheme failed: " + t);
            try {
                call.reject("apply failed: " + t);
            } catch (Throwable ignored) {
            }
        }
    }

    /** 冷启动时按系统夜间模式设置一次状态栏（styles.xml 的兜底之外的保险） */
    public void applyForSystemTheme(Activity activity) {
        try {
            if (activity == null) {
                return;
            }
            int mode = activity.getResources().getConfiguration().uiMode
                    & Configuration.UI_MODE_NIGHT_MASK;
            boolean dark = (mode == Configuration.UI_MODE_NIGHT_YES);
            // 直接使用传入的 activity（此时 bridge 可能尚未就绪，getActivity() 会返回 null）
            applyStatusBar(activity, dark);
        } catch (Throwable t) {
            Log.w(TAG, "applyForSystemTheme failed: " + t);
        }
    }

    private void applyStatusBar(Activity activity, boolean dark) {
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