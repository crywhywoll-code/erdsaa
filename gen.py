import os
import shutil
import base64

# Название приложения (меняй тут):
APP_NAME = 'time个'

FILES = {
'app/build.gradle.kts': r'''plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.example.glasstime"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.glasstime"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
''',
'app/src/main/AndroidManifest.xml': r'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <uses-permission
        android:name="android.permission.PACKAGE_USAGE_STATS"
        tools:ignore="ProtectedPermissions" />

    <queries>
        <intent>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent>
    </queries>

    <application
        android:allowBackup="true"
        android:label="Glass Time"
        android:theme="@style/Theme.Glass">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".MediaTrackerService"
            android:exported="true"
            android:label="Glass Time"
            android:permission="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE">
            <intent-filter>
                <action android:name="android.service.notification.NotificationListenerService" />
            </intent-filter>
        </service>
    </application>
</manifest>
''',
'app/src/main/java/com/example/glasstime/Data.kt': r'''package com.example.glasstime

import android.app.AppOpsManager
import android.app.usage.UsageStatsManager
import android.content.Context
import android.os.Build
import android.os.Process
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.core.app.NotificationManagerCompat
import androidx.core.graphics.drawable.toBitmap
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

class AppUsage(val pkg: String, val label: String, val icon: ImageBitmap?, val millis: Long)

fun fmt(ms: Long): String {
    val m = ms / 60000
    val h = m / 60
    return if (h > 0) "$h ч ${m % 60} мин" else if (m > 0) "$m мин" else "меньше минуты"
}

object AppInfo {
    private val icons = ConcurrentHashMap<String, ImageBitmap>()

    fun label(c: Context, pkg: String): String {
        return try {
            val pm = c.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        } catch (e: Exception) {
            pkg
        }
    }

    fun icon(c: Context, pkg: String): ImageBitmap? {
        icons[pkg]?.let { return it }
        return try {
            val bmp = c.packageManager.getApplicationIcon(pkg).toBitmap(96, 96).asImageBitmap()
            icons[pkg] = bmp
            bmp
        } catch (e: Exception) {
            null
        }
    }
}

object UsageData {
    @Suppress("DEPRECATION")
    fun hasAccess(c: Context): Boolean {
        val ops = c.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = if (Build.VERSION.SDK_INT >= 29) {
            ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.packageName)
        } else {
            ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.packageName)
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun midnight(): Calendar {
        val cal = Calendar.getInstance()
        cal.set(Calendar.HOUR_OF_DAY, 0)
        cal.set(Calendar.MINUTE, 0)
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        return cal
    }

    private fun record(c: Context, usm: UsageStatsManager) {
        val stats = usm.queryAndAggregateUsageStats(midnight().timeInMillis, System.currentTimeMillis())
        val d = SimpleDateFormat("yyyyMMdd", Locale.US).format(Date())
        val e = c.getSharedPreferences("usage", Context.MODE_PRIVATE).edit()
        for (s in stats.values) {
            if (s.totalTimeInForeground >= 1000L) e.putLong("u:" + d + ":" + s.packageName, s.totalTimeInForeground)
        }
        e.apply()
    }

    fun load(c: Context, days: Int): List<AppUsage> {
        val usm = c.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        record(c, usm)
        val cal = midnight()
        if (days == 0) cal.add(Calendar.DAY_OF_YEAR, -365) else if (days > 1) cal.add(Calendar.DAY_OF_YEAR, -(days - 1))
        val stats = usm.queryAndAggregateUsageStats(cal.timeInMillis, System.currentTimeMillis())
        val totals = HashMap<String, Long>()
        for (s in stats.values) totals[s.packageName] = s.totalTimeInForeground
        if (days == 0) {
            val own = HashMap<String, Long>()
            for ((key, value) in c.getSharedPreferences("usage", Context.MODE_PRIVATE).all) {
                val v = (value as? Long) ?: continue
                val parts = key.split(":", limit = 3)
                if (parts.size == 3 && parts[0] == "u") own[parts[2]] = (own[parts[2]] ?: 0L) + v
            }
            for ((pkg, v) in own) {
                if (v > (totals[pkg] ?: 0L)) totals[pkg] = v
            }
        }
        val pm = c.packageManager
        val out = ArrayList<AppUsage>()
        for ((pkg, ms) in totals) {
            if (ms < 60_000L) continue
            if (pm.getLaunchIntentForPackage(pkg) == null) continue
            out.add(AppUsage(pkg, AppInfo.label(c, pkg), AppInfo.icon(c, pkg), ms))
        }
        out.sortByDescending { it.millis }
        return out
    }
}

class MediaRow(val pkg: String, val label: String, val icon: ImageBitmap?, val millis: Long)
class NowPlaying(val pkg: String, val title: String, val artist: String)

object MediaLog {
    private fun sp(c: Context) = c.getSharedPreferences("media", Context.MODE_PRIVATE)
    private fun dateStr(d: Date): String = SimpleDateFormat("yyyyMMdd", Locale.US).format(d)
    private const val MAX_SESSION = 12 * 3600_000L

    fun onStart(c: Context, pkg: String) {
        sp(c).edit().putLong("p:$pkg", System.currentTimeMillis()).apply()
    }

    fun onStop(c: Context, pkg: String) {
        val s = sp(c)
        val st = s.getLong("p:$pkg", 0L)
        if (st > 0L) {
            val d = (System.currentTimeMillis() - st).coerceIn(0L, MAX_SESSION)
            val k = "t:" + dateStr(Date()) + ":" + pkg
            s.edit().putLong(k, s.getLong(k, 0L) + d).remove("p:$pkg").apply()
        }
    }

    fun setMeta(c: Context, pkg: String, title: String?, artist: String?) {
        sp(c).edit()
            .putString("title:$pkg", title ?: "")
            .putString("artist:$pkg", artist ?: "")
            .apply()
    }

    fun rows(c: Context, days: Int): List<MediaRow> {
        val dates = HashSet<String>()
        for (i in 0 until days) {
            val cal = Calendar.getInstance()
            cal.add(Calendar.DAY_OF_YEAR, -i)
            dates.add(dateStr(cal.time))
        }
        val totals = HashMap<String, Long>()
        val now = System.currentTimeMillis()
        for ((key, value) in sp(c).all) {
            val v = (value as? Long) ?: continue
            if (key.startsWith("t:")) {
                val parts = key.split(":", limit = 3)
                if (parts.size == 3 && (days == 0 || parts[1] in dates)) {
                    totals[parts[2]] = (totals[parts[2]] ?: 0L) + v
                }
            } else if (key.startsWith("p:")) {
                val pkg = key.substring(2)
                val live = (now - v).coerceIn(0L, MAX_SESSION)
                totals[pkg] = (totals[pkg] ?: 0L) + live
            }
        }
        return totals.entries
            .filter { it.value >= 1000L }
            .sortedByDescending { it.value }
            .map { MediaRow(it.key, AppInfo.label(c, it.key), AppInfo.icon(c, it.key), it.value) }
    }

    fun nowPlaying(c: Context): List<NowPlaying> {
        val s = sp(c)
        val out = ArrayList<NowPlaying>()
        for ((key, value) in s.all) {
            if (key.startsWith("p:") && value is Long) {
                val pkg = key.substring(2)
                out.add(NowPlaying(pkg, s.getString("title:$pkg", "") ?: "", s.getString("artist:$pkg", "") ?: ""))
            }
        }
        return out
    }

    fun listenerEnabled(c: Context): Boolean {
        return NotificationManagerCompat.getEnabledListenerPackages(c).contains(c.packageName)
    }
}
''',
'app/src/main/java/com/example/glasstime/Glass.kt': r'''package com.example.glasstime

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.BlurredEdgeTreatment
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

fun Modifier.glass(t: ThemeState, radius: Dp = 28.dp): Modifier {
    val shape = RoundedCornerShape(radius)
    val a = t.glass
    return this
        .clip(shape)
        .background(
            Brush.linearGradient(
                listOf(
                    Color.White.copy(alpha = (a + 0.14f).coerceAtMost(0.85f)),
                    Color.White.copy(alpha = (a * 0.6f).coerceAtMost(0.85f))
                )
            )
        )
        .border(
            1.dp,
            Brush.linearGradient(
                listOf(
                    Color.White.copy(alpha = 0.8f),
                    Color.White.copy(alpha = 0.08f),
                    Color.White.copy(alpha = 0.45f)
                )
            ),
            shape
        )
}

@Composable
fun Background(t: ThemeState) {
    Box(Modifier.fillMaxSize()) {
        val photo = t.photo
        if (t.bgType == 1 && photo != null) {
            Image(
                bitmap = photo,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .fillMaxSize()
                    .graphicsLayer(scaleX = 1.12f, scaleY = 1.12f)
                    .blur(t.blur.dp, BlurredEdgeTreatment.Unbounded)
            )
        } else {
            val cols = Presets[t.preset.coerceIn(0, Presets.size - 1)].colors
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(cols)))
            Canvas(Modifier.fillMaxSize()) {
                val w = size.width
                val h = size.height
                drawRect(
                    Brush.radialGradient(
                        colors = listOf(t.accentColor.copy(alpha = 0.55f), Color.Transparent),
                        center = Offset(w * 0.15f, h * 0.2f),
                        radius = w * 0.9f
                    )
                )
                drawRect(
                    Brush.radialGradient(
                        colors = listOf(cols.last().copy(alpha = 0.6f), Color.Transparent),
                        center = Offset(w * 0.9f, h * 0.75f),
                        radius = w * 1.0f
                    )
                )
            }
        }
        Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = t.dim)))
    }
}

