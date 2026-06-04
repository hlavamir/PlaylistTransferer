#!/usr/bin/env python3
"""PyObjC GUI — Spotify → macOS Music Playlist Transferer."""

import os
import shutil
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import objc
from AppKit import (
    NSAlert,
    NSAlertFirstButtonReturn,
    NSAlertSecondButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSProgressIndicator,
    NSScrollView,
    NSSecureTextField,
    NSTextField,
    NSTextAlignmentCenter,
    NSTextView,
    NSView,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSViewHeightSizable,
    NSViewMaxXMargin,
    NSViewMaxYMargin,
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSWorkspace,
)
from Foundation import NSObject, NSProcessInfo, NSThread, NSURL
from dotenv import load_dotenv

import transfer

WIN_W, WIN_H = 640, 360

# NSVisualEffectView integer constants
_VEF_POPOVER = 6   # NSVisualEffectMaterialPopover
_VEF_BEHIND  = 0   # NSVisualEffectBlendingModeBehindWindow
_VEF_ACTIVE  = 1   # NSVisualEffectStateActive


# ── Native UI helpers ──────────────────────────────────────────────────────────

def _field(rect, placeholder: str, secure: bool = False, font_size: float = 14) -> NSTextField:
    """Rounded text field using NSTextFieldRoundedBezel — no custom drawing."""
    cls = NSSecureTextField if secure else NSTextField
    f = cls.alloc().initWithFrame_(rect)
    f.setPlaceholderString_(placeholder)
    f.setFont_(NSFont.systemFontOfSize_(font_size))
    f.setBezeled_(True)
    f.setBezelStyle_(1)   # NSTextFieldRoundedBezel
    return f


def _button(rect, title: str, target, action: str, *,
            key: str = "", color: NSColor | None = None) -> NSButton:
    """Large native rounded button. key='\r' → accent blue; color → bezel tint."""
    btn = NSButton.alloc().initWithFrame_(rect)
    btn.setTitle_(title)
    btn.setBezelStyle_(NSBezelStyleRounded)
    btn.setControlSize_(3)   # NSControlSizeLarge (macOS 11+)
    btn.setTarget_(target)
    btn.setAction_(action)
    if key:
        btn.setKeyEquivalent_(key)
    if color:
        btn.setBezelColor_(color)
    return btn


def _glass_circle(rect, symbol: str, target, action) -> NSVisualEffectView:
    """Circular liquid-glass vibrancy button (NSVisualEffectView + SF Symbol)."""
    vev = NSVisualEffectView.alloc().initWithFrame_(rect)
    vev.setMaterial_(_VEF_POPOVER)
    vev.setBlendingMode_(_VEF_BEHIND)
    vev.setState_(_VEF_ACTIVE)
    vev.setWantsLayer_(True)
    r = min(rect.size.width, rect.size.height) / 2
    vev.layer().setCornerRadius_(r)
    vev.layer().setMasksToBounds_(True)

    sz = rect.size
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, sz.width, sz.height))
    btn.setImage_(NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, symbol))
    btn.setImageScaling_(3)   # NSImageScaleProportionallyUpOrDown
    btn.setBordered_(False)
    btn.setTarget_(target)
    btn.setAction_(action)
    vev.addSubview_(btn)
    return vev


# ── Main-thread dispatch ───────────────────────────────────────────────────────

class _Helper(NSObject):
    def run_(self, fn):
        fn()

_helper = _Helper.alloc().init()


def on_main(fn):
    if NSThread.isMainThread():
        fn()
    else:
        _helper.performSelectorOnMainThread_withObject_waitUntilDone_("run:", fn, False)


# ── Credential utilities ───────────────────────────────────────────────────────

