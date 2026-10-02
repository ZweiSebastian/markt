// Markt Terminal – macOS-Hülle
// Fenster mit WKWebView; die Oberfläche liegt in Resources/web.
// Die Brücke "native" erledigt Netzabrufe ohne CORS-Grenzen, öffnet Links im Browser
// und speichert die letzte Datenbasis in ~/Library/Application Support/Markt Terminal.

import Cocoa
import WebKit

let userAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    let session: URLSession = {
        let c = URLSessionConfiguration.default
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.httpAdditionalHeaders = ["User-Agent": userAgent, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"]
        c.timeoutIntervalForRequest = 30
        return URLSession(configuration: c)
    }()

    lazy var storeDir: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let d = base.appendingPathComponent("Markt Terminal", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }()

    func file(_ key: String) -> URL {
        let safe = key.replacingOccurrences(of: "[^A-Za-z0-9_-]", with: "_", options: .regularExpression)
        return storeDir.appendingPathComponent(safe + ".txt")
    }

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any], let op = body["op"] as? String else {
            replyHandler(nil, "ungültige Nachricht"); return
        }
        switch op {
        case "fetch":
            guard let s = body["url"] as? String, let url = URL(string: s),
                  let scheme = url.scheme, scheme == "https" || scheme == "http" else {
                replyHandler(["ok": false, "status": 0, "text": ""], nil); return
            }
            var req = URLRequest(url: url)
            req.timeoutInterval = (body["timeout"] as? Double) ?? 25
            session.dataTask(with: req) { data, resp, err in
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                var text = ""
                if let d = data {
                    text = String(data: d, encoding: .utf8) ?? String(data: d, encoding: .isoLatin1) ?? ""
                }
                let ok = err == nil && (200..<300).contains(code)
                DispatchQueue.main.async { replyHandler(["ok": ok, "status": code, "text": text], nil) }
            }.resume()
        case "open":
            if let s = body["url"] as? String, let url = URL(string: s), url.scheme?.hasPrefix("http") == true {
                NSWorkspace.shared.open(url)
            }
            replyHandler(true, nil)
        case "save":
            if let k = body["key"] as? String, let t = body["text"] as? String {
                try? t.write(to: file(k), atomically: true, encoding: .utf8)
            }
            replyHandler(true, nil)
        case "load":
            if let k = body["key"] as? String, let t = try? String(contentsOf: file(k), encoding: .utf8) {
                replyHandler(t, nil)
            } else { replyHandler(NSNull(), nil) }
        default:
            replyHandler(nil, "unbekannt")
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    let bridge = Bridge()

    func applicationDidFinishLaunching(_ n: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.addScriptMessageHandler(bridge, contentWorld: .page, name: "native")
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.customUserAgent = userAgent
        web.setValue(false, forKey: "drawsBackground")
        if #available(macOS 13.3, *) { web.isInspectable = true }

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1500, height: 940),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "Markt Terminal"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = false
        window.backgroundColor = NSColor(red: 0.043, green: 0.051, blue: 0.067, alpha: 1)
        window.appearance = NSAppearance(named: .darkAqua)
        window.minSize = NSSize(width: 1080, height: 680)
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("MarktTerminalHauptfenster")
        window.tabbingMode = .disallowed
        window.makeKeyAndOrderFront(nil)

        if let dir = Bundle.main.resourceURL?.appendingPathComponent("web"),
           FileManager.default.fileExists(atPath: dir.appendingPathComponent("index.html").path) {
            web.loadFileURL(dir.appendingPathComponent("index.html"), allowingReadAccessTo: dir)
        } else {
            web.loadHTMLString("<body style='background:#0b0d11;color:#eee;font:14px -apple-system'>Oberfläche fehlt im App-Paket.</body>", baseURL: nil)
        }
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // Externe Links im Standardbrowser öffnen
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, let s = u.scheme, s == "http" || s == "https" {
            NSWorkspace.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { NSWorkspace.shared.open(u) }
        return nil
    }
    // Wenn der Web-Prozess abstürzt (z. B. nach dem Ruhezustand): neu laden
    func webViewWebContentProcessDidTerminate(_ w: WKWebView) { w.reload() }

    @objc func reloadPage(_ s: Any?) { web.reload() }

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem(); main.addItem(appItem)
        let app = NSMenu()
        app.addItem(withTitle: "Über Markt Terminal", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Markt Terminal ausblenden", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let other = app.addItem(withTitle: "Andere ausblenden", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        other.keyEquivalentModifierMask = [.command, .option]
        app.addItem(.separator())
        app.addItem(withTitle: "Markt Terminal beenden", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = app

        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Bearbeiten")
        edit.addItem(withTitle: "Ausschneiden", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Kopieren", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Einsetzen", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Alles auswählen", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "Darstellung")
        // ⌘R, ⌘K, ⌘1–9 und ⌘N behandelt die Oberfläche selbst
        view.addItem(withTitle: "Oberfläche neu laden", action: #selector(reloadPage(_:)), keyEquivalent: "")
        let fs = view.addItem(withTitle: "Vollbild", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fs.keyEquivalentModifierMask = [.command, .control]
        viewItem.submenu = view

        let winItem = NSMenuItem(); main.addItem(winItem)
        let win = NSMenu(title: "Fenster")
        win.addItem(withTitle: "Im Dock ablegen", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Zoomen", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        win.addItem(withTitle: "Fenster schließen", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        NSApp.windowsMenu = win
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