@Composable
fun GText(
    t: ThemeState,
    text: String,
    size: Int = 15,
    bold: Boolean = false,
    secondary: Boolean = false,
    modifier: Modifier = Modifier
) {
    Text(
        text = text,
        modifier = modifier,
        color = if (secondary) t.textColor.copy(alpha = 0.7f) else t.textColor,
        fontSize = size.sp,
        fontWeight = if (bold) FontWeight.SemiBold else FontWeight.Normal
    )
}

@Composable
fun GlassCard(t: ThemeState, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = modifier.fillMaxWidth().glass(t).padding(16.dp),
        content = content
    )
}

@Composable
fun GButton(t: ThemeState, label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier = modifier
            .glass(t, 22.dp)
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center
    ) {
        GText(t, label, 15, true)
    }
}

@Composable
fun GChip(t: ThemeState, label: String, selected: Boolean, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .glass(t, 20.dp)
            .background(if (selected) t.accentColor.copy(alpha = 0.4f) else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 9.dp),
        contentAlignment = Alignment.Center
    ) {
        GText(t, label, 14, selected)
    }
}

@Composable
fun BottomBar(t: ThemeState, tab: Int, onTab: (Int) -> Unit) {
    val labels = listOf("📱 Экран", "🎧 Плеер", "🎨 Стиль")
    Row(
        modifier = Modifier
            .padding(horizontal = 20.dp, vertical = 10.dp)
            .fillMaxWidth()
            .glass(t, 32.dp)
            .padding(6.dp),
        horizontalArrangement = Arrangement.SpaceEvenly
    ) {
        labels.forEachIndexed { i, label ->
            Box(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(26.dp))
                    .background(if (tab == i) t.accentColor.copy(alpha = 0.38f) else Color.Transparent)
                    .clickable { onTab(i) }
                    .padding(vertical = 12.dp),
                contentAlignment = Alignment.Center
            ) {
                GText(t, label, 14, tab == i)
            }
        }
    }
}
''',
'app/src/main/java/com/example/glasstime/MainActivity.kt': r'''package com.example.glasstime

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val theme = ThemeState(getSharedPreferences("glass", MODE_PRIVATE))
        setContent {
            LaunchedEffect(Unit) {
                theme.photo = withContext(Dispatchers.IO) { PhotoStore.load(applicationContext) }
            }
            MaterialTheme(colorScheme = darkColorScheme()) {
                App(theme)
            }
        }
    }
}

