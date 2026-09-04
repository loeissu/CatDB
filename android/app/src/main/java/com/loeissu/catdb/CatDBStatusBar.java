package com.loeissu.catdb;

import android.app.Activity;
import android.content.res.Configuration;
import android.os.Looper;
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
 * 即时生效策略（切换主题无需重启）：
 * - JS 每次 applyTheme 都会调用本插件 setTheme（首选），并同步兜底官方 StatusBar；
 * - lastDark 记录「用户当前实际生效的主题」，MainActivity 在 onResume /
 *   onConfigurationChanged 时重放该值（或系统主题），保证回到前台/系统切换后状态栏
 *   始终与页面一致；
 * - 所有对外入口均 try/catch 兜底、强制主线程、窗口未附加时自动重试——任何机型/
 *   系统版本上的异常都绝不允许导致 App 崩溃（只记日志降级）。
 */
@CapacitorPlugin(name = "CatDBStatusBar")
public class CatDBStatusBar extends Plugin {

    private static final String TAG = "CatDBStatusBar";

    /** 浅色主题背景（与 www/index.html 浅色主题一致） */
    private static final int BG_LIGHT = 0xFFF9F5F0;
    /** 深色主题背景（与 www/index.html 深色主题一致） */
    private static final int BG_DARK = 0xFF14100D;

    /** JS 最近一次显式设置的主题（null=尚未设置，按系统主题处理） */
    private static volatile Boolean lastDark = null;

    @PluginMethod
    public void setTheme(PluginCall call) {
        try {
            Boolean dark = call.getBoolean("dark");
            if (dark == null) {
                call.reject("dark is required");
                return;
            }
            lastDark = dark.booleanValue();
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
    public static void applyForSystemTheme(Activity activity) {
        try {
            if (activity == null) {
                return;
            }
            int mode = activity.getResources().getConfiguration().uiMode
                    & Configuration.UI_MODE_NIGHT_MASK;
            boolean dark = (mode == Configuration.UI_MODE_NIGHT_YES);
            applyStatusBar(activity, dark);
        } catch (Throwable t) {
            Log.w(TAG, "applyForSystemTheme failed: " + t);
        }
    }

    /**
     * 重放「最近一次用户主题」；尚未设置过则跟随系统主题。
     * 由 MainActivity.onResume / onConfigurationChanged 调用，保证回到前台或
     * 系统深浅色切换后状态栏仍与页面主题一致（与 JS visibilitychange 幂等互补）。
     */
    public static void applyLastOrSystemTheme(Activity activity) {
        try {
            Boolean d = lastDark;
            if (d != null) {
                applyStatusBar(activity, d.booleanValue());
            } else {
                applyForSystemTheme(activity);
            }
        } catch (Throwable t) {
            Log.w(TAG, "applyLastOrSystemTheme failed: " + t);
        }
    }

    private static void applyStatusBar(Activity activity, boolean dark) {
        if (activity == null || activity.isFinishing()) {
            return;
        }
        // 窗口操作必须在主线程
        if (Looper.myLooper() != Looper.getMainLooper()) {
            final Activity act = activity;
            final boolean d = dark;
            try {
                act.runOnUiThread(() -> applyStatusBar(act, d));
            } catch (Throwable t) {
                Log.w(TAG, "runOnUiThread failed: " + t);
            }
            return;
        }
        final Window window = activity.getWindow();
        if (window == null) {
            return;
        }
        final View decor = window.getDecorView();
        if (decor == null) {
            return;
        }
        final int bg = dark ? BG_DARK : BG_LIGHT;

        // 图标明暗：浅色主题 -> 深色图标（light=true），深色主题 -> 浅色图标
        try {
            WindowInsetsControllerCompat controller =
                    WindowCompat.getInsetsController(window, decor);
            if (controller != null) {
                controller.setAppearanceLightStatusBars(!dark);
                controller.setAppearanceLightNavigationBars(!dark);
            }
        } catch (Throwable t) {
            Log.w(TAG, "insets controller failed: " + t);
        }
        // 背景色与页面主题保持一致
        try {
            window.setStatusBarColor(bg);
        } catch (Throwable t) {
            Log.w(TAG, "setStatusBarColor failed: " + t);
        }
        try {
            window.setNavigationBarColor(bg);
        } catch (Throwable t) {
            Log.w(TAG, "setNavigationBarColor failed: " + t);
        }
        // 窗口尚未附加（冷启动极早期）：附加后自动重试一次，保证颜色最终落地
        if (!decor.isAttachedToWindow()) {
            try {
                decor.post(() -> {
                    try {
                        applyStatusBar(activity, dark);
                    } catch (Throwable ignored) {
                    }
                });
            } catch (Throwable t) {
                Log.w(TAG, "decor post failed: " + t);
            }
        }
    }
}