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
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
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
            addJavascriptInterface(LiveBridge(), "Live")
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

    // ------------------------------------------------------------ Live-Kurs
    private val live = Executors.newSingleThreadExecutor()
    private val nyZone = ZoneId.of("America/New_York")

    private fun get(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 10000
        c.readTimeout = 10000
        c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
        c.setRequestProperty("Accept", "application/json")
        if (c.responseCode != 200) throw Exception("HTTP ${c.responseCode}")
        return c.inputStream.bufferedReader().use { it.readText() }
    }

    private fun num(s: String): Double = s.replace(",", "").replace("+", "").trim().toDouble()

    /** Echtzeitkurs S&P 500 von CNBC. */
    private fun cnbc(): JSONObject {
        val q = JSONObject(get("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol" +
                "?symbols=.SPX&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=0&output=json"))
            .getJSONObject("FormattedQuoteResult").getJSONArray("FormattedQuote").getJSONObject(0)
        val t = OffsetDateTime.parse(q.getString("last_time").replace(Regex("""\.\d+"""), "")
            .replace(Regex("""([+-]\d\d)(\d\d)$"""), "$1:$2")).atZoneSameInstant(nyZone)
        return JSONObject()
            .put("price", num(q.getString("last")))
            .put("open", num(q.optString("open", q.getString("last"))))
            .put("high", num(q.optString("high", q.getString("last"))))
            .put("low", num(q.optString("low", q.getString("last"))))
            .put("prev", num(q.getString("previous_day_closing")))
            .put("date", t.toLocalDate().toString())
            .put("hm", "%02d:%02d".format(t.hour, t.minute))
            .put("state", q.optString("curmktstatus", ""))
            .put("src", "CNBC")
    }

    /** Ersatzquelle: Yahoo Finance. */
    private fun yahoo(): JSONObject {
        val r = JSONObject(get("https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1d&interval=5m"))
            .getJSONObject("chart").getJSONArray("result").getJSONObject(0)
        val m = r.getJSONObject("meta")
        val p = m.getDouble("regularMarketPrice")
        val t = Instant.ofEpochSecond(m.getLong("regularMarketTime")).atZone(nyZone)
        var open = p
        try {
            val o = r.getJSONObject("indicators").getJSONArray("quote").getJSONObject(0).getJSONArray("open")
            for (i in 0 until o.length()) if (!o.isNull(i)) { open = o.getDouble(i); break }
        } catch (_: Exception) {}
        return JSONObject()
            .put("price", p).put("open", open)
            .put("high", m.optDouble("regularMarketDayHigh", p)).put("low", m.optDouble("regularMarketDayLow", p))
            .put("prev", m.optDouble("chartPreviousClose", m.optDouble("previousClose", p)))
            .put("date", t.toLocalDate().toString())
            .put("hm", "%02d:%02d".format(t.hour, t.minute))
            .put("state", "").put("src", "Yahoo")
    }

    inner class LiveBridge {
        /** Live-Kurs holen; Ergebnis über window.onLive(json) bzw. window.onLiveError(text). */
        @JavascriptInterface
        fun live() {
            live.execute {
                val q = try { cnbc() } catch (e: Exception) { try { yahoo() } catch (e2: Exception) { null } }
                if (q != null) send("window.onLive(${JSONObject.quote(q.toString())})")
                else send("window.onLiveError && window.onLiveError()")
            }
        }
    }

    private fun send(js: String) = runOnUiThread { web.evaluateJavascript(js, null) }
}