@Composable
fun App(t: ThemeState) {
    var tab by remember { mutableIntStateOf(0) }
    Box(Modifier.fillMaxSize()) {
        Background(t)
        Column(Modifier.fillMaxSize().systemBarsPadding()) {
            Box(Modifier.weight(1f)) {
                when (tab) {
                    0 -> UsageScreen(t)
                    1 -> PlayerScreen(t)
                    else -> StyleScreen(t)
                }
            }
            BottomBar(t, tab) { tab = it }
        }
    }
}
''',
'app/src/main/java/com/example/glasstime/MediaTrackerService.kt': r'''package com.example.glasstime

import android.content.ComponentName
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.service.notification.NotificationListenerService

class MediaTrackerService : NotificationListenerService() {

    private var msm: MediaSessionManager? = null
    private val controllers = HashMap<String, MediaController>()
    private val callbacks = HashMap<String, MediaController.Callback>()
    private val playing = HashSet<String>()

    private val sessionsListener =
        MediaSessionManager.OnActiveSessionsChangedListener { list ->
            refresh(list ?: emptyList())
        }

    override fun onListenerConnected() {
        super.onListenerConnected()
        val m = getSystemService(MEDIA_SESSION_SERVICE) as MediaSessionManager
        msm = m
        val cn = ComponentName(this, MediaTrackerService::class.java)
        try {
            m.addOnActiveSessionsChangedListener(sessionsListener, cn)
            refresh(m.getActiveSessions(cn))
        } catch (e: SecurityException) {
            // no access yet
        }
    }

