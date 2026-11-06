import os

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

    fun load(c: Context, days: Int): List<AppUsage> {
        val usm = c.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val cal = Calendar.getInstance()
        cal.set(Calendar.HOUR_OF_DAY, 0)
        cal.set(Calendar.MINUTE, 0)
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        if (days > 1) cal.add(Calendar.DAY_OF_YEAR, -(days - 1))
        val start = cal.timeInMillis
        val end = System.currentTimeMillis()
        val stats = usm.queryAndAggregateUsageStats(start, end)
        val pm = c.packageManager
        val out = ArrayList<AppUsage>()
        for (s in stats.values) {
            if (s.totalTimeInForeground < 60_000L) continue
            if (pm.getLaunchIntentForPackage(s.packageName) == null) continue
            out.add(AppUsage(s.packageName, AppInfo.label(c, s.packageName), AppInfo.icon(c, s.packageName), s.totalTimeInForeground))
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
                if (parts.size == 3 && parts[1] in dates) {
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
                    GText(t, if (range == 1) "Сегодня всего" else "За 7 дней всего", 14, secondary = true)
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
    val enabled = remember(tick) { MediaLog.listenerEnabled(ctx) }
    val rows = remember(tick, range) { MediaLog.rows(ctx, range) }
    val now = remember(tick) { MediaLog.nowPlaying(ctx) }
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
                items(now, key = { it.pkg }) { n ->
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
                }
            }
            if (rows.isEmpty()) {
                item { GText(t, "Пока ничего не играло. Включи музыку или видео.", 14, secondary = true) }
            }
            items(rows, key = { it.pkg }) { r ->
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

for path, text in FILES.items():
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
print('ok', len(FILES), 'files')