def load_credentials():
    creds = {"client_id": "", "client_secret": ""}
    env_path = os.path.join(transfer._CONFIG_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                key, _, val = line.partition("=")
                if key.strip() == "SPOTIFY_CLIENT_ID":
                    creds["client_id"] = val.strip()
                elif key.strip() == "SPOTIFY_CLIENT_SECRET":
                    creds["client_secret"] = val.strip()
    return creds


def save_credentials(client_id, client_secret):
    env_path = os.path.join(transfer._CONFIG_DIR, ".env")
    os.makedirs(transfer._CONFIG_DIR, exist_ok=True)
    with open(env_path, "w") as f:
        f.write(f"SPOTIFY_CLIENT_ID={client_id}\n")
        f.write(f"SPOTIFY_CLIENT_SECRET={client_secret}\n")
        f.write("SPOTIFY_REDIRECT_URI=https://google.com\n")
    load_dotenv(env_path, override=True)


def delete_all_data():
    if os.path.exists(transfer._CONFIG_DIR):
        shutil.rmtree(transfer._CONFIG_DIR)
    os.makedirs(transfer._CONFIG_DIR, exist_ok=True)


# ── App delegate ───────────────────────────────────────────────────────────────

class AppDelegate(NSObject):

    def applicationDidFinishLaunching_(self, _notif):
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIN_W, WIN_H), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Playlist Transferer")
        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        self._build_menu()
        self._show_main()

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True

    # ── Menu ──────────────────────────────────────────────────────────────────

    @objc.python_method
    def _build_menu(self):
        bar = NSMenu.alloc().init()

        app_item = NSMenuItem.alloc().init()
        bar.addItem_(app_item)
        app_menu = NSMenu.alloc().init()
        app_menu.addItemWithTitle_action_keyEquivalent_(
            "Quit Playlist Transferer", "terminate:", "q"
        )
        app_item.setSubmenu_(app_menu)

        edit_item = NSMenuItem.alloc().init()
        bar.addItem_(edit_item)
        edit_menu = NSMenu.alloc().initWithTitle_("Edit")
        for title, action, key in [
            ("Undo",       "undo:",      "z"),
            ("Redo",       "redo:",      "Z"),
            ("-",          "",           ""),
            ("Cut",        "cut:",       "x"),
            ("Copy",       "copy:",      "c"),
            ("Paste",      "paste:",     "v"),
            ("Select All", "selectAll:", "a"),
        ]:
            if title == "-":
                edit_menu.addItem_(NSMenuItem.separatorItem())
            else:
                edit_menu.addItemWithTitle_action_keyEquivalent_(title, action, key)
        edit_item.setSubmenu_(edit_menu)

        NSApplication.sharedApplication().setMainMenu_(bar)

    # ── Views ─────────────────────────────────────────────────────────────────

    @objc.python_method
    def _show_main(self):
        bounds = self.window.contentView().bounds()
        w, h = bounds.size.width, bounds.size.height
        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))

        # Gear — liquid glass circle, top-right
        gs = 52
        gear = _glass_circle(
            NSMakeRect(w - gs - 14, h - gs - 14, gs, gs),
            "gear", self, "showSettings:",
        )
        gear.setAutoresizingMask_(NSViewMinXMargin | NSViewMinYMargin)
        root.addSubview_(gear)

        # URL field
        pad, fh = 32, 32
        self.url_field = _field(
            NSMakeRect(pad, h / 2 + 14, w - pad * 2, fh),
            "Paste Spotify playlist URL…", font_size=15,
        )
        self.url_field.setAutoresizingMask_(
            NSViewWidthSizable | NSViewMinYMargin | NSViewMaxYMargin
        )
        root.addSubview_(self.url_field)

        # Import button — \r makes it the accent (blue) default button
        bw, bh = 148, 36
        import_btn = _button(
            NSMakeRect((w - bw) / 2, h / 2 - 58, bw, bh),
            "Import", self, "startImport:", key="\r",
        )
        import_btn.setAutoresizingMask_(
            NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin
        )
        root.addSubview_(import_btn)

        self.window.setContentView_(root)
        self.window.makeFirstResponder_(self.url_field)

    @objc.python_method
    def _show_loading(self):
        bounds = self.window.contentView().bounds()
        w, h = bounds.size.width, bounds.size.height
        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        cm = NSViewMinXMargin | NSViewMaxXMargin | NSViewMinYMargin | NSViewMaxYMargin

        spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect((w - 32) / 2, h / 2 + 10, 32, 32)
        )
        spinner.setStyle_(1)   # NSProgressIndicatorStyleSpinning
        spinner.startAnimation_(None)
        spinner.setAutoresizingMask_(cm)
        root.addSubview_(spinner)

        lbl = NSTextField.labelWithString_("Importing…")
        lbl.setFrame_(NSMakeRect((w - 200) / 2, h / 2 - 30, 200, 20))
        lbl.setAlignment_(NSTextAlignmentCenter)
        lbl.setAutoresizingMask_(cm)
        root.addSubview_(lbl)

        self.window.setContentView_(root)

    @objc.python_method
    def _show_results(self, result: dict):
        bounds = self.window.contentView().bounds()
        w, h = bounds.size.width, bounds.size.height
        root = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))

        lines = [f"Done — {result['added']} of {result['total']} tracks imported."]
        skipped = result["matched"] - result["added"]
        if skipped > 0:
            lines.append(f"  ({skipped} already in playlist, skipped)")
        if result["not_found"]:
            lines.append(f"\n✗  {len(result['not_found'])} not in local library:")
            for t, score, _ in result["not_found"]:
                lines.append(f"   [{score:4.0f}]  {t}")
        if result["low_confidence"]:
            lines.append(f"\n⚠  {len(result['low_confidence'])} low-confidence match(es):")
            for sp, loc, s in result["low_confidence"]:
                lines.append(f"   [{s:4.0f}]  {sp}  →  {loc}")

        bh = 36
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(12, bh + 20, w - 24, h - bh - 32))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, w - 24, h - bh - 32))
        tv.setEditable_(False)
        tv.setString_("\n".join(lines))
        tv.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0))
        scroll.setDocumentView_(tv)
        root.addSubview_(scroll)

        bw = 220
        btn = _button(
            NSMakeRect((w - bw) / 2, 12, bw, bh),
            "Import Another Playlist", self, "backToMain:", key="\r",
        )
        btn.setAutoresizingMask_(NSViewMinXMargin | NSViewMaxXMargin)
        root.addSubview_(btn)

        self.window.setContentView_(root)

    # ── Import action ─────────────────────────────────────────────────────────

    def startImport_(self, _sender):
        url = self.url_field.stringValue().strip()
        if not url:
            return

        creds = load_credentials()
        if not creds["client_id"] or not creds["client_secret"]:
            a = NSAlert.alloc().init()
            a.setMessageText_("Spotify credentials required")
            a.setInformativeText_(
                "Open Settings (⚙) and enter your Spotify Client ID and Secret."
            )
            a.runModal()
            return

        if not transfer.has_valid_token():
            a = NSAlert.alloc().init()
            a.setMessageText_("Authorization required")
            a.setInformativeText_(
                "Open Settings (⚙), click 'Open Spotify Authorization Page', "
                "authorize in your browser, paste the redirect URL, then click Save."
            )
            a.runModal()
            return

        self._show_loading()

        def run():
            try:
                playlist_name, spotify_tracks = transfer.fetch_spotify_playlist(
                    url, interactive=False
                )

                if transfer.playlist_exists(playlist_name):
                    mode_holder: list[str | None] = [None]
                    done = threading.Event()

                    def ask_user():
                        a = NSAlert.alloc().init()
                        a.setMessageText_(f"'{playlist_name}' already exists")
                        a.setInformativeText_(
                            "Extend it with new tracks, replace it entirely, or cancel?"
                        )
                        a.addButtonWithTitle_("Extend")
                        a.addButtonWithTitle_("Replace")
                        a.addButtonWithTitle_("Cancel")
                        resp = a.runModal()
                        if resp == NSAlertFirstButtonReturn:
                            mode_holder[0] = "extend"
                        elif resp == NSAlertSecondButtonReturn:
                            mode_holder[0] = "replace"
                        else:
                            mode_holder[0] = "cancel"
                        done.set()

                    on_main(ask_user)
                    done.wait()

                    if mode_holder[0] == "cancel":
                        on_main(self._show_main)
                        return
                    mode = mode_holder[0]
                    assert mode is not None
                else:
                    mode = "new"

                result = transfer.run_transfer_from_fetched(
                    playlist_name, spotify_tracks, mode, log=lambda _: None
                )
                on_main(lambda: self._show_results(result))

            except Exception as exc:
                captured = exc
                def show_err():
                    a = NSAlert.alloc().init()
                    a.setMessageText_("Import failed")
                    a.setInformativeText_(str(captured))
                    a.runModal()
                    self._show_main()
                on_main(show_err)

        threading.Thread(target=run, daemon=True).start()

    def backToMain_(self, _sender):
        self._show_main()

    # ── Settings sheet ────────────────────────────────────────────────────────

    def showSettings_(self, _sender):
        sw, sh = 480, 330
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        panel = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, sw, sh), style, NSBackingStoreBuffered, False
        )
        panel.setTitle_("Settings")
        self._settings_panel = panel
        v = panel.contentView()

        pad, fw, fh = 24, sw - 48, 28
        y = sh - 44

        def add_label(text, y_pos):
            lbl = NSTextField.labelWithString_(text)
            lbl.setFrame_(NSMakeRect(pad, y_pos, fw, 17))
            lbl.setFont_(NSFont.boldSystemFontOfSize_(12))
            v.addSubview_(lbl)

        def add_field(placeholder, y_pos, secure=False):
            f = _field(NSMakeRect(pad, y_pos, fw, fh), placeholder, secure=secure)
            v.addSubview_(f)
            return f

        add_label("Spotify Client ID", y);          y -= 22
        self._f_id     = add_field("Client ID", y); y -= fh + 14

        add_label("Spotify Client Secret", y);      y -= 22
        self._f_secret = add_field("Client Secret", y, secure=True); y -= fh + 14

        add_label("Authorization Redirect URL", y); y -= 22
        self._f_auth   = add_field(
            "Paste the full redirect URL after authorizing…", y
        );                                           y -= fh + 10

        open_btn = NSButton.alloc().initWithFrame_(NSMakeRect(pad, y, 260, 22))
        open_btn.setTitle_("Open Spotify Authorization Page →")
        open_btn.setBezelStyle_(15)   # NSBezelStyleInline
        open_btn.setTarget_(self)
        open_btn.setAction_("openSpotifyAuth:")
        v.addSubview_(open_btn)

        creds = load_credentials()
        self._f_id.setStringValue_(creds["client_id"])
        self._f_secret.setStringValue_(creds["client_secret"])

        by, bh = 14, 32
        v.addSubview_(_button(
            NSMakeRect(pad, by, 88, bh), "Cancel", self, "cancelSettings:", key="\033",
        ))
        v.addSubview_(_button(
            NSMakeRect(sw - 270, by, 128, bh), "Delete All Data", self, "deleteData:",
            color=NSColor.systemRedColor(),
        ))
        v.addSubview_(_button(
            NSMakeRect(sw - 130, by, 106, bh), "Save", self, "saveSettings:", key="\r",
        ))

        self.window.beginSheet_completionHandler_(panel, None)

    def saveSettings_(self, _sender):
        client_id = self._f_id.stringValue().strip()
        secret    = self._f_secret.stringValue().strip()
        auth_url  = self._f_auth.stringValue().strip()

        if not client_id or not secret:
            a = NSAlert.alloc().init()
            a.setMessageText_("Missing credentials")
            a.setInformativeText_("Please enter both Client ID and Client Secret.")
            a.runModal()
            return

        save_credentials(client_id, secret)

        if auth_url:
            try:
                transfer.exchange_token(client_id, secret, auth_url)
            except Exception as exc:
                a = NSAlert.alloc().init()
                a.setMessageText_("Authorization failed")
                a.setInformativeText_(str(exc))
                a.runModal()
                return

        self.window.endSheet_(self._settings_panel)
        self._settings_panel.orderOut_(None)

    def cancelSettings_(self, _sender):
        self.window.endSheet_(self._settings_panel)
        self._settings_panel.orderOut_(None)

    def deleteData_(self, _sender):
        a = NSAlert.alloc().init()
        a.setMessageText_("Delete all stored data?")
        a.setInformativeText_("This removes your Spotify credentials and authorization token.")
        a.addButtonWithTitle_("Delete")
        a.addButtonWithTitle_("Cancel")
        if a.runModal() == NSAlertFirstButtonReturn:
            delete_all_data()
            self._f_id.setStringValue_("")
            self._f_secret.setStringValue_("")
            self._f_auth.setStringValue_("")

    def openSpotifyAuth_(self, _sender):
        client_id = self._f_id.stringValue().strip()
        secret    = self._f_secret.stringValue().strip()
        if not client_id or not secret:
            a = NSAlert.alloc().init()
            a.setMessageText_("Enter credentials first")
            a.setInformativeText_(
                "Fill in Client ID and Client Secret before opening authorization."
            )
            a.runModal()
            return
        try:
            url = transfer.get_auth_url(client_id, secret)
            NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
        except Exception as exc:
            a = NSAlert.alloc().init()
            a.setMessageText_("Error")
            a.setInformativeText_(str(exc))
            a.runModal()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    NSProcessInfo.processInfo().setValue_forKey_("Playlist Transferer", "processName")
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