    override fun onListenerDisconnected() {
        shutdown()
        super.onListenerDisconnected()
    }

    override fun onDestroy() {
        shutdown()
        super.onDestroy()
    }

    private fun shutdown() {
        try {
            msm?.removeOnActiveSessionsChangedListener(sessionsListener)
        } catch (e: Exception) {
        }
        for ((pkg, c) in controllers) {
            callbacks[pkg]?.let { c.unregisterCallback(it) }
            stopTrack(pkg)
        }
        controllers.clear()
        callbacks.clear()
    }

    private fun refresh(list: List<MediaController>) {
        val pkgs = list.map { it.packageName }.toSet()
        for (pkg in controllers.keys.toList()) {
            if (pkg !in pkgs) {
                stopTrack(pkg)
                val c = controllers.remove(pkg)
                val cb = callbacks.remove(pkg)
                if (c != null && cb != null) c.unregisterCallback(cb)
            }
        }
        for (c in list) {
            val pkg = c.packageName
            if (controllers.containsKey(pkg)) continue
            val cb = object : MediaController.Callback() {
                override fun onPlaybackStateChanged(state: PlaybackState?) {
                    handle(pkg, state)
                }

                override fun onMetadataChanged(metadata: MediaMetadata?) {
                    meta(pkg, metadata)
                }
            }
            c.registerCallback(cb)
            controllers[pkg] = c
            callbacks[pkg] = cb
            handle(pkg, c.playbackState)
            meta(pkg, c.metadata)
        }
    }

    private fun handle(pkg: String, st: PlaybackState?) {
        val isPlaying = st?.state == PlaybackState.STATE_PLAYING
        if (isPlaying) {
            if (playing.add(pkg)) MediaLog.onStart(this, pkg)
        } else {
            stopTrack(pkg)
        }
    }

    private fun stopTrack(pkg: String) {
        if (playing.remove(pkg)) MediaLog.onStop(this, pkg)
    }

    private fun meta(pkg: String, md: MediaMetadata?) {
        MediaLog.setMeta(
            this,
            pkg,
            md?.getString(MediaMetadata.METADATA_KEY_TITLE),
            md?.getString(MediaMetadata.METADATA_KEY_ARTIST)
        )
    }
}
''',
'app/src/main/java/com/example/glasstime/Screens.kt': r'''package com.example.glasstime

import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun AppRow(t: ThemeState, icon: ImageBitmap?, label: String, ms: Long, frac: Float) {
    Row(
        modifier = Modifier.fillMaxWidth().glass(t, 24.dp).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (icon != null) {
            Image(
                bitmap = icon,
                contentDescription = null,
                modifier = Modifier.size(42.dp).clip(RoundedCornerShape(12.dp))
            )
        } else {
            Spacer(Modifier.size(42.dp))
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            GText(t, label, 15, true)
            Spacer(Modifier.height(6.dp))
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp))
                    .background(Color.White.copy(alpha = 0.18f))
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(frac.coerceIn(0.02f, 1f))
                        .fillMaxHeight()
                        .clip(RoundedCornerShape(3.dp))
                        .background(t.accentColor)
                )
            }
        }
        Spacer(Modifier.width(12.dp))
        GText(t, fmt(ms), 13, secondary = true)
    }
}

