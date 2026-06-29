"""Localization helpers for VoxScribe UI.

The interface is intentionally fixed to English. Input and output language
settings control transcription only, not the application chrome.
"""

UI_LANGUAGE = "en"
_current_ui_language = UI_LANGUAGE

TRANSLATIONS = {
    "PREPARING": {"en": "PREPARING", "id": "MENYIAPKAN", "zh": "准备中"},
    "READY": {"en": "READY", "id": "SIAP", "zh": "就绪"},
    "ACTIVE": {"en": "ACTIVE", "id": "AKTIF", "zh": "处理中"},
    "SWITCHING": {"en": "SWITCHING", "id": "BERGANTI", "zh": "切换中"},
    "ERROR": {"en": "ERROR", "id": "ERROR", "zh": "错误"},
    "STOPPED": {"en": "STOPPED", "id": "BERHENTI", "zh": "已停止"},
    "STATUS: INITIALIZATION IN PROGRESS": {"en": "STATUS: INITIALIZATION IN PROGRESS", "id": "STATUS: INISIALISASI", "zh": "状态：正在初始化"},
    "Start Transcription": {"en": "Start Transcription", "id": "Mulai Transkripsi", "zh": "开始转录"},
    "Overlay Mode": {"en": "Overlay Mode", "id": "Mode Overlay", "zh": "浮窗模式"},
    "Save": {"en": "Save", "id": "Simpan", "zh": "保存"},
    "Clear": {"en": "Clear", "id": "Hapus", "zh": "清除"},
    "Input Language": {"en": "Input Language", "id": "Bahasa Input", "zh": "输入语言"},
    "Output Language": {"en": "Output Language", "id": "Bahasa Output", "zh": "输出语言"},
    "Audio Source": {"en": "Audio Source", "id": "Sumber Audio", "zh": "音频源"},
    "History": {"en": "History", "id": "Riwayat", "zh": "历史记录"},
    "Active: {label}": {"en": "Active: {label}", "id": "Aktif: {label}", "zh": "当前：{label}"},
    "Transcription ({label})": {"en": "Transcription ({label})", "id": "Transkripsi ({label})", "zh": "转录（{label}）"},
    "Source ({label})": {"en": "Source ({label})", "id": "Sumber ({label})", "zh": "源语言（{label}）"},
    "Active: {label} | Preparing: {label}": {"en": "Active: {label} | Preparing: {label}", "id": "Aktif: {label} | Menyiapkan: {label}", "zh": "当前：{label} | 准备：{label}"},
    "Source: {label}": {"en": "Source: {label}", "id": "Sumber: {label}", "zh": "源语言：{label}"},
    "Translation: {label}": {"en": "Translation: {label}", "id": "Terjemahan: {label}", "zh": "翻译：{label}"},
    "Output language: {label}": {"en": "Output language: {label}", "id": "Bahasa output: {label}", "zh": "输出语言：{label}"},
    "Audio source: {label}": {"en": "Audio source: {label}", "id": "Sumber audio: {label}", "zh": "音频源：{label}"},
    "Retry Start": {"en": "Retry Start", "id": "Coba Lagi", "zh": "重试"},
    "Preparing...": {"en": "Preparing...", "id": "Menyiapkan...", "zh": "准备中..."},
    "Checking...": {"en": "Checking...", "id": "Memeriksa...", "zh": "检查中..."},
    "Downloading...": {"en": "Downloading...", "id": "Mengunduh...", "zh": "下载中..."},
    "Starting...": {"en": "Starting...", "id": "Memulai...", "zh": "启动中..."},
    "Stop Transcription": {"en": "Stop Transcription", "id": "Hentikan Transkripsi", "zh": "停止转录"},
    "Installing...": {"en": "Installing...", "id": "Menginstal...", "zh": "安装中..."},
    "Processing...": {"en": "Processing...", "id": "Memproses...", "zh": "处理中..."},
    "Press Start to begin transcription.": {"en": "Press Start to begin transcription.", "id": "Tekan Mulai untuk memulai transkripsi.", "zh": "按开始以开始转录"},
    "Please wait until preparation finishes.": {"en": "Please wait until preparation finishes.", "id": "Mohon tunggu hingga persiapan selesai.", "zh": "请等待准备完成"},
    "Ready - Click Start Transcription": {"en": "Ready - Click Start Transcription", "id": "Siap - Klik Mulai Transkripsi", "zh": "就绪 - 点击开始转录"},
    "Audio device not ready. Check Windows output device and retry.": {"en": "Audio device not ready. Check Windows output device and retry.", "id": "Perangkat audio belum siap. Periksa output device Windows dan coba lagi.", "zh": "音频设备未就绪。请检查Windows输出设备并重试。"},
    "Failed to prepare speech model": {"en": "Failed to prepare speech model", "id": "Gagal menyiapkan model speech", "zh": "语音模型准备失败"},
    "Processing ({label})... Press F5 to stop": {"en": "Processing ({label})... Press F5 to stop", "id": "Memproses ({label})... Tekan F5 untuk berhenti", "zh": "处理中（{label}）... 按F5停止"},
    "Stopped. Click Start Transcription when ready.": {"en": "Stopped. Click Start Transcription when ready.", "id": "Berhenti. Klik Mulai Transkripsi jika sudah siap.", "zh": "已停止。准备就绪后点击开始转录。"},
    "Transcription error: {error}. Click Retry Start.": {"en": "Transcription error: {error}. Click Retry Start.", "id": "Error transkripsi: {error}. Klik Coba Lagi.", "zh": "转录错误：{error}。点击重试。"},
    "Transcript cleared.": {"en": "Transcript cleared.", "id": "Transkrip dihapus.", "zh": "转录已清除"},
    "Saved: {filename}": {"en": "Saved: {filename}", "id": "Disimpan: {filename}", "zh": "已保存：{filename}"},
    "Save failed. Choose another location.": {"en": "Save failed. Choose another location.", "id": "Gagal menyimpan. Pilih lokasi lain.", "zh": "保存失败。请选择其他位置。"},
    "Audio system is not available": {"en": "Audio system is not available", "id": "Sistem audio tidak tersedia", "zh": "音频系统不可用"},
    "Transcription did not start. Check audio output and retry.": {"en": "Transcription did not start. Check audio output and retry.", "id": "Transkripsi gagal mulai. Periksa output audio dan coba lagi.", "zh": "转录未启动。请检查音频输出并重试。"},
    "Transcription failed to start. Check audio output and retry.": {"en": "Transcription failed to start. Check audio output and retry.", "id": "Transkripsi gagal mulai. Periksa output audio dan coba lagi.", "zh": "转录启动失败。请检查音频输出并重试。"},
    "Failed to install Whisper engine. Check internet and retry.": {"en": "Failed to install Whisper engine. Check internet and retry.", "id": "Gagal menginstal Whisper engine. Periksa internet dan coba lagi.", "zh": "Whisper引擎安装失败。请检查网络并重试。"},
    "Checking {label} model and audio device...": {"en": "Checking {label} model and audio device...", "id": "Memeriksa model {label} dan perangkat audio...", "zh": "正在检查{label}模型和音频设备..."},
    "Preparing {label} model for startup...": {"en": "Preparing {label} model for startup...", "id": "Menyiapkan model {label} untuk startup...", "zh": "正在准备{label}模型..."},
    "First-time preparation for {label} model...": {"en": "First-time preparation for {label} model...", "id": "Persiapan pertama untuk model {label}...", "zh": "首次准备{label}模型..."},
    "{label} model is missing. Opening download...": {"en": "{label} model is missing. Opening download...", "id": "Model {label} tidak ditemukan. Membuka download...", "zh": "{label}模型缺失。正在打开下载..."},
    "Preparing Whisper model...": {"en": "Preparing Whisper model...", "id": "Menyiapkan model Whisper...", "zh": "正在准备Whisper模型..."},
    "Preparing audio device...": {"en": "Preparing audio device...", "id": "Menyiapkan perangkat audio...", "zh": "正在准备音频设备..."},
    "Preparing audio device before starting transcription...": {"en": "Preparing audio device before starting transcription...", "id": "Menyiapkan perangkat audio sebelum memulai transkripsi...", "zh": "启动转录前准备音频设备..."},
    "Transcription is starting...": {"en": "Transcription is starting...", "id": "Transkripsi sedang dimulai...", "zh": "转录启动中..."},
    "Audio sedang disiapkan... transcription akan mulai otomatis.": {"en": "Preparing audio... transcription will start automatically.", "id": "Audio sedang disiapkan... transkripsi akan mulai otomatis.", "zh": "音频准备中... 转录将自动开始。"},
    "Model sedang disiapkan... transcription akan mulai otomatis.": {"en": "Preparing model... transcription will start automatically.", "id": "Model sedang disiapkan... transkripsi akan mulai otomatis.", "zh": "模型准备中... 转录将自动开始。"},
    "Starting transcription ({label})...": {"en": "Starting transcription ({label})...", "id": "Memulai transkripsi ({label})...", "zh": "正在启动转录（{label}）..."},
    "Installing Whisper engine dependency...": {"en": "Installing Whisper engine dependency...", "id": "Menginstal dependensi Whisper engine...", "zh": "正在安装Whisper引擎依赖..."},
    "Installing {label} engine...": {"en": "Installing {label} engine...", "id": "Menginstal engine {label}...", "zh": "正在安装{label}引擎..."},
    "{label} transcription will appear here.": {"en": "{label} transcription will appear here.", "id": "Transkripsi {label} akan muncul di sini.", "zh": "{label}转录将显示在此处。"},
    "Terjemahan sementara tidak tersedia.": {"en": "Translation temporarily unavailable.", "id": "Terjemahan sementara tidak tersedia.", "zh": "翻译暂时不可用。"},
    "Preparing": {"en": "Preparing", "id": "Menyiapkan", "zh": "准备中"},
    "Ready": {"en": "Ready", "id": "Siap", "zh": "就绪"},
    "Processing": {"en": "Processing", "id": "Memproses", "zh": "处理中"},
    "Switching": {"en": "Switching", "id": "Berganti", "zh": "切换中"},
    "Needs attention": {"en": "Needs attention", "id": "Perlu perhatian", "zh": "需要注意"},
    "Stopped": {"en": "Stopped", "id": "Berhenti", "zh": "已停止"},
    "Translating... {text}": {"en": "Translating... {text}", "id": "Menerjemahkan... {text}", "zh": "翻译中... {text}"},
    "VoxScribe | {status}": {"en": "VoxScribe | {status}", "id": "VoxScribe | {status}", "zh": "VoxScribe | {status}"},
    "Stop": {"en": "Stop", "id": "Stop", "zh": "停止"},
    "Wait": {"en": "Wait", "id": "Tunggu", "zh": "等待"},
    "Start": {"en": "Start", "id": "Mulai", "zh": "开始"},
    "Menu": {"en": "Menu", "id": "Menu", "zh": "菜单"},
    "Caption": {"en": "Caption", "id": "Caption", "zh": "字幕"},
    "Input": {"en": "Input", "id": "Input", "zh": "输入"},
    "Output": {"en": "Output", "id": "Output", "zh": "输出"},
    "Transcript": {"en": "Transcript", "id": "Transkrip", "zh": "转录"},
    "Font size: {n}": {"en": "Font size: {n}", "id": "Ukuran font: {n}", "zh": "字体大小：{n}"},
    "Reset Bottom": {"en": "Reset Bottom", "id": "Reset Posisi", "zh": "重置位置"},
    "Exit": {"en": "Exit", "id": "Keluar", "zh": "退出"},
    "F5 Start/Stop  |  Ctrl+Shift+C Pill/Subtitle": {"en": "F5 Start/Stop  |  Ctrl+Shift+C Pill/Subtitle", "id": "F5 Mulai/Berhenti  |  Ctrl+Shift+C Pill/Subtitle", "zh": "F5 开始/停止  |  Ctrl+Shift+C 切换模式"},
    "No transcript yet.": {"en": "No transcript yet.", "id": "Belum ada transkrip.", "zh": "暂无转录"},
    "Words: {n} | Duration: {time}": {"en": "Words: {n} | Duration: {time}", "id": "Kata: {n} | Durasi: {time}", "zh": "字数：{n} | 时长：{time}"},
    " | WPM: {wpm:.1f}": {"en": " | WPM: {wpm:.1f}", "id": " | KPM: {wpm:.1f}", "zh": " | 字/分：{wpm:.1f}"},
}


def set_ui_language(language_code: str):
    """Keep backward-compatible locale API while pinning UI text to English."""
    global _current_ui_language
    _current_ui_language = UI_LANGUAGE


def get_ui_language() -> str:
    return _current_ui_language


def _L(text: str) -> str:
    """Translate a user-facing string to the current UI language."""
    lang = UI_LANGUAGE
    entry = TRANSLATIONS.get(text)
    if entry and lang in entry:
        return entry[lang]
    return text


def translate(text: str, language_code: str) -> str:
    """Translate a string to a specific language (bypasses global UI language)."""
    lang = language_code
    if lang and lang.startswith("zh"):
        lang = "zh"
    entry = TRANSLATIONS.get(text)
    if entry and lang in entry:
        return entry[lang]
    return text
