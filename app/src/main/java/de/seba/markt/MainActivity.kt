package de.seba.markt

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * Markt: täglicher Shiller-CAPE des S&P 500 mit Ø/σ-Bändern und S&P-500-Wochenkerzen mit 200-Tage-Linie.
 * Die Daten berechnet ein GitHub-Actions-Job jeden Handelstag (data/markt.json im Repo ZweiSebastian/markt).
 * Die App lädt nur diese Datei, speichert sie zwischen und zeigt sie an – auch offline.
 */
class MainActivity : ComponentActivity() {

    private val dataUrl = "https://raw.githubusercontent.com/ZweiSebastian/markt/main/data/markt.json"
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var web: WebView
    private val cache by lazy { File(filesDir, "markt.json") }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = 0xFF0F1115.toInt()
        window.navigationBarColor = 0xFF0F1115.toInt()
        web = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#0F1115"))
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = WebViewClient()
            addJavascriptInterface(Bridge(), "Android")
            loadUrl("file:///android_asset/index.html")
        }
        setContentView(web)
    }

    override fun onResume() {
        super.onResume()
        // Beim Zurückkehren in die App still aktualisieren
        if (::web.isInitialized) web.evaluateJavascript("window.refresh && window.refresh()", null)
    }

    inner class Bridge {
        /** Zuletzt gespeicherte Daten (oder leer). */
        @JavascriptInterface
        fun cached(): String = try { if (cache.exists()) cache.readText() else "" } catch (e: Exception) { "" }

        /** Neu laden; Ergebnis kommt über window.onData(json) bzw. window.onError(text). */
        @JavascriptInterface
        fun load() {
            io.execute {
                try {
                    val c = URL("$dataUrl?t=${System.currentTimeMillis() / 60000}").openConnection() as HttpURLConnection
                    c.connectTimeout = 15000
                    c.readTimeout = 20000
                    c.setRequestProperty("Cache-Control", "no-cache")
                    val text = c.inputStream.bufferedReader().use { it.readText() }
                    if (c.responseCode != 200) throw Exception("HTTP ${c.responseCode}")
                    JSONObject(text) // prüfen, dass es gültiges JSON ist
                    cache.writeText(text)
                    send("window.onData(${JSONObject.quote(text)})")
                } catch (e: Exception) {
                    send("window.onError(${JSONObject.quote(e.message ?: "Fehler")})")
                }
            }
        }
    }

    private fun send(js: String) = runOnUiThread { web.evaluateJavascript(js, null) }
}