@Composable
fun UsageScreen(t: ThemeState) {
    val ctx = LocalContext.current
    var range by remember { mutableIntStateOf(1) }
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(3000)
            tick++
        }
    }
    val has = remember(tick) { UsageData.hasAccess(ctx) }
    var apps by remember { mutableStateOf<List<AppUsage>>(emptyList()) }
    LaunchedEffect(range, has, tick / 5) {
        if (has) apps = withContext(Dispatchers.IO) { UsageData.load(ctx, range) }
    }
    var total = 0L
    var max = 1L
    for (a in apps) {
        total += a.millis
        if (a.millis > max) max = a.millis
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { GText(t, "Экранное время", 30, true) }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GChip(t, "Сегодня", range == 1) { range = 1 }
                GChip(t, "7 дней", range == 7) { range = 7 }
                GChip(t, "Всё время", range == 0) { range = 0 }
            }
        }
        if (!has) {
            item {
                GlassCard(t) {
                    GText(t, "Нужен доступ к статистике использования", 16, true)
                    Spacer(Modifier.height(6.dp))
                    GText(t, "Откроются настройки. Найди Glass Time в списке и включи доступ.", 14, secondary = true)
                    Spacer(Modifier.height(12.dp))
                    GButton(t, "Открыть настройки") {
                        ctx.startActivity(
                            Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        )
                    }
                }
            }
        } else {
            item {
                GlassCard(t) {
                    GText(t, if (range == 1) "Сегодня всего" else if (range == 7) "За 7 дней всего" else "За всё время", 14, secondary = true)
                    GText(t, fmt(total), 34, true)
                }
            }
            items(apps, key = { it.pkg }) { a ->
                AppRow(t, a.icon, a.label, a.millis, a.millis.toFloat() / max.toFloat())
            }
        }
    }
}

@Composable
fun PlayerScreen(t: ThemeState) {
    val ctx = LocalContext.current
    var range by remember { mutableIntStateOf(1) }
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(3000)
            tick++
        }
    }
    val enabled = remember(tick) { try { MediaLog.listenerEnabled(ctx) } catch (e: Exception) { false } }
    val rows = remember(tick, range) { try { MediaLog.rows(ctx, range) } catch (e: Exception) { emptyList<MediaRow>() } }
    val now = remember(tick) { try { MediaLog.nowPlaying(ctx) } catch (e: Exception) { emptyList<NowPlaying>() } }
    var max = 1L
    for (r in rows) if (r.millis > max) max = r.millis

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { GText(t, "Плееры", 30, true) }
        if (!enabled) {
            item {
                GlassCard(t) {
                    GText(t, "Нужен доступ к уведомлениям", 16, true)
                    Spacer(Modifier.height(6.dp))
                    GText(
                        t,
                        "Так приложение видит, что сейчас играет, и считает время. Если вкл. недоступно, открой информацию о приложении, нажми три точки и разреши ограниченные настройки.",
                        14,
                        secondary = true
                    )
                    Spacer(Modifier.height(12.dp))
                    GButton(t, "Открыть настройки") {
                        ctx.startActivity(
                            Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        )
                    }
                }
            }
        } else {
            if (now.isNotEmpty()) {
                items(now, key = { "now:" + it.pkg }) { n ->
                    GlassCard(t) {
                        GText(t, "Сейчас играет · " + AppInfo.label(ctx, n.pkg), 13, secondary = true)
                        GText(t, if (n.title.isEmpty()) "Без названия" else n.title, 20, true)
                        if (n.artist.isNotEmpty()) GText(t, n.artist, 14, secondary = true)
                    }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    GChip(t, "Сегодня", range == 1) { range = 1 }
                    GChip(t, "7 дней", range == 7) { range = 7 }
                    GChip(t, "Всё время", range == 0) { range = 0 }
                }
            }
            if (rows.isEmpty()) {
                item { GText(t, "Пока ничего не играло. Включи музыку или видео.", 14, secondary = true) }
            }
            items(rows, key = { "row:" + it.pkg }) { r ->
                AppRow(t, r.icon, r.label, r.millis, r.millis.toFloat() / max.toFloat())
            }
        }
    }
}

@Composable
fun SliderRow(t: ThemeState, label: String, value: Float, range: ClosedFloatingPointRange<Float>, onChange: (Float) -> Unit) {
    GText(t, label, 14, secondary = true)
    Slider(
        value = value,
        onValueChange = onChange,
        valueRange = range,
        colors = SliderDefaults.colors(
            thumbColor = t.accentColor,
            activeTrackColor = t.accentColor,
            inactiveTrackColor = Color.White.copy(alpha = 0.25f)
        )
    )
}

@Composable
fun StyleScreen(t: ThemeState) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            scope.launch {
                val ok = withContext(Dispatchers.IO) { PhotoStore.save(ctx, uri) }
                if (ok) {
                    t.photo = withContext(Dispatchers.IO) { PhotoStore.load(ctx) }
                    t.bgType = 1
                    t.save()
                }
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { GText(t, "Стиль", 30, true) }
        item {
            GlassCard(t) {
                GText(t, "Фон", 16, true)
                Spacer(Modifier.height(10.dp))
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Presets.forEachIndexed { i, p ->
                        val selected = t.bgType == 0 && t.preset == i
                        Box(
                            Modifier
                                .size(52.dp)
                                .clip(CircleShape)
                                .background(Brush.linearGradient(p.colors))
                                .border(if (selected) 3.dp else 1.dp, Color.White.copy(alpha = if (selected) 1f else 0.5f), CircleShape)
                                .clickable {
                                    t.preset = i
                                    t.bgType = 0
                                    t.save()
                                }
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    GButton(t, "Своё фото") {
                        picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                    }
                    if (t.bgType == 1) {
                        GButton(t, "Убрать фото") {
                            t.bgType = 0
                            t.save()
                        }
                    }
                }
            }
        }
        item {
            GlassCard(t) {
                GText(t, "Стекло", 16, true)
                SliderRow(t, "Размытие фото (Android 12+)", t.blur, 0f..40f) { t.blur = it; t.save() }
                SliderRow(t, "Прозрачность стекла", t.glass, 0.04f..0.5f) { t.glass = it; t.save() }
                SliderRow(t, "Затемнение фона", t.dim, 0f..0.6f) { t.dim = it; t.save() }
            }
        }
        item {
            GlassCard(t) {
                GText(t, "Цвета", 16, true)
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Accents.forEachIndexed { i, c ->
                        Box(
                            Modifier
                                .size(40.dp)
                                .clip(CircleShape)
                                .background(c)
                                .border(if (t.accent == i) 3.dp else 1.dp, Color.White.copy(alpha = if (t.accent == i) 1f else 0.5f), CircleShape)
                                .clickable {
                                    t.accent = i
                                    t.save()
                                }
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    GText(t, "Тёмный текст", 15, modifier = Modifier.weight(1f))
                    Switch(checked = t.darkText, onCheckedChange = { t.darkText = it; t.save() })
                }
            }
        }
        item { GButton(t, "Сбросить стиль") { t.reset() } }
    }
}
''',
'app/src/main/java/com/example/glasstime/Theme.kt': r'''package com.example.glasstime

import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import java.io.File

class Preset(val name: String, val colors: List<Color>)

val Presets = listOf(
    Preset("Рассвет", listOf(Color(0xFFFF9A9E), Color(0xFFFAD0C4), Color(0xFFA18CD1))),
    Preset("Океан", listOf(Color(0xFF2193B0), Color(0xFF6DD5ED), Color(0xFF3A6073))),
    Preset("Ночь", listOf(Color(0xFF0F2027), Color(0xFF203A43), Color(0xFF2C5364))),
    Preset("Лес", listOf(Color(0xFF134E5E), Color(0xFF71B280), Color(0xFF0B3D2E))),
    Preset("Графит", listOf(Color(0xFF232526), Color(0xFF414345), Color(0xFF6B6B6B))),
    Preset("Лаванда", listOf(Color(0xFFDDD6F3), Color(0xFFFAACA8), Color(0xFF9AA7F0)))
)

val Accents = listOf(
    Color(0xFF7CC4FF),
    Color(0xFFFF8FB1),
    Color(0xFFB9F27C),
    Color(0xFFFFD36E),
    Color(0xFFC8A2FF),
    Color(0xFFFFFFFF)
)

class ThemeState(private val sp: SharedPreferences) {
    var bgType by mutableIntStateOf(sp.getInt("bgType", 0))
    var preset by mutableIntStateOf(sp.getInt("preset", 0))
    var blur by mutableFloatStateOf(sp.getFloat("blur", 18f))
    var glass by mutableFloatStateOf(sp.getFloat("glass", 0.18f))
    var dim by mutableFloatStateOf(sp.getFloat("dim", 0.12f))
    var darkText by mutableStateOf(sp.getBoolean("darkText", false))
    var accent by mutableIntStateOf(sp.getInt("accent", 0))
    var photo by mutableStateOf<ImageBitmap?>(null)

    val textColor: Color
        get() = if (darkText) Color(0xFF14161A) else Color.White
    val accentColor: Color
        get() = Accents[accent.coerceIn(0, Accents.size - 1)]

    fun save() {
        sp.edit()
            .putInt("bgType", bgType)
            .putInt("preset", preset)
            .putFloat("blur", blur)
            .putFloat("glass", glass)
            .putFloat("dim", dim)
            .putBoolean("darkText", darkText)
            .putInt("accent", accent)
            .apply()
    }

    fun reset() {
        bgType = 0
        preset = 0
        blur = 18f
        glass = 0.18f
        dim = 0.12f
        darkText = false
        accent = 0
        save()
    }
}

object PhotoStore {
    fun save(ctx: Context, uri: Uri): Boolean {
        return try {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            ctx.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
            var sample = 1
            while (bounds.outWidth / sample > 2000 || bounds.outHeight / sample > 2000) sample *= 2
            val opts = BitmapFactory.Options().apply { inSampleSize = sample }
            val bmp = ctx.contentResolver.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(it, null, opts)
            } ?: return false
            File(ctx.filesDir, "bg.jpg").outputStream().use {
                bmp.compress(Bitmap.CompressFormat.JPEG, 90, it)
            }
            true
        } catch (e: Exception) {
            false
        }
    }

    fun load(ctx: Context): ImageBitmap? {
        val f = File(ctx.filesDir, "bg.jpg")
        if (!f.exists()) return null
        return BitmapFactory.decodeFile(f.path)?.asImageBitmap()
    }
}
''',
'app/src/main/res/values/themes.xml': r'''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Glass" parent="android:Theme.Material.NoActionBar">
        <item name="android:windowBackground">@android:color/black</item>
        <item name="android:statusBarColor">@android:color/transparent</item>
        <item name="android:navigationBarColor">@android:color/transparent</item>
    </style>
</resources>
''',
'build.gradle.kts': r'''plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.20" apply false
}
''',
'gradle.properties': r'''android.useAndroidX=true
org.gradle.jvmargs=-Xmx2g
''',
'settings.gradle.kts': r'''pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "GlassTime"
include(":app")
''',
}

ICON_B64 = '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'

for path, text in FILES.items():
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)

# название
mf = 'app/src/main/AndroidManifest.xml'
t = open(mf, encoding='utf-8').read().replace('android:label="Glass Time"', 'android:label="' + APP_NAME + '"')

# иконка: если в корне репозитория лежит icon.png, берётся он, иначе встроенная
icon_dir = 'app/src/main/res/mipmap-xxxhdpi'
os.makedirs(icon_dir, exist_ok=True)
if os.path.exists('icon.png'):
    shutil.copy('icon.png', icon_dir + '/ic_launcher.png')
else:
    with open(icon_dir + '/ic_launcher.png', 'wb') as f:
        f.write(base64.b64decode(ICON_B64))
t = t.replace('android:allowBackup="true"', 'android:allowBackup="true"\n        android:icon="@mipmap/ic_launcher"', 1)
open(mf, 'w', encoding='utf-8').write(t)
print('ok', len(FILES), 'files')
