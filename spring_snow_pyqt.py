# -*- coding: utf-8 -*-
r"""
春之雪考研英语助手 (PyQt 版)
UI 架构完全遵循 D:\code\arm\gnss_host.py 的上位机实现：
  - QMainWindow + FramelessWindowHint
  - QWidget#mainRoot 作为 setCentralWidget，border-image 铺背景
  - QVBoxLayout: 自定义 titleBar (logo/最小化/最大化/关闭 + 拖拽)  +  page_stack(QStackedWidget)
  - page0 EnglishPage: 左上 QGroupBox 控制区 + 大 QTableWidget 错词表
  - page1 ~ page5: 仪表盘 / 单词 / 语法 / 阅读 / 设置 占位卡
  - QGroupBox / QLineEdit / QTableWidget 统一 rgba 半透明卡片
"""
from __future__ import annotations

import os
import sys
import uuid
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta, datetime
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer, QSize, QPoint, QPointF, QRectF, QUrl, QEventLoop, QThread, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import (
    QIcon, QPixmap, QImage, QFont, QColor, QPainter, QBrush, QPen, QKeySequence,
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QStackedWidget, QGroupBox, QLineEdit, QComboBox, QPlainTextEdit,
    QFileDialog, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDialog, QDialogButtonBox, QTextEdit, QTextBrowser, QShortcut,
    QSizePolicy, QSplitter, QCheckBox, QScrollArea, QFrame, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QGraphicsOpacityEffect,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineSettings
    _HAS_WEBENGINE = True
except Exception:
    QWebEngineView = None  # type: ignore[assignment,misc]
    QWebEnginePage = None  # type: ignore[assignment,misc]
    QWebEngineSettings = None  # type: ignore[assignment,misc]
    _HAS_WEBENGINE = False


# 自定义 WebPage: 让所有 target="_blank" 的新窗口请求直接在当前页面打开
# (解决 B 站视频/搜索按钮点了"黑屏/页面不跳转"的问题)
class _CourseWebPage(QWebEnginePage if QWebEnginePage is not None else object):
    def __init__(self, view_ref, profile=None):
        if QWebEnginePage is None:
            super().__init__()
            return
        if profile is None:
            super().__init__(view_ref)
        else:
            super().__init__(profile, view_ref)
        self._view_ref = view_ref
        self._tmp_pages: list = []

    def acceptNavigationRequest(self, url, nav_type, isMainFrame):  # type: ignore[override]
        # 所有导航全部交给 WebEngine 自己处理 (留在应用内置浏览器内播放, 不弹外部浏览器)
        return True

    def createWindow(self, _window_type):  # type: ignore[override]
        # PyQt5 5.15 的 createWindow() 必须返回 QWebEnginePage, 不能返回 QWebEngineView
        # 思路: 新建一个临时 Page, 等它拿到目标 URL 就交给主 view 加载, 然后销毁临时 Page
        tmp = QWebEnginePage(self._view_ref)
        self._tmp_pages.append(tmp)

        def _capture_url(qurl):
            try:
                tmp.urlChanged.disconnect(_capture_url)
            except Exception:
                pass
            url_str = ""
            try:
                url_str = qurl.toString()
            except Exception:
                pass
            if url_str and url_str not in ("", "about:blank"):
                self._view_ref.load(qurl)
            QTimer.singleShot(0, lambda: self._cleanup(tmp))

        tmp.urlChanged.connect(_capture_url)
        return tmp

    def _cleanup(self, page) -> None:
        try:
            if page in self._tmp_pages:
                self._tmp_pages.remove(page)
        except Exception:
            pass
        try:
            page.setParent(None)
            page.deleteLater()
        except Exception:
            pass


# ===========================================================
# 常量 & 存储 (直接沿用原 spring_snow_kaoyan.py 的结构)
# ===========================================================
APP_TITLE = "春之雪考研小助手"
APP_VERSION = "v2.1-PyQt"
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "kaoyan_data.json"
FOCUS_DATA_PATH = BASE_DIR / "focus_sessions.json"
AI_CHAT_HISTORY_PATH = BASE_DIR / "ai_chat_history.json"
BACKGROUND_PATH = Path(r"D:\code\english\image\kaoyan_background.png")
IMAGE_DIR = Path(r"D:\code\english\image")


QUOTES: List[str] = [
    "日拱一卒，功不唐捐。",
    "追风赶月莫停留，平芜尽处是春山。",
    "路虽远，行则将至；事虽难，做则必成。",
    "凡是过往，皆为序章。",
    "种一棵树最好的时间是十年前，其次是现在。",
    "你每多学一个知识点，考场上就少慌一次。",
    "别人的懈怠，都是你超越的机会。",
    "所谓奇迹，不过是你熬到最后的奖励。",
    "所有的惊艳，都来自长久的准备。",
    "今天的努力，是为了将来能从容选择。",
    "相信时间的复利，把单词、错题、真题做扎实。",
    "稳住节奏，不要和别人比进度，你有自己的花期。",
]

NOTE_SUBJECTS: Tuple[str, ...] = ("英语", "数学", "专业课")

# 考研高频词种子表 (P0-D) - 用户可后续用 JSON 导入完整 5500 词
KAOYAN_VOCAB_SEED: List[Dict[str, str]] = [
    {"word": "abandon", "phonetic": "/əˈbændən/", "meaning": "vt. 放弃；遗弃；抛弃", "example": "He abandoned his career for family."},
    {"word": "benefit", "phonetic": "/ˈbenɪfɪt/", "meaning": "n. 利益；好处 v. 有益于", "example": "Reading benefits the mind."},
    {"word": "challenge", "phonetic": "/ˈtʃælɪndʒ/", "meaning": "n. 挑战 vt. 向…挑战", "example": "The exam was a real challenge."},
    {"word": "determine", "phonetic": "/dɪˈtɜːmɪn/", "meaning": "v. 决定；决心；查明", "example": "She determined to win."},
    {"word": "evidence", "phonetic": "/ˈevɪdəns/", "meaning": "n. 证据；迹象", "example": "There is no evidence to support it."},
    {"word": "factor", "phonetic": "/ˈfæktə(r)/", "meaning": "n. 因素；要素", "example": "Money is a key factor."},
    {"word": "generate", "phonetic": "/ˈdʒenəreɪt/", "meaning": "vt. 产生；引起", "example": "Wind generates power."},
    {"word": "handle", "phonetic": "/ˈhændl/", "meaning": "v. 处理；操纵 n. 把手", "example": "She handled the problem well."},
    {"word": "indicate", "phonetic": "/ˈɪndɪkeɪt/", "meaning": "vt. 指出；表明；象征", "example": "The arrow indicates north."},
    {"word": "justify", "phonetic": "/ˈdʒʌstɪfaɪ/", "meaning": "v. 证明…正当；辩护", "example": "Nothing justifies his act."},
    {"word": "knowledge", "phonetic": "/ˈnɒlɪdʒ/", "meaning": "n. 知识；学问；认识", "example": "Knowledge is power."},
    {"word": "launch", "phonetic": "/lɔːntʃ/", "meaning": "v. 发起；发射；启动", "example": "They launched a new project."},
    {"word": "maintain", "phonetic": "/meɪnˈteɪn/", "meaning": "vt. 维持；保养；主张", "example": "Maintain a healthy diet."},
    {"word": "notion", "phonetic": "/ˈnəʊʃn/", "meaning": "n. 概念；观念；想法", "example": "He has no notion of time."},
    {"word": "obtain", "phonetic": "/əbˈteɪn/", "meaning": "v. 获得；得到", "example": "She obtained the data."},
    {"word": "potential", "phonetic": "/pəˈtenʃl/", "meaning": "adj. 潜在的 n. 潜力", "example": "She has great potential."},
    {"word": "qualify", "phonetic": "/ˈkwɒlɪfaɪ/", "meaning": "v. (使)具有资格", "example": "He qualified for the final."},
    {"word": "recognize", "phonetic": "/ˈrekəɡnaɪz/", "meaning": "vt. 认出；承认", "example": "I recognized her voice."},
    {"word": "significant", "phonetic": "/sɪɡˈnɪfɪkənt/", "meaning": "adj. 重要的；意义重大的", "example": "A significant change occurred."},
    {"word": "theory", "phonetic": "/ˈθɪəri/", "meaning": "n. 理论；学说；观点", "example": "In theory, it should work."},
    {"word": "unique", "phonetic": "/juˈniːk/", "meaning": "adj. 独一无二的；独特的", "example": "Each person is unique."},
    {"word": "valid", "phonetic": "/ˈvælɪd/", "meaning": "adj. 有效的；合理的", "example": "The ticket is valid."},
    {"word": "wealth", "phonetic": "/welθ/", "meaning": "n. 财富；富有；大量", "example": "Health is better than wealth."},
    {"word": "yield", "phonetic": "/jiːld/", "meaning": "v. 产出；屈服 n. 产量", "example": "The tree yields apples."},
    {"word": "adapt", "phonetic": "/əˈdæpt/", "meaning": "v. (使)适应；改编", "example": "She adapted to the new life."},
    {"word": "consequence", "phonetic": "/ˈkɒnsɪkwəns/", "meaning": "n. 结果；后果；重要性", "example": "Think of the consequences."},
    {"word": "distinguish", "phonetic": "/dɪˈstɪŋɡwɪʃ/", "meaning": "v. 区分；辨别", "example": "Can you distinguish them?"},
    {"word": "establish", "phonetic": "/ɪˈstæblɪʃ/", "meaning": "vt. 建立；确立", "example": "They established a school."},
    {"word": "fundamental", "phonetic": "/ˌfʌndəˈmentl/", "meaning": "adj. 基本的 n. 基本原理", "example": "Fundamental rights matter."},
    {"word": "inevitable", "phonetic": "/ɪnˈevɪtəbl/", "meaning": "adj. 不可避免的；必然的", "example": "Change is inevitable."},
]

import webbrowser as _webbrowser

# 命中以下域名/路径的导航, 认为是视频/网课播放页 -> 改用系统默认浏览器打开,
# 这样绕开 PyQtWebEngine 对 H.264/AAC 的编解码限制, 100% 能播放.
_COURSE_OPEN_EXTERNAL_PATTERNS: Tuple[str, ...] = (
    "bilibili.com/video/",
    "bilibili.com/bangumi/",
    "bilibili.com/medialist/",
    "b23.tv/",
    "youku.com/v_show/",
    "v.qq.com/x/cover",
    "v.qq.com/x/page",
    "iqiyi.com/v_",
    "iqiyi.com/a_",
    "icourse163.org/learn/",
    "icourse163.org/spoc/learn/",
    "xuetangx.com/course/",
    "imooc.com/learn/",
    "imooc.com/video/",
    "open.163.com/newview/",
    "open.163.com/movie/",
    "study.163.com/course/",
    "zhihuishu.com/",
    "chaoxing.com/",
    "ke.qq.com/course/",
    "class.duokan.com/",
    "kouda.baidu.com/",
)


def iso(d: date) -> str:
    return datetime.combine(d, datetime.min.time()).isoformat(timespec="seconds")


def _is_external_video_url(url: str) -> bool:
    """命中视频/网课域名 -> True (调用系统默认浏览器打开更稳妥)"""
    if not url:
        return False
    u = url.strip().lower()
    if u.startswith("about:") or u.startswith("data:") or u.startswith("chrome-") or u.startswith("devtools:"):
        return False
    return any(p in u for p in _COURSE_OPEN_EXTERNAL_PATTERNS)


def _open_in_system_browser(url: str) -> None:
    try:
        _webbrowser.open(url, new=2)
    except Exception:
        pass


def today() -> date:
    return date.today()


@dataclass
class FocusSession:
    """一次专注会话"""
    task: str = ""                  # 专注任务名
    target_minutes: int = 25        # 目标时长 (分钟)
    actual_seconds: int = 0         # 实际专注秒数 (完成时 = target*60, 中途停止则为已计秒数)
    completed: bool = False         # 是否完成目标
    started_at: str = ""            # 开始时间 ISO
    ended_at: str = ""              # 结束时间 ISO
    date: str = ""                  # 日期 YYYY-MM-DD (用于按日统计)


class FocusStore:
    """专注会话持久化 (独立 JSON, 不影响主数据)"""
    def __init__(self):
        self.sessions: List[Dict[str, Any]] = []

    @classmethod
    def load(cls) -> "FocusStore":
        s = cls()
        if FOCUS_DATA_PATH.exists():
            try:
                data = json.loads(FOCUS_DATA_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("sessions"), list):
                    s.sessions = data["sessions"]
            except Exception:
                pass
        return s

    def save(self) -> None:
        try:
            FOCUS_DATA_PATH.write_text(
                json.dumps({"sessions": self.sessions}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self, sess: FocusSession) -> None:
        self.sessions.append({
            "task": sess.task,
            "target_minutes": sess.target_minutes,
            "actual_seconds": sess.actual_seconds,
            "completed": sess.completed,
            "started_at": sess.started_at,
            "ended_at": sess.ended_at,
            "date": sess.date,
        })
        self.save()

    def today_sessions(self) -> List[Dict[str, Any]]:
        t = today().isoformat()
        return [s for s in self.sessions if s.get("date") == t]

    def today_total_minutes(self) -> int:
        return sum(s.get("actual_seconds", 0) for s in self.today_sessions()) // 60

    def today_completed_count(self) -> int:
        return sum(1 for s in self.today_sessions() if s.get("completed"))

    def recent(self, n: int = 20) -> List[Dict[str, Any]]:
        return self.sessions[-n:][::-1]


# ===========================================================
# AI 聊天面板 (P0-A)
# ===========================================================
class AIChatHistory:
    """AI 对话历史持久化 (独立 JSON 文件)"""
    def __init__(self):
        self.sessions: List[Dict[str, Any]] = []

    @classmethod
    def load(cls) -> "AIChatHistory":
        h = cls()
        if AI_CHAT_HISTORY_PATH.exists():
            try:
                data = json.loads(AI_CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("sessions"), list):
                    h.sessions = data["sessions"]
            except Exception:
                pass
        return h

    def save(self) -> None:
        try:
            AI_CHAT_HISTORY_PATH.write_text(
                json.dumps({"sessions": self.sessions}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def new_session(self, title: str = "新对话") -> str:
        import uuid as _uuid
        sid = _uuid.uuid4().hex
        self.sessions.append({
            "id": sid,
            "title": title,
            "messages": [],
            "created_at": datetime.now().isoformat(),
        })
        self.save()
        return sid

    def get_session(self, sid: str) -> Optional[Dict[str, Any]]:
        for s in self.sessions:
            if s.get("id") == sid:
                return s
        return None

    def add_message(self, sid: str, role: str, content: str) -> None:
        s = self.get_session(sid)
        if s is None:
            return
        s["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        # 自动用第一条用户消息更新标题
        if role == "user" and s["title"] in ("新对话", ""):
            s["title"] = content[:20] + ("…" if len(content) > 20 else "")
        self.save()

    def delete_session(self, sid: str) -> None:
        self.sessions = [s for s in self.sessions if s.get("id") != sid]
        self.save()

    def session_titles(self) -> List[tuple]:
        """返回 [(id, title), ...] 倒序(最新在前)"""
        return [(s.get("id", ""), s.get("title", "新对话")) for s in reversed(self.sessions)]


class AIWorkerThread(QThread):
    """后台线程调用 OpenAI 兼容 API (P0-A 非流式, P0-B 升级流式)"""
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    chunk_received = pyqtSignal(str)  # P0-B 流式用

    def __init__(self, settings: dict, messages: list, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._messages = messages
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            import urllib.request
            import urllib.error
            base_url = self._settings.get("ai_base_url", "").rstrip("/")
            api_key = self._settings.get("ai_api_key", "")
            model = self._settings.get("ai_model", "")
            if not api_key:
                self.error_occurred.emit("未配置 API Key, 请点击右上角齿轮设置。")
                return
            url = f"{base_url}/chat/completions"
            payload = {
                "model": model,
                "messages": self._messages,
                "stream": True,        # P0-B 流式
                "temperature": 0.7,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Accept", "text/event-stream")
            # 国内 API (如 siliconflow) 无需代理; 禁用系统代理避免本地代理未启动时被拒绝
            no_proxy_opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({})
            )
            full = []
            with no_proxy_opener.open(req, timeout=120) as resp:
                # SSE 逐行读取
                for raw in resp:
                    if self._stop:
                        break
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[len("data:"):].strip()
                    if body == "[DONE]":
                        break
                    try:
                        obj = json.loads(body)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}) or {}
                    chunk = delta.get("content", "") or ""
                    if chunk:
                        full.append(chunk)
                        self.chunk_received.emit(chunk)
            content = "".join(full)
            if self._stop:
                # 中断: 仍把已收到的部分作为结果返回 (UI 决定是否保存)
                self.response_ready.emit(content + "\n\n_(已中断)_")
            elif not content:
                self.error_occurred.emit("API 返回空内容 (stream)。")
            else:
                self.response_ready.emit(content)
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                self.error_occurred.emit(f"HTTP {e.code}: {err_body[:300]}")
            except Exception:
                self.error_occurred.emit(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.error_occurred.emit(f"请求失败: {e}")


# ===========================================================
# iOS 风格长圆形滑动开关 (Sun / Moon)
# ===========================================================
class ThemeToggleSwitch(QWidget):
    """iOS 风格长圆滑动开关: 关闭=☀️ 浅色, 开启=🌙 深色"""

    toggled = pyqtSignal(bool)  # True=深色, False=浅色

    def __init__(self, checked: bool = False, parent=None, size: tuple = (62, 32)):
        super().__init__(parent)
        self.setFixedSize(*size)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = checked
        self._track_w = size[0]
        self._track_h = size[1]
        self._knob_r = (size[1] - 4) // 2  # 滑块半径
        self._knob_x = self._knob_r + 2 if not checked else self._track_w - self._knob_r - 2
        # 平滑动画
        self._anim = QPropertyAnimation(self, b"knob_x", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 1. 圆角矩形轨道
        track_color = QColor("#111827") if self._checked else QColor("#e2e8f0")
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(0, 0, self._track_w, self._track_h, self._track_h // 2, self._track_h // 2)
        # 2. 滑块阴影 + 白色圆
        knob_color = QColor("#ffffff")
        # 阴影
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawEllipse(QPointF(self._knob_x + 1, self._track_h / 2 + 1), self._knob_r, self._knob_r)
        # 滑块
        p.setPen(QPen(QColor("#cbd5e1"), 1))
        p.setBrush(knob_color)
        p.drawEllipse(QPointF(self._knob_x, self._track_h / 2), self._knob_r, self._knob_r)
        # 3. 图标: ☀️ / 🌙
        p.setPen(QColor("#f59e0b" if not self._checked else "#475569"))
        font = p.font()
        font.setPointSize(int(self._knob_r * 0.95))
        font.setBold(True)
        p.setFont(font)
        if not self._checked:
            # ☀️ 在滑块里 (左侧)
            p.drawText(
                QRectF(
                    self._knob_x - self._knob_r, 0,
                    self._knob_r * 2, self._track_h,
                ),
                Qt.AlignCenter, "☀",
            )
        else:
            # 🌙 在滑块里 (右侧)
            p.drawText(
                QRectF(
                    self._knob_x - self._knob_r, 0,
                    self._knob_r * 2, self._track_h,
                ),
                Qt.AlignCenter, "🌙",
            )

    def _get_knob_x(self) -> float:
        return self._knob_x

    def _set_knob_x(self, v: float):
        self._knob_x = v
        self.update()

    knob_x = pyqtProperty(float, fget=_get_knob_x, fset=_set_knob_x)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True):
        if checked == self._checked:
            return
        self._checked = checked
        target = self._track_w - self._knob_r - 2 if checked else self._knob_r + 2
        if animate and self._anim is not None:
            try:
                self._anim.stop()
                self._anim.setStartValue(self._knob_x)
                self._anim.setEndValue(target)
                self._anim.start()
            except RuntimeError:
                self._knob_x = target
                self.update()
        else:
            self._knob_x = target
            self.update()
        # 关键: 状态变化时发射信号
        self.toggled.emit(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            print(f"[ThemeToggleSwitch] click! _checked={self._checked} -> toggling")
            self.setChecked(not self._checked)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 兼容: 有时 release 才会触发
            pass


# ===========================================================
# 主题设置弹窗 (白天/夜晚 长圆形滑动)
# ===========================================================
class ThemeDialog(QDialog):
    """主题设置弹窗 - 完整白天/夜晚长圆形滑动切换 + 主题预览"""

    PRESETS = [
        # (id, 显示名, 主背景, 卡片背景, 边框, 标题栏背景, 强调色, 强调色前景)
        ("light", "☀️  白天 · TraeCode 浅色", "#f8fafc", "#ffffff", "#e2e8f0", "#ffffff", "#2563eb", "#ffffff"),
        ("dark",  "🌙  夜晚 · 护眼深色",      "#0f172a", "#1e293b", "#334155", "#020617", "#60a5fa", "#0f172a"),
    ]

    def __init__(self, store: StudyStore, main_window=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.main_window = main_window
        self.setWindowTitle("主题设置")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMinimumHeight(440)
        self.setStyleSheet(
            "QDialog{background:#f8fafc;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
            "QScrollBar::handle:vertical{background:#cbd5e1;border-radius:4px;min-height:30px;}"
        )
        self._build_ui()
        self._load()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(16)

        # 顶部 header
        header = QFrame()
        header.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;"
            "  border-top:3px solid #6366f1;border-radius:12px;}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(12)
        icon = QLabel("🎨")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(38, 38)
        icon.setStyleSheet(
            "QLabel{background:#eef2ff;color:#6366f1;"
            "border-radius:19px;font-size:20px;font-weight:900;}"
        )
        hl.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("主题外观")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#0f172a;background:transparent;border:none;")
        col.addWidget(title)
        sub = QLabel("切换日间/夜间模式 · 即时生效 · 自动保存")
        sub.setStyleSheet("font-size:11px;color:#64748b;background:transparent;border:none;")
        col.addWidget(sub)
        hl.addLayout(col, 1)
        v.addWidget(header)

        # 长圆形滑动开关大区域
        switch_card = QFrame()
        switch_card.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;}"
        )
        sl = QVBoxLayout(switch_card)
        sl.setContentsMargins(28, 22, 28, 22)
        sl.setSpacing(14)
        # 标题
        lbl_t = QLabel("外观模式")
        lbl_t.setStyleSheet("font-size:12px;font-weight:800;color:#475569;background:transparent;border:none;")
        sl.addWidget(lbl_t)
        # 横向 row: 左 ☀️ 白天 / 中间大开关 / 右 🌙 夜晚
        row = QHBoxLayout()
        row.setSpacing(18)
        row.setAlignment(Qt.AlignVCenter)
        # 白天图 + 文字
        left_box = QVBoxLayout()
        left_box.setSpacing(2)
        sun = QLabel("☀️")
        sun.setAlignment(Qt.AlignCenter)
        sun.setStyleSheet("font-size:28px;background:transparent;border:none;")
        sun_t = QLabel("白天")
        sun_t.setAlignment(Qt.AlignCenter)
        sun_t.setStyleSheet("font-size:11px;color:#f59e0b;font-weight:800;background:transparent;border:none;")
        left_box.addWidget(sun)
        left_box.addWidget(sun_t)
        row.addLayout(left_box)
        # 大号开关 (94, 46)
        self.toggle = ThemeToggleSwitch(checked=False, size=(94, 46))
        self.toggle.toggled.connect(self._on_toggle)
        row.addWidget(self.toggle, 0, Qt.AlignVCenter)
        # 夜晚图 + 文字
        right_box = QVBoxLayout()
        right_box.setSpacing(2)
        moon = QLabel("🌙")
        moon.setAlignment(Qt.AlignCenter)
        moon.setStyleSheet("font-size:28px;background:transparent;border:none;")
        moon_t = QLabel("夜晚")
        moon_t.setAlignment(Qt.AlignCenter)
        moon_t.setStyleSheet("font-size:11px;color:#475569;font-weight:800;background:transparent;border:none;")
        right_box.addWidget(moon)
        right_box.addWidget(moon_t)
        row.addLayout(right_box)
        row.addStretch(1)
        # 模式名
        self.lbl_mode = QLabel("☀️  白天模式")
        self.lbl_mode.setStyleSheet(
            "font-size:13px;font-weight:800;color:#0f172a;background:transparent;border:none;"
        )
        row.addWidget(self.lbl_mode)
        sl.addLayout(row)
        v.addWidget(switch_card)

        # 主题预览卡片 (2 个并排, 选中态边框)
        preview_lab = QLabel("主题预览")
        preview_lab.setStyleSheet("font-size:12px;font-weight:800;color:#475569;background:transparent;")
        v.addWidget(preview_lab)
        ph = QHBoxLayout()
        ph.setSpacing(10)
        self._preview_cards = []
        for tid, name, bg, card_bg, bd, tb, accent, _ in self.PRESETS:
            card = QFrame()
            card.setCursor(Qt.PointingHandCursor)
            card.setStyleSheet(
                f"QFrame{{background:{card_bg};border:1.5px solid {bd};border-radius:12px;}}"
                f"QFrame:hover{{border:2px solid {accent};}}"
            )
            card.setFixedHeight(120)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(6)
            # 模拟窗口
            bar = QFrame()
            bar.setFixedHeight(14)
            bar.setStyleSheet(
                f"QFrame{{background:{tb};border:1px solid {bd};border-radius:4px;}}"
            )
            cl.addWidget(bar)
            # 模拟内容区
            body = QFrame()
            body.setStyleSheet(
                f"QFrame{{background:{bg};border:1px solid {bd};border-radius:4px;}}"
            )
            bl = QHBoxLayout(body)
            bl.setContentsMargins(4, 4, 4, 4)
            bl.setSpacing(4)
            for i in range(3):
                dot = QFrame()
                dot.setFixedHeight(6)
                dot.setStyleSheet(
                    f"QFrame{{background:{accent};border:none;border-radius:3px;}}"
                )
                bl.addWidget(dot)
            cl.addWidget(body, 1)
            # 名称
            nm = QLabel(name)
            is_dark = tid == "dark"
            nm_color = "#f1f5f9" if is_dark else "#0f172a"
            nm.setStyleSheet(
                f"font-size:11px;font-weight:800;color:{nm_color};background:transparent;border:none;"
            )
            cl.addWidget(nm)
            card._theme_id = tid
            card._accent = accent
            card.mousePressEvent = lambda e, c=card: self._select_theme(c)
            self._preview_cards.append(card)
            ph.addWidget(card)
        v.addLayout(ph)

        v.addStretch(1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("完成")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setFixedHeight(34)
        btn_close.setStyleSheet(
            "QPushButton{background:#111827;color:white;border:none;border-radius:8px;"
            "  padding:0 18px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#1f2937;}"
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

    def _load(self):
        cur = self.store.settings.get("theme", "light")
        for card in self._preview_cards:
            if card._theme_id == cur:
                self._select_theme(card, animate=False)
                break
        is_dark = cur == "dark"
        self.toggle.blockSignals(True)
        self.toggle.setChecked(is_dark, animate=False)
        self.toggle.blockSignals(False)
        self.lbl_mode.setText("🌙  夜晚模式" if is_dark else "☀️  白天模式")

    def _on_toggle(self, checked: bool):
        target_id = "dark" if checked else "light"
        for card in self._preview_cards:
            if card._theme_id == target_id:
                self._select_theme(card, animate=False)
                break
        self.lbl_mode.setText("🌙  夜晚模式" if checked else "☀️  白天模式")
        self._apply_theme(target_id)

    def _select_theme(self, selected_card, animate=True):
        for card in self._preview_cards:
            if card is selected_card:
                card.setStyleSheet(
                    f"QFrame{{background:{self._card_bg_for(card._theme_id)};"
                    f"  border:2.5px solid {card._accent};border-radius:12px;}}"
                )
            else:
                card.setStyleSheet(
                    f"QFrame{{background:{self._card_bg_for(card._theme_id)};"
                    f"  border:1.5px solid #e2e8f0;border-radius:12px;}}"
                    f"QFrame:hover{{border:2px solid {card._accent};}}"
                )
        self._apply_theme(selected_card._theme_id, animate=animate)

    def _card_bg_for(self, tid):
        for k, n, bg, card_bg, bd, tb, ac, fg in self.PRESETS:
            if k == tid:
                return card_bg
        return "#ffffff"

    def _apply_theme(self, theme_id: str, animate: bool = True):
        self.store.settings["theme"] = theme_id
        self.store.save()
        if self.main_window is not None and hasattr(self.main_window, "_apply_theme"):
            self.main_window._apply_theme(theme_id, animate=animate)


class AIConfigDialog(QDialog):
    """AI 服务配置对话框"""
    SILICONFLOW_MODELS = [
        "deepseek-ai/DeepSeek-V4-Flash",      # 最新, 性价比高
        "deepseek-ai/DeepSeek-V3.2",
        "Qwen/Qwen2.5-7B-Instruct",            # 轻量, 便宜
        "Qwen/Qwen3-8B",
        "Qwen/Qwen2.5-72B-Instruct",
        "zai-org/GLM-4.5-Air",
    ]
    ZHIPU_MODELS = [
        "glm-4-flash",        # 永久免费, 128K
        "glm-4-flashx",       # 永久免费, 更快
        "glm-4.5-flash",     # 永久免费, 200K
        "glm-4-plus",        # 付费
        "glm-4.7-flash",     # 永久免费, 编程 SOTA
    ]
    ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    def __init__(self, store: StudyStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("AI 服务配置")
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setMinimumHeight(620)
        # 整体浅色主题
        self.setStyleSheet(
            "QDialog{background:#f8fafc;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
            "QScrollBar::handle:vertical{background:#cbd5e1;border-radius:4px;min-height:30px;}"
            "QScrollBar::handle:vertical:hover{background:#94a3b8;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 滚动区域, 防止小屏放不下
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;}")
        v = QVBoxLayout(page)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(14)

        # ============ 顶部 Header 卡片 ============
        header = QFrame()
        header.setStyleSheet(
            "QFrame{"
            "  background:#ffffff;"
            "  border:1px solid #e2e8f0;"
            "  border-top:3px solid #6366f1;"
            "  border-radius:12px;"
            "}"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 14, 16, 14)
        hl.setSpacing(12)
        icon = QLabel("✦")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(38, 38)
        icon.setStyleSheet(
            "QLabel{background:#eef2ff;color:#6366f1;"
            "border-radius:19px;font-size:20px;font-weight:900;}"
        )
        hl.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("AI 服务配置")
        title.setStyleSheet("font-size:16px;font-weight:800;color:#0f172a;background:transparent;border:none;")
        col.addWidget(title)
        sub = QLabel("配置 API Key / 模型 / 系统提示词 · 仅本地存储, 不上传任何服务器")
        sub.setStyleSheet("font-size:11px;color:#64748b;background:transparent;border:none;")
        sub.setWordWrap(True)
        col.addWidget(sub)
        hl.addLayout(col, 1)
        v.addWidget(header)

        # ============ 提供方卡片 (3 个并排, 单选样式) ============
        prov_lab = QLabel("AI 提供方")
        prov_lab.setStyleSheet("font-size:12px;font-weight:800;color:#475569;background:transparent;")
        v.addWidget(prov_lab)
        prov_row = QHBoxLayout()
        prov_row.setSpacing(8)
        self._provider_cards = []
        provs = [
            ("硅基流动", "SiliconFlow · 便宜稳定", "siliconflow", "#2563eb", "#eff6ff", "#bfdbfe"),
            ("智谱 AI", "GLM-4-Flash · 永久免费", "zhipu", "#a855f7", "#faf5ff", "#e9d5ff"),
            ("自定义", "OpenAI 兼容服务", "custom", "#64748b", "#f1f5f9", "#cbd5e1"),
        ]
        for name, desc, key, fg, bg, bd in provs:
            card = QFrame()
            card.setCursor(Qt.PointingHandCursor)
            card.setStyleSheet(
                f"QFrame{{background:{bg};border:1px solid {bd};border-radius:10px;}}"
                f"QFrame:hover{{border:1.5px solid {fg};}}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 10, 10, 10)
            cl.setSpacing(2)
            n = QLabel(name)
            n.setStyleSheet(f"font-size:13px;font-weight:800;color:{fg};background:transparent;border:none;")
            d = QLabel(desc)
            d.setStyleSheet("font-size:10px;color:#64748b;background:transparent;border:none;")
            d.setWordWrap(True)
            cl.addWidget(n)
            cl.addWidget(d)
            card._provider_key = key
            card._fg = fg
            card._bg = bg
            card._bd = bd
            card.mousePressEvent = lambda e, c=card: self._select_provider_card(c)
            self._provider_cards.append(card)
            prov_row.addWidget(card, 1)
        # 隐藏的 QComboBox 用于兼容 _save_to_store
        self.cb_provider = QComboBox()
        self.cb_provider.addItem("SiliconFlow", "siliconflow")
        self.cb_provider.addItem("Zhipu", "zhipu")
        self.cb_provider.addItem("Custom", "custom")
        self.cb_provider.hide()
        v.addLayout(prov_row)

        # ============ API Key 卡片 ============
        v.addWidget(self._build_section_label("🔑  API Key"))
        key_card = QFrame()
        key_card.setObjectName("aiCfgCard")
        key_card.setStyleSheet(
            "QFrame#aiCfgCard{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        kl = QHBoxLayout(key_card)
        kl.setContentsMargins(12, 8, 12, 8)
        kl.setSpacing(8)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText("sk-...")
        self.ed_key.setStyleSheet(
            "QLineEdit{background:transparent;border:none;color:#0f172a;"
            "  font-size:13px;padding:4px 0;font-family:Consolas,'Cascadia Code',monospace;}"
            "QLineEdit:focus{outline:0;}"
        )
        kl.addWidget(self.ed_key, 1)
        self.btn_show = QPushButton("👁")
        self.btn_show.setCheckable(True)
        self.btn_show.setCursor(Qt.PointingHandCursor)
        self.btn_show.setFixedSize(34, 28)
        self.btn_show.setToolTip("显示/隐藏 Key")
        self.btn_show.setStyleSheet(
            "QPushButton{background:#f1f5f9;color:#475569;border:1px solid #e2e8f0;"
            "  border-radius:6px;font-size:13px;}"
            "QPushButton:hover{background:#e2e8f0;color:#0f172a;}"
            "QPushButton:checked{background:#dbeafe;color:#1e3a8a;border-color:#bfdbfe;}"
        )
        self.btn_show.clicked.connect(self._toggle_key_visible)
        kl.addWidget(self.btn_show)
        btn_clear = QPushButton("✕")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setFixedSize(34, 28)
        btn_clear.setToolTip("清空")
        btn_clear.setStyleSheet(
            "QPushButton{background:#fef2f2;color:#dc2626;border:1px solid #fecaca;"
            "  border-radius:6px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#fee2e2;}"
        )
        btn_clear.clicked.connect(lambda: self.ed_key.clear())
        kl.addWidget(btn_clear)
        v.addWidget(key_card)

        # ============ Base URL 卡片 ============
        v.addWidget(self._build_section_label("🌐  Base URL"))
        url_card = QFrame()
        url_card.setObjectName("aiCfgCard")
        url_card.setStyleSheet(
            "QFrame#aiCfgCard{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        ul = QHBoxLayout(url_card)
        ul.setContentsMargins(12, 6, 12, 6)
        ul.setSpacing(6)
        self.ed_url = QLineEdit()
        self.ed_url.setStyleSheet(
            "QLineEdit{background:transparent;border:none;color:#0f172a;"
            "  font-size:12px;padding:4px 0;font-family:Consolas,'Cascadia Code',monospace;}"
            "QLineEdit:focus{outline:0;}"
            "QLineEdit:read-only{color:#94a3b8;}"
        )
        ul.addWidget(self.ed_url, 1)
        self._lbl_lock = QLabel("🔒")
        self._lbl_lock.setStyleSheet("font-size:13px;background:transparent;border:none;")
        self._lbl_lock.setToolTip("Base URL 已由提供方固定, 切换到「自定义」可修改")
        ul.addWidget(self._lbl_lock)
        v.addWidget(url_card)

        # ============ 模型卡片 ============
        v.addWidget(self._build_section_label("🧠  模型"))
        model_card = QFrame()
        model_card.setObjectName("aiCfgCard")
        model_card.setStyleSheet(
            "QFrame#aiCfgCard{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        ml = QHBoxLayout(model_card)
        ml.setContentsMargins(12, 6, 12, 6)
        ml.setSpacing(6)
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)
        self.cb_model.setCursor(Qt.PointingHandCursor)
        for m in self.SILICONFLOW_MODELS:
            self.cb_model.addItem(m)
        self.cb_model.setStyleSheet(
            "QComboBox{background:transparent;border:none;color:#0f172a;"
            "  font-size:12px;padding:4px 0;font-family:Consolas,'Cascadia Code',monospace;}"
            "QComboBox:focus{outline:0;}"
            "QComboBox::drop-down{subcontrol-origin:padding;subcontrol-position:top right;"
            "  width:18px;border:none;}"
            "QComboBox::down-arrow{image:none;border-left:4px solid transparent;"
            "  border-right:4px solid transparent;border-top:5px solid #64748b;}"
            "QComboBox QAbstractItemView{background:white;border:1px solid #e2e8f0;"
            "  border-radius:8px;padding:4px;font-size:12px;"
            "  selection-background-color:#dbeafe;selection-color:#1e3a8a;outline:0;}"
        )
        ml.addWidget(self.cb_model, 1)
        v.addWidget(model_card)

        # ============ 系统提示词卡片 ============
        v.addWidget(self._build_section_label("💬  系统提示词 (可选)"))
        prompt_card = QFrame()
        prompt_card.setObjectName("aiCfgCard")
        prompt_card.setStyleSheet(
            "QFrame#aiCfgCard{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;}"
        )
        pl = QVBoxLayout(prompt_card)
        pl.setContentsMargins(12, 8, 12, 8)
        pl.setSpacing(4)
        self.ed_prompt = QTextEdit()
        self.ed_prompt.setMaximumHeight(80)
        self.ed_prompt.setPlaceholderText("例如: 你是一个考研复习助手, 回答要简洁, 重点突出…")
        self.ed_prompt.setStyleSheet(
            "QTextEdit{background:transparent;border:none;color:#0f172a;"
            "  font-size:12px;line-height:1.5;}"
            "QTextEdit:focus{outline:0;}"
        )
        pl.addWidget(self.ed_prompt)
        v.addWidget(prompt_card)

        # ============ 测试连接区 ============
        test_row = QHBoxLayout()
        test_row.setSpacing(8)
        self.btn_test = QPushButton("🔌  测试连接")
        self.btn_test.setCursor(Qt.PointingHandCursor)
        self.btn_test.setFixedHeight(34)
        self.btn_test.setStyleSheet(
            "QPushButton{background:#f1f5f9;color:#334155;border:1px solid #e2e8f0;"
            "  border-radius:8px;padding:0 14px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#e2e8f0;color:#0f172a;}"
            "QPushButton:disabled{background:#f8fafc;color:#cbd5e1;}"
        )
        self.btn_test.clicked.connect(self._test_connection)
        test_row.addWidget(self.btn_test)
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setStyleSheet(
            "font-size:11px;color:#64748b;font-weight:600;background:transparent;border:none;"
        )
        self.lbl_test_result.setWordWrap(True)
        test_row.addWidget(self.lbl_test_result, 1)
        v.addLayout(test_row)

        scroll.setWidget(page)
        root.addWidget(scroll, 1)

        # ============ 底部固定按钮栏 (在滚动区外) ============
        bottom_bar = QFrame()
        bottom_bar.setStyleSheet(
            "QFrame{background:#ffffff;border-top:1px solid #e2e8f0;}"
        )
        bl = QHBoxLayout(bottom_bar)
        bl.setContentsMargins(20, 12, 20, 12)
        bl.setSpacing(8)
        help_lbl = QLabel("💡 提示: Key 保存在本地 kaoyan_data.json")
        help_lbl.setStyleSheet("font-size:11px;color:#94a3b8;background:transparent;border:none;")
        bl.addWidget(help_lbl, 1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setFixedHeight(34)
        self.btn_cancel.setStyleSheet(
            "QPushButton{background:#ffffff;color:#475569;border:1px solid #e2e8f0;"
            "  border-radius:8px;padding:0 16px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#f1f5f9;color:#0f172a;}"
        )
        self.btn_cancel.clicked.connect(self.reject)
        bl.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("✓  保存配置")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setFixedHeight(34)
        self.btn_ok.setStyleSheet(
            "QPushButton{background:#111827;color:white;border:none;border-radius:8px;"
            "  padding:0 18px;font-weight:700;font-size:12px;}"
            "QPushButton:hover{background:#1f2937;}"
            "QPushButton:pressed{background:#374151;}"
        )
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        bl.addWidget(self.btn_ok)
        root.addWidget(bottom_bar)

    def _build_section_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setStyleSheet(
            "font-size:12px;font-weight:800;color:#475569;"
            "background:transparent;border:none;padding:2px 0;"
        )
        return lab

    def _select_provider_card(self, selected_card):
        """三张提供方卡片单选"""
        for card in self._provider_cards:
            if card is selected_card:
                card.setStyleSheet(
                    f"QFrame{{background:#ffffff;border:2px solid {card._fg};"
                    f"  border-radius:10px;}}"
                )
            else:
                card.setStyleSheet(
                    f"QFrame{{background:{card._bg};border:1px solid {card._bd};"
                    f"  border-radius:10px;}}"
                    f"QFrame:hover{{border:1.5px solid {card._fg};}}"
                )
        idx = self.cb_provider.findData(selected_card._provider_key)
        if idx >= 0:
            self.cb_provider.setCurrentIndex(idx)
        self._on_provider_changed()

    def _load_values(self):
        s = self.store.settings
        provider = s.get("ai_provider", "siliconflow")
        # 选中对应卡片
        for card in self._provider_cards:
            if card._provider_key == provider:
                self._select_provider_card(card)
                break
        self.ed_key.setText(s.get("ai_api_key", ""))
        self.ed_url.setText(s.get("ai_base_url", "https://api.siliconflow.cn/v1"))
        self.ed_prompt.setPlainText(s.get("ai_system_prompt", ""))
        # _on_provider_changed 会重置模型列表, 这里再设回保存的模型名
        model = s.get("ai_model", self.SILICONFLOW_MODELS[0])
        self.cb_model.setCurrentText(model)

    def _on_provider_changed(self):
        provider = self.cb_provider.currentData()
        # 切换模型下拉列表
        self.cb_model.clear()
        if provider == "siliconflow":
            for m in self.SILICONFLOW_MODELS:
                self.cb_model.addItem(m)
            self.ed_url.setText("https://api.siliconflow.cn/v1")
            self.ed_url.setReadOnly(True)
            self.cb_model.setEditable(False)
            self.ed_key.setPlaceholderText("sk-... (在 cloud.siliconflow.cn 获取)")
            self._lbl_lock.setVisible(True)
        elif provider == "zhipu":
            for m in self.ZHIPU_MODELS:
                self.cb_model.addItem(m)
            self.ed_url.setText(self.ZHIPU_BASE_URL)
            self.ed_url.setReadOnly(True)
            self.cb_model.setEditable(False)
            self.ed_key.setPlaceholderText("智谱 API Key (在 open.bigmodel.cn 获取)")
            # 默认选第一个免费模型
            self.cb_model.setCurrentIndex(0)
            self._lbl_lock.setVisible(True)
        else:  # custom
            self.ed_url.setReadOnly(False)
            self.cb_model.setEditable(True)
            self.ed_key.setPlaceholderText("sk-...")
            self._lbl_lock.setVisible(False)

    def _toggle_key_visible(self):
        if self.btn_show.isChecked():
            self.ed_key.setEchoMode(QLineEdit.Normal)
            self.btn_show.setText("🙈")
        else:
            self.ed_key.setEchoMode(QLineEdit.Password)
            self.btn_show.setText("👁")

    def _test_connection(self):
        self._save_to_store()
        self.lbl_test_result.setStyleSheet(
            "font-size:11px;color:#2563eb;font-weight:700;background:transparent;border:none;"
        )
        self.lbl_test_result.setText("⏳ 测试中…")
        self.btn_test.setEnabled(False)
        self._worker = AIWorkerThread(self.store.settings, [
            {"role": "user", "content": "ping, 回复 pong"}
        ], self)
        self._worker.response_ready.connect(lambda msg: self._on_test_ok(msg))
        self._worker.error_occurred.connect(lambda err: self._on_test_fail(err))
        self._worker.start()

    def _on_test_ok(self, msg: str):
        self.lbl_test_result.setStyleSheet(
            "font-size:11px;color:#059669;font-weight:700;background:transparent;border:none;"
        )
        self.lbl_test_result.setText(f"✅ 连接成功: {msg[:80]}")
        self.btn_test.setEnabled(True)

    def _on_test_fail(self, err: str):
        self.lbl_test_result.setStyleSheet(
            "font-size:11px;color:#dc2626;font-weight:700;background:transparent;border:none;"
        )
        self.lbl_test_result.setText(f"❌ {err[:120]}")
        self.btn_test.setEnabled(True)

    def _save_to_store(self):
        s = self.store.settings
        s["ai_provider"] = self.cb_provider.currentData()
        s["ai_api_key"] = self.ed_key.text().strip()
        s["ai_base_url"] = self.ed_url.text().strip()
        s["ai_model"] = self.cb_model.currentText().strip()
        s["ai_system_prompt"] = self.ed_prompt.toPlainText().strip()
        self.store.save()

    def accept(self):
        self._save_to_store()
        super().accept()


class AIChatPanel(QWidget):
    """AI 聊天面板 (全局右侧第三栏)"""
    def __init__(self, store: StudyStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.history = AIChatHistory.load()
        self._worker: Optional[AIWorkerThread] = None
        self._current_sid: Optional[str] = None
        # P0-B 流式状态
        self._stream_bubble: Optional[QTextBrowser] = None
        self._stream_buf: str = ""
        self._build_ui()
        self._refresh_session_combo()
        # 启动时若有历史, 自动选最近一个
        titles = self.history.session_titles()
        if titles:
            self._current_sid = titles[0][0]
            self.cb_session.setCurrentIndex(0)
            self._render_messages()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        # 极简风: 纯白背景 + 极淡的灰色分割线, 仿 TraeCode / VSCode Chat
        self._theme = "light"  # 记录当前主题, 切换时方便用
        self.setStyleSheet(self._get_chatpanel_qss("light"))

        # ========== 顶栏 (极简风: 纯白 + 1px 底部分割线) ==========
        top = QFrame()
        top.setFixedHeight(52)
        top.setStyleSheet(
            "QFrame{background:#ffffff;border-bottom:1px solid #f1f5f9;}"
        )
        th = QHBoxLayout(top)
        th.setContentsMargins(14, 0, 10, 0)
        th.setSpacing(6)

        # AI 图标 (仿 TraeCode 左侧的 AI 符号)
        ai_mark = QLabel("✦")
        ai_mark.setStyleSheet("font-size:18px;font-weight:900;color:#6366f1;")
        ai_mark.setFixedSize(22, 22)
        ai_mark.setAlignment(Qt.AlignCenter)
        th.addWidget(ai_mark)

        # 标题 (现代风格: "AI 助手" 粗体 + 会话下拉紧跟)
        title_lbl = QLabel("AI 助手")
        title_lbl.setStyleSheet("font-size:14px;font-weight:800;color:#0f172a;")
        th.addWidget(title_lbl)
        th.addSpacing(6)

        # 会话下拉 (现代胶囊样式已在全局 setStyleSheet 中定义)
        self.cb_session = QComboBox()
        self.cb_session.setMinimumWidth(140)
        self.cb_session.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cb_session.currentIndexChanged.connect(self._on_session_changed)
        th.addWidget(self.cb_session, 1)
        th.addSpacing(2)

        # 工具按钮: 统一 30x30 圆圈 hover
        def _mk_icon_btn(unicode_char: str, tip: str, color: str = "#475569") -> QPushButton:
            b = QPushButton(unicode_char)
            b.setFixedSize(30, 30)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{color};"
                f"  border:none;border-radius:8px;font-size:15px;font-weight:700;}}"
                f"QPushButton:hover{{background:#f1f5f9;color:#0f172a;}}"
                f"QPushButton:pressed{{background:#e2e8f0;}}"
            )
            return b

        self.btn_new = _mk_icon_btn("＋", "新建对话 (Ctrl+N)", "#10b981")
        self.btn_new.clicked.connect(self._on_new_session)
        th.addWidget(self.btn_new)
        self.btn_del = _mk_icon_btn("✕", "删除当前对话", "#ef4444")
        self.btn_del.clicked.connect(self._on_delete_session)
        th.addWidget(self.btn_del)
        self.btn_cfg = _mk_icon_btn("⚙", "模型设置")
        self.btn_cfg.clicked.connect(self._on_config)
        th.addWidget(self.btn_cfg)
        self.btn_collapse = _mk_icon_btn("›", "折叠面板 (Ctrl+Shift+K)", "#6366f1")
        self.btn_collapse.setStyleSheet(self.btn_collapse.styleSheet() +
            "QPushButton{font-size:20px;}QPushButton:hover{background:#eef2ff;color:#4338ca;}")
        self.btn_collapse.clicked.connect(self._on_collapse)
        th.addWidget(self.btn_collapse)
        v.addWidget(top)

        # ========== 消息列表 ==========
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{border:none;background:#fafafa;}")
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("QWidget{background:#fafafa;}")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(14, 16, 14, 16)
        self.msg_layout.setSpacing(14)
        self.msg_layout.addStretch(1)
        self.scroll.setWidget(self.msg_container)
        v.addWidget(self.scroll, 1)

        # ========== 空状态 (无会话时的欢迎屏) ==========
        self.empty_state = QWidget()
        self.empty_state.setStyleSheet("QWidget{background:transparent;}")
        empty_v = QVBoxLayout(self.empty_state)
        empty_v.setContentsMargins(0, 20, 0, 20)
        empty_v.setSpacing(12)
        empty_v.addStretch(1)
        empty_logo = QLabel("✦")
        empty_logo.setAlignment(Qt.AlignCenter)
        empty_logo.setStyleSheet("font-size:48px;font-weight:900;color:#6366f1;")
        empty_v.addWidget(empty_logo)
        empty_title = QLabel("我是你的考研复习助手")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setStyleSheet("font-size:16px;font-weight:800;color:#0f172a;")
        empty_v.addWidget(empty_title)
        empty_tip = QLabel("试试问我：\n• 英语长难句分析\n• 数学解题思路\n• 今日学习规划")
        empty_tip.setAlignment(Qt.AlignCenter)
        empty_tip.setStyleSheet("color:#64748b;line-height:1.6;font-size:12px;")
        empty_tip.setWordWrap(True)
        empty_v.addWidget(empty_tip)
        empty_v.addStretch(1)
        self.msg_layout.insertWidget(0, self.empty_state)

        # ========== 输入区 (现代风格: 白色卡片 + 1px 圆角灰边 + focus蓝边) ==========
        input_wrap = QFrame()
        input_wrap.setStyleSheet(
            "QFrame{background:#ffffff;border-top:1px solid #f1f5f9;}"
        )
        iv = QVBoxLayout(input_wrap)
        iv.setContentsMargins(14, 12, 14, 14)
        iv.setSpacing(8)

        # 输入框外框 (圆角 12px + 柔和边框)
        input_card = QFrame()
        input_card.setObjectName("aiInputCard")
        input_card.setStyleSheet(
            "QFrame#aiInputCard{"
            "  background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;"
            "}"
            "QFrame#aiInputCard:focus-within{"
            "  background:white;border:1.5px solid #6366f1;"
            "}"
        )
        ic = QVBoxLayout(input_card)
        ic.setContentsMargins(12, 8, 12, 4)
        ic.setSpacing(4)

        self.ed_input = QTextEdit()
        self.ed_input.setMinimumHeight(36)   # 缩小发送窗 (原 56)
        self.ed_input.setMaximumHeight(90)   # 缩小发送窗 (原 160)
        self.ed_input.setPlaceholderText("输入消息，Ctrl+Enter 发送…")
        self.ed_input.setStyleSheet(
            "QTextEdit{background:transparent;border:none;color:#0f172a;"
            "  font-size:13px;line-height:1.6;padding:4px 0;}"
            "QTextEdit:focus{outline:0;}"
        )
        ic.addWidget(self.ed_input)

        # 输入区按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("font-size:11px;color:#94a3b8;font-weight:500;")
        btn_row.addWidget(self.lbl_status, 1)

        # ---------- 模型选择下拉 (右上角的模型切换) ----------
        from PyQt5.QtWidgets import QComboBox as _QCB
        self.cb_model = _QCB()
        self.cb_model.setToolTip("选择 AI 模型")
        self.cb_model.setCursor(Qt.PointingHandCursor)
        self.cb_model.setFixedHeight(28)
        # 收集可用模型列表 (合并 siliconflow + zhipu)
        all_models = []
        seen = set()
        for m in list(AIConfigDialog.SILICONFLOW_MODELS) + list(AIConfigDialog.ZHIPU_MODELS):
            if m not in seen:
                seen.add(m)
                all_models.append(m)
        self.cb_model.addItems(all_models)
        # 选中 store.settings 当前模型
        cur_model = self.store.settings.get("ai_model", all_models[0])
        idx = self.cb_model.findText(cur_model)
        if idx >= 0:
            self.cb_model.setCurrentIndex(idx)
        self.cb_model.currentTextChanged.connect(self._on_model_changed)
        self.cb_model.setStyleSheet(
            "QComboBox{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;"
            "  padding:2px 8px 2px 10px;font-size:11px;color:#334155;font-weight:600;"
            "  min-width:90px;max-width:140px;}"
            "QComboBox:hover{background:#eff6ff;border-color:#bfdbfe;color:#1e3a8a;}"
            "QComboBox::drop-down{subcontrol-origin:padding;subcontrol-position:top right;"
            "  width:18px;border:none;}"
            "QComboBox::down-arrow{image:none;border-left:3px solid transparent;"
            "  border-right:3px solid transparent;border-top:4px solid #64748b;}"
            "QComboBox QAbstractItemView{background:white;border:1px solid #e2e8f0;"
            "  border-radius:6px;padding:3px;font-size:12px;"
            "  selection-background-color:#dbeafe;selection-color:#1e3a8a;outline:0;}"
        )
        btn_row.addWidget(self.cb_model)

        # ---------- 🔑 Key 配置按钮 (蓝色, 显眼) ----------
        self.btn_key = QPushButton("🔑  Key")
        self.btn_key.setCursor(Qt.PointingHandCursor)
        self.btn_key.setToolTip("配置 API Key / Base URL")
        self.btn_key.setFixedHeight(28)
        # 已配置过 key 的话, 按钮变绿色
        has_key = bool(self.store.settings.get("ai_api_key", ""))
        if has_key:
            k_bg, k_fg, k_bd = "#d1fae5", "#065f46", "#a7f3d0"
            k_text = "🔑  Key ✓"
        else:
            k_bg, k_fg, k_bd = "#fef3c7", "#92400e", "#fde68a"
            k_text = "🔑  Key (未配置)"
        self.btn_key.setText(k_text)
        self.btn_key.setStyleSheet(
            f"QPushButton{{background:{k_bg};color:{k_fg};border:1px solid {k_bd};"
            f"  border-radius:6px;padding:0 8px;font-weight:700;font-size:11px;}}"
            f"QPushButton:hover{{background:{k_fg};color:white;}}"
        )
        self.btn_key.clicked.connect(self._on_config)
        btn_row.addWidget(self.btn_key)

        # 停止按钮 (红色胶囊)
        self.btn_stop = QPushButton("■ 停止")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setFixedHeight(28)
        self.btn_stop.setStyleSheet(
            "QPushButton{background:#fee2e2;color:#b91c1c;border:1px solid #fecaca;"
            "  border-radius:6px;padding:0 10px;font-weight:700;font-size:11px;}"
            "QPushButton:hover{background:#fecaca;color:#991b1b;}"
        )
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.hide()
        btn_row.addWidget(self.btn_stop)

        # 发送按钮 (深蓝胶囊, 仿 TraeCode)
        self.btn_send = QPushButton("发送 ⏎")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedHeight(28)
        self.btn_send.setStyleSheet(
            "QPushButton{background:#111827;color:white;border:none;border-radius:6px;"
            "  padding:0 12px;font-weight:700;font-size:11px;}"
            "QPushButton:hover{background:#1f2937;}"
            "QPushButton:pressed{background:#374151;}"
            "QPushButton:disabled{background:#e5e7eb;color:#9ca3af;}"
        )
        self.btn_send.clicked.connect(self._on_send)
        btn_row.addWidget(self.btn_send)

        ic.addLayout(btn_row)
        iv.addWidget(input_card)
        v.addWidget(input_wrap)

        # 快捷键: Ctrl+Enter 发送, Ctrl+N 新会话
        sc_send = QShortcut(QKeySequence("Ctrl+Return"), self.ed_input)
        sc_send.activated.connect(self._on_send)
        sc_new = QShortcut(QKeySequence("Ctrl+N"), self)
        sc_new.activated.connect(self._on_new_session)

    # ----- 会话管理 -----
    def _refresh_session_combo(self):
        self.cb_session.blockSignals(True)
        self.cb_session.clear()
        for sid, title in self.history.session_titles():
            self.cb_session.addItem(title, sid)
        self.cb_session.blockSignals(False)
        # 无会话时禁用下拉
        self.cb_session.setEnabled(self.cb_session.count() > 0)

    def _set_empty_state(self, visible: bool):
        # 用 sip 包装 / RuntimeError 防御: empty_state 可能已被 deleteLater
        try:
            es = self.empty_state
            if es is not None:
                es.setVisible(visible)
        except RuntimeError:
            pass

    def _on_session_changed(self, idx: int):
        if idx < 0:
            return
        self._current_sid = self.cb_session.itemData(idx)
        self._render_messages()

    def _on_model_changed(self, model_name: str):
        """发送区模型下拉切换: 写回 store, 不重开 dialog"""
        self.store.settings["ai_model"] = model_name
        self.store.save()
        # 状态栏提示
        if hasattr(self, "lbl_status"):
            self._show_status(
                f"✓ 已切换模型: {model_name}",
                color="#065f46", bg="#d1fae5", border="#a7f3d0",
            )
            QTimer.singleShot(2200, lambda: self._stop_loading())

    def _on_new_session(self):
        sid = self.history.new_session("新对话")
        self._current_sid = sid
        self._refresh_session_combo()
        self.cb_session.setCurrentIndex(0)
        self._render_messages()
        self.ed_input.setFocus()

    def _on_delete_session(self):
        if not self._current_sid:
            return
        self.history.delete_session(self._current_sid)
        titles = self.history.session_titles()
        if titles:
            self._current_sid = titles[0][0]
        else:
            self._current_sid = None
        self._refresh_session_combo()
        if self._current_sid:
            self.cb_session.setCurrentIndex(0)
        self._render_messages()

    def _on_config(self):
        dlg = AIConfigDialog(self.store, self)
        if dlg.exec_():
            self._show_status("✓ 配置已保存", color="#065f46", bg="#d1fae5", border="#a7f3d0")
            QTimer.singleShot(2200, lambda: self._stop_loading())
            # 刷新发送区的 Key 按钮状态
            has_key = bool(self.store.settings.get("ai_api_key", ""))
            if has_key:
                self.btn_key.setText("🔑  Key ✓")
                self.btn_key.setStyleSheet(
                    "QPushButton{background:#d1fae5;color:#065f46;border:1px solid #a7f3d0;"
                    "  border-radius:6px;padding:0 8px;font-weight:700;font-size:11px;}"
                    "QPushButton:hover{background:#065f46;color:white;}"
                )
            # 刷新模型下拉
            cur_model = self.store.settings.get("ai_model", "")
            idx = self.cb_model.findText(cur_model)
            if idx >= 0:
                self.cb_model.setCurrentIndex(idx)

    def _on_collapse(self):
        # 通知主窗口折叠
        if hasattr(self.parent(), "_toggle_ai_panel"):
            self.parent()._toggle_ai_panel(False)

    # ----- 消息渲染 -----
    def _render_messages(self):
        # 清空现有气泡: 第 0 项是 empty_state, 最后一项是 stretch, 中间都是气泡 row
        # 只删 [1, count-2) 区间的项
        try:
            empty_state_index = self.msg_layout.indexOf(self.empty_state)
        except RuntimeError:
            empty_state_index = 0
        last_index = self.msg_layout.count() - 1  # stretch
        # 倒序删除中间所有项, 避免索引变化
        for i in range(last_index - 1, empty_state_index, -1):
            item = self.msg_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is None:
                continue
            self.msg_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        has_msg = False
        if self._current_sid:
            s = self.history.get_session(self._current_sid)
            if s is not None:
                msgs = s.get("messages", [])
                for msg in msgs:
                    self._add_bubble(msg.get("role", "user"), msg.get("content", ""))
                has_msg = len(msgs) > 0
        self._set_empty_state(not has_msg)

    def _add_bubble(self, role: str, content: str):
        """现代风格气泡: 独立 QFrame 包裹 + 真圆角 + 自适应宽度 + 左右对齐"""
        html = self._md_to_html(content)

        # 外层容器 (左右对齐)
        row_wrap = QWidget()
        row_wrap.setStyleSheet("QWidget{background:transparent;}")
        rl = QHBoxLayout(row_wrap)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # 气泡卡片 (真 QFrame 圆角 + 内边距)
        card = QFrame()
        card.setAttribute(Qt.WA_TranslucentBackground, False)
        # 不设 setMaximumWidth, 改为气泡自适应内容宽度

        is_user = role == "user"
        is_error = role == "error"

        if is_user:
            # 用户气泡: 柔和浅蓝填充 + 1px 蓝边 (VSCode 风格)
            card.setStyleSheet(
                "QFrame{"
                "  background: #eff6ff;"
                "  border: 1px solid #bfdbfe;"
                "  border-radius: 14px 14px 2px 14px;"
                "}"
            )
        elif is_error:
            card.setStyleSheet(
                "QFrame{"
                "  background:#fef2f2;border:1px solid #fecaca;"
                "  border-radius:14px;"
                "}"
            )
        else:
            # AI 气泡: 纯白 + 1px 淡灰边
            card.setStyleSheet(
                "QFrame{"
                "  background:#ffffff;border:1px solid #e2e8f0;"
                "  border-radius: 14px 14px 14px 2px;"
                "}"
            )

        # 内部 QTextBrowser 显示 Markdown
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setReadOnly(True)
        browser.document().setDocumentMargin(0)
        if is_user:
            txt_color = "#1e3a8a"
            link_color = "#2563eb"
            code_bg = "#dbeafe"
            code_color = "#1e40af"
            pre_border = "#bfdbfe"
        elif is_error:
            txt_color = "#991b1b"
            link_color = "#b91c1c"
            code_bg = "#fee2e2"
            code_color = "#7f1d1d"
            pre_border = "#fecaca"
        else:
            txt_color = "#0f172a"
            link_color = "#4338ca"
            code_bg = "#f1f5f9"
            code_color = "#1e293b"
            pre_border = "#e2e8f0"

        browser.document().setDefaultStyleSheet(
            f"body{{color:{txt_color};font-size:13px;line-height:1.65;margin:0;padding:0;}}"
            f"a{{color:{link_color};}}"
            f"code{{background:{code_bg};color:{code_color};"
            f"  padding:1px 5px;border-radius:4px;font-family:'Consolas','Courier New',monospace;"
            f"  font-size:12px;}}"
            f"pre{{background:{code_bg};color:{code_color};"
            f"  border:1px solid {pre_border};"
            f"  border-radius:8px;padding:8px 10px;"
            f"  overflow-x:auto;font-family:'Consolas','Courier New',monospace;font-size:12px;}}"
            f"b{{font-weight:800;}}"
            f"ul,ol{{margin:4px 0 4px 20px;padding:0;}}"
            f"li{{margin:2px 0;}}"
            f"h1,h2,h3,h4,h5,h6{{margin:6px 0 4px 0;font-weight:800;}}"
            f"h1{{font-size:18px;}}h2{{font-size:16px;}}h3{{font-size:14px;}}"
        )
        wrapped_html = (
            f'<body style="margin:0;padding:0;">{html}</body>'
        )
        browser.setHtml(wrapped_html)
        browser.setStyleSheet(
            "QTextBrowser{background:transparent;border:none;padding:0;"
            "color:inherit;selection-background-color:#bfdbfe;selection-color:#0f172a;}"
        )

        # 气泡内容 padding 用 layout 控制 (保证圆角内的内边距是真的)
        bl = QVBoxLayout(card)
        pad_tb, pad_lr = (10, 14) if not is_error else (10, 14)
        bl.setContentsMargins(pad_lr, pad_tb, pad_lr, pad_tb)
        bl.setSpacing(0)
        bl.addWidget(browser)

        # ---- 气泡宽度根据文字数量自适应 (仿微信/QQ) ----
        # 先用 parent 宽度算出气泡允许的最大宽度 (避免超出 AI 面板)
        max_bubble_w = 360  # 气泡最大宽度 (单条消息最长到这, 超过就换行)
        # 让 browser 用最大宽度计算理想高度 (这样多行会折行)
        browser.setMaximumWidth(max_bubble_w - pad_lr * 2)
        browser.setMinimumWidth(0)  # 短消息可以窄
        # 设置 sizePolicy 让 browser 高度自适应、宽度按内容
        from PyQt5.QtWidgets import QSizePolicy
        browser.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        browser.document().setTextWidth(max_bubble_w - pad_lr * 2)

        # 气泡宽度策略:
        #  - 短消息 (内容宽度 < 120): 气泡最小 80, 内容多宽气泡多宽
        #  - 长消息: 最多 max_bubble_w 宽
        # 通过先估文字宽度, 再用 QTextDocument 的 idealWidth / textWidth 取小
        content_w = max(
            browser.fontMetrics().horizontalAdvance("中"),
            30,
        )
        # 简单估文字宽度: 每个字符按 7.5px (中文约等于字号, 英文更窄, 取平均)
        text_lines = content.split("\n")
        longest_line_chars = max((len(line) for line in text_lines), default=1)
        estimated_text_w = min(
            int(longest_line_chars * 7.5) + 10,
            max_bubble_w - pad_lr * 2,
        )
        # 气泡最终内容区宽度: 估算的文字宽 和 max 之间的较小值
        bubble_content_w = max(60, estimated_text_w)
        bubble_total_w = bubble_content_w + pad_lr * 2

        card.setMinimumWidth(int(bubble_total_w))
        card.setMaximumWidth(max_bubble_w)
        browser.setMinimumWidth(int(bubble_content_w))

        # 等浏览器布局完成, 再根据文档实际尺寸调整气泡高度
        def _fit_card_size():
            try:
                doc_h = int(browser.document().size().height())
                card.setMinimumHeight(max(40, doc_h + pad_tb * 2 + 4))
                browser.setMinimumHeight(max(20, doc_h))
            except (RuntimeError, ValueError):
                pass

        QTimer.singleShot(0, _fit_card_size)

        # 对齐
        if is_user:
            rl.addStretch(1)
            rl.addWidget(card)
        else:
            # AI 气泡: 左侧加一个小图标 (仿 TraeCode 助手头像)
            avatar = QLabel("✦")
            avatar.setFixedSize(26, 26)
            avatar.setAlignment(Qt.AlignCenter)
            if is_error:
                avatar.setStyleSheet(
                    "QLabel{background:#fee2e2;color:#ef4444;border-radius:13px;"
                    "font-size:14px;font-weight:900;}"
                )
                avatar.setText("!")
            else:
                avatar.setStyleSheet(
                    "QLabel{background:#2563eb;color:white;"
                    "border-radius:13px;font-size:13px;font-weight:800;}"
                )
            col_w = QWidget()
            col_w.setStyleSheet("QWidget{background:transparent;}")
            cv = QVBoxLayout(col_w)
            cv.setContentsMargins(0, 2, 0, 0)
            cv.setSpacing(0)
            cv.addWidget(avatar, 0, Qt.AlignTop)
            rl.addWidget(col_w)
            rl.addSpacing(8)
            rl.addWidget(card)
            rl.addStretch(1)

        self.msg_layout.insertWidget(self.msg_layout.count() - 1, row_wrap)
        self._set_empty_state(False)
        return browser

    def _md_to_html(self, text: str) -> str:
        """简易 Markdown 转 HTML (标题/列表/加粗/行内代码/代码块/换行)"""
        import html as _html
        import re
        lines = text.split("\n")
        out_lines: List[str] = []
        in_code = False
        code_buf: List[str] = []
        in_ul = False
        in_ol = False

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                out_lines.append("</ul>")
                in_ul = False
            if in_ol:
                out_lines.append("</ol>")
                in_ol = False

        for ln in lines:
            if ln.strip().startswith("```"):
                if not in_code:
                    close_lists()
                    in_code = True
                    code_buf = []
                else:
                    code = _html.escape("\n".join(code_buf))
                    out_lines.append(f"<pre><code>{code}</code></pre>")
                    in_code = False
                continue
            if in_code:
                code_buf.append(ln)
                continue
            esc = _html.escape(ln)
            stripped = ln.strip()
            m = re.match(r'^(#{1,6})\s+(.*)$', stripped)
            if m:
                close_lists()
                level = len(m.group(1))
                tag = f"h{level}" if level <= 6 else "h6"
                out_lines.append(f"<{tag}>{m.group(2)}</{tag}>")
                continue
            if re.match(r'^[-*]\s+', stripped):
                if not in_ul:
                    close_lists()
                    out_lines.append("<ul>")
                    in_ul = True
                item = re.sub(r'^[-*]\s+', '', stripped)
                out_lines.append(f"<li>{self._md_inline(item)}</li>")
                continue
            if re.match(r'^\d+\.\s+', stripped):
                if not in_ol:
                    close_lists()
                    out_lines.append("<ol>")
                    in_ol = True
                item = re.sub(r'^\d+\.\s+', '', stripped)
                out_lines.append(f"<li>{self._md_inline(item)}</li>")
                continue
            if not stripped:
                close_lists()
                out_lines.append("")
                continue
            close_lists()
            out_lines.append(self._md_inline(esc))
        close_lists()
        if in_code and code_buf:
            code = _html.escape("\n".join(code_buf))
            out_lines.append(f"<pre><code>{code}</code></pre>")
        block_tags = ("<ul", "<ol", "<li", "</ul", "</ol", "<pre", "<h1", "<h2", "<h3", "<h4", "<h5", "<h6")
        parts: List[str] = []
        for i, ln in enumerate(out_lines):
            if i > 0:
                prev = out_lines[i - 1]
                is_block = ln.startswith(block_tags) or prev.startswith(block_tags)
                if not is_block and prev and ln:
                    parts.append("<br>")
            if ln:
                parts.append(ln)
        return "".join(parts)

    def _md_inline(self, text: str) -> str:
        """行内 Markdown: 加粗 / 行内代码 / 斜体"""
        import re
        out = text
        out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)
        out = re.sub(r'`(.+?)`', r'<code>\1</code>', out)
        out = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', out)
        return out

    # ----- 发送 -----
    def _on_send(self):
        text = self.ed_input.toPlainText().strip()
        if not text:
            return
        if not self._current_sid:
            self._on_new_session()
        # 检查 API Key
        if not self.store.settings.get("ai_api_key"):
            self._add_bubble("error", "未配置 API Key，请点击右上角 ⚙ 设置模型与密钥。")
            dlg = AIConfigDialog(self.store, self)
            dlg.exec_()
            return
        # 添加用户气泡
        self._add_bubble("user", text)
        self.history.add_message(self._current_sid, "user", text)
        self.ed_input.clear()
        # 切换到"生成中"状态, 显示停止按钮
        self.btn_send.hide()
        self.btn_stop.show()
        # 启动思考动画
        self._start_loading()
        # 创建空 assistant 气泡, 流式增量填充
        self._stream_buf = ""
        self._stream_bubble = self._add_bubble("assistant", "▌")
        self._scroll_to_bottom()
        # 构造 messages (系统提示 + 最近 20 条)
        sys_prompt = self.store.settings.get("ai_system_prompt", "")
        s = self.history.get_session(self._current_sid)
        msgs = []
        if sys_prompt:
            msgs.append({"role": "system", "content": sys_prompt})
        recent = (s.get("messages", []) if s else [])[-20:]
        for m in recent:
            if m.get("role") in ("user", "assistant"):
                msgs.append({"role": m["role"], "content": m["content"]})
        # 调用 (流式)
        self._worker = AIWorkerThread(self.store.settings, msgs, self)
        self._worker.chunk_received.connect(self._on_chunk)
        self._worker.response_ready.connect(self._on_response)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.start()

    def _on_chunk(self, chunk: str):
        """流式增量: 追加到缓冲, 重新渲染当前气泡的 Markdown"""
        # 收到第一个 chunk 时, 关闭思考动画, 切换到"正在生成"状态
        if not self._stream_buf:
            self._stop_loading("正在生成…", "#059669")
            # 给状态加绿色徽章
            self.lbl_status.setStyleSheet(
                "font-size:12px;color:#059669;font-weight:700;"
                "background:#d1fae5;border:1px solid #a7f3d0;border-radius:8px;"
                "padding:2px 10px;"
            )
        self._stream_buf += chunk
        if self._stream_bubble is None:
            return
        html = self._md_to_html(self._stream_buf + " ▌")
        self._stream_bubble.setHtml(f'<body style="margin:0;padding:0;">{html}</body>')
        self._scroll_to_bottom()

    def _on_stop(self):
        """用户点击停止: 通知 worker 中断"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
            self.lbl_status.setText("正在停止…")

    def _on_response(self, content: str):
        """流式结束: 用完整内容替换气泡, 写入历史"""
        final = content
        if self._stream_bubble is not None:
            html = self._md_to_html(final)
            self._stream_bubble.setHtml(f'<body style="margin:0;padding:0;">{html}</body>')
            self._stream_bubble = None
        else:
            self._add_bubble("assistant", final)
        self._stream_buf = ""
        self.history.add_message(self._current_sid, "assistant", final)
        # 成功: 显示绿色"已完成"徽章 2 秒后恢复
        self._stop_loading("✓ 已完成", "#059669")
        self.lbl_status.setStyleSheet(
            "font-size:12px;color:#059669;font-weight:700;"
            "background:#d1fae5;border:1px solid #a7f3d0;border-radius:8px;"
            "padding:2px 10px;"
        )
        QTimer.singleShot(2200, lambda: self._stop_loading())
        self._worker = None
        self.btn_stop.hide()
        self.btn_send.show()
        self.btn_send.setEnabled(True)
        self._scroll_to_bottom()

    def _on_error(self, err: str):
        # 流式过程中出错: 移除空的 assistant 气泡 (它在 row_wrap 里)
        if self._stream_bubble is not None:
            # 向上找 row_wrap: _stream_bubble -> card -> row_wrap
            card = self._stream_bubble.parent()
            row_wrap = card.parent() if card else None
            if row_wrap is not None:
                row_wrap.setParent(None)
                row_wrap.deleteLater()
            self._stream_bubble = None
            self._stream_buf = ""
        self._add_bubble("error", err)
        # 错误: 在状态栏显示红色"请求失败"徽章 6 秒后恢复
        self._stop_loading()
        self._show_status(
            f"⚠ 请求失败: {err[:60]}{'…' if len(err) > 60 else ''}",
            color="#991b1b", bg="#fee2e2", border="#fecaca",
        )
        QTimer.singleShot(6000, lambda: self._stop_loading())
        self.btn_stop.hide()
        self.btn_send.show()
        self.btn_send.setEnabled(True)
        self._worker = None
        self._scroll_to_bottom()

    def _finish_generate(self):
        """生成结束 (正常/中断/出错) 的统一收尾"""
        self.btn_stop.hide()
        self.btn_send.show()
        self.btn_send.setEnabled(True)
        # 停掉 loading 动画
        self._stop_loading()
        self._worker = None
        self._scroll_to_bottom()

    # ==================== 思考进度动画 ====================
    def _start_loading(self):
        """在 lbl_status 跑点动画, 让用户看到 AI 正在思考"""
        self._loading_dots = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(380)
        self._loading_timer.timeout.connect(self._tick_loading)
        self._loading_timer.start()

    def _tick_loading(self):
        self._loading_dots = (self._loading_dots + 1) % 4
        dots = "·" * self._loading_dots + " " * (3 - self._loading_dots)
        self.lbl_status.setText(f"  AI 正在思考{dots}  ")
        self.lbl_status.setStyleSheet(
            "font-size:12px;color:#2563eb;font-weight:700;"
            "background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;"
            "padding:2px 10px;"
        )

    def _stop_loading(self, final_text: str = "就绪", final_color: str = "#94a3b8"):
        try:
            if hasattr(self, "_loading_timer") and self._loading_timer is not None:
                self._loading_timer.stop()
                self._loading_timer = None
        except RuntimeError:
            pass
        self.lbl_status.setText(final_text)
        self.lbl_status.setStyleSheet(
            f"font-size:11px;color:{final_color};font-weight:500;"
            "background:transparent;border:none;padding:0;"
        )

    def _show_status(self, text: str, color: str = "#0f172a", bg: str = "#f1f5f9", border: str = "#e2e8f0"):
        """通用: 在状态栏显示一条彩色信息 (eg. 错误红/警告橙)"""
        try:
            if hasattr(self, "_loading_timer") and self._loading_timer is not None:
                self._loading_timer.stop()
                self._loading_timer = None
        except RuntimeError:
            pass
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"font-size:11px;color:{color};font-weight:700;"
            f"background:{bg};border:1px solid {border};border-radius:8px;"
            "padding:2px 10px;"
        )

    def _scroll_to_bottom(self):
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def set_visible(self, visible: bool):
        """外部调用: 展开/折叠"""
        self.store.settings["ai_panel_visible"] = visible
        self.store.save()


class WrongWordItem:
    word: str
    id: Any = field(default_factory=uuid.uuid4)
    meaning: str = ""
    example: str = ""      # 图片绝对路径 (原 Tkinter 版中 example 字段是图片路径)
    source: str = "manual"
    wrong_count: int = 1
    correct_count: int = 0
    last_wrong_at: str = field(default_factory=lambda: iso(today()))
    next_review_at: str = field(default_factory=lambda: iso(today() + timedelta(days=1)))
    note: str = ""


# ---------------- AIChatPanel 主题支持方法 ----------------
def _ai_panel_apply_theme(self, theme: str):
    """MainWindow 调用: 切换 AI 面板主题 (背景/边框/文字)"""
    if theme not in ("light", "dark"):
        theme = "light"
    self._theme = theme
    self.setStyleSheet(self._get_chatpanel_qss(theme))
    for w in self.findChildren(QWidget):
        try:
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
        except Exception:
            pass

def _ai_panel_get_qss(self, theme: str) -> str:
    """生成 AI 面板主题样式 (用 MainWindow 的 THEME_COLORS 统一色板, 含牛奶色系)"""
    # 取 MainWindow 的 THEME_COLORS 统一色 (含牛奶色)
    main = None
    try:
        # 通过父链找 MainWindow
        p = self.parent()
        while p is not None and not isinstance(p, QMainWindow):
            p = p.parent()
        main = p
    except Exception:
        pass
    theme_colors = None
    if main is not None and hasattr(main, "THEME_COLORS"):
        theme_colors = main.THEME_COLORS.get(theme)
    # 兜底
    if theme == "dark":
        c = theme_colors or {
            "bg": "#0f172a", "card": "#1e293b", "border": "#334155",
            "text": "#f5f0e1", "text2": "#e8e3d3", "text3": "#c9c2b0",
            "accent": "#fbbf24", "accent_fg": "#0f172a",
            "nav_hover": "#334155", "nav_active": "#3a2810",
        }
    else:
        c = theme_colors or {
            "bg": "#f8fafc", "card": "#ffffff", "border": "#e2e8f0",
            "text": "#0f172a", "text2": "#475569", "text3": "#64748b",
            "accent": "#2563eb", "accent_fg": "#ffffff",
            "nav_hover": "#f1f5f9", "nav_active": "#dbeafe",
        }
    if theme == "dark":
        return (
            f"QWidget{{font-family:'Microsoft YaHei UI','Microsoft YaHei','微软雅黑';font-size:13px;"
            f"  color:{c['text']};}}"
            f"AIChatPanel{{background:{c['bg']};border-left:1px solid {c['card']};}}"
            f"QScrollArea{{border:none;background:transparent;}}"
            f"QScrollBar:vertical{{background:transparent;width:8px;margin:4px 2px;}}"
            f"QScrollBar::handle:vertical{{background:{c['text3']};border-radius:4px;min-height:30px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{c['text2']};}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
            f"QComboBox{{background:{c['card']};border:1px solid {c['border']};border-radius:8px;"
            f"  padding:6px 28px 6px 12px;font-size:13px;color:{c['text']};min-height:24px;}}"
            f"QComboBox:hover{{background:{c['nav_hover']};border-color:{c['accent']};}}"
            f"QComboBox:focus{{border-color:{c['accent']};}}"
            f"QComboBox::drop-down{{subcontrol-origin:padding;subcontrol-position:top right;"
            f"  width:24px;border:none;}}"
            f"QComboBox::down-arrow{{image:none;border-left:4px solid transparent;"
            f"  border-right:4px solid transparent;border-top:5px solid {c['text3']};}}"
            f"QComboBox QAbstractItemView{{background:{c['card']};border:1px solid {c['border']};"
            f"  border-radius:8px;padding:4px;selection-background-color:{c['nav_active']};"
            f"  selection-color:{c['text']};outline:0;color:{c['text']};}}"
            f"QTextEdit,QTextBrowser{{color:{c['text']};}}"
            f"QLabel{{color:{c['text']};}}"
            f"QLineEdit{{background:{c['card']};border:1px solid {c['border']};color:{c['text']};"
            f"  border-radius:8px;padding:6px 10px;}}"
        )
    # 浅色
    return (
        f"QWidget{{font-family:'Microsoft YaHei UI','Microsoft YaHei','微软雅黑';font-size:13px;"
        f"  color:{c['text']};}}"
        f"AIChatPanel{{background:{c['card']};border-left:1px solid {c['border']};}}"
        f"QScrollArea{{border:none;background:transparent;}}"
        f"QScrollBar:vertical{{background:transparent;width:8px;margin:4px 2px;}}"
        f"QScrollBar::handle:vertical{{background:#d1d5db;border-radius:4px;min-height:30px;}}"
        f"QScrollBar::handle:vertical:hover{{background:#9ca3af;}}"
        f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
        f"QComboBox{{background:#f3f4f6;border:1px solid {c['border']};border-radius:8px;"
        f"  padding:6px 28px 6px 12px;font-size:13px;color:#111827;min-height:24px;}}"
        f"QComboBox:hover{{background:#eef2ff;border-color:#c7d2fe;}}"
        f"QComboBox:focus{{border-color:{c['accent']};background:white;}}"
        f"QComboBox::drop-down{{subcontrol-origin:padding;subcontrol-position:top right;"
        f"  width:24px;border:none;}}"
        f"QComboBox::down-arrow{{image:none;border-left:4px solid transparent;"
        f"  border-right:4px solid transparent;border-top:5px solid #6b7280;}}"
        f"QComboBox QAbstractItemView{{background:white;border:1px solid {c['border']};"
        f"  border-radius:8px;padding:4px;selection-background-color:{c['nav_active']};"
        f"  selection-color:#4338ca;outline:0;color:#111827;}}"
        f"QTextEdit,QTextBrowser{{color:{c['text']};}}"
        f"QLabel{{color:{c['text']};}}"
        f"QLineEdit{{background:{c['card']};border:1px solid {c['border']};color:{c['text']};"
        f"  border-radius:8px;padding:6px 10px;}}"
    )

# 绑定到 AIChatPanel (鸭子类型, 直接挂到类上)
AIChatPanel._apply_theme = _ai_panel_apply_theme
AIChatPanel._get_chatpanel_qss = _ai_panel_get_qss
del _ai_panel_apply_theme
del _ai_panel_get_qss


@dataclass
class StudyStore:
    daily_plan: int = 50
    today_date: str = field(default_factory=lambda: today().isoformat())
    plan_id: Optional[int] = None
    plans: List[Dict[str, Any]] = field(default_factory=list)
    words: List[Dict[str, Any]] = field(default_factory=list)
    progress: Dict[str, Any] = field(default_factory=lambda: {
        "index": 0,
        "learned_today": 0,
        "reviewed_today": 0,
        "known_ids": [],
        "unknown_ids": [],
        "review_ids": [],
    })
    wrong_words: List[Dict[str, Any]] = field(default_factory=list)
    grammars: List[Dict[str, Any]] = field(default_factory=list)
    readings: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[Dict[str, Any]] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=lambda: {
        "theme": "spring_snow",
        "auto_pronounce": False,
        "example_count": 2,
        # AI 面板配置 (P0-A)
        "ai_provider": "siliconflow",   # siliconflow / custom
        "ai_api_key": "",
        "ai_base_url": "https://api.siliconflow.cn/v1",
        "ai_model": "deepseek-ai/DeepSeek-V4-Flash",
        "ai_system_prompt": "你是一个考研复习助手，请简洁准确地回答问题。",
        "ai_panel_visible": False,      # 启动时默认折叠
    })

    @classmethod
    def load(cls) -> "StudyStore":
        if not DATA_PATH.exists():
            store = cls()
            store.save()
            return store
        try:
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            _migrate_old_keys(data)
            return cls(
                daily_plan=int(data.get("daily_plan", 50) or 50),
                today_date=str(data.get("today_date") or today().isoformat()),
                plan_id=data.get("plan_id"),
                plans=list(data.get("plans") or []),
                words=list(data.get("words") or []),
                progress=dict(data.get("progress") or {}),
                wrong_words=list(data.get("wrong_words") or []),
                grammars=list(data.get("grammars") or []),
                readings=list(data.get("readings") or []),
                notes=list(data.get("notes") or []),
                settings=dict(data.get("settings") or {}),
            )
        except Exception:
            return cls()

    def save(self) -> None:
        try:
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            import traceback
            print(f"[DataStore.save] 失败: {e}")
            traceback.print_exc()

    # ---------- Dashboard 辅助字段 ----------
    @property
    def kaoyan_date(self) -> date:
        """2028考研初试日（按 2027-12-25 圣诞前后惯例）。可在 settings['kaoyan_date'] 覆盖 YYYY-MM-DD"""
        custom = self.settings.get("kaoyan_date")
        if isinstance(custom, str) and custom:
            try:
                return datetime.strptime(custom, "%Y-%m-%d").date()
            except Exception:
                pass
        return date(2027, 12, 25)

    def ensure_today_tasks(self) -> None:
        """每次回到主界面调用：跨天后刷新今日任务列表（保留已勾选状态跨日无意义）"""
        today_iso = today().isoformat()
        s = self.settings
        if s.get("dashboard_date") != today_iso:
            s["dashboard_date"] = today_iso
            default_tasks = s.get("default_tasks") or [
                {"text": "背 50 个单词", "done": False},
                {"text": "复习昨日英语错题 10 题", "done": False},
                {"text": "数学真题 1 节 / 1 章错题回顾", "done": False},
                {"text": "专业课知识点 30 分钟精读", "done": False},
                {"text": "阅读 1 篇英语阅读理解并订正", "done": False},
                {"text": "写择校笔记 1 条（目标院校信息）", "done": False},
            ]
            # 给每一项分配 id 方便定位
            s["today_tasks"] = [
                {
                    "id": t.get("id") or uuid.uuid4().hex[:8],
                    "text": str(t.get("text", "") or ""),
                    "done": bool(t.get("done", False)),
                }
                for t in default_tasks
                if str(t.get("text", "") or "").strip()
            ]
            if "target_school" not in s or not s["target_school"]:
                s["target_school"] = "待定"
            if "target_major" not in s or not s["target_major"]:
                s["target_major"] = "待定"
            if "daily_quote" not in s or not s.get("daily_quote_date") == today_iso:
                import random
                quotes = QUOTES
                s["daily_quote"] = random.choice(quotes)
                s["daily_quote_date"] = today_iso
            self.save()

    def toggle_task_done(self, task_id: str, done: bool) -> None:
        tasks = self.settings.get("today_tasks") or []
        for t in tasks:
            if t.get("id") == task_id:
                t["done"] = bool(done)
                break
        # 排序：未完成在前，已完成在后（"做一个就划到底部变灰"）
        tasks.sort(key=lambda x: (bool(x.get("done")), x.get("__order", 0)))
        self.settings["today_tasks"] = tasks
        self.save()

    def add_wrong_word(
        self,
        word: str,
        meaning: str = "",
        example: str = "",
        source: str = "manual",
        note: str = "",
    ) -> Dict[str, Any]:
        if not word:
            raise ValueError("错题单词不能为空")
        existing = next(
            (w for w in self.wrong_words if w.get("word") == word), None
        )
        if existing is not None:
            existing["wrong_count"] = int(existing.get("wrong_count", 0)) + 1
            existing["last_wrong_at"] = iso(today())
            if meaning and not existing.get("meaning"):
                existing["meaning"] = meaning
            if example and not existing.get("example"):
                existing["example"] = example
            if note and not existing.get("note"):
                existing["note"] = note
            self.save()
            return existing
        item = asdict(WrongWordItem(
            word=word, meaning=meaning, example=example, source=source, note=note
        ))
        item["id"] = uuid.uuid4().hex
        self.wrong_words.append(item)
        self.save()
        return item

    # ---------- 单词背诵 (P0-D) ----------
    # 艾宾浩斯复习间隔 (天): 1, 2, 4, 7, 15
    VOCAB_REVIEW_INTERVALS = [1, 2, 4, 7, 15]

    def ensure_vocab(self) -> None:
        """词表为空时, 用内置种子初始化 (只跑一次)"""
        if self.words:
            return
        today_iso = today().isoformat()
        self.words = [
            {
                "id": uuid.uuid4().hex[:12],
                "word": w["word"],
                "phonetic": w.get("phonetic", ""),
                "meaning": w.get("meaning", ""),
                "example": w.get("example", ""),
                # 艾宾浩斯复习状态
                "stage": 0,            # 已掌握阶段 0-5 (5=毕业)
                "next_review": today_iso,  # 下次复习日期
                "last_review": "",    # 上次复习日期
                "wrong_count": 0,     # 答错次数
            }
            for w in KAOYAN_VOCAB_SEED
        ]
        # 进度初始化
        p = self.progress
        p.setdefault("index", 0)
        p.setdefault("learned_today", 0)
        p.setdefault("reviewed_today", 0)
        p.setdefault("known_ids", [])
        p.setdefault("unknown_ids", [])
        p.setdefault("review_ids", [])
        p.setdefault("learn_date", today_iso)  # 学习日期, 跨天重置计数
        self.save()

    def vocab_stats(self) -> Dict[str, int]:
        """汇总单词背诵进度"""
        self.ensure_vocab()
        self._vocab_rollover_day()
        total = len(self.words)
        known = sum(1 for w in self.words if w.get("stage", 0) >= len(self.VOCAB_REVIEW_INTERVALS))
        today_iso = today().isoformat()
        due_review = sum(
            1 for w in self.words
            if 0 < w.get("stage", 0) < len(self.VOCAB_REVIEW_INTERVALS)
            and str(w.get("next_review", "")) <= today_iso
        )
        learned_today = int(self.progress.get("learned_today", 0))
        reviewed_today = int(self.progress.get("reviewed_today", 0))
        return {
            "total": total,
            "known": known,
            "due_review": due_review,
            "learned_today": learned_today,
            "reviewed_today": reviewed_today,
            "remaining": max(0, total - known),
        }

    def _vocab_rollover_day(self) -> None:
        """跨天重置今日学习/复习计数"""
        today_iso = today().isoformat()
        if self.progress.get("learn_date") != today_iso:
            self.progress["learn_date"] = today_iso
            self.progress["learned_today"] = 0
            self.progress["reviewed_today"] = 0
            self.save()

    def vocab_next_word(self) -> Optional[Dict[str, Any]]:
        """取下一个待学习的词 (stage==0 的未学词)"""
        self.ensure_vocab()
        self._vocab_rollover_day()
        for w in self.words:
            if w.get("stage", 0) == 0:
                return w
        return None

    def vocab_next_review(self) -> Optional[Dict[str, Any]]:
        """取下一个待复习的词 (到期且未毕业)"""
        self.ensure_vocab()
        self._vocab_rollover_day()
        today_iso = today().isoformat()
        for w in self.words:
            if 0 < w.get("stage", 0) < len(self.VOCAB_REVIEW_INTERVALS):
                if str(w.get("next_review", "")) <= today_iso:
                    return w
        return None

    def vocab_mark(self, word_id: str, known: bool) -> Dict[str, Any]:
        """标记一个词 认识/不认识, 更新艾宾浩斯阶段"""
        w = next((x for x in self.words if x.get("id") == word_id), None)
        if w is None:
            return {}
        today_iso = today().isoformat()
        stage = int(w.get("stage", 0))
        was_new = (stage == 0)
        if known:
            # 认识: 阶段 +1, 按间隔安排下次复习
            stage = min(stage + 1, len(self.VOCAB_REVIEW_INTERVALS))
            if stage >= len(self.VOCAB_REVIEW_INTERVALS):
                # 毕业, 不再复习
                w["next_review"] = ""
            else:
                gap = self.VOCAB_REVIEW_INTERVALS[stage - 1]
                w["next_review"] = (today() + timedelta(days=gap)).isoformat()
            w["stage"] = stage
        else:
            # 不认识: 阶段回退到 1 (明天再复习), 错误计数 +1
            w["stage"] = 1
            w["next_review"] = (today() + timedelta(days=1)).isoformat()
            w["wrong_count"] = int(w.get("wrong_count", 0)) + 1
        w["last_review"] = today_iso
        # 更新今日计数
        if was_new:
            self.progress["learned_today"] = int(self.progress.get("learned_today", 0)) + 1
        else:
            self.progress["reviewed_today"] = int(self.progress.get("reviewed_today", 0)) + 1
        self.save()
        return w

    def vocab_import(self, items: List[Dict[str, Any]]) -> int:
        """从外部词表导入, 跳过已存在的 word. 返回新增数量"""
        self.ensure_vocab()
        existing = {w["word"].lower() for w in self.words if w.get("word")}
        added = 0
        today_iso = today().isoformat()
        for it in items:
            word = (it.get("word") or "").strip()
            if not word or word.lower() in existing:
                continue
            self.words.append({
                "id": uuid.uuid4().hex[:12],
                "word": word,
                "phonetic": it.get("phonetic", ""),
                "meaning": it.get("meaning", ""),
                "example": it.get("example", ""),
                "stage": 0,
                "next_review": today_iso,
                "last_review": "",
                "wrong_count": 0,
            })
            existing.add(word.lower())
            added += 1
        if added:
            self.save()
        return added

    # ---------- Markdown 笔记 (网课学习区) ----------
    def list_notes(self, subject: Optional[str] = None) -> List[Dict[str, Any]]:
        arr = list(self.notes or [])
        if subject:
            arr = [n for n in arr if n.get("subject") == subject]
        arr.sort(key=lambda n: str(n.get("updated_at") or ""), reverse=True)
        return arr

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        return next((n for n in self.notes if n.get("id") == note_id), None)

    def upsert_note(
        self,
        subject: str,
        title: str,
        content: str,
        note_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        subject = subject if subject in NOTE_SUBJECTS else NOTE_SUBJECTS[0]
        title = (title or "").strip() or "未命名笔记"
        content = content or ""
        now = datetime.now().isoformat(timespec="seconds")
        if note_id:
            existing = self.get_note(note_id)
            if existing is not None:
                existing["subject"] = subject
                existing["title"] = title
                existing["content"] = content
                existing["updated_at"] = now
                self.save()
                return existing
        new_note = {
            "id": uuid.uuid4().hex[:12],
            "subject": subject,
            "title": title,
            "content": content,
            "created_at": now,
            "updated_at": now,
        }
        self.notes.append(new_note)
        self.save()
        return new_note

    def delete_note(self, note_id: str) -> bool:
        before = len(self.notes)
        self.notes = [n for n in self.notes if n.get("id") != note_id]
        if len(self.notes) != before:
            self.save()
            return True
        return False


def _migrate_old_keys(d: Dict[str, Any]) -> None:
    """把旧 JSON 里缺失 id 的错词条补一次 uuid，保证选中/删除 iid 映射稳定。"""
    wws = d.get("wrong_words") or []
    seen: set = set()
    need_save = False
    for it in wws:
        if not it.get("id") or it.get("id") in seen:
            it["id"] = uuid.uuid4().hex
            need_save = True
        seen.add(it["id"])
    if need_save:
        try:
            DATA_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


# ===========================================================
# 工具函数
# ===========================================================
def scale_pixmap(pix: QPixmap, *, max_w: int = 0, max_h: int = 0) -> QPixmap:
    if pix.isNull():
        return pix
    w, h = pix.width(), pix.height()
    if w == 0 or h == 0:
        return pix
    ratio = 1.0
    if max_w > 0 and w > max_w:
        ratio = min(ratio, max_w / w)
    if max_h > 0 and h > max_h:
        ratio = min(ratio, max_h / h)
    if abs(ratio - 1.0) < 1e-6:
        return pix
    return pix.scaled(
        int(w * ratio), int(h * ratio),
        Qt.KeepAspectRatio, Qt.SmoothTransformation,
    )


def load_pixmap_safe(p: str, *, max_w: int = 0, max_h: int = 0) -> Optional[QPixmap]:
    try:
        path = Path(p)
        if not (path.exists() and path.is_file()):
            return None
        qimg = QImage(str(path))
        if qimg.isNull():
            # Pillow fallback (Windows 中文路径某些 PNG 格式 QImage 不识别)
            try:
                from PIL import Image  # type: ignore
                with Image.open(path) as im:
                    im = im.convert("RGBA")
                    data = im.tobytes("raw", "RGBA")
                    qimg = QImage(data, im.width, im.height, QImage.Format_RGBA8888).copy()
            except Exception:
                return None
        pix = QPixmap.fromImage(qimg)
        if max_w > 0 or max_h > 0:
            pix = scale_pixmap(pix, max_w=max_w, max_h=max_h)
        return pix
    except Exception:
        return None


# ===========================================================
# 编辑错词弹窗 (支持题 / 答案 / 解析 / 上传图片)
# ===========================================================
class WrongWordEditorDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        word: str = "",
        meaning: str = "",
        note: str = "",
        image_path: str = "",
        title: str = "编辑错词",
        allow_edit_word: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(540, 420)
        self._image_path = image_path

        form = QVBoxLayout(self)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)

        self.word_edit = QLineEdit(word)
        self.word_edit.setPlaceholderText("错题：可以填写题目标题，或上传图片再填标题")
        if not allow_edit_word:
            self.word_edit.setReadOnly(True)
        self.meaning_edit = QLineEdit(meaning)
        self.meaning_edit.setPlaceholderText("答案 / 正确含义")
        self.note_edit = QTextEdit(note)
        self.note_edit.setPlaceholderText("解析 / 笔记 (对应错词表的解析列)")
        self.note_edit.setFixedHeight(110)

        img_row = QHBoxLayout()
        self.image_preview = QLabel("(无图片)")
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setFixedHeight(120)
        self.image_preview.setStyleSheet(
            "background: rgba(255,255,255,60); border-radius: 6px; color: #64748b;"
        )
        self.image_path_edit = QLineEdit(image_path)
        self.image_path_edit.setPlaceholderText("图片绝对路径")
        self.image_path_edit.setReadOnly(True)
        btn_upload = QPushButton("上传图片…")
        btn_clear = QPushButton("清空图片")
        btn_upload.clicked.connect(self._on_upload)
        btn_clear.clicked.connect(self._on_clear_image)
        img_row.addWidget(self.image_preview, 1)

        form.addWidget(QLabel("错题名"))
        form.addWidget(self.word_edit)
        form.addWidget(QLabel("答案"))
        form.addWidget(self.meaning_edit)
        form.addWidget(QLabel("解析 / 笔记"))
        form.addWidget(self.note_edit)
        img_box = QHBoxLayout()
        img_box.addWidget(self.image_path_edit, 1)
        img_box.addWidget(btn_upload)
        img_box.addWidget(btn_clear)
        form.addWidget(QLabel("题目原图"))
        form.addLayout(img_box)
        form.addWidget(self.image_preview)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addWidget(bb)

        self._refresh_preview()

    # ---- 对外取值 ----
    def get_word(self) -> str:
        return self.word_edit.text().strip()

    def get_meaning(self) -> str:
        return self.meaning_edit.text().strip()

    def get_note(self) -> str:
        return self.note_edit.toPlainText().strip()

    def get_image_path(self) -> str:
        return self._image_path

    # ---- 内部 ----
    def _on_upload(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择题目图片", str(IMAGE_DIR if IMAGE_DIR.exists() else Path.home()),
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp)",
        )
        if not p:
            return
        p = str(Path(p).resolve())
        self._image_path = p
        self.image_path_edit.setText(p)
        self._refresh_preview()

    def _on_clear_image(self):
        self._image_path = ""
        self.image_path_edit.setText("")
        self._refresh_preview()

    def _refresh_preview(self):
        if not self._image_path:
            self.image_preview.setText("(无图片)")
            self.image_preview.setPixmap(QPixmap())
            return
        pix = load_pixmap_safe(self._image_path, max_h=120)
        if pix is None or pix.isNull():
            self.image_preview.setText(f"(图片加载失败)\n{self._image_path}")
            self.image_preview.setPixmap(QPixmap())
            return
        self.image_preview.setPixmap(pix)
        self.image_preview.setText("")


# ===========================================================
# 图片浏览 Toplevel 等价类: QDialog (双击错词原图弹出, 等比缩放随窗口)
# ===========================================================
class ImageViewerDialog(QDialog):
    def __init__(self, parent=None, *, image_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"错题原图 - {Path(image_path).name}")
        self.resize(1000, 760)
        self.setMinimumSize(320, 240)
        self._src_path = image_path
        self._src_pix: Optional[QPixmap] = load_pixmap_safe(image_path)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background: #fdfaf7;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render()

    def update_image(self, image_path: str):
        self.setWindowTitle(f"错题原图 - {Path(image_path).name}")
        self._src_path = image_path
        self._src_pix = load_pixmap_safe(image_path)
        self._render()

    def _render(self):
        if self._src_pix is None or self._src_pix.isNull():
            self._label.setText(f"图片加载失败：\n{self._src_path}")
            return
        w = max(1, self._label.width())
        h = max(1, self._label.height())
        scaled = scale_pixmap(self._src_pix, max_w=w, max_h=h)
        self._label.setPixmap(scaled)
        self._label.setText("")


# ===========================================================
# EnglishPage (错词本 Tab)
# ===========================================================
class EnglishPage(QWidget):
    def __init__(self, store: StudyStore, parent=None, theme_colors: dict = None):
        super().__init__(parent)
        self.store = store
        self._theme_colors = theme_colors or {
            "bg": "#f8fafc", "card": "#ffffff", "border": "#e2e8f0",
            "text": "#0f172a", "text2": "#475569",
            "nav_hover": "#f1f5f9", "nav_active": "#dbeafe",
            "accent": "#2563eb", "accent_fg": "#ffffff",
        }
        self._thumb_cache: Dict[str, QPixmap] = {}
        self._viewer: Optional[ImageViewerDialog] = None
        self._last_shown_row: Optional[int] = None
        self._sel_connected: bool = False
        self._build_ui()
        self.refresh()

    # ----- UI -----
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ===== 英语模块多 Tab 结构 (P0-C) =====
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            "QTabWidget::pane {"
            "  border: 1px solid #e2e8f0;"
            "  border-radius: 0px 8px 8px 8px;"
            "  background: #ffffff;"
            "  top: -1px;"
            "}"
            "QTabBar::tab {"
            "  background: #f8fafc;"
            "  border: 1px solid #e2e8f0;"
            "  border-bottom: 1px solid #e2e8f0;"
            "  border-top-left-radius: 8px;"
            "  border-top-right-radius: 8px;"
            "  padding: 7px 18px;"
            "  margin-right: 2px;"
            "  font-size: 13px;"
            "  font-weight: 600;"
            "  color: #64748b;"
            "}"
            "QTabBar::tab:selected {"
            "  background: #ffffff;"
            "  color: #2563eb;"
            "  border: 1px solid #e2e8f0;"
            "  border-bottom: 1px solid #ffffff;"
            "  font-weight: 700;"
            "}"
            "QTabBar::tab:hover:!selected {"
            "  background: #f1f5f9;"
            "  color: #334155;"
            "}"
        )
        root.addWidget(self.tabs, 1)

        # ===== Tab1: 错题本 (迁移现有功能) =====
        wrong_tab = QWidget()
        wrong_layout = QVBoxLayout(wrong_tab)
        wrong_layout.setContentsMargins(0, 0, 0, 0)
        wrong_layout.setSpacing(10)

        # ----- 顶部控制区 QGroupBox -----
        ctrl_group = QGroupBox("错题本 · 操作")
        ctrl_group.setStyleSheet(
            "QGroupBox {"
            "  background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #10b981;"
            "  border-radius: 12px;"
            "  margin-top: 16px;"
            "  padding-top: 10px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin; left: 18px; padding: 2px 10px;"
            "  color: #059669; font-size: 13px; font-weight: 700;"
            "  background: transparent;"
            "}"
        )
        grid = QHBoxLayout(ctrl_group)
        grid.setContentsMargins(12, 14, 12, 12)
        grid.setSpacing(8)

        self.btn_upload = QPushButton("上传错题")
        self.btn_add = QPushButton("添加错题")
        self.btn_answer = QPushButton("输入答案")
        self.btn_update_q = QPushButton("更新错题")
        self.btn_update_a = QPushButton("更新答案")
        self.btn_del = QPushButton("删除错题")
        self.btn_refresh = QPushButton("刷新")
        for b in (self.btn_upload, self.btn_add, self.btn_answer, self.btn_update_q,
                  self.btn_update_a, self.btn_del, self.btn_refresh):
            b.setCursor(Qt.PointingHandCursor)

        grid.addWidget(self.btn_upload)
        grid.addWidget(self.btn_add)
        grid.addWidget(self.btn_answer)
        grid.addWidget(self.btn_update_q)
        grid.addWidget(self.btn_update_a)
        grid.addWidget(self.btn_del)
        grid.addSpacing(16)
        grid.addWidget(QLabel("编号(1-N)"))
        self.idx_edit = QLineEdit()
        self.idx_edit.setFixedWidth(70)
        self.idx_edit.setPlaceholderText("选填")
        grid.addWidget(self.idx_edit)
        grid.addStretch(1)
        grid.addWidget(self.btn_refresh)

        wrong_layout.addWidget(ctrl_group)

        # ===== 错词表 QTableWidget =====
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["序号", "错题名", "答案", "解析", "ID"])
        self.tbl.setColumnHidden(4, True)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.verticalHeader().setDefaultSectionSize(130)  # 容纳缩略图
        self.tbl.setIconSize(QSize(120, 120))
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl.setStyleSheet(self._get_wrong_table_qss())
        self.tbl.setWordWrap(True)
        wrong_layout.addWidget(self.tbl, 1)

        # 加入 Tab1
        self.tabs.addTab(wrong_tab, "错题本")

        # ===== Tab2-6 占位 (后续 P0-D / P1 / P2 实现) =====
        self.tabs.addTab(self._build_vocab_tab(), "单词背诵")
        self.tabs.addTab(self._build_reading_tab(), "阅读理解")
        self.tabs.addTab(self._build_translation_tab(), "翻译练习")
        self.tabs.addTab(self._build_writing_tab(), "写作练习")
        self.tabs.addTab(self._build_speaking_tab(), "口语练习")

        # 切换 Tab 时触发内容区淡入动画
        self.tabs.currentChanged.connect(self._on_english_tab_changed)

        # ----- 信号 -----
        self.btn_upload.clicked.connect(self._on_upload_questions)
        self.btn_add.clicked.connect(self._on_add_question)
        self.btn_answer.clicked.connect(lambda: self._on_edit(kind="answer"))
        self.btn_update_q.clicked.connect(lambda: self._on_edit(kind="word"))
        self.btn_update_a.clicked.connect(lambda: self._on_edit(kind="all"))
        self.btn_del.clicked.connect(self._on_delete)
        self.btn_refresh.clicked.connect(self.refresh)
        self.tbl.cellDoubleClicked.connect(self._on_double_click)

        # Delete 快捷键
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.tbl)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(self._on_delete)

    # ----- 主题 -----
    def _get_wrong_table_qss(self) -> str:
        """根据当前主题生成错题本表格 QSS (表头/网格线/选中态都用主题色)"""
        c = self._theme_colors
        return (
            f"QTableWidget {{"
            f"  background: {c['card']};"
            f"  gridline-color: {c['border']};"
            f"  color: {c['text']};"
            f"  selection-background-color: {c['accent']};"
            f"  selection-color: {c.get('accent_fg', '#ffffff')};"
            f"  alternate-background-color: {c['bg']};"
            f"}}"
            f"QHeaderView::section {{"
            f"  background: {c['nav_hover']};"
            f"  color: {c['text']};"
            f"  padding: 6px 8px;"
            f"  border: none;"
            f"  border-right: 1px solid {c['border']};"
            f"  font-weight: 600;"
            f"}}"
            f"QTableWidget::item {{"
            f"  padding: 2px;"
            f"  border-bottom: 1px solid {c['border']};"
            f"}}"
            f"QTableWidget::item:selected {{"
            f"  background: {c['nav_active']};"
            f"  color: {c['text']};"
            f"}}"
        )

    def _apply_theme(self, theme_colors: dict):
        """切换主题时调用: 重设错题本表格样式"""
        self._theme_colors = theme_colors
        try:
            self.tbl.setStyleSheet(self._get_wrong_table_qss())
        except Exception:
            pass

    # ----- 工具：选中定位 -----
    def _first_selected_index(self) -> Optional[int]:
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()})
        if not rows:
            return self._parse_idx_from_input()
        return rows[0]

    def _all_selected_indices(self) -> List[int]:
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()}, reverse=True)
        if not rows:
            idx = self._parse_idx_from_input()
            if idx is not None:
                rows = [idx]
        return rows

    def _parse_idx_from_input(self) -> Optional[int]:
        txt = self.idx_edit.text().strip()
        if not txt.isdigit():
            return None
        n = int(txt)
        if 1 <= n <= len(self.store.wrong_words):
            return n - 1
        return None

    def _confirm(self, title: str, text: str) -> bool:
        r = QMessageBox.question(
            self, title, text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        return r == QMessageBox.Yes

    # ----- 业务动作 -----
    def _on_upload_questions(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择错题图片", str(IMAGE_DIR if IMAGE_DIR.exists() else Path.home()),
            "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp)",
        )
        if not paths:
            return
        added = 0
        for p in paths:
            pp = Path(p).resolve()
            word = pp.stem
            abs_path = str(pp)
            try:
                self.store.add_wrong_word(
                    word=word, meaning="", example=abs_path, source="upload", note=""
                )
                added += 1
            except Exception as e:
                QMessageBox.warning(self, "上传失败", f"{pp.name}: {e}")
        if added:
            self.store.save()
            self.refresh()
            QMessageBox.information(self, "完成", f"成功添加 {added} 条错题")

    def _on_add_question(self):
        dlg = WrongWordEditorDialog(
            self, title="添加错题", allow_edit_word=True,
            word="", meaning="", note="", image_path="",
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        word, meaning, note, img = (
            dlg.get_word(), dlg.get_meaning(), dlg.get_note(), dlg.get_image_path()
        )
        if not word and not img:
            QMessageBox.warning(self, "提示", "错题名 和 题目原图 至少填一项")
            return
        title = word if word else Path(img).stem
        try:
            self.store.add_wrong_word(
                word=title, meaning=meaning, example=img, source="manual", note=note
            )
        except Exception as e:
            QMessageBox.warning(self, "添加失败", str(e))
            return
        self.store.save()
        self.refresh()

    def _on_edit(self, *, kind: str):
        row = self._first_selected_index()
        if row is None:
            QMessageBox.information(self, "提示", "请先在表格里选中一条（或填写编号）")
            return
        item = self.store.wrong_words[row]
        allow_word = kind in ("word", "all")
        title_map = {
            "answer": "输入答案",
            "word": "更新错题",
            "all": "更新答案与错题",
        }
        dlg = WrongWordEditorDialog(
            self,
            title=title_map.get(kind, "编辑"),
            word=item.get("word", ""),
            meaning=item.get("meaning", ""),
            note=item.get("note", ""),
            image_path=item.get("example", ""),
            allow_edit_word=allow_word,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        if allow_word:
            item["word"] = dlg.get_word() or item.get("word", "")
        if kind in ("answer", "all"):
            item["meaning"] = dlg.get_meaning()
        if kind in ("word", "all"):
            item["note"] = dlg.get_note()
            item["example"] = dlg.get_image_path()
        self.store.save()
        self.refresh()

    def _on_delete(self):
        rows = self._all_selected_indices()
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的错题（或填写编号）")
            return
        if len(rows) == 1:
            one = self.store.wrong_words[rows[0]]
            if not self._confirm("删除", f"确定删除错题：{one.get('word')} ?"):
                return
        else:
            if not self._confirm("删除", f"确定删除选中的 {len(rows)} 条错题？"):
                return
        for r in rows:
            if 0 <= r < len(self.store.wrong_words):
                self.store.wrong_words.pop(r)
        self.store.save()
        self.refresh()

    def _on_double_click(self, row: int, col: int):
        if 0 > row or row >= len(self.store.wrong_words):
            return
        it = self.store.wrong_words[row]
        p = (it.get("example") or "").strip()
        if not p or not Path(p).exists():
            QMessageBox.information(self, "提示", "该错题没有关联原图")
            return
        if self._viewer is not None and self._viewer.isVisible():
            self._viewer.update_image(p)
            self._viewer.raise_()
            self._viewer.activateWindow()
            return
        self._viewer = ImageViewerDialog(self, image_path=p)
        self._viewer.setAttribute(Qt.WA_DeleteOnClose, False)
        self._viewer.finished.connect(lambda _r: self._clear_viewer())
        self._viewer.show()

    def _clear_viewer(self):
        self._viewer = None

    # ----- 刷新 -----
    def refresh(self):
        data = self.store.wrong_words
        self.tbl.setRowCount(len(data))
        # 先补 id（兼容老 JSON）
        need_save = False
        for it in data:
            if not it.get("id"):
                it["id"] = uuid.uuid4().hex
                need_save = True
        if need_save:
            self.store.save()

        for row, it in enumerate(data):
            wd = str(it.get("word", "") or "")
            meaning = str(it.get("meaning", "") or "")
            note = str(it.get("note", "") or "")
            item_id = str(it.get("id", ""))
            display_answer = "****" if meaning else ""

            # 序号
            self.tbl.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            # 错题名（带图片 icon + 文字）
            cell = QTableWidgetItem(wd)
            img_path = str(it.get("example") or "")
            pix: Optional[QPixmap] = None
            if img_path and item_id:
                if item_id in self._thumb_cache:
                    pix = self._thumb_cache[item_id]
                else:
                    pix = load_pixmap_safe(img_path, max_h=120, max_w=160)
                    if pix is not None:
                        self._thumb_cache[item_id] = pix
            if pix is not None:
                cell.setIcon(QIcon(pix))
            cell.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tbl.setItem(row, 1, cell)

            # 答案（未编辑显示 ****）
            ans_cell = QTableWidgetItem(display_answer)
            ans_cell.setData(Qt.UserRole, meaning)
            ans_cell.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tbl.setItem(row, 2, ans_cell)
            # 解析
            note_cell = QTableWidgetItem(note)
            note_cell.setTextAlignment(Qt.AlignLeft | Qt.AlignTop | Qt.AlignVCenter)
            self.tbl.setItem(row, 3, note_cell)
            # ID (隐藏)
            self.tbl.setItem(row, 4, QTableWidgetItem(item_id))

        self.tbl.resizeRowsToContents()
        # 答案 hover: 只连接一次信号 (避免重复 connect 导致触发多次报错)
        if not self._sel_connected:
            self.tbl.itemSelectionChanged.connect(self._on_sel_changed)
            self._sel_connected = True

    def _on_sel_changed(self):
        # 把之前高亮的行恢复 ****
        if self._last_shown_row is not None:
            cell = self.tbl.item(self._last_shown_row, 2)
            if cell is not None:
                real = cell.data(Qt.UserRole)
                if real:
                    cell.setText("****")
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()})
        if not rows:
            self._last_shown_row = None
            return
        r = rows[0]
        cell = self.tbl.item(r, 2)
        if cell is not None:
            real = cell.data(Qt.UserRole)
            if real is not None:
                cell.setText(str(real))
        self._last_shown_row = r

    # ===== 英语模块 Tab2-6 占位 (后续 P0-D / P1 / P2 实现) =====
    def _build_vocab_tab(self) -> QWidget:
        """Tab2: 单词背诵 (P0-D) - 翻卡 + 艾宾浩斯复习"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        # vocab 状态
        self._vocab_word: Optional[Dict[str, Any]] = None
        self._vocab_flipped: bool = False
        self._vocab_mode: str = "learn"  # learn / review

        # ----- 顶部进度统计栏 -----
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self._vocab_stats_lab = QLabel("加载中…")
        self._vocab_stats_lab.setStyleSheet(
            "background: #ffffff; border: 1px solid #e2e8f0;"
            " border-radius: 10px; padding: 7px 14px; font-size: 13px; color: #0f172a;"
            " font-weight: 600;"
        )
        stats_row.addWidget(self._vocab_stats_lab, 1)

        # 模式切换
        self._vocab_mode_learn = QPushButton("📚 学习新词")
        self._vocab_mode_review = QPushButton("🔄 复习")
        for b in (self._vocab_mode_learn, self._vocab_mode_review):
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setStyleSheet(
                "QPushButton{background:#f1f5f9;color:#334155;"
                "border:1px solid #e2e8f0;border-radius:10px;"
                "padding:7px 16px;font-size:13px;font-weight:600;}"
                "QPushButton:hover{background:#e2e8f0;}"
                "QPushButton:checked{background:#2563eb;color:white;border-color:#2563eb;}"
            )
        self._vocab_mode_learn.setChecked(True)
        self._vocab_mode_learn.clicked.connect(lambda: self._vocab_switch_mode("learn"))
        self._vocab_mode_review.clicked.connect(lambda: self._vocab_switch_mode("review"))
        stats_row.addWidget(self._vocab_mode_learn)
        stats_row.addWidget(self._vocab_mode_review)

        btn_import = QPushButton("📥 导入词表")
        btn_import.setCursor(Qt.PointingHandCursor)
        btn_import.setStyleSheet(
            "QPushButton{background:#ffffff;color:#475569;"
            "border:1px solid #e2e8f0;border-radius:10px;"
            "padding:7px 16px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#f8fafc;border-color:#cbd5e1;}"
        )
        btn_import.clicked.connect(self._vocab_import)
        stats_row.addWidget(btn_import)
        v.addLayout(stats_row)

        # ----- 单词卡 (可点击翻面) -----
        self._vocab_card = QFrame()
        self._vocab_card.setCursor(Qt.PointingHandCursor)
        self._vocab_card.setMinimumHeight(320)
        self._vocab_card.setStyleSheet(
            "QFrame{background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #3b82f6;"
            "  border-radius: 16px;}"
        )
        card_lay = QVBoxLayout(self._vocab_card)
        card_lay.setContentsMargins(28, 24, 28, 24)
        card_lay.setSpacing(10)
        card_lay.setAlignment(Qt.AlignCenter)

        # 模式提示
        self._vocab_mode_tag = QLabel("学习新词")
        self._vocab_mode_tag.setAlignment(Qt.AlignCenter)
        self._vocab_mode_tag.setStyleSheet(
            "background: #dbeafe; color: #1d4ed8; font-size: 12px; font-weight: 700;"
            " padding: 3px 10px; border-radius: 8px; letter-spacing: 1px;"
        )
        card_lay.addWidget(self._vocab_mode_tag)

        # 单词大字
        self._vocab_word_lab = QLabel("—")
        self._vocab_word_lab.setAlignment(Qt.AlignCenter)
        self._vocab_word_lab.setStyleSheet(
            "background: transparent; color: #0f172a; font-size: 44px; font-weight: 800;"
            " letter-spacing: 2px;"
        )
        card_lay.addWidget(self._vocab_word_lab)

        # 音标
        self._vocab_phonetic_lab = QLabel("")
        self._vocab_phonetic_lab.setAlignment(Qt.AlignCenter)
        self._vocab_phonetic_lab.setStyleSheet(
            "background: transparent; color: #64748b; font-size: 16px; font-style: italic;"
        )
        card_lay.addWidget(self._vocab_phonetic_lab)

        # 释义 (翻面后才显示)
        self._vocab_meaning_lab = QLabel("")
        self._vocab_meaning_lab.setAlignment(Qt.AlignCenter)
        self._vocab_meaning_lab.setWordWrap(True)
        self._vocab_meaning_lab.setStyleSheet(
            "background: transparent; color: #0f172a; font-size: 17px; font-weight: 600;"
        )
        self._vocab_meaning_lab.hide()
        card_lay.addWidget(self._vocab_meaning_lab)

        # 例句 (翻面后才显示)
        self._vocab_example_lab = QLabel("")
        self._vocab_example_lab.setAlignment(Qt.AlignCenter)
        self._vocab_example_lab.setWordWrap(True)
        self._vocab_example_lab.setStyleSheet(
            "background: transparent; color: #64748b; font-size: 13px;"
        )
        self._vocab_example_lab.hide()
        card_lay.addWidget(self._vocab_example_lab)

        # 翻面提示
        self._vocab_hint_lab = QLabel("点击卡片或按 空格键 翻面查看释义")
        self._vocab_hint_lab.setAlignment(Qt.AlignCenter)
        self._vocab_hint_lab.setStyleSheet(
            "background: transparent; color: #94a3b8; font-size: 12px;"
        )
        card_lay.addWidget(self._vocab_hint_lab)

        # 卡片点击翻面
        self._vocab_card.mousePressEvent = lambda e: self._vocab_flip()
        v.addWidget(self._vocab_card, 1)

        # ----- 底部操作按钮 -----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._vocab_btn_unknown = QPushButton("❌ 不认识")
        self._vocab_btn_flip = QPushButton("🔄 翻面")
        self._vocab_btn_known = QPushButton("✅ 认识")
        for b in (self._vocab_btn_unknown, self._vocab_btn_flip, self._vocab_btn_known):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(40)
            b.setStyleSheet(
                "QPushButton{background:#f1f5f9;color:#334155;"
                "border:1px solid #e2e8f0;border-radius:10px;"
                "font-size:15px;font-weight:700;padding:0 28px;}"
                "QPushButton:disabled{color:#cbd5e1;background:#f8fafc;border-color:#f1f5f9;}"
            )
        self._vocab_btn_unknown.setStyleSheet(
            "QPushButton{background:#ef4444;color:white;border:1px solid #ef4444;"
            "border-radius:10px;font-size:15px;font-weight:700;padding:0 28px;}"
            "QPushButton:hover{background:#dc2626;border-color:#dc2626;}"
            "QPushButton:disabled{background:#fecaca;border-color:#fecaca;color:#fff;}"
        )
        self._vocab_btn_known.setStyleSheet(
            "QPushButton{background:#10b981;color:white;border:1px solid #10b981;"
            "border-radius:10px;font-size:15px;font-weight:700;padding:0 28px;}"
            "QPushButton:hover{background:#059669;border-color:#059669;}"
            "QPushButton:disabled{background:#a7f3d0;border-color:#a7f3d0;color:#fff;}"
        )
        self._vocab_btn_flip.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;border:1px solid #2563eb;"
            "border-radius:10px;font-size:15px;font-weight:700;padding:0 28px;}"
            "QPushButton:hover{background:#1d4ed8;border-color:#1d4ed8;}"
        )
        self._vocab_btn_unknown.clicked.connect(lambda: self._vocab_mark(False))
        self._vocab_btn_flip.clicked.connect(self._vocab_flip)
        self._vocab_btn_known.clicked.connect(lambda: self._vocab_mark(True))
        # 翻面前, 认识/不认识 按钮禁用
        self._vocab_btn_unknown.setEnabled(False)
        self._vocab_btn_known.setEnabled(False)
        btn_row.addStretch(1)
        btn_row.addWidget(self._vocab_btn_unknown)
        btn_row.addWidget(self._vocab_btn_flip)
        btn_row.addWidget(self._vocab_btn_known)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        # 空格键 / 左右键 快捷键 (仅单词 Tab 生效)
        sc_flip = QShortcut(QKeySequence(Qt.Key_Space), page)
        sc_flip.setContext(Qt.WidgetWithChildrenShortcut)
        sc_flip.activated.connect(self._vocab_flip)
        sc_known = QShortcut(QKeySequence(Qt.Key_Right), page)
        sc_known.setContext(Qt.WidgetWithChildrenShortcut)
        sc_known.activated.connect(lambda: self._vocab_mark(True) if self._vocab_flipped else None)
        sc_unknown = QShortcut(QKeySequence(Qt.Key_Left), page)
        sc_unknown.setContext(Qt.WidgetWithChildrenShortcut)
        sc_unknown.activated.connect(lambda: self._vocab_mark(False) if self._vocab_flipped else None)

        # 初次加载
        self._vocab_refresh()
        return page

    # ----- 单词背诵 逻辑 -----
    def _vocab_refresh_stats(self) -> None:
        s = self.store.vocab_stats()
        self._vocab_stats_lab.setText(
            f"词表: {s['total']}  |  已掌握: {s['known']}  |  今日新学: {s['learned_today']}  "
            f"|  今日复习: {s['reviewed_today']}  |  待复习: {s['due_review']}"
        )

    def _vocab_switch_mode(self, mode: str) -> None:
        self._vocab_mode = mode
        self._vocab_mode_learn.setChecked(mode == "learn")
        self._vocab_mode_review.setChecked(mode == "review")
        self._vocab_mode_tag.setText("学习新词" if mode == "learn" else "复习旧词")
        self._vocab_refresh()

    def _vocab_refresh(self) -> None:
        """加载下一个词并刷新进度统计"""
        self._vocab_refresh_stats()
        if self._vocab_mode == "learn":
            word = self.store.vocab_next_word()
        else:
            word = self.store.vocab_next_review()
        self._vocab_word = word
        self._vocab_flipped = False
        if word is None:
            # 没有可学/可复习的词
            self._vocab_word_lab.setText("🎉")
            self._vocab_phonetic_lab.setText(
                "今日新词已学完" if self._vocab_mode == "learn" else "暂无到期复习"
            )
            self._vocab_meaning_lab.setText("")
            self._vocab_example_lab.setText("")
            self._vocab_hint_lab.setText("切换模式或改天再来吧~")
            self._vocab_btn_unknown.setEnabled(False)
            self._vocab_btn_known.setEnabled(False)
            self._vocab_btn_flip.setEnabled(False)
            return
        self._vocab_word_lab.setText(str(word.get("word", "")))
        self._vocab_phonetic_lab.setText(str(word.get("phonetic", "")))
        self._vocab_meaning_lab.setText(str(word.get("meaning", "")))
        self._vocab_example_lab.setText(
            "例: " + str(word.get("example", "")) if word.get("example") else ""
        )
        self._vocab_meaning_lab.hide()
        self._vocab_example_lab.hide()
        self._vocab_hint_lab.setText("点击卡片或按 空格键 翻面查看释义")
        self._vocab_btn_unknown.setEnabled(False)
        self._vocab_btn_known.setEnabled(False)
        self._vocab_btn_flip.setEnabled(True)

    def _vocab_flip(self) -> None:
        if self._vocab_word is None:
            return
        self._vocab_flipped = not self._vocab_flipped
        if self._vocab_flipped:
            self._vocab_meaning_lab.show()
            self._vocab_example_lab.show()
            self._vocab_hint_lab.setText("认识按 → 或 ✅，不认识按 ← 或 ❌")
            self._vocab_btn_unknown.setEnabled(True)
            self._vocab_btn_known.setEnabled(True)
            self._vocab_btn_flip.setEnabled(False)
        else:
            self._vocab_meaning_lab.hide()
            self._vocab_example_lab.hide()
            self._vocab_hint_lab.setText("点击卡片或按 空格键 翻面查看释义")
            self._vocab_btn_unknown.setEnabled(False)
            self._vocab_btn_known.setEnabled(False)
            self._vocab_btn_flip.setEnabled(True)

    def _vocab_mark(self, known: bool) -> None:
        if self._vocab_word is None or not self._vocab_flipped:
            return
        self.store.vocab_mark(str(self._vocab_word.get("id", "")), known)
        self._vocab_refresh()

    def _vocab_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "导入词表 (JSON)",
            str(BASE_DIR),
            "JSON 文件 (*.json)",
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("words") or data.get("vocab") or []
            added = self.store.vocab_import(items)
            QMessageBox.information(self, "导入完成", f"成功导入 {added} 个新单词。")
            self._vocab_refresh()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"读取文件出错: {e}")

    def _build_reading_tab(self) -> QWidget:
        """Tab3: 阅读理解 (P1-A, 暂占位)"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #10b981;"
            "  border-radius: 16px;}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(40, 50, 40, 50)
        hint = QLabel("📚 阅读理解\n\n导入文章 · 逐题作答 · 正确率统计 · 错题联动\n\n(P1-A 开发中)")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:16px;color:#0f172a;font-weight:600;white-space:pre-line;line-height:200%;")
        cv.addWidget(hint)
        v.addWidget(card, 1)
        return page

    def _build_translation_tab(self) -> QWidget:
        """Tab4: 翻译练习 (P1-B, 暂占位)"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #f59e0b;"
            "  border-radius: 16px;}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(40, 50, 40, 50)
        hint = QLabel("🔄 翻译练习\n\n中英互译 · 参考对照 · AI 批改\n\n(P1-B 开发中)")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:16px;color:#0f172a;font-weight:600;white-space:pre-line;line-height:200%;")
        cv.addWidget(hint)
        v.addWidget(card, 1)
        return page

    def _build_writing_tab(self) -> QWidget:
        """Tab5: 写作练习 (P1-C, 暂占位)"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #8b5cf6;"
            "  border-radius: 16px;}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(40, 50, 40, 50)
        hint = QLabel("✍️ 写作练习\n\n题目+正文编辑 · AI 批改评分 · 范文参考\n\n(P1-C 开发中)")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:16px;color:#0f172a;font-weight:600;white-space:pre-line;line-height:200%;")
        cv.addWidget(hint)
        v.addWidget(card, 1)
        return page

    def _build_speaking_tab(self) -> QWidget:
        """Tab6: 口语练习 (P2, 暂占位)"""
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 12, 14, 12)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #ec4899;"
            "  border-radius: 16px;}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(40, 50, 40, 50)
        hint = QLabel("🎤 口语练习\n\n情景对话 · AI 表达建议 · 笔记记录\n\n(P2 开发中)")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:16px;color:#0f172a;font-weight:600;white-space:pre-line;line-height:200%;")
        cv.addWidget(hint)
        v.addWidget(card, 1)
        return page

    def _on_english_tab_changed(self, idx: int):
        """Tab 切换时内容区淡入动画"""
        try:
            from PyQt5.QtWidgets import QGraphicsOpacityEffect
            from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
            widget = self.tabs.widget(idx)
            if widget is None:
                return
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", widget)
            anim.setDuration(200)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            widget._tab_enter_anim = anim  # 持有引用避免 GC
        except Exception:
            pass


# ===========================================================
# 其他页占位
# ===========================================================
def make_placeholder_page(title: str, hint: str, color_style: str = "default") -> QWidget:
    # 各模块 TraeCode 风格顶部强调色
    COLOR_SCHEMES = {
        "math":   "#3b82f6",  # blue
        "major":  "#10b981",  # emerald
        "school": "#f59e0b",  # amber
        "course": "#8b5cf6",  # violet
        "default": "#64748b",  # slate
    }
    accent = COLOR_SCHEMES.get(color_style, COLOR_SCHEMES["default"])
    # 标题色用稍微深一点的色调
    TITLE_COLORS = {
        "math":   "#1d4ed8",
        "major":  "#047857",
        "school": "#b45309",
        "course": "#6d28d9",
        "default": "#475569",
    }
    title_color = TITLE_COLORS.get(color_style, TITLE_COLORS["default"])

    page = QWidget()
    outer = QVBoxLayout(page)
    outer.setContentsMargins(10, 0, 10, 10)
    outer.setSpacing(8)
    title_row = QHBoxLayout()
    title_lab = QLabel(title)
    title_lab.setStyleSheet(
        "font-size: 22px; font-weight: 800; letter-spacing: 1px; color: #0f172a;"
    )
    title_row.addWidget(title_lab)
    title_row.addStretch(1)
    outer.addLayout(title_row)
    card = QGroupBox("建设中")
    card.setStyleSheet(
        f"QGroupBox {{"
        f"  background: #ffffff;"
        f"  border: 1px solid #e2e8f0;"
        f"  border-top: 3px solid {accent};"
        f"  border-radius: 16px;"
        f"  margin-top: 18px;"
        f"  padding-top: 10px;"
        f"}}"
        f"QGroupBox::title {{"
        f"  subcontrol-origin: margin; left: 18px; padding: 2px 10px;"
        f"  color: {title_color}; font-size: 13px; font-weight: 700;"
        f"  background: transparent;"
        f"}}"
    )
    v = QVBoxLayout(card)
    v.setContentsMargins(40, 50, 40, 50)
    hint_lab = QLabel(hint)
    hint_lab.setAlignment(Qt.AlignCenter)
    hint_lab.setStyleSheet(
        f"font-size: 16px; color: #334155; font-weight: 600; padding: 20px 0; line-height: 200%;"
    )
    v.addWidget(hint_lab)
    outer.addWidget(card, 1)
    return page


# ===========================================================
# MainWindow (仿上位机 Frameless + border-image)
# ===========================================================
class MainWindow(QMainWindow):
    PAGE_SPECS: List[Tuple[str, str, str]] = [
        # (key, 中文名, 图标/副标题)
        ("dashboard", "主界面", "学习总览 · 进度概览"),
        ("english",   "英语",   "单词 · 语法 · 阅读 · 错题"),
        ("math",      "数学",   "高数 · 线代 · 概率 · 错题"),
        ("major",     "专业课", "专业基础 · 真题 · 错题"),
        ("school",    "择校",   "院校数据 · 经验分享"),
        ("course",    "网课学习区", "网页听课 · Markdown 笔记"),
        ("pdf",       "PDF阅读", "讲义 · 真题 · 标注笔记"),
        ("focus",     "专注",   "番茄钟 · 计时 · 统计"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(1320, 820)
        self.setMinimumSize(1080, 700)
        self._drag_pos: Optional[QPoint] = None
        self.store = StudyStore.load()
        self.pages: Dict[str, QWidget] = {}
        self.page_stack = QStackedWidget()
        self._nav_buttons: List[QPushButton] = []
        self._build_ui()

    # ---- 全局事件过滤器: 浏览器卡片放大时 box/主窗口尺寸变化立刻重算 view 几何 ----
    def eventFilter(self, obj, event):
        et = event.type() if event is not None else None
        if getattr(self, "_course_maximized", False):
            want = False
            try:
                from PyQt5.QtCore import QEvent as _QE
                want = et in (_QE.Resize, _QE.Move, _QE.Show, _QE.WindowActivate, _QE.LayoutRequest)
            except Exception:
                want = et in (14, 13, 17, 24, 76)
            if want:
                try:
                    self._course_relayout_maximized()
                except Exception:
                    pass
        # Edge 宿主尺寸变化 -> 对齐嵌入的 Edge --app 窗口大小
        if obj is not None and obj is getattr(self, "course_edge_host", None):
            try:
                from PyQt5.QtCore import QEvent as _QE
                if et in (_QE.Resize, _QE.Show, _QE.Move, _QE.LayoutRequest):
                    if int(getattr(self, "course_edge_hwnd", 0) or 0):
                        self._course_edge_resize_to_host()
            except Exception:
                pass
        # 再交给父类
        return super().eventFilter(obj, event)

    # ---- 关闭窗口时: 先归位独立窗口/退出放大，再杀 Edge 子进程，防止子进程残留 ----
    def closeEvent(self, e):
        try:
            if getattr(self, "_course_pop_win", None) is not None:
                try:
                    self._course_pop_win_close_then_restore(do_restore=True)
                except Exception:
                    pass
            if getattr(self, "_course_maximized", False):
                try:
                    self._course_toggle_maximize_in_card()
                except Exception:
                    pass
            # WebView2 真·内嵌: destroy 控件
            try:
                self._course_wv2_kill()
            except Exception:
                pass
            # 外置 Edge/Chrome 子进程: 强杀（只杀我们自己启动的）
            try:
                self._course_edge_kill(kill_proc=True)
            except Exception:
                pass
        except Exception:
            pass
        super().closeEvent(e)

    # ===== 主 UI (严格按照上位机模式) =====
    def _build_ui(self):
        # ===== 根据当前主题选色 (两套互不干扰) =====
        if not hasattr(self, "_current_theme") or self._current_theme is None:
            self._current_theme = self.store.settings.get("theme", "light")
        _t = self._current_theme
        if _t == "dark":
            _bg = "#0f172a"
            _text = "#f1f5f9"
            _input_bg = "#1e293b"
            _btn_bg = "#1e293b"
            _hover = "#334155"
        else:
            _bg = "#f8fafc"
            _text = "#0f172a"
            _input_bg = "#ffffff"
            _btn_bg = "#ffffff"
            _hover = "#f1f5f9"
        root = QWidget()
        root.setObjectName("mainRoot")
        root.setStyleSheet(f"""
            QWidget#mainRoot {{
                background: {_bg};
            }}
            QWidget {{
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑";
                font-size: 13px;
                color: {_text};
            }}
            QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {{
                background: {_input_bg};
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 10px;
                color: {_text};
                selection-background-color: #c7d2fe;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus,
            QPlainTextEdit:focus, QSpinBox:focus {{
                border: 1.5px solid #6366f1;
                background: {_input_bg};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
                border-left: 1px solid #e2e8f0;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #64748b;
            }}
            QComboBox QAbstractItemView {{
                background: {_input_bg};
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 4px;
                outline: 0;
                selection-background-color: #eef2ff;
                selection-color: #4338ca;
            }}
            QPushButton {{
                background: {_btn_bg};
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 6px 14px;
                color: {_text};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {_hover};
            }}
        """)

        main = QVBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ---------- titleBar (仿上位机) ----------
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(10, 0, 0, 0)
        title_layout.setSpacing(0)
        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        title_icon.setScaledContents(True)
        if BACKGROUND_PATH.exists():
            pix = load_pixmap_safe(str(BACKGROUND_PATH), max_h=24, max_w=24)
            if pix is not None:
                title_icon.setPixmap(pix)
        title_text = QLabel(f"{APP_TITLE}  ·  {APP_VERSION}")
        title_text.setObjectName("titleBarText")

        min_btn = QPushButton("－")
        max_btn = QPushButton("□")
        close_btn = QPushButton("×")
        for b in (min_btn, max_btn, close_btn):
            b.setObjectName("titleButton")
            b.setFixedSize(46, 32)
        close_btn.setObjectName("closeButton")
        min_btn.clicked.connect(self.showMinimized)
        max_btn.clicked.connect(self.toggle_maximize)
        close_btn.clicked.connect(self.close)

        title_layout.addWidget(title_icon)
        title_layout.addSpacing(8)
        title_layout.addWidget(title_text)
        title_layout.addStretch(1)
        # ---------- 主题切换小开关 (放在最小化按钮左边) ----------
        self.title_theme_switch = ThemeToggleSwitch(
            checked=(self.store.settings.get("theme", "light") == "dark"),
            size=(52, 26),
        )
        self.title_theme_switch.setToolTip("切换日间/夜间模式")
        self.title_theme_switch.toggled.connect(self._on_title_theme_toggled)
        title_layout.addSpacing(6)
        title_layout.addWidget(self.title_theme_switch, 0, Qt.AlignVCenter)
        title_layout.addSpacing(4)
        # ---------- 主题设置按钮 (完整弹窗) ----------
        self.btn_theme_settings = QPushButton("🎨")
        self.btn_theme_settings.setObjectName("titleButton")
        self.btn_theme_settings.setFixedSize(36, 32)
        self.btn_theme_settings.setToolTip("主题外观设置")
        self.btn_theme_settings.setCursor(Qt.PointingHandCursor)
        self.btn_theme_settings.clicked.connect(self._open_theme_dialog)
        title_layout.addWidget(self.btn_theme_settings)
        title_layout.addWidget(min_btn)
        title_layout.addWidget(max_btn)
        title_layout.addWidget(close_btn)

        # 拖拽 (仿上位机)
        title_bar.mousePressEvent = self.title_mouse_press
        title_bar.mouseMoveEvent = self.title_mouse_move
        title_bar.mouseReleaseEvent = self.title_mouse_release
        # titleBar 主题色
        if _t == "dark":
            _tb_bg = "#0b1220"
            _tb_text = "#e2e8f0"
            _tb_btn_bg = "#0b1220"
            _tb_btn_hover = "#1e293b"
            _tb_close_hover = "#dc2626"
        else:
            _tb_bg = "#ffffff"
            _tb_text = "#0f172a"
            _tb_btn_bg = "#ffffff"
            _tb_btn_hover = "#f1f5f9"
            _tb_close_hover = "#dc2626"
        title_bar.setStyleSheet(
            f"QWidget#titleBar{{background:{_tb_bg};border-bottom:1px solid {_border if False else '#e2e8f0'};}}"
            f"QLabel#titleBarText{{color:{_tb_text};font-weight:600;font-size:12px;background:transparent;border:none;}}"
            f"QPushButton#titleButton{{background:{_tb_btn_bg};border:none;color:{_tb_text};font-size:14px;font-weight:700;}}"
            f"QPushButton#titleButton:hover{{background:{_tb_btn_hover};}}"
            f"QPushButton#closeButton{{background:{_tb_btn_bg};border:none;color:{_tb_text};font-size:16px;font-weight:700;}}"
            f"QPushButton#closeButton:hover{{background:{_tb_close_hover};color:white;}}"
        )
        main.addWidget(title_bar)

        # ---------- 中间层: QSplitter(左侧导航栏 | 内容区 page_stack | AI面板) ----------
        middle = QWidget()
        middle_lay = QSplitter(Qt.Horizontal)
        middle_lay.setHandleWidth(10)
        # QSplitter 没有 setContentsMargins/setSpacing, 用 QHBoxLayout 包一层实现外边距
        middle_wrap = QHBoxLayout(middle)
        middle_wrap.setContentsMargins(12, 12, 12, 12)
        middle_wrap.setSpacing(0)
        middle_wrap.addWidget(middle_lay)

        # --- 左侧导航栏 (TraeCode 风格白卡) ---
        nav_panel = QWidget()
        nav_panel.setObjectName("navPanel")
        # nav_panel 样式在 _refresh_nav_styles 里根据主题动态生成
        self.nav_panel = nav_panel
        nav_panel.setFixedWidth(190)
        nv = QVBoxLayout(nav_panel)
        nv.setContentsMargins(14, 16, 14, 16)
        nv.setSpacing(10)

        nav_head_title = QLabel("春雪考研")
        nav_head_title.setObjectName("navTitle")
        nav_head_sub = QLabel("考研一站式助手")
        nav_head_sub.setObjectName("navSub")
        nv.addWidget(nav_head_title)
        nv.addWidget(nav_head_sub)
        nv.addSpacing(8)

        nav_line = QFrame()
        nav_line.setFrameShape(QFrame.HLine)
        nav_line.setProperty("nav_line", True)  # 标记一下, _refresh_nav_styles 里能识别
        nv.addWidget(nav_line)
        nv.addSpacing(6)

        # 导航按钮 (TraeCode 风格: 左侧色标 + 两行文字, 颜色在 _refresh_nav_styles 里按主题应用)
        for key, name, sub in self.PAGE_SPECS:
            b = QPushButton()
            b.setObjectName("navBtn")
            b.setProperty("page_key", key)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(58)
            accent = self.NAV_ACCENTS.get(key, "#6366f1")
            bl = QHBoxLayout(b)
            bl.setContentsMargins(12, 10, 12, 10)
            bl.setSpacing(10)
            bl.setAlignment(Qt.AlignVCenter)
            # 左侧色标点
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setProperty("nav_dot", True)
            bl.addWidget(dot)
            # 两行文字区
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            text_col.setContentsMargins(0, 0, 0, 0)
            t = QLabel(name)
            t.setProperty("nav_text", True)
            s = QLabel(sub)
            s.setProperty("nav_sub", True)
            text_col.addWidget(t)
            text_col.addWidget(s)
            bl.addLayout(text_col, 1)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self._nav_buttons.append(b)
            nv.addWidget(b)

        nv.addStretch(1)
        nav_foot = QLabel(f"共 {len(self.PAGE_SPECS)} 个模块")
        nav_foot.setObjectName("navSub")
        nav_foot.setAlignment(Qt.AlignCenter)
        nv.addWidget(nav_foot)

        # 初始化导航栏样式 (用当前主题)
        self._refresh_nav_styles(self._current_theme)

        middle_lay.addWidget(nav_panel)
        middle_lay.setCollapsible(0, False)

        # --- 内容区 ---
        self._build_pages()
        middle_lay.addWidget(self.page_stack)
        middle_lay.setCollapsible(1, False)
        middle_lay.setStretchFactor(1, 1)

        # --- AI 面板 (第三栏, P0-A) ---
        self.ai_panel = AIChatPanel(self.store, self)
        self.ai_panel.setMinimumWidth(320)
        self.ai_panel.setMaximumWidth(560)  # AI 面板最大 560, 不让拉伸到最长
        middle_lay.addWidget(self.ai_panel)
        middle_lay.setCollapsible(2, True)
        # 中间内容区也加最大宽度限制, 避免拉到最长
        self.page_stack.setMaximumWidth(16777215)  # 不限制内容区, 由 splitter 控制

        # 折叠时的展开竖条 (加宽加高, 更好拉)
        self.ai_expand_bar = QPushButton("‹\nA\nI\n›", self)
        self.ai_expand_bar.setFixedSize(34, 180)
        self.ai_expand_bar.setToolTip("展开 AI 面板 (Ctrl+Shift+K)")
        self.ai_expand_bar.setCursor(Qt.PointingHandCursor)
        self.ai_expand_bar.setStyleSheet(
            "QPushButton{background: qlineargradient(x1:0,y1:0, x2:1,y2:0,"
            "  stop:0 #0f172a, stop:1 #1e293b); color:#e2e8f0;"
            "  border-top-left-radius:14px; border-bottom-left-radius:14px;"
            "  border: 1px solid rgba(148,163,184,80);"
            "  font-size:13px;font-weight:900; letter-spacing: 1px;"
            "  padding: 6px 2px;}"
            "QPushButton:hover{background: qlineargradient(x1:0,y1:0, x2:1,y2:0,"
            "  stop:0 #1e293b, stop:1 #334155); color:white;"
            "  border: 1px solid rgba(148,163,184,150);}"
        )
        self.ai_expand_bar.clicked.connect(lambda: self._toggle_ai_panel(True))
        self.ai_expand_bar.hide()

        # 根据配置决定初始展开/折叠
        if self.store.settings.get("ai_panel_visible", False):
            middle_lay.setSizes([180, 600, 360])
            self.ai_expand_bar.hide()
        else:
            self.ai_panel.setVisible(False)
            middle_lay.setSizes([180, 800, 0])
            self.ai_expand_bar.show()
        self._ai_splitter = middle_lay

        main.addWidget(middle, 1)

        self.setCentralWidget(root)
        self.show_page("dashboard")

    def _build_pages(self):
        for spec in self.PAGE_SPECS:
            if len(spec) == 3:
                key, name, _sub = spec
            else:
                key, name = spec  # type: ignore[misc]
            if key == "dashboard":
                page = self._build_dashboard_page(name)
            elif key == "english":
                page = EnglishPage(self.store, theme_colors=self.THEME_COLORS.get(self._current_theme, self.THEME_COLORS["light"]))
                self.english_page = page
            elif key == "course":
                page = self._build_course_page(name)
            elif key == "math":
                page = make_placeholder_page(
                    f"{name} · 考研数学",
                    "在这里整理高等数学 / 线性代数 / 概率论与数理统计的知识点、题目、错题。",
                    color_style="math",
                )
            elif key == "major":
                page = make_placeholder_page(
                    f"{name} · 专业课",
                    "在这里整理目标院校的专业课参考资料、历年真题、章节笔记与错题。",
                    color_style="major",
                )
            elif key == "school":
                page = make_placeholder_page(
                    f"{name} · 考研择校",
                    "历年分数线、招生人数、考试科目、上岸经验帖汇总，助你锁定目标院校。",
                    color_style="school",
                )
            elif key == "pdf":
                page = self._build_pdf_page(name)
            elif key == "focus":
                page = self._build_focus_page(name)
            else:
                page = make_placeholder_page(name, "")
            self.pages[key] = page
            self.page_stack.addWidget(page)

    def _build_dashboard_page(self, name: str) -> QWidget:
        self.store.ensure_today_tasks()
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 2, 4, 4)
        outer.setSpacing(12)

        title_row = QHBoxLayout()
        title_lab = QLabel(name)
        title_lab.setStyleSheet(
            "font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: 1px;"
        )
        date_lab = QLabel(datetime.now().strftime("%Y年%m月%d日  %A"))
        date_lab.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500;")
        title_row.addWidget(title_lab)
        title_row.addSpacing(12)
        title_row.addWidget(date_lab)
        title_row.addStretch(1)
        btn_refresh_quote = QPushButton("换一句")
        btn_refresh_quote.setCursor(Qt.PointingHandCursor)
        btn_refresh_quote.setFixedHeight(28)
        btn_refresh_quote.clicked.connect(self._on_refresh_quote)
        title_row.addWidget(btn_refresh_quote)
        outer.addLayout(title_row)

        # 通用 TraeCode 风卡片标题样式工厂
        def group_style(title_accent: str, border_top: str) -> str:
            return (
                "QGroupBox {"
                "  background: #ffffff;"
                f"  border: 1px solid #e2e8f0;"
                f"  border-top: 3px solid {border_top};"
                "  border-radius: 12px;"
                "  margin-top: 18px;"
                "  padding-top: 12px;"
                "}"
                "QGroupBox::title {"
                "  subcontrol-origin: margin; left: 18px; padding: 2px 12px;"
                f"  color: {title_accent}; font-size: 13px; font-weight: 700;"
                "  background: transparent;"
                "}"
            )

        # ===== 大卡1: 励志语录 (全宽，大字，居中) =====
        quote_group = QGroupBox("今日寄语")
        quote_group.setStyleSheet(group_style("#f59e0b", "#f59e0b"))
        qg = QVBoxLayout(quote_group)
        qg.setContentsMargins(28, 20, 28, 20)
        qg.setSpacing(6)
        self.dash_quote = QLabel()
        self.dash_quote.setAlignment(Qt.AlignCenter)
        self.dash_quote.setWordWrap(True)
        self.dash_quote.setMinimumHeight(90)
        self.dash_quote.setStyleSheet(
            "color: #0f172a; font-size: 24px; font-weight: 800;"
            " letter-spacing: 1px; line-height: 160%;"
        )
        # 给语录标签加 QGraphicsOpacityEffect, 支持淡出/淡入动画
        self.dash_quote_opacity = QGraphicsOpacityEffect(self.dash_quote)
        self.dash_quote_opacity.setOpacity(1.0)
        self.dash_quote.setGraphicsEffect(self.dash_quote_opacity)
        quote_sign = QLabel("—— 送给今天的你")
        quote_sign.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        quote_sign.setStyleSheet("color: #64748b; font-size: 12px; font-weight: 600;")
        qg.addWidget(self.dash_quote)
        qg.addWidget(quote_sign)
        outer.addWidget(quote_group)

        # ===== 主体: 左(倒计时+目标两排) | 右(今日任务大卡) =====
        body = QHBoxLayout()
        body.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # 倒计时卡
        cd_group = QGroupBox("28考研倒计时")
        cd_group.setStyleSheet(group_style("#ef4444", "#ef4444"))
        cd_g = QGridLayout(cd_group)
        cd_g.setContentsMargins(16, 18, 16, 16)
        cd_g.setSpacing(10)
        self.dash_cd_num = QLabel()
        self.dash_cd_num.setAlignment(Qt.AlignCenter)
        self.dash_cd_num.setStyleSheet(
            "color: #dc2626; font-size: 68px; font-weight: 900; letter-spacing: 2px;"
        )
        self.dash_cd_unit = QLabel("天")
        self.dash_cd_unit.setAlignment(Qt.AlignCenter)
        self.dash_cd_unit.setStyleSheet(
            "color: #991b1b; font-size: 22px; font-weight: 800;"
        )
        self.dash_cd_target = QLabel()
        self.dash_cd_target.setAlignment(Qt.AlignCenter)
        self.dash_cd_target.setStyleSheet(
            "color: #64748b; font-size: 13px; font-weight: 500;"
        )
        cd_g.addWidget(self.dash_cd_num, 0, 0, 2, 1)
        cd_g.addWidget(self.dash_cd_unit, 0, 1, 1, 1, Qt.AlignBottom)
        cd_g.addWidget(self.dash_cd_target, 1, 1, 1, 1, Qt.AlignTop)
        cd_g.setColumnStretch(0, 1)
        left_col.addWidget(cd_group, 2)

        # 目标院校 / 专业
        target_group = QGroupBox("我的目标")
        target_group.setStyleSheet(group_style("#0ea5e9", "#0ea5e9"))
        tg = QVBoxLayout(target_group)
        tg.setContentsMargins(16, 18, 16, 14)
        tg.setSpacing(10)

        def make_row(label: str, key: str):
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setStyleSheet(
                "color: #334155; font-size: 13px; font-weight: 600;"
            )
            lab.setFixedWidth(78)
            val = QLineEdit(str(self.store.settings.get(key) or "待定"))
            val.setPlaceholderText("点击右侧编辑按钮修改，再点保存")
            val.setReadOnly(True)
            btn = QPushButton("编辑")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(64)
            btn.setProperty("dash_key", key)
            btn.setProperty("dash_edit", val)
            btn.clicked.connect(lambda _=False, b=btn: self._on_toggle_target_edit(b))
            row.addWidget(lab)
            row.addWidget(val, 1)
            row.addWidget(btn)
            tg.addLayout(row)
            return lab, val, btn

        _, self.dash_school_edit, self.dash_school_btn = make_row("目标院校", "target_school")
        _, self.dash_major_edit, self.dash_major_btn = make_row("目标专业", "target_major")
        left_col.addWidget(target_group, 3)

        body.addLayout(left_col, 5)

        # ---- 右侧: 今日任务大卡 ----
        task_group = QGroupBox("今日任务")
        task_group.setStyleSheet(group_style("#8b5cf6", "#8b5cf6"))
        task_head = QHBoxLayout()
        task_head.setContentsMargins(-8, -4, -8, 4)
        self.dash_task_progress = QLabel("0 / 0")
        self.dash_task_progress.setStyleSheet(
            "color: #334155; font-size: 13px; font-weight: 600;"
        )
        btn_add_task = QPushButton("+ 新增")
        btn_add_task.setCursor(Qt.PointingHandCursor)
        btn_add_task.clicked.connect(self._on_add_task)
        btn_reset_task = QPushButton("重置")
        btn_reset_task.setCursor(Qt.PointingHandCursor)
        btn_reset_task.clicked.connect(self._on_reset_tasks)
        task_head.addWidget(self.dash_task_progress)
        task_head.addStretch(1)
        task_head.addWidget(btn_add_task)
        task_head.addWidget(btn_reset_task)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        self.dash_task_container = QWidget()
        self.dash_task_container.setStyleSheet("background: transparent;")
        self.dash_task_lay = QVBoxLayout(self.dash_task_container)
        self.dash_task_lay.setContentsMargins(4, 4, 4, 4)
        self.dash_task_lay.setSpacing(8)
        self.dash_task_lay.addStretch(1)
        self._dash_task_stretch_idx = self.dash_task_lay.count() - 1
        scroll.setWidget(self.dash_task_container)

        task_lay = QVBoxLayout(task_group)
        task_lay.setContentsMargins(14, 18, 14, 14)
        task_lay.setSpacing(6)
        task_lay.addLayout(task_head)
        task_lay.addWidget(scroll, 1)
        body.addWidget(task_group, 6)

        outer.addLayout(body, 1)

        # 保存控件引用, 并刷新
        self._btn_refresh_quote = btn_refresh_quote
        self._page = page
        self._refresh_dashboard()
        # 定时每秒刷新倒计时显示
        self._dash_timer = QTimer(page)
        self._dash_timer.timeout.connect(self._refresh_countdown_only)
        self._dash_timer.start(30 * 1000)
        # 语录轮播: 每 5 秒自动切一条, 切换时淡出->更新->淡入
        self._quote_timer = QTimer(page)
        self._quote_timer.setInterval(5000)
        self._quote_timer.timeout.connect(self._rotate_quote)
        self._quote_timer.start()
        return page

    # ============== Dashboard 刷新 / 动作 ==============
    def _refresh_dashboard(self):
        self.store.ensure_today_tasks()
        # 励志语录
        self.dash_quote.setText(str(self.store.settings.get("daily_quote") or "加油！"))
        # 倒计时
        self._refresh_countdown_only()
        # 目标院校/专业
        self.dash_school_edit.setText(str(self.store.settings.get("target_school") or "待定"))
        self.dash_major_edit.setText(str(self.store.settings.get("target_major") or "待定"))
        # 今日任务
        self._rebuild_task_rows()

    def _refresh_countdown_only(self):
        target = self.store.kaoyan_date
        delta_days = (target - today()).days
        if delta_days < 0:
            num, unit = max(0, delta_days), "天(已到)"
        else:
            num, unit = delta_days, "天"
        self.dash_cd_num.setText(f"{num:,}")
        self.dash_cd_unit.setText(unit)
        self.dash_cd_target.setText(f"初试日：{target.isoformat()}")

    # ============== AI 面板折叠/展开 ==============
    def _toggle_ai_panel(self, visible: bool):
        """切换 AI 面板展开/折叠"""
        splitter: QSplitter = self._ai_splitter
        if visible:
            # 展开: 显示 AI 面板，隐藏折叠竖条
            self.ai_panel.setVisible(True)
            self.ai_expand_bar.hide()
            sizes = splitter.sizes()
            # 第三栏为 0 时，从内容区(第二栏)借 360px 给 AI 面板
            if sizes[2] == 0:
                need = 360
                take = min(need, max(0, sizes[1] - 360))
                if take < need:
                    # 内容区不够，从导航(第一栏)也借
                    extra = need - take
                    take_nav = min(extra, max(0, sizes[0] - 160))
                    sizes[0] = sizes[0] - take_nav
                sizes[1] = sizes[1] - take
                sizes[2] = need
            splitter.setSizes(sizes)
            self.store.settings["ai_panel_visible"] = True
        else:
            # 折叠: 隐藏 AI 面板，显示折叠竖条
            sizes = splitter.sizes()
            ai_w = sizes[2]
            self.ai_panel.setVisible(False)
            # 把 AI 面板的宽度归还给内容区
            if ai_w > 0:
                sizes[1] = sizes[1] + ai_w
                sizes[2] = 0
                splitter.setSizes(sizes)
            self.ai_expand_bar.show()
            self._position_ai_expand_bar()
            self.store.settings["ai_panel_visible"] = False
        self.store.save()

    def _position_ai_expand_bar(self):
        """把折叠竖条放到窗口右侧竖直居中"""
        if not self.ai_expand_bar.isVisible():
            return
        bar = self.ai_expand_bar
        bar.move(
            self.width() - bar.width(),
            self.height() // 2 - bar.height() // 2,
        )
        bar.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 折叠时保证竖条还在右侧竖直居中
        if not self.ai_panel.isVisible():
            self._position_ai_expand_bar()

    def keyPressEvent(self, e):
        # Ctrl+Shift+K 切换 AI 面板
        if (
            e.modifiers() & Qt.ControlModifier
            and e.modifiers() & Qt.ShiftModifier
            and e.key() == Qt.Key_K
        ):
            self._toggle_ai_panel(not self.ai_panel.isVisible())
            e.accept()
            return
        super().keyPressEvent(e)

    def _on_refresh_quote(self):
        """点击"换一句": 重置定时器 + 触发动画轮播"""
        if hasattr(self, "_quote_timer") and self._quote_timer is not None:
            try:
                self._quote_timer.start()  # 重新计时 (5s 后下一次自动轮播)
            except Exception:
                pass
        self._rotate_quote()

    def _rotate_quote(self):
        """语录轮播: 淡出 -> 更新文字 -> 淡入"""
        if not hasattr(self, "dash_quote") or self.dash_quote is None:
            return
        import random
        # 选一条新语录 (尽量不与当前重复)
        current = self.dash_quote.text() or ""
        pool = [q for q in QUOTES if q != current] or list(QUOTES)
        new_quote = random.choice(pool)
        # 用 QPropertyAnimation 做淡出/淡入
        opacity = getattr(self, "dash_quote_opacity", None)
        if opacity is None:
            # 没装 effect (兼容老代码), 直接换字
            self.dash_quote.setText(new_quote)
            return
        # 如果上一次动画还在跑, 先停下避免叠加
        for attr in ("_quote_anim_out", "_quote_anim_in"):
            old = getattr(self, attr, None)
            if old is not None:
                try:
                    old.stop()
                except Exception:
                    pass
        # 1. 淡出 (200ms)
        self._quote_anim_out = QPropertyAnimation(opacity, b"opacity", self.dash_quote)
        self._quote_anim_out.setDuration(200)
        self._quote_anim_out.setStartValue(opacity.opacity())
        self._quote_anim_out.setEndValue(0.0)
        self._quote_anim_out.setEasingCurve(QEasingCurve.OutQuad)

        def _after_fade_out():
            # 2. 更新文字
            self.dash_quote.setText(new_quote)
            # 3. 淡入 (300ms)
            self._quote_anim_in = QPropertyAnimation(opacity, b"opacity", self.dash_quote)
            self._quote_anim_in.setDuration(300)
            self._quote_anim_in.setStartValue(0.0)
            self._quote_anim_in.setEndValue(1.0)
            self._quote_anim_in.setEasingCurve(QEasingCurve.InOutCubic)
            self._quote_anim_in.start()

        self._quote_anim_out.finished.connect(_after_fade_out)
        self._quote_anim_out.start()

    def _on_toggle_target_edit(self, btn: QPushButton):
        key: str = btn.property("dash_key")
        edit: QLineEdit = btn.property("dash_edit")
        if btn.text() == "编辑":
            edit.setReadOnly(False)
            edit.setStyleSheet(
                "background: rgba(255,255,255,200); border: 1px solid rgba(170,130,70,150);"
                " border-radius: 6px; padding: 4px 8px; color: #1f2937;"
            )
            btn.setText("保存")
            edit.setFocus()
            edit.selectAll()
        else:
            val = edit.text().strip() or "待定"
            self.store.settings[key] = val
            self.store.save()
            edit.setText(val)
            edit.setReadOnly(True)
            edit.setStyleSheet(
                "background: rgba(255,255,255,120); border: 1px solid rgba(160,140,110,90);"
                " border-radius: 6px; padding: 4px 8px; color: #1f2937;"
            )
            btn.setText("编辑")

    # ---- 今日任务 ----
    def _rebuild_task_rows(self):
        tasks = self.store.settings.get("today_tasks") or []
        # 找 stretch spacer：优先用记录的 _dash_task_stretch_idx（若还存在且是 spacer），否则用最后一项
        stretch_idx = -1
        for i in range(self.dash_task_lay.count() - 1, -1, -1):
            it = self.dash_task_lay.itemAt(i)
            if it is None:
                continue
            if it.spacerItem() is not None:
                stretch_idx = i
                break
        # 先清空旧 widgets（但保留 stretch spacer）
        i = 0
        while i < self.dash_task_lay.count():
            item = self.dash_task_lay.itemAt(i)
            if item is None:
                i += 1
                continue
            if item.spacerItem() is not None:
                i += 1
                continue
            # 非 spacer, 取走
            taken = self.dash_task_lay.takeAt(i)
            w = taken.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        tasks_sorted = sorted(tasks, key=lambda x: (bool(x.get("done")), x.get("id", "")))

        done = 0
        insert_at = stretch_idx if stretch_idx >= 0 else self.dash_task_lay.count()
        for t in tasks_sorted:
            if t.get("done"):
                done += 1
            row = QFrame()
            row.setFrameShape(QFrame.NoFrame)
            row_cb = QHBoxLayout(row)
            row_cb.setContentsMargins(10, 8, 10, 8)
            row_cb.setSpacing(10)

            cb = QCheckBox()
            tid = str(t.get("id", ""))
            text = str(t.get("text", "") or "")
            is_done = bool(t.get("done"))
            cb.setProperty("task_id", tid)
            cb.setChecked(is_done)

            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setStyleSheet("background: transparent;")

            btn_del = QPushButton("✕")
            btn_del.setFixedSize(26, 26)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet(
                "QPushButton { background: transparent; color: rgba(120,90,50,130);"
                " border: none; border-radius: 13px; font-size: 13px; }"
                "QPushButton:hover { background: rgba(220,60,60,140); color: white; }"
            )
            btn_del.setProperty("task_id", tid)
            btn_del.clicked.connect(lambda _=False, b=btn_del: self._on_delete_task(b))

            row_cb.addWidget(cb)
            row_cb.addWidget(lab, 1)
            row_cb.addWidget(btn_del)

            # 样式：已完成变灰 + 删除线 + 略小的圆角卡片
            if is_done:
                row.setStyleSheet(
                    "QFrame { background: rgba(180,180,180,45);"
                    " border: 1px solid rgba(150,150,150,90); border-radius: 10px; }"
                )
                cb.setStyleSheet(
                    "QCheckBox { color: rgba(90,90,90,235); font-size: 13px; }"
                )
                lab.setStyleSheet(
                    "background: transparent; color: rgba(90,90,90,230);"
                    " text-decoration: line-through; font-size: 13px;"
                )
            else:
                row.setStyleSheet(
                    "QFrame { background: rgba(255,255,255,110);"
                    " border: 1px solid rgba(200,170,120,130); border-radius: 10px; }"
                )
                cb.setStyleSheet(
                    "QCheckBox { color: #3a280b; font-size: 14px; font-weight: 700; }"
                )
                lab.setStyleSheet(
                    "background: transparent; color: #2a1f0f; font-size: 14px;"
                    " font-weight: 600;"
                )
            cb.stateChanged.connect(
                lambda state, t_id=tid: self._on_task_toggle(t_id, state == Qt.Checked)
            )

            self.dash_task_lay.insertWidget(insert_at, row)
            insert_at += 1
        total = len(tasks_sorted)
        self.dash_task_progress.setText(f"{done} / {total}  已完成")

    def _on_task_toggle(self, task_id: str, done: bool):
        self.store.toggle_task_done(task_id, done)
        self._rebuild_task_rows()

    def _on_delete_task(self, btn: QPushButton):
        tid = str(btn.property("task_id"))
        tasks = [t for t in (self.store.settings.get("today_tasks") or []) if t.get("id") != tid]
        self.store.settings["today_tasks"] = tasks
        self.store.save()
        self._rebuild_task_rows()

    def _on_add_task(self):
        txt, ok = self._dash_input_dialog("添加今日任务", "要做什么？ (例如：阅读 1 篇英语阅读)")
        if not ok:
            return
        txt = txt.strip()
        if not txt:
            return
        tasks = self.store.settings.get("today_tasks") or []
        tasks.append({"id": uuid.uuid4().hex[:8], "text": txt, "done": False})
        self.store.settings["today_tasks"] = tasks
        self.store.save()
        self._rebuild_task_rows()

    def _on_reset_tasks(self):
        ret = QMessageBox.question(
            self._page if hasattr(self, "_page") else self,
            "重置今日任务",
            "将用默认 6 条任务替换当前清单，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.store.settings.pop("dashboard_date", None)
        self.store.settings.pop("today_tasks", None)
        self.store.ensure_today_tasks()
        self._rebuild_task_rows()

    def _dash_input_dialog(self, title: str, label: str) -> Tuple[str, bool]:
        dlg = QDialog(self._page if hasattr(self, "_page") else self)
        dlg.setWindowTitle(title)
        dlg.resize(420, 140)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        v.addWidget(QLabel(label))
        edit = QLineEdit()
        v.addWidget(edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        edit.setFocus()
        if dlg.exec_() == QDialog.Accepted:
            return edit.text(), True
        return "", False

    # ============================================================
    # 网课学习区：上 = 内置浏览器 / 下左 = Markdown 编辑 + 保存 / 下右 = 笔记列表 + 预览
    # ============================================================
    def _build_course_page(self, name: str) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 2, 4, 4)
        outer.setSpacing(10)

        # 标题行
        title_row = QHBoxLayout()
        title_lab = QLabel(name)
        title_lab.setStyleSheet(
            "font-size: 22px; font-weight: 900; letter-spacing: 3px; color: #2a1f0f;"
        )
        sub = QLabel("内置浏览器上网课 · 随时记 Markdown 笔记 · 按学科归档")
        sub.setStyleSheet("color: rgba(42,31,15,150); font-size: 13px;")
        title_row.addWidget(title_lab)
        title_row.addSpacing(12)
        title_row.addWidget(sub)
        title_row.addStretch(1)
        outer.addLayout(title_row)

        # 整个页用 QSplitter(vertical): 上方 浏览器 | 下方 Markdown 区
        main_split = QSplitter(Qt.Vertical)
        main_split.setChildrenCollapsible(False)
        browser_w = self._course_build_browser()
        browser_w.setMaximumHeight(720)  # 限制浏览器区最大高度
        main_split.addWidget(browser_w)
        main_split.addWidget(self._course_build_markdown())
        main_split.setSizes([480, 520])
        outer.addWidget(main_split, 1)

        # 进入页面时刷新列表 & 载入浏览器默认页
        QTimer.singleShot(40, self._course_on_enter)
        return page

    # ==================== 专注页 (番茄钟) - 极简现代风 ====================
    def _build_focus_page(self, name: str) -> QWidget:
        from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QTimer as _QTimer, pyqtProperty
        from PyQt5.QtGui import QPainter as _QP, QColor as _QC, QPen as _QPen, QFont as _QFont
        page = QWidget()
        page.setObjectName("focusPage")
        page.setStyleSheet("QWidget#focusPage{background:#f8fafc;}")
        # 淡入
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._focus_opacity = QGraphicsOpacityEffect(page)
        self._focus_opacity.setOpacity(0.0)
        page.setGraphicsEffect(self._focus_opacity)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(18)

        # ===== 顶部标题 (极简: 大标题 + 副标 + 右上角徽章) =====
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_lab = QLabel(name)
        title_lab.setStyleSheet(
            "font-size: 26px; font-weight: 900; color: #0f172a; letter-spacing: 1px;"
        )
        sub = QLabel("心无旁骛，专注当下 · 番茄钟计时")
        sub.setStyleSheet("color: #64748b; font-size: 13px;")
        title_col.addWidget(title_lab)
        title_col.addWidget(sub)
        header_row.addLayout(title_col)
        header_row.addStretch(1)
        # 今日专注状态徽章
        self._focus_badge = QLabel("今日 0 分钟")
        self._focus_badge.setStyleSheet(
            "QLabel{background:#eef2ff;color:#4338ca;border:1px solid #e0e7ff;"
            "border-radius:999px;padding:6px 14px;font-weight:700;font-size:12px;}"
        )
        header_row.addWidget(self._focus_badge)
        outer.addLayout(header_row)

        # 主体: 左大计时器卡片 | 右统计卡片 (整体大圆角 + 1px 边框)
        main_split = QSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(2)
        main_split.setStyleSheet(
            "QSplitter::handle{background:transparent;}"
        )
        main_split.setSizes([640, 400])  # 默认分配 + 限制最大尺寸

        # ============ 左: 计时器卡片 (极简单色白卡) ============
        left = QFrame()
        left.setMaximumWidth(820)  # 限制最大宽度, 不让拉到最长
        left.setStyleSheet(
            "QFrame{"
            "  background:#ffffff;"
            "  border:1px solid #e2e8f0;"
            "  border-radius:24px;"
            "}"
        )
        lv = QVBoxLayout(left)
        lv.setContentsMargins(32, 28, 32, 28)
        lv.setSpacing(18)

        # ---- 任务输入 (现代风格: 灰色底 + focus蓝边) ----
        task_wrap = QFrame()
        task_wrap.setStyleSheet(
            "QFrame{background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;}"
            "QFrame:focus-within{background:white;border:1.5px solid #6366f1;}"
        )
        tl = QHBoxLayout(task_wrap)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(8)
        task_icon = QLabel("🎯")
        task_icon.setStyleSheet("font-size:16px;")
        self._focus_task_input = QLineEdit()
        self._focus_task_input.setPlaceholderText("想专注做点什么？（如：背单词 List 5）")
        self._focus_task_input.setStyleSheet(
            "QLineEdit{background:transparent;border:none;font-size:14px;color:#0f172a;"
            "padding:4px 0;}"
            "QLineEdit:focus{outline:0;}"
        )
        tl.addWidget(task_icon)
        tl.addWidget(self._focus_task_input, 1)
        lv.addWidget(task_wrap)

        # ---- 目标时长 (现代 Segmented Control) ----
        label_row = QHBoxLayout()
        time_lab = QLabel("专注时长")
        time_lab.setStyleSheet("font-size:13px;font-weight:700;color:#334155;")
        label_row.addWidget(time_lab)
        label_row.addStretch(1)
        lv.addLayout(label_row)

        seg_wrap = QFrame()
        seg_wrap.setStyleSheet(
            "QFrame{background:#f1f5f9;border-radius:14px;padding:4px;}"
        )
        seg_lay = QHBoxLayout(seg_wrap)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(4)
        self._focus_time_btns = []
        SEG_COLOR = "#6366f1"
        for m in (15, 25, 45, 60):
            b = QPushButton(f"{m} 分钟")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(36)
            b.setStyleSheet(
                "QPushButton{background:transparent;border:none;border-radius:10px;"
                "padding:0 16px;font-weight:700;color:#64748b;font-size:13px;}"
                "QPushButton:hover{color:#0f172a;}"
                f"QPushButton:checked{{background:{SEG_COLOR};color:white;}}"
            )
            b.clicked.connect(lambda _=False, mm=m: self._focus_set_target(mm))
            self._focus_time_btns.append((b, m))
            seg_lay.addWidget(b, 1)
        # 默认 25 分
        self._focus_time_btns[1][0].setChecked(True)
        self._focus_target_minutes = 25
        lv.addWidget(seg_wrap)

        # ---- 进度环 + 时间显示 (居中大卡片) ----
        ring_card = QFrame()
        ring_card.setStyleSheet(
            "QFrame{"
            "  background: qlineargradient(x1:0,y1:0, x2:1,y2:1,"
            "    stop:0 #fafafa, stop:1 #f1f5f9);"
            "  border:1px solid #e2e8f0;border-radius:22px;"
            "}"
        )
        ring_lay = QVBoxLayout(ring_card)
        ring_lay.setContentsMargins(12, 16, 12, 16)

        self._focus_ring_label = QLabel()
        self._focus_ring_label.setAlignment(Qt.AlignCenter)
        self._focus_ring_label.setMinimumHeight(260)
        self._focus_progress = 0.0
        self._focus_ring_anim = None
        self._focus_ring_label.resizeEvent = lambda _e: self._focus_draw_ring()
        ring_lay.addWidget(self._focus_ring_label)
        lv.addWidget(ring_card, 1)
        QTimer.singleShot(60, self._focus_draw_ring)

        # ---- 控制按钮 (现代胶囊按钮, 开始是深蓝主按钮) ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._focus_btn_start = QPushButton("▶  开始专注")
        self._focus_btn_start.setCursor(Qt.PointingHandCursor)
        self._focus_btn_start.setFixedHeight(44)
        self._focus_btn_start.setMinimumWidth(160)
        self._focus_btn_start.setStyleSheet(
            "QPushButton{background:#111827;color:white;border:none;"
            "border-radius:14px;padding:0 28px;font-weight:800;font-size:14px;}"
            "QPushButton:hover{background:#1f2937;}"
            "QPushButton:pressed{background:#374151;}"
            "QPushButton:disabled{background:#e5e7eb;color:#9ca3af;}"
        )
        self._focus_btn_start.clicked.connect(self._focus_start)

        self._focus_btn_pause = QPushButton("⏸  暂停")
        self._focus_btn_pause.setCursor(Qt.PointingHandCursor)
        self._focus_btn_pause.setFixedHeight(44)
        self._focus_btn_pause.setEnabled(False)
        self._focus_btn_pause.setMinimumWidth(110)
        self._focus_btn_pause.setStyleSheet(
            "QPushButton{background:#f59e0b;color:white;border:none;"
            "border-radius:14px;padding:0 22px;font-weight:800;font-size:14px;}"
            "QPushButton:hover{background:#d97706;}"
            "QPushButton:disabled{background:#e5e7eb;color:#9ca3af;}"
        )
        self._focus_btn_pause.clicked.connect(self._focus_pause)

        self._focus_btn_stop = QPushButton("⏹  结束")
        self._focus_btn_stop.setCursor(Qt.PointingHandCursor)
        self._focus_btn_stop.setFixedHeight(44)
        self._focus_btn_stop.setEnabled(False)
        self._focus_btn_stop.setMinimumWidth(110)
        self._focus_btn_stop.setStyleSheet(
            "QPushButton{background:white;color:#ef4444;border:1px solid #fecaca;"
            "border-radius:14px;padding:0 22px;font-weight:800;font-size:14px;}"
            "QPushButton:hover{background:#fef2f2;border-color:#fca5a5;}"
            "QPushButton:disabled{background:#f8fafc;color:#cbd5e1;border-color:#e2e8f0;}"
        )
        self._focus_btn_stop.clicked.connect(self._focus_stop)

        btn_row.addWidget(self._focus_btn_pause)
        btn_row.addSpacing(10)
        btn_row.addWidget(self._focus_btn_start)
        btn_row.addSpacing(10)
        btn_row.addWidget(self._focus_btn_stop)
        btn_row.addStretch(1)
        lv.addLayout(btn_row)

        main_split.addWidget(left)

        # ============ 右: 统计面板 (极简白卡) ============
        right = QFrame()
        right.setMaximumWidth(560)  # 限制最大宽度, 不让拉到最长
        right.setStyleSheet(
            "QFrame{"
            "  background:#ffffff;border:1px solid #e2e8f0;border-radius:24px;"
            "}"
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(22, 22, 22, 22)
        rv.setSpacing(14)

        # 统计标题
        stat_row = QHBoxLayout()
        stat_title = QLabel("今日统计")
        stat_title.setStyleSheet("font-size:16px;font-weight:800;color:#0f172a;")
        stat_row.addWidget(stat_title)
        stat_row.addStretch(1)
        rv.addLayout(stat_row)

        # 3 个大数字统计卡 (纯色背景无渐变, 现代极简)
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)
        self._focus_card_total = self._make_stat_card_modern("专注分钟", "0", "#10b981", "#dcfce7", "#166534")
        self._focus_card_done = self._make_stat_card_modern("完成番茄", "0", "#ef4444", "#fee2e2", "#991b1b")
        self._focus_card_count = self._make_stat_card_modern("会话次数", "0", "#6366f1", "#eef2ff", "#4338ca")
        cards_grid.addWidget(self._focus_card_total, 0, 0)
        cards_grid.addWidget(self._focus_card_done, 0, 1)
        cards_grid.addWidget(self._focus_card_count, 1, 0, 1, 2)
        rv.addLayout(cards_grid)

        # 最近会话
        hist_hdr = QHBoxLayout()
        hist_title = QLabel("最近会话")
        hist_title.setStyleSheet("font-size:14px;font-weight:700;color:#0f172a;")
        hist_hdr.addWidget(hist_title)
        hist_hdr.addStretch(1)
        rv.addLayout(hist_hdr)

        self._focus_history = QListWidget()
        self._focus_history.setStyleSheet(
            "QListWidget{"
            "  background:#fafafa;border:1px solid #e5e7eb;border-radius:14px;"
            "  padding:6px;font-size:12px;color:#334155;outline:0;}"
            "QListWidget::item{padding:8px 10px;border-radius:8px;margin:2px 0;}"
            "QListWidget::item:selected{background:#eef2ff;color:#4338ca;}"
            "QListWidget::item:hover:!selected{background:#f1f5f9;}"
        )
        rv.addWidget(self._focus_history, 1)
        main_split.addWidget(right)

        main_split.setSizes([580, 400])
        outer.addWidget(main_split, 1)

        # 状态/计时器/存储
        self._focus_store = FocusStore.load()
        self._focus_timer = _QTimer(self)
        self._focus_timer.setInterval(1000)
        self._focus_timer.timeout.connect(self._focus_tick)
        self._focus_running = False
        self._focus_paused = False
        self._focus_remaining = 0
        self._focus_elapsed = 0
        self._focus_session_start = ""
        self._focus_refresh_stats()

        # 淡入动画
        page_timer = _QTimer(page)
        page_timer.setSingleShot(True)
        page_timer.timeout.connect(lambda: self._focus_play_enter_anim(page))
        page_timer.start(50)

        return page

    def _make_stat_card_modern(self, title: str, value: str, accent: str, bg: str, fg: str) -> QFrame:
        """极简风格统计卡: 纯色圆角背景 + 大数字 + 标题"""
        f = QFrame()
        f.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid rgba(226,232,240,140);"
            f"border-radius:18px;}}"
        )
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(6)
        val_label = QLabel(value)
        val_label.setStyleSheet(f"font-size:32px;font-weight:900;color:{fg};")
        val_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size:12px;color:{accent};font-weight:700;")
        title_label.setAlignment(Qt.AlignLeft)
        # 小色点
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(f"background:{accent};border-radius:3px;")
        dot_row = QHBoxLayout()
        dot_row.setSpacing(6)
        dot_row.addWidget(dot)
        dot_row.addWidget(title_label)
        dot_row.addStretch(1)
        v.addLayout(dot_row)
        v.addWidget(val_label)
        f._value_label = val_label
        return f

    def _focus_play_enter_anim(self, page):
        """页面进入动画: 仅淡入 (避免 pos 偏移和 layout 冲突)"""
        try:
            from PyQt5.QtCore import QPropertyAnimation, QEasingCurve
            anim = QPropertyAnimation(self._focus_opacity, b"opacity", page)
            anim.setDuration(450)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._focus_enter_anim = anim  # 持有引用避免 GC
        except Exception:
            try:
                self._focus_opacity.setOpacity(1.0)
            except Exception:
                pass

    def _focus_draw_ring(self):
        """自绘进度环 + 中央时间文字"""
        try:
            from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QConicalGradient
            label = self._focus_ring_label
            # 高分屏适配
            dpr = label.devicePixelRatioF() if hasattr(label, "devicePixelRatioF") else 1.0
            w = max(220, label.width() or 220)
            h = max(220, label.height() or 220)
            size = min(w, h)
            pm = QPixmap(int(size * dpr), int(size * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(QColor(0, 0, 0, 0))
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            # 背景灰环
            cx = cy = size / 2
            r = size / 2 - 18
            pen = QPen(QColor(220, 210, 190, 200), 14)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2), 0, 360 * 16)
            # 进度红环
            if self._focus_progress > 0:
                # 用锥形渐变让进度环有渐变色
                grad = QConicalGradient(cx, cy, 90)
                grad.setColorAt(0.0, QColor(220, 38, 38))
                grad.setColorAt(1.0, QColor(251, 113, 50))
                pen = QPen(QColor(220, 38, 38), 14)
                pen.setCapStyle(Qt.RoundCap)
                # Qt drawArc 角度: 从 12 点开始顺时针; 起始 90° (12点), 负值表顺时针
                span = int(-360 * 16 * self._focus_progress)
                p.setPen(pen)
                p.setBrush(grad)
                p.drawArc(int(cx - r), int(cy - r), int(r * 2), int(r * 2), 90 * 16, span)
            # 中央文字
            mins = self._focus_remaining // 60
            secs = self._focus_remaining % 60
            time_str = f"{mins:02d}:{secs:02d}"
            p.setPen(QColor(42, 31, 15))
            font = QFont("Microsoft YaHei", 28, QFont.Black)
            p.setFont(font)
            p.drawText(int(cx - r), int(cy - r), int(r * 2), int(r * 2),
                       Qt.AlignCenter, time_str)
            # 状态文字
            if self._focus_running and not self._focus_paused:
                state = "专注中"
                sc = QColor(220, 38, 38)
            elif self._focus_paused:
                state = "已暂停"
                sc = QColor(217, 119, 6)
            else:
                state = "准备就绪"
                sc = QColor(22, 163, 74)
            p.setPen(sc)
            font2 = QFont("Microsoft YaHei", 11, QFont.Bold)
            p.setFont(font2)
            p.drawText(int(cx - r), int(cy + 22), int(r * 2), 30,
                       Qt.AlignCenter, state)
            p.end()
            label.setPixmap(pm)
        except Exception:
            pass

    def _focus_set_target(self, minutes: int):
        if self._focus_running:
            return  # 运行中不可改
        self._focus_target_minutes = minutes
        self._focus_remaining = minutes * 60
        self._focus_progress = 0.0
        # 更新按钮选中状态
        for b, m in self._focus_time_btns:
            b.setChecked(m == minutes)
        self._focus_draw_ring()

    def _focus_start(self):
        if self._focus_running and self._focus_paused:
            # 从暂停恢复
            self._focus_paused = False
            self._focus_btn_pause.setText("⏸ 暂停")
            self._focus_btn_start.setEnabled(False)
            self._focus_timer.start()
            self._focus_draw_ring()
            return
        if self._focus_running:
            return
        # 新一轮专注
        if self._focus_remaining <= 0:
            self._focus_remaining = self._focus_target_minutes * 60
            self._focus_elapsed = 0
        self._focus_running = True
        self._focus_paused = False
        self._focus_session_start = datetime.now().isoformat()
        self._focus_btn_start.setEnabled(False)
        self._focus_btn_pause.setEnabled(True)
        self._focus_btn_stop.setEnabled(True)
        # 禁用任务输入和时长按钮
        self._focus_task_input.setEnabled(False)
        for b, _ in self._focus_time_btns:
            b.setEnabled(False)
        self._focus_timer.start()
        self._focus_draw_ring()

    def _focus_pause(self):
        if not self._focus_running or self._focus_paused:
            return
        self._focus_paused = True
        self._focus_timer.stop()
        self._focus_btn_pause.setText("▶ 继续")
        self._focus_btn_start.setEnabled(True)  # 也可以点开始恢复
        self._focus_draw_ring()

    def _focus_stop(self):
        """手动停止: 记录实际已计秒数"""
        if not self._focus_running:
            return
        self._focus_timer.stop()
        self._focus_running = False
        self._focus_paused = False
        # 保存会话 (实际专注 >= 60s 才记录)
        if self._focus_elapsed >= 60:
            sess = FocusSession(
                task=self._focus_task_input.text().strip() or "(未命名任务)",
                target_minutes=self._focus_target_minutes,
                actual_seconds=self._focus_elapsed,
                completed=False,
                started_at=self._focus_session_start,
                ended_at=datetime.now().isoformat(),
                date=today().isoformat(),
            )
            self._focus_store.add(sess)
        # 重置
        self._focus_remaining = self._focus_target_minutes * 60
        self._focus_elapsed = 0
        self._focus_progress = 0.0
        self._focus_btn_start.setEnabled(True)
        self._focus_btn_pause.setEnabled(False)
        self._focus_btn_pause.setText("⏸ 暂停")
        self._focus_btn_stop.setEnabled(False)
        self._focus_task_input.setEnabled(True)
        for b, _ in self._focus_time_btns:
            b.setEnabled(True)
        self._focus_draw_ring()
        self._focus_refresh_stats()

    def _focus_tick(self):
        if not self._focus_running or self._focus_paused:
            return
        if self._focus_remaining > 0:
            self._focus_remaining -= 1
            self._focus_elapsed += 1
            total = self._focus_target_minutes * 60
            self._focus_progress = 1.0 - (self._focus_remaining / max(1, total))
            self._focus_draw_ring()
        if self._focus_remaining <= 0:
            # 完成目标
            self._focus_timer.stop()
            self._focus_running = False
            self._focus_paused = False
            self._focus_progress = 1.0
            sess = FocusSession(
                task=self._focus_task_input.text().strip() or "(未命名任务)",
                target_minutes=self._focus_target_minutes,
                actual_seconds=self._focus_elapsed,
                completed=True,
                started_at=self._focus_session_start,
                ended_at=datetime.now().isoformat(),
                date=today().isoformat(),
            )
            self._focus_store.add(sess)
            # 重置 UI
            self._focus_remaining = self._focus_target_minutes * 60
            self._focus_elapsed = 0
            self._focus_btn_start.setEnabled(True)
            self._focus_btn_pause.setEnabled(False)
            self._focus_btn_stop.setEnabled(False)
            self._focus_task_input.setEnabled(True)
            for b, _ in self._focus_time_btns:
                b.setEnabled(True)
            self._focus_draw_ring()
            self._focus_refresh_stats()
            self._focus_play_finish_anim()
            try:
                QMessageBox.information(self, "🎉 专注完成",
                    f"恭喜完成一个 {self._focus_target_minutes} 分钟番茄钟!\n\n"
                    f"任务: {sess.task}\n坚持就是胜利 💪")
            except Exception:
                pass

    def _focus_play_finish_anim(self):
        """完成时的脉冲动画: 进度环短暂放大再缩回"""
        try:
            from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup
            label = self._focus_ring_label
            anim1 = QPropertyAnimation(label, b"geometry", label)
            g = label.geometry()
            anim1.setDuration(200)
            anim1.setStartValue(g)
            anim1.setEndValue(g.adjusted(-15, -15, 15, 15))
            anim1.setEasingCurve(QEasingCurve.OutCubic)
            anim2 = QPropertyAnimation(label, b"geometry", label)
            anim2.setDuration(250)
            anim2.setStartValue(g.adjusted(-15, -15, 15, 15))
            anim2.setEndValue(g)
            anim2.setEasingCurve(QEasingCurve.OutBounce)
            group = QSequentialAnimationGroup(label)
            group.addAnimation(anim1)
            group.addAnimation(anim2)
            group.start()
            self._focus_finish_anim = group
        except Exception:
            pass

    def _focus_refresh_stats(self):
        """刷新右侧统计面板"""
        try:
            total_min = self._focus_store.today_total_minutes()
            done = self._focus_store.today_completed_count()
            sessions = self._focus_store.today_sessions()
            self._focus_card_total._value_label.setText(str(total_min))
            self._focus_card_done._value_label.setText(str(done))
            self._focus_card_count._value_label.setText(str(len(sessions)))
            # 历史列表
            self._focus_history.clear()
            for s in self._focus_store.recent(20):
                task = s.get("task", "")
                mins = s.get("actual_seconds", 0) // 60
                secs = s.get("actual_seconds", 0) % 60
                target = s.get("target_minutes", 0)
                done_flag = "✅" if s.get("completed") else "⏹"
                date_str = s.get("date", "")
                started = s.get("started_at", "")[11:16] if s.get("started_at") else ""
                self._focus_history.addItem(f"{done_flag} [{date_str} {started}] {task}  {mins}m{secs:02d}s / {target}m")
        except Exception:
            pass

    def _build_pdf_page(self, name: str) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 2, 4, 4)
        outer.setSpacing(8)

        # 标题行
        title_row = QHBoxLayout()
        title_lab = QLabel(name)
        title_lab.setStyleSheet(
            "font-size: 22px; font-weight: 800; letter-spacing: 1px; color: #0f172a;"
        )
        sub = QLabel("导入 PDF · 目录跳转 · 划红线标注 · 划词翻译")
        sub.setStyleSheet("color: #64748b; font-size: 13px; font-weight: 500;")
        title_row.addWidget(title_lab)
        title_row.addSpacing(12)
        title_row.addWidget(sub)
        title_row.addStretch(1)
        outer.addLayout(title_row)

        # 工具栏 (TraeCode 风: 白卡 + 细灰底)
        tool_bar_wrap = QFrame()
        tool_bar_wrap.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;"
            "border-top:3px solid #06b6d4;border-radius:12px;}"
        )
        tool_bar = QHBoxLayout(tool_bar_wrap)
        tool_bar.setSpacing(6)
        tool_bar.setContentsMargins(10, 8, 10, 8)

        def _solid_btn(color: str, color_hover: str) -> str:
            return (
                f"QPushButton{{background:{color};color:white;font-weight:600;"
                f"border:1px solid {color};border-radius:8px;padding:6px 14px;font-size:13px;}}"
                f"QPushButton:hover{{background:{color_hover};border-color:{color_hover};}}"
            )

        btn_open = QPushButton("📂 打开 PDF")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.setStyleSheet(_solid_btn("#2563eb", "#1d4ed8"))
        btn_open.clicked.connect(self._pdf_open_file)

        btn_prev = QPushButton("◀ 上一页")
        btn_prev.setCursor(Qt.PointingHandCursor)
        btn_prev.setStyleSheet(
            "QPushButton{background:#ffffff;color:#475569;font-weight:600;"
            "border:1px solid #e2e8f0;border-radius:8px;padding:6px 12px;font-size:13px;}"
            "QPushButton:hover{background:#f1f5f9;border-color:#cbd5e1;}"
        )
        btn_prev.clicked.connect(lambda: self._pdf_goto_page(self._pdf_cur_page - 1))

        btn_next = QPushButton("下一页 ▶")
        btn_next.setCursor(Qt.PointingHandCursor)
        btn_next.setStyleSheet(
            "QPushButton{background:#ffffff;color:#475569;font-weight:600;"
            "border:1px solid #e2e8f0;border-radius:8px;padding:6px 12px;font-size:13px;}"
            "QPushButton:hover{background:#f1f5f9;border-color:#cbd5e1;}"
        )
        btn_next.clicked.connect(lambda: self._pdf_goto_page(self._pdf_cur_page + 1))

        self._pdf_page_spin = QSpinBox()
        self._pdf_page_spin.setRange(1, 1)
        self._pdf_page_spin.setValue(1)
        self._pdf_page_spin.setStyleSheet(
            "QSpinBox{border:1px solid #e2e8f0;border-radius:8px;padding:4px 8px;"
            "background:#ffffff;}"
        )
        self._pdf_page_spin.valueChanged.connect(self._pdf_goto_page)

        self._pdf_total_label = QLabel(" / 0")
        self._pdf_total_label.setStyleSheet("color:#64748b;font-weight:600;font-size:13px;")

        zoom_out = QPushButton("➖")
        zoom_out.setCursor(Qt.PointingHandCursor)
        zoom_out.setFixedWidth(32)
        zoom_out.setStyleSheet(
            "QPushButton{background:#f1f5f9;color:#334155;border:1px solid #e2e8f0;"
            "border-radius:8px;font-weight:700;}"
            "QPushButton:hover{background:#e2e8f0;}"
        )
        zoom_out.clicked.connect(lambda: self._pdf_set_zoom(self._pdf_zoom - 0.1))

        self._pdf_zoom_label = QLabel("100%")
        self._pdf_zoom_label.setStyleSheet("color:#334155;font-weight:600;font-size:13px;")

        zoom_in = QPushButton("➕")
        zoom_in.setCursor(Qt.PointingHandCursor)
        zoom_in.setFixedWidth(32)
        zoom_in.setStyleSheet(
            "QPushButton{background:#f1f5f9;color:#334155;border:1px solid #e2e8f0;"
            "border-radius:8px;font-weight:700;}"
            "QPushButton:hover{background:#e2e8f0;}"
        )
        zoom_in.clicked.connect(lambda: self._pdf_set_zoom(self._pdf_zoom + 0.1))

        btn_hl = QPushButton("🖍️ 划红线")
        btn_hl.setCursor(Qt.PointingHandCursor)
        btn_hl.setCheckable(True)
        btn_hl.setStyleSheet(
            "QPushButton{background:#ffffff;color:#dc2626;font-weight:600;"
            "border:1px solid #fecaca;border-radius:8px;padding:6px 12px;font-size:13px;}"
            "QPushButton:hover{background:#fef2f2;}"
            "QPushButton:checked{background:#ef4444;color:white;border-color:#ef4444;}"
        )
        btn_hl.clicked.connect(lambda: setattr(self, "_pdf_hl_mode", btn_hl.isChecked()))
        self._pdf_hl_button = btn_hl

        btn_translate = QPushButton("🌐 翻译选中")
        btn_translate.setCursor(Qt.PointingHandCursor)
        btn_translate.setStyleSheet(_solid_btn("#10b981", "#059669"))
        btn_translate.clicked.connect(self._pdf_translate_selection)

        btn_clear = QPushButton("🧹 清除标注")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(
            "QPushButton{background:#ffffff;color:#475569;font-weight:600;"
            "border:1px solid #e2e8f0;border-radius:8px;padding:6px 12px;font-size:13px;}"
            "QPushButton:hover{background:#f1f5f9;}"
        )
        btn_clear.clicked.connect(self._pdf_clear_annotations)

        btn_save = QPushButton("💾 保存PDF")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet(_solid_btn("#8b5cf6", "#7c3aed"))
        btn_save.clicked.connect(self._pdf_save_file)

        tool_bar.addWidget(btn_open)
        tool_bar.addSpacing(6)
        tool_bar.addWidget(btn_prev)
        tool_bar.addWidget(self._pdf_page_spin)
        tool_bar.addWidget(self._pdf_total_label)
        tool_bar.addWidget(btn_next)
        tool_bar.addSpacing(8)
        tool_bar.addWidget(zoom_out)
        tool_bar.addWidget(self._pdf_zoom_label)
        tool_bar.addWidget(zoom_in)
        tool_bar.addStretch(1)
        tool_bar.addWidget(btn_hl)
        tool_bar.addWidget(btn_translate)
        tool_bar.addWidget(btn_clear)
        tool_bar.addWidget(btn_save)
        outer.addWidget(tool_bar_wrap)

        # 主体部分: 左侧目录 + 右侧 PDF 视图
        main_split = QSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(8)
        # 限制左侧目录最大宽度, 不让拉到最长
        main_split.setSizes([280, 700])

        # 左侧目录/翻译面板
        left_panel = QFrame()
        left_panel.setMaximumWidth(380)  # 限制最大宽度, 不让拉到最长
        left_panel.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;"
            "border-top:3px solid #06b6d4;border-radius:12px;}"
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(6)

        toc_title = QLabel("📑 目录结构")
        toc_title.setStyleSheet("font-weight:700;color:#0f172a;font-size:14px;")
        left_layout.addWidget(toc_title)

        self._pdf_toc_tree = QTreeWidget()
        self._pdf_toc_tree.setHeaderHidden(True)
        self._pdf_toc_tree.setStyleSheet(
            "QTreeWidget{border:1px solid #e2e8f0;border-radius:8px;background:#ffffff;"
            "font-size:13px;color:#334155;padding:4px;}"
            "QTreeWidget::item{padding:4px;border-radius:4px;}"
            "QTreeWidget::item:hover{background:#f1f5f9;}"
            "QTreeWidget::item:selected{background:#dbeafe;color:#1d4ed8;}"
        )
        self._pdf_toc_tree.itemClicked.connect(self._pdf_toc_jump)
        left_layout.addWidget(self._pdf_toc_tree, 1)

        # 翻译面板
        trans_title = QLabel("🌐 翻译结果")
        trans_title.setStyleSheet("font-weight:700;color:#0f172a;font-size:13px;margin-top:6px;")
        left_layout.addWidget(trans_title)

        self._pdf_translate_output = QPlainTextEdit()
        self._pdf_translate_output.setReadOnly(True)
        self._pdf_translate_output.setPlaceholderText("选中 PDF 中的文字后点「翻译选中」，结果会显示在这里。")
        self._pdf_translate_output.setMaximumBlockCount(500)
        self._pdf_translate_output.setStyleSheet(
            "QPlainTextEdit{border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;"
            "font-family: 'Microsoft YaHei', sans-serif;font-size:13px;padding:8px;color:#0f172a;}"
        )
        left_layout.addWidget(self._pdf_translate_output, 1)

        main_split.addWidget(left_panel)

        # 右侧 PDF 渲染区
        right_panel = QFrame()
        right_panel.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;"
            "border-top:3px solid #06b6d4;border-radius:12px;}"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self._pdf_scroll = QScrollArea()
        self._pdf_scroll.setWidgetResizable(True)
        self._pdf_scroll.setStyleSheet(
            "QScrollArea{border:none;background:#f8fafc;}"
        )

        self._pdf_canvas = QWidget()
        self._pdf_canvas.setStyleSheet("background:#f8fafc;")
        self._pdf_canvas_layout = QVBoxLayout(self._pdf_canvas)
        self._pdf_canvas_layout.setContentsMargins(20, 20, 20, 20)
        self._pdf_canvas_layout.setSpacing(12)

        self._pdf_pages: list[QLabel] = []
        self._pdf_doc = None
        self._pdf_cur_page = 0
        self._pdf_zoom = 1.0
        self._pdf_hl_mode = False
        self._pdf_path = ""
        self._pdf_annotations: dict[int, list] = {}  # {page_num: [{x,y,width,height,page_w,page_h,text}]}
        self._pdf_ann_widgets: dict[int, list] = {}  # {page_num: [QLabel, ...]} 对应 annotations, 可拖动

        # 初始提示
        self._pdf_welcome = QLabel(
            "📂 请点击左上角【打开 PDF】选择文件\n\n"
            "支持功能:\n"
            "  • 📑 目录结构 点击跳转到对应页\n"
            "  • 🖍️ 划红线 选中文字段落做标注\n"
            "  • 🌐 划词翻译 选中文字后点按钮查翻译\n"
            "  • 💾 保存修改 标注会写回 PDF 文件"
        )
        self._pdf_welcome.setAlignment(Qt.AlignCenter)
        self._pdf_welcome.setStyleSheet(
            "color:#64748b;font-size:15px;line-height:200%;padding:40px;"
        )
        self._pdf_canvas_layout.addWidget(self._pdf_welcome)
        self._pdf_canvas_layout.addStretch(1)

        self._pdf_scroll.setWidget(self._pdf_canvas)
        right_layout.addWidget(self._pdf_scroll)
        main_split.addWidget(right_panel)
        main_split.setSizes([260, 840])
        main_split.setStretchFactor(0, 0)
        main_split.setStretchFactor(1, 1)

        outer.addWidget(main_split, 1)

        return page

    # ---------- PDF 功能方法 ----------
    def _pdf_open_file(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 PDF 文件", "", "PDF 文件 (*.pdf);;所有文件 (*)"
            )
        except Exception:
            path = ""
        if not path:
            return
        try:
            import fitz
            doc = fitz.open(path)
            self._pdf_doc = doc
            self._pdf_path = path
            self._pdf_annotations = {}
            self._pdf_ann_widgets = {}
            self._pdf_total_label.setText(f" / {doc.page_count}")
            self._pdf_page_spin.setRange(1, max(1, doc.page_count))
            self._pdf_page_spin.setValue(1)
            self._pdf_cur_page = 0
            self._pdf_zoom = 1.0
            self._pdf_zoom_label.setText("100%")
            self._pdf_load_toc()
            self._pdf_render_pages()
        except Exception as e:
            try:
                QMessageBox.critical(self, "PDF 打开失败", f"无法打开文件:\n{path}\n\n错误:\n{e}")
            except Exception:
                pass

    def _pdf_load_toc(self):
        self._pdf_toc_tree.clear()
        if self._pdf_doc is None:
            return
        try:
            toc = self._pdf_doc.get_toc(simple=True)
            if not toc:
                item = QTreeWidgetItem(["(该 PDF 没有目录)"])
                self._pdf_toc_tree.addTopLevelItem(item)
                return
            for lvl, title, page in toc:
                item = QTreeWidgetItem([f"  " * (lvl - 1) + title.strip() + f"  · 第 {page} 页"])
                item.setData(0, Qt.UserRole, max(0, int(page) - 1))
                item.setData(0, Qt.UserRole + 1, lvl)
                self._pdf_toc_tree.addTopLevelItem(item)
        except Exception:
            pass

    def _pdf_toc_jump(self, item, _col):
        page_idx = item.data(0, Qt.UserRole)
        if page_idx is None:
            return
        try:
            page_idx = int(page_idx)
        except Exception:
            return
        self._pdf_goto_page(page_idx)

    def _pdf_render_pages(self):
        if self._pdf_doc is None:
            return
        try:
            if self._pdf_welcome is not None and self._pdf_welcome.parent() is not None:
                self._pdf_canvas_layout.removeWidget(self._pdf_welcome)
                self._pdf_welcome.setParent(None)
        except Exception:
            pass
        for w in self._pdf_pages:
            try:
                self._pdf_canvas_layout.removeWidget(w)
                w.setParent(None)
            except Exception:
                pass
        self._pdf_pages.clear()
        # 清空标注 widgets 字典 (旧 page label 已销毁, 子 widget 自动销毁, 这里只清引用)
        self._pdf_ann_widgets = {}
        # 清空干净 pixmap 缓存 (zoom 变了尺寸会变)
        if hasattr(self, "_pdf_clean_pixmaps"):
            self._pdf_clean_pixmaps.clear()
        try:
            self._pdf_doc.close()
        except Exception:
            pass
        import fitz
        self._pdf_doc = fitz.open(self._pdf_path)
        total = self._pdf_doc.page_count
        zoom = self._pdf_zoom
        mat = fitz.Matrix(zoom, zoom)
        for i in range(total):
            try:
                page = self._pdf_doc.load_page(i)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                if img.isNull():
                    continue
                pixmap = QPixmap.fromImage(img)
                label = QLabel()
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignCenter)
                label.setStyleSheet(
                    "QLabel{background:white;border:1px solid #d1d5db;border-radius:4px;"
                    "margin:0px;padding:0px;}"
                )
                label.setCursor(Qt.PointingHandCursor)
                # 三件套: 按下/移动/松开, 支持拖动画线
                label.mousePressEvent = lambda _e, pi=i: self._pdf_on_page_press(pi, _e)
                label.mouseMoveEvent = lambda _e, pi=i: self._pdf_on_page_move(pi, _e)
                label.mouseReleaseEvent = lambda _e, pi=i: self._pdf_on_page_release(pi, _e)
                # 双击翻译 (非划线模式)
                label.mouseDoubleClickEvent = lambda _e, pi=i: self._pdf_on_page_doubleclick(pi, _e)
                # Ctrl+滚轮缩放
                label.wheelEvent = lambda _e, pi=i: self._pdf_on_wheel(pi, _e)
                self._pdf_pages.append(label)
                self._pdf_canvas_layout.addWidget(label)
                # 重建该页的可拖动标注 widgets (替代旧的画 pixmap 方式)
                self._pdf_rebuild_ann_widgets(i)
            except Exception:
                continue
        self._pdf_canvas_layout.addStretch(1)

    def _pdf_rebuild_ann_widgets(self, page_idx: int):
        """根据 _pdf_annotations 重建该页所有可拖动标注 widgets"""
        # 先清掉旧的
        old = self._pdf_ann_widgets.pop(page_idx, [])
        for w in old:
            try:
                w.setParent(None)
                w.deleteLater()
            except Exception:
                pass
        self._pdf_ann_widgets[page_idx] = []
        if page_idx not in self._pdf_annotations:
            return
        if page_idx >= len(self._pdf_pages):
            return
        page_label = self._pdf_pages[page_idx]
        if page_label is None or page_label.pixmap() is None:
            return
        for i, ann in enumerate(self._pdf_annotations[page_idx]):
            try:
                w = self._create_ann_widget(page_idx, i, page_label)
                if w is not None:
                    self._pdf_ann_widgets[page_idx].append(w)
            except Exception:
                continue

    def _create_ann_widget(self, page_idx: int, ann_idx: int, page_label):
        """创建一个可拖动 + 右键删除的标注 widget"""
        w = QLabel(page_label)
        w.setStyleSheet(
            "background:rgba(220,38,38,90);border:2px solid #dc2626;border-radius:2px;"
        )
        w.setCursor(Qt.SizeAllCursor)
        w.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # 几何: 从 ann 的 PDF 坐标换算到当前 label 像素坐标
        ann = self._pdf_annotations[page_idx][ann_idx]
        wl = page_label.width()
        hl = page_label.height()
        sx = ann["x"] * wl / max(1, ann.get("page_w", wl))
        sy = ann["y"] * hl / max(1, ann.get("page_h", hl))
        sw = ann["width"] * wl / max(1, ann.get("page_w", wl))
        sh = ann["height"] * hl / max(1, ann.get("page_h", hl))
        w.setGeometry(int(sx), int(sy), max(6, int(sw)), max(4, int(sh)))
        w.show()
        w.raise_()
        # 绑定拖动
        w._ann_drag_start = None
        w._ann_drag_orig_geom = None
        w.mousePressEvent = lambda e, p=page_idx, i=ann_idx: self._pdf_ann_widget_press(p, i, e)
        w.mouseMoveEvent = lambda e, p=page_idx, i=ann_idx: self._pdf_ann_widget_move(p, i, e)
        w.mouseReleaseEvent = lambda e, p=page_idx, i=ann_idx: self._pdf_ann_widget_release(p, i, e)
        # 右键菜单
        w.setContextMenuPolicy(Qt.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos, p=page_idx, i=ann_idx: self._pdf_ann_widget_context_menu(p, i, pos)
        )
        # 鼠标悬停显示标注文字 (tooltip)
        txt = ann.get("text", "")
        if txt:
            w.setToolTip(txt[:200])
        return w

    def _pdf_ann_widget_press(self, page_idx: int, ann_idx: int, event):
        try:
            if event.button() != Qt.LeftButton:
                return
            w = self._pdf_ann_widgets[page_idx][ann_idx]
            w._ann_drag_start = event.pos()
            w._ann_drag_orig_geom = w.geometry()
        except Exception:
            pass

    def _pdf_ann_widget_move(self, page_idx: int, ann_idx: int, event):
        try:
            w = self._pdf_ann_widgets[page_idx][ann_idx]
            if getattr(w, "_ann_drag_start", None) is None:
                return
            delta = event.pos() - w._ann_drag_start
            g = w._ann_drag_orig_geom
            w.move(g.x() + delta.x(), g.y() + delta.y())
        except Exception:
            pass

    def _pdf_ann_widget_release(self, page_idx: int, ann_idx: int, event):
        try:
            w = self._pdf_ann_widgets[page_idx][ann_idx]
            if getattr(w, "_ann_drag_start", None) is None:
                return
            w._ann_drag_start = None
            w._ann_drag_orig_geom = None
            # 把新像素坐标回写到 ann 的 PDF 坐标 (width/height 不变, 只更新 x/y)
            page_label = self._pdf_pages[page_idx]
            g = w.geometry()
            wl = page_label.width()
            hl = page_label.height()
            ann = self._pdf_annotations[page_idx][ann_idx]
            ann["x"] = g.x() / wl * ann.get("page_w", wl)
            ann["y"] = g.y() / hl * ann.get("page_h", hl)
            # 重新抽取该区域文字
            try:
                import fitz
                page = self._pdf_doc.load_page(page_idx)
                rect_fitz = fitz.Rect(ann["x"], ann["y"],
                                      ann["x"] + ann["width"], ann["y"] + ann["height"])
                txt = page.get_textbox(rect_fitz)
                ann["text"] = txt.strip() if txt else ""
                if ann["text"]:
                    w.setToolTip(ann["text"][:200])
                    self._pdf_translate_output.setPlainText(
                        f"已标注文字:\n{ann['text'][:300]}\n\n可点「翻译选中」查看翻译。"
                    )
            except Exception:
                pass
        except Exception:
            pass

    def _pdf_ann_widget_context_menu(self, page_idx: int, ann_idx: int, pos):
        try:
            from PyQt5.QtWidgets import QMenu
            w = self._pdf_ann_widgets[page_idx][ann_idx]
            menu = QMenu(self)
            act_del = menu.addAction("🗑 删除此标注")
            menu.addSeparator()
            act_tr = menu.addAction("🌐 翻译此标注文字")
            action = menu.exec_(w.mapToGlobal(pos))
            if action == act_del:
                self._pdf_delete_ann(page_idx, ann_idx)
            elif action == act_tr:
                ann = self._pdf_annotations[page_idx][ann_idx]
                if ann.get("text"):
                    self._pdf_translate_output.setPlainText(
                        f"已标注文字:\n{ann['text'][:300]}\n\n可点「翻译选中」查看翻译。"
                    )
                    self._pdf_translate_selection()
        except Exception:
            pass

    def _pdf_delete_ann(self, page_idx: int, ann_idx: int):
        """删除单个标注"""
        try:
            self._pdf_annotations[page_idx].pop(ann_idx)
            if not self._pdf_annotations[page_idx]:
                del self._pdf_annotations[page_idx]
            self._pdf_rebuild_ann_widgets(page_idx)
        except Exception:
            pass

    def _pdf_goto_page(self, page: int):
        if self._pdf_doc is None:
            return
        page = int(max(0, min(self._pdf_doc.page_count - 1, page)))
        self._pdf_cur_page = page
        try:
            self._pdf_page_spin.blockSignals(True)
            self._pdf_page_spin.setValue(page + 1)
            self._pdf_page_spin.blockSignals(False)
        except Exception:
            pass
        if page < len(self._pdf_pages):
            label = self._pdf_pages[page]
            self._pdf_scroll.ensureWidgetVisible(label, 10, 10)

    def _pdf_set_zoom(self, zoom: float):
        zoom = float(max(0.2, min(4.0, round(zoom, 2))))
        self._pdf_zoom = zoom
        self._pdf_zoom_label.setText(f"{int(round(zoom * 100))}%")
        if self._pdf_doc is not None:
            self._pdf_render_pages()

    def _pdf_on_page_press(self, page_idx: int, event):
        if self._pdf_doc is None:
            return
        try:
            label = self._pdf_pages[page_idx]
            if label.pixmap() is None:
                return
            if self._pdf_hl_mode and event.button() == Qt.LeftButton:
                # 进入拖动画线状态
                self._pdf_hl_start = event.pos()
                self._pdf_hl_cur = event.pos()
                self._pdf_hl_label = label
                self._pdf_hl_page_idx = page_idx
                # 创建临时 overlay 用于实时画线
                self._pdf_hl_overlay = QLabel(label)
                self._pdf_hl_overlay.setStyleSheet("background:transparent;")
                self._pdf_hl_overlay.setGeometry(label.rect())
                self._pdf_hl_overlay.show()
        except Exception:
            pass

    def _pdf_on_page_move(self, page_idx: int, event):
        if not getattr(self, "_pdf_hl_mode", False) or getattr(self, "_pdf_hl_start", None) is None:
            return
        try:
            label = self._pdf_pages[page_idx]
            if label is not getattr(self, "_pdf_hl_label", None):
                return
            self._pdf_hl_cur = event.pos()
            self._pdf_draw_hl_overlay()
        except Exception:
            pass

    def _pdf_on_page_release(self, page_idx: int, event):
        if not getattr(self, "_pdf_hl_mode", False) or getattr(self, "_pdf_hl_start", None) is None:
            return
        try:
            label = self._pdf_pages[page_idx]
            start = self._pdf_hl_start
            end = event.pos()
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            zoom = self._pdf_zoom
            # 先按像素算出拉直后的矩形 (PDF 坐标)
            if abs(dx) >= abs(dy):
                # 水平: 起点y做基线, 行高 14pt
                line_h = max(8, int(14 * zoom))
                x1 = min(start.x(), end.x())
                x2 = max(start.x(), end.x())
                y_base = start.y()
                px_rect = (x1, y_base, x2, y_base + line_h)
            else:
                # 垂直: 起点x做基线, 列宽 6pt
                line_w = max(6, int(6 * zoom))
                y1 = min(start.y(), end.y())
                y2 = max(start.y(), end.y())
                x_base = start.x()
                px_rect = (x_base, y1, x_base + line_w, y2)
            # 太短忽略
            if abs(px_rect[2] - px_rect[0]) < 3 and abs(px_rect[3] - px_rect[1]) < 3:
                self._pdf_hl_clear_state()
                return
            pdf_rect = (
                px_rect[0] / zoom,
                px_rect[1] / zoom,
                px_rect[2] / zoom,
                px_rect[3] / zoom,
            )
            # ★ 吸附文字行: 找最近的文字行 bbox, 把 y/height 对齐到文字行
            snapped = self._pdf_snap_to_text_line(page_idx, pdf_rect)
            if snapped is not None:
                pdf_rect = snapped
            ann = {
                "x": pdf_rect[0],
                "y": pdf_rect[1],
                "width": pdf_rect[2] - pdf_rect[0],
                "height": pdf_rect[3] - pdf_rect[1],
                "page_w": label.width() / zoom,
                "page_h": label.height() / zoom,
                "text": "",
            }
            if page_idx not in self._pdf_annotations:
                self._pdf_annotations[page_idx] = []
            # 抽取吸附后区域的文字
            try:
                import fitz
                page = self._pdf_doc.load_page(page_idx)
                rect_fitz = fitz.Rect(ann["x"], ann["y"],
                                      ann["x"] + ann["width"], ann["y"] + ann["height"])
                txt = page.get_textbox(rect_fitz)
                if txt and txt.strip():
                    ann["text"] = txt.strip()
            except Exception:
                pass
            self._pdf_annotations[page_idx].append(ann)
            # 清除临时 overlay
            self._pdf_hl_clear_state()
            # 重建可拖动标注 widgets
            self._pdf_rebuild_ann_widgets(page_idx)
            if ann.get("text"):
                self._pdf_translate_output.setPlainText(
                    f"已标注文字:\n{ann['text'][:300]}\n\n可点「翻译选中」查看翻译。"
                )
        except Exception:
            pass

    def _pdf_snap_to_text_line(self, page_idx: int, pdf_rect: tuple):
        """把矩形吸附到最近文字行 bbox; 返回 (x0,y0,x1,y1) PDF 坐标或 None"""
        try:
            import fitz
            page = self._pdf_doc.load_page(page_idx)
            cx = (pdf_rect[0] + pdf_rect[2]) / 2
            cy = (pdf_rect[1] + pdf_rect[3]) / 2
            blocks = page.get_text("dict")["blocks"]
            best = None
            best_dist = float("inf")
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    bbox = line.get("bbox", (0, 0, 0, 0))
                    if len(bbox) != 4:
                        continue
                    lx0, ly0, lx1, ly1 = bbox
                    lcy = (ly0 + ly1) / 2
                    d = abs(lcy - cy)
                    if d < best_dist:
                        best_dist = d
                        best = bbox
            if best is None:
                return None
            lx0, ly0, lx1, ly1 = best
            # x 范围: 用拖动范围, 但裁剪到行宽内; 若太窄就用整行
            new_x0 = max(lx0, min(pdf_rect[0], lx1))
            new_x1 = min(lx1, max(pdf_rect[2], lx0))
            if new_x1 - new_x0 < 5:
                new_x0, new_x1 = lx0, lx1
            # y/height: 直接对齐到行 bbox
            return (new_x0, ly0, new_x1, ly1)
        except Exception:
            return None

    def _pdf_hl_clear_state(self):
        """清除拖动画线的临时状态"""
        try:
            if getattr(self, "_pdf_hl_overlay", None) is not None:
                self._pdf_hl_overlay.setParent(None)
                self._pdf_hl_overlay = None
        except Exception:
            pass
        self._pdf_hl_start = None
        self._pdf_hl_cur = None
        self._pdf_hl_label = None
        self._pdf_hl_page_idx = None

    def _pdf_draw_hl_overlay(self):
        """拖动时实时画临时红线 (自动拉直预览)"""
        try:
            label = self._pdf_hl_label
            overlay = self._pdf_hl_overlay
            start = self._pdf_hl_start
            cur = self._pdf_hl_cur
            if label is None or overlay is None or start is None or cur is None:
                return
            from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen
            base = label.pixmap()
            if base is None:
                return
            pm = QPixmap(base.size())
            pm.fill(QColor(0, 0, 0, 0))
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing, True)
            dx = cur.x() - start.x()
            dy = cur.y() - start.y()
            pen = QPen(QColor(220, 38, 38, 160), 3)
            p.setPen(pen)
            if abs(dx) >= abs(dy):
                line_h = max(8, int(14 * self._pdf_zoom))
                p.drawLine(start.x(), start.y() + line_h // 2,
                           cur.x(), start.y() + line_h // 2)
            else:
                line_w = max(6, int(6 * self._pdf_zoom))
                p.drawLine(start.x() + line_w // 2, start.y(),
                           start.x() + line_w // 2, cur.y())
            p.end()
            overlay.setPixmap(pm)
        except Exception:
            pass

    def _pdf_on_wheel(self, page_idx: int, event):
        """Ctrl+滚轮缩放"""
        try:
            from PyQt5.QtCore import QEvent
            if event.modifiers() & Qt.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._pdf_set_zoom(self._pdf_zoom + 0.1)
                else:
                    self._pdf_set_zoom(self._pdf_zoom - 0.1)
                event.accept()
                return
            # 非 Ctrl: 走默认滚动
            label = self._pdf_pages[page_idx] if page_idx < len(self._pdf_pages) else None
            if label is not None:
                QLabel.wheelEvent(label, event)
        except Exception:
            pass

    def _pdf_on_page_doubleclick(self, page_idx: int, event):
        """非划线模式: 双击选中文字翻译"""
        if self._pdf_doc is None or self._pdf_hl_mode:
            return
        try:
            self._pdf_try_get_text_at(page_idx, event.pos())
        except Exception:
            pass

    def _pdf_try_get_text_at(self, page_idx: int, pos):
        if self._pdf_doc is None:
            return
        try:
            page = self._pdf_doc.load_page(page_idx)
            zoom = self._pdf_zoom
            x = pos.x() / zoom
            y = pos.y() / zoom
            # 用字块 bbox 找最近文字
            blocks = page.get_text("dict")["blocks"]
            found_text = ""
            min_dist = float("inf")
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span.get("bbox", (0, 0, 0, 0))
                        if len(bbox) != 4:
                            continue
                        if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                            found_text = span.get("text", "")
                            break
                if found_text:
                    break
            if found_text:
                self._pdf_translate_output.setPlainText(
                    f"选中文字:\n{found_text}\n\n点「翻译选中」查看翻译。"
                )
        except Exception:
            pass

    def _pdf_translate_selection(self):
        text = self._pdf_translate_output.toPlainText().strip()
        if not text:
            try:
                QMessageBox.information(self, "翻译", "请先在 PDF 中划线或双击选中文字。")
            except Exception:
                pass
            return
        # 提取要翻译的文字 (去掉前面的提示)
        body = text
        if "选中文字:" in text:
            body = text.split("选中文字:", 1)[-1]
        elif "已标注文字:" in text:
            body = text.split("已标注文字:", 1)[-1]
        body = body.split("\n\n")[0].strip()
        if not body:
            return
        # 用免费接口: MyMemory 翻译 API
        self._pdf_translate_output.setPlainText("⏳ 正在翻译...")
        try:
            import urllib.request
            import urllib.parse
            import json
            src_lang = "en"
            dest_lang = "zh-CN"
            # 检测中文: 若包含中文字符则翻译成英文
            has_cn = any("\u4e00" <= c <= "\u9fff" for c in body)
            if has_cn:
                src_lang, dest_lang = "zh-CN", "en"
            params = urllib.parse.urlencode({
                "q": body[:450],
                "from": src_lang,
                "to": dest_lang,
            })
            url = f"https://api.mymemory.translated.net/get?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            translated = data.get("responseData", {}).get("translatedText", "")
            match = data.get("matches", [{}])
            confidence = match[0].get("quality", "") if match else ""
            if translated:
                src_label = "中文" if has_cn else "英文"
                dst_label = "英文" if has_cn else "中文"
                self._pdf_translate_output.setPlainText(
                    f"【原文 · {src_label}】\n{body}\n\n【译文 · {dst_label}】(质量: {confidence})\n{translated}"
                )
            else:
                self._pdf_translate_output.setPlainText(f"翻译失败: {data}")
        except Exception as e:
            self._pdf_translate_output.setPlainText(f"翻译失败: {e}")

    def _pdf_clear_annotations(self):
        if self._pdf_doc is None:
            return
        # 先销毁所有标注 widgets
        for page_idx in list(self._pdf_ann_widgets.keys()):
            for w in self._pdf_ann_widgets[page_idx]:
                try:
                    w.setParent(None)
                    w.deleteLater()
                except Exception:
                    pass
        self._pdf_ann_widgets = {}
        self._pdf_annotations = {}
        self._pdf_render_pages()
        try:
            QMessageBox.information(self, "清除标注", "已清除所有标注。")
        except Exception:
            pass

    def _pdf_save_file(self):
        if self._pdf_doc is None:
            return
        try:
            save_path, _ = QFileDialog.getSaveFileName(
                self, "保存 PDF", self._pdf_path or "", "PDF 文件 (*.pdf)"
            )
        except Exception:
            save_path = ""
        if not save_path:
            return
        try:
            import fitz
            # 如果有标注, 用 PyMuPDF 写入 highlight 注释
            doc = fitz.open(self._pdf_path)
            for page_idx, anns in self._pdf_annotations.items():
                try:
                    page = doc.load_page(page_idx)
                    for ann in anns:
                        rect = fitz.Rect(
                            ann["x"], ann["y"],
                            ann["x"] + ann["width"],
                            ann["y"] + ann["height"]
                        )
                        highlight = page.add_highlight_annot(rect)
                        highlight.set_colors(stroke=[1, 0, 0])
                        highlight.set_opacity(0.3)
                        if ann.get("text"):
                            try:
                                highlight.set_info(content=ann["text"][:200])
                            except Exception:
                                pass
                except Exception:
                    continue
            doc.save(save_path)
            doc.close()
            try:
                QMessageBox.information(self, "保存成功", f"PDF 已保存到:\n{save_path}")
            except Exception:
                pass
        except Exception as e:
            try:
                QMessageBox.critical(self, "保存失败", f"无法保存:\n{e}")
            except Exception:
                pass

    # ---------- 浏览器部分 ----------
    def _course_build_browser(self) -> QWidget:
        box = QGroupBox("内置浏览器")
        box.setStyleSheet(
            "QGroupBox {"
            "  background: qlineargradient(x1:0,y1:0, x2:1,y2:1,"
            "      stop:0 rgba(120,170,220,110),"
            "      stop:1 rgba(80,120,200,100));"
            "  border: 1px solid rgba(255,255,255,180);"
            "  border-radius: 16px;"
            "  margin-top: 18px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin; left: 16px; padding: 0 6px;"
            "  color: #1e3a8a; font-size: 14px; font-weight: 800;"
            "}"
        )
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 22, 12, 12)
        v.setSpacing(8)

        # 工具栏: 后退 / 前进 / 刷新 / 首页 / 地址栏 / 打开 / 启动Edge / 重启Edge / 放大 / 独立窗口
        bar = QHBoxLayout()
        bar.setSpacing(6)

        def mkbtn(text: str, tip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(28)
            if tip:
                b.setToolTip(tip)
            return b

        self.course_btn_back = mkbtn("◀", "后退 (Alt+←)")
        self.course_btn_fwd = mkbtn("▶", "前进 (Alt+→)")
        self.course_btn_refresh = mkbtn("⟳", "刷新 (F5)")
        self.course_btn_home = mkbtn("⌂", "首页")
        self.course_addr = QLineEdit()
        self.course_addr.setPlaceholderText("输入网课地址，例如: https://www.bilibili.com  回车打开")
        self.course_addr.setFixedHeight(28)
        self.course_btn_go = mkbtn("打开")

        self.course_btn_edge_start = mkbtn(
            "🧩启动Edge浏览器",
            "启动系统里的 Microsoft Edge 并嵌入到当前卡内\n"
            "（不用装任何 Python 依赖，用的是 Windows 自带 Edge）",
        )
        self.course_btn_edge_start.setStyleSheet(
            "QPushButton{background:#0ea5e9;color:white;font-weight:800;"
            "border:1px solid rgba(0,0,0,80);border-radius:5px;padding:2px 8px;}"
            "QPushButton:hover{background:#38bdf8;}"
        )

        self.course_btn_edge_restart = mkbtn(
            "♻️重启Edge",
            "关掉当前 Edge 子进程再重新启动 (卡顿时用)",
        )
        self.course_btn_edge_restart.setStyleSheet(
            "QPushButton{background:#475569;color:white;font-weight:700;"
            "border:1px solid rgba(0,0,0,80);border-radius:5px;padding:2px 8px;}"
            "QPushButton:hover{background:#64748b;}"
        )

        self.course_btn_maxarea = mkbtn("⛶", "放大：浏览器填满整个浏览器卡片区域 (ESC 还原)")
        self.course_btn_popout = mkbtn("🗔", "独立窗口：浏览器单独弹出一个新窗口 (关闭即归位)")
        self.course_btn_pure_video = mkbtn(
            "🎬 视频纯净模式",
            "把当前页面里正在播放的视频单独提取出来，黑底放大填满整个卡片区域，\n不显示推荐/弹幕/评论等杂项。再点一次或按 ESC 可以还原。"
        )
        self.course_btn_pure_video.setStyleSheet(
            "QPushButton{background:#dc2626;color:white;font-weight:800;"
            "border:1px solid rgba(0,0,0,80);border-radius:5px;padding:2px 8px;}"
            "QPushButton:hover{background:#ef4444;}"
        )
        self.course_btn_video_fit = mkbtn(
            "🔲 填充模式",
            "切换纯净视频模式下的画面填充方式：\n「等比完整」(显示全部画面, 有黑边) ↔「铺满裁剪」(不留黑边, 画面裁掉四角)"
        )
        self.course_btn_video_fit.setCheckable(True)
        self.course_btn_video_fit.setChecked(False)  # False=contain 完整, True=cover 裁剪
        for extra in (self.course_btn_maxarea, self.course_btn_popout, self.course_btn_pure_video, self.course_btn_video_fit):
            extra.setCursor(Qt.PointingHandCursor)

        bar.addWidget(self.course_btn_back)
        bar.addWidget(self.course_btn_fwd)
        bar.addWidget(self.course_btn_refresh)
        bar.addWidget(self.course_btn_home)
        bar.addSpacing(4)
        bar.addWidget(self.course_addr, 1)
        bar.addWidget(self.course_btn_go)
        bar.addSpacing(4)
        bar.addWidget(self.course_btn_edge_start)
        bar.addWidget(self.course_btn_edge_restart)
        bar.addWidget(self.course_btn_maxarea)
        bar.addWidget(self.course_btn_popout)
        bar.addWidget(self.course_btn_pure_video)
        bar.addWidget(self.course_btn_video_fit)
        v.addLayout(bar)

        # =============== Web 内容区 (PyQtWebEngine 真嵌入) ===============
        self.course_edge_host = None  # 统一初始化，fallback 分支会覆盖
        self.course_web_container: Optional["QFrame"] = QFrame()
        self.course_web_container.setStyleSheet(
            "background: white; border: 1px solid rgba(255,255,255,150); border-radius: 10px;"
        )
        wl = QVBoxLayout(self.course_web_container)
        wl.setContentsMargins(0, 0, 0, 0)

        # QWebEngineView: Qt 自带 Chromium 内核, 直接嵌到 PyQt widget 里
        self.course_webview = None
        self.course_webview_page = None
        self.course_webview_loaded = False
        self.course_webview_js_results: dict = {}
        self._course_webview_js_id = 0

        if _HAS_WEBENGINE and QWebEngineView is not None:
            self.course_webview = QWebEngineView(self.course_web_container)
            self.course_webview.setStyleSheet("background: white; border-radius: 10px;")
            self.course_webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # 自定义 Page: 拦截 target="_blank" 跳转
            self.course_webview_page = _CourseWebPage(self.course_webview)
            self.course_webview.setPage(self.course_webview_page)
            # 启用设置
            try:
                settings = self.course_webview.settings()
                settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
                settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
                settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            except Exception:
                pass
            # 信号: URL 变化
            try:
                self.course_webview.urlChanged.connect(self._course_webview_on_url_changed)
                self.course_webview.loadFinished.connect(self._course_webview_on_load_finished)
                self.course_webview.loadStarted.connect(lambda: setattr(self, "course_webview_loaded", False))
            except Exception:
                pass
            wl.addWidget(self.course_webview, 1)
        else:
            # fallback: 保留旧的 Edge 子进程方案
            self.course_edge_host: Optional[QWidget] = QWidget()
            self.course_edge_host.setStyleSheet("background: white;")
            wl.addWidget(self.course_edge_host, 1)

        self.course_edge_hint = QLabel(
            "👇 浏览器已使用【PyQtWebEngine】(Qt 自带 Chromium 内核，无需外部浏览器)\n\n"
            "👉 点 🧩加载页面，或在地址栏输入网址回车即可开始\n\n"
            "💡 B 站/腾讯课堂等主流视频网站 HTML5 播放器 100% 支持\n\n"
            "💡 点 🎬 视频纯净模式 可把视频单独提取出来黑底放大填满整个区域"
        )
        self.course_edge_hint.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.course_edge_hint.setWordWrap(True)
        self.course_edge_hint.setStyleSheet(
            "background: rgba(255,255,255,230); color: #0c4a6e;"
            " padding: 20px; border-radius: 10px; font-size: 14px; line-height: 180%;"
        )
        wl.addWidget(self.course_edge_hint)

        v.addWidget(self.course_web_container, 1)

        # ---- Edge 进程/句柄/放大/独立窗口 状态 ----
        self.course_edge_exe_path: Optional[str] = None
        self.course_edge_proc = None
        self.course_edge_hwnd: int = 0
        self.course_edge_original_style: int = 0
        self.course_edge_original_exstyle: int = 0
        self.course_edge_original_parent: int = 0
        self.course_edge_url: str = ""
        self.course_edge_starting: bool = False

        self._course_maximized: bool = False
        self._course_pop_win: Optional["QDialog"] = None
        self._course_pop_win_shortcut_close: Optional["QShortcut"] = None
        self._course_pop_win_shortcut_esc: Optional["QShortcut"] = None
        self._course_max_shortcut_esc: Optional["QShortcut"] = None
        self._course_max_box = None
        self._course_max_restore_container = None

        # 绑定动作
        self.course_btn_back.clicked.connect(self._course_go_back)
        self.course_btn_fwd.clicked.connect(self._course_go_forward)
        self.course_btn_refresh.clicked.connect(self._course_refresh)
        self.course_btn_home.clicked.connect(self._course_go_home)
        self.course_btn_go.clicked.connect(self._course_go_address)
        self.course_addr.returnPressed.connect(self._course_go_address)
        self.course_btn_maxarea.clicked.connect(self._course_toggle_maximize_in_card)
        self.course_btn_popout.clicked.connect(self._course_pop_out_browser)
        self.course_btn_pure_video.clicked.connect(self._course_toggle_pure_video_mode)
        self.course_btn_video_fit.clicked.connect(self._course_toggle_video_fit_mode)
        # 启动/重启: WebEngine 模式下直接加载/重载
        self.course_btn_edge_start.clicked.connect(lambda: self._course_load(
            getattr(self, "course_edge_url", "") or self._course_default_home()))
        self.course_btn_edge_restart.clicked.connect(lambda: self._course_refresh())

        if self.course_edge_host is not None:
            self.course_edge_host.installEventFilter(self)
        return box

    # ==================== 真·内嵌 WebView2 (pywebview + Edge WebView2 Runtime Evergreen) ====================
    # 这条路线 = Windows 10/11 自带 WebView2 COM，直接把浏览器控件渲染 HWND 塞进 course_edge_host
    # 不会启动 msedge.exe 独立窗口，也不会触碰你桌面上 Edge 的登录/收藏/历史

    def _course_wv2_data_dir(self) -> str:
        try:
            d = str(Path(__file__).resolve().parent / "image" / "wv2_data")
            Path(d).mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return ""

    def _course_wv2_ensure(self, silent: bool = False) -> bool:
        """确保 WebView2 控件已创建并嵌到 host；没装 pywebview 就自动回退到旧的 Edge --app 外置模式"""
        host = getattr(self, "course_edge_host", None)
        if host is None:
            return False
        if getattr(self, "course_wv2_window", None) is not None:
            return True
        if getattr(self, "course_wv2_starting", False):
            return True
        try:
            host.createWinId()
        except Exception:
            pass
        try:
            host_hwnd = int(host.winId())
        except Exception:
            host_hwnd = 0
        if host_hwnd <= 0:
            if not silent:
                try:
                    QMessageBox.warning(self, "无法创建宿主窗口", "PyQt 宿主 widget 拿不到 HWND，WebView2 无法嵌入。")
                except Exception:
                    pass
            return False
        # --- 尝试 pywebview 真内嵌 WebView2 ---
        try:
            import webview  # noqa: F401
            import threading as _th
            start_url = getattr(self, "course_edge_url", "") or self._course_default_home()
            self.course_wv2_starting = True
            self.course_wv2_creation_result = {"ok": False, "error": None, "window": None}

            def _worker():
                try:
                    data_dir = self._course_wv2_data_dir() or None
                    w = webview.create_window(
                        title="__kaoyan_wv2__",
                        url=str(start_url),
                        width=max(480, int(host.width())),
                        height=max(320, int(host.height())),
                        resizable=True,
                        frameless=True,
                        easy_drag=False,
                        background_color="#FFFFFF",
                        # pywebview 6.x create_window 不支持 hwnd= / debug= / user_data_dir=.
                        # 所以这里只传标准参数；真正嵌入通过后续找 WebView2 子 HWND 再 SetParent 做。
                    )
                    self.course_wv2_creation_result["ok"] = True
                    self.course_wv2_creation_result["window"] = w
                except Exception as e:
                    self.course_wv2_creation_result["ok"] = False
                    self.course_wv2_creation_result["error"] = repr(e)

            def _run_gui_loop():
                try:
                    # pywebview 6.x start: private_mode=True = 不写磁盘缓存; 传 storage_path 让 profile 落到 image/wv2_data
                    storage = self._course_wv2_data_dir() or None
                    webview.start(
                        func=None,
                        gui="edgechromium",
                        debug=False,
                        http_server=False,
                        private_mode=False if storage else True,
                        storage_path=storage,
                    )
                except Exception as e:
                    if self.course_wv2_creation_result.get("error") is None:
                        self.course_wv2_creation_result["error"] = repr(e)

            w_th = _th.Thread(target=_worker, name="wv2-create", daemon=True)
            g_th = _th.Thread(target=_run_gui_loop, name="wv2-gui", daemon=True)
            w_th.start()
            # 等 worker 把 window 对象塞进去 (webview.create_window 本身很快)
            import time as _t
            for _ in range(60):
                _t.sleep(0.05)
                if self.course_wv2_creation_result.get("ok"):
                    break
                if self.course_wv2_creation_result.get("error"):
                    break
            if not self.course_wv2_creation_result.get("ok"):
                err = self.course_wv2_creation_result.get("error") or "unknown"
                self.course_wv2_starting = False
                try:
                    import sys as _sys
                    import datetime as _dt
                    ts = _dt.datetime.now().strftime("%H:%M:%S")
                    print(f"[{ts}] WebView2 init FAILED: {err}", file=_sys.stderr, flush=True)
                except Exception:
                    pass
                raise RuntimeError(err)
            w = self.course_wv2_creation_result.get("window")
            # pywebview 6.x 不支持 hwnd=. create_window 只是在内存里构造 Window 对象,
            # 真正的 HWND 要等 webview.start() 里 WinForms Show 之后才会出现.
            # 所以这里先启动 gui 线程，然后走 QTimer 轮询找标题 "__kaoyan_wv2__" 的本进程窗体，
            # 找到后再 SetParent(host) 嵌入 + 剥边框 + MoveWindow 对齐。
            self.course_wv2_expected_title = str("__kaoyan_wv2__")
            g_th.start()
            self.course_wv2_gui_thread = g_th
            self.course_wv2_window_raw = w
            self._course_wv2_embed_ticks = 0
            try:
                from PyQt5.QtCore import QTimer
                self._course_wv2_embed_timer = QTimer(self)
                self._course_wv2_embed_timer.setInterval(80)
                self._course_wv2_embed_timer.timeout.connect(self._course_wv2_embed_hwnd_poll)
                self._course_wv2_embed_timer.start()
            except Exception:
                pass
            return True
        except Exception as e:
            self.course_wv2_starting = False
            if not silent:
                try:
                    QMessageBox.information(
                        self,
                        "WebView2 不可用，自动回退到 Edge 外置模式",
                        f"WebView2 创建失败：{e}\n\n"
                        f"为保证你能继续上网课，程序会自动退回之前的方案：\n"
                        f"用系统 Edge --app 模式（独立 profile）嵌入到 PyQt，不会污染你本地 Edge。"
                    )
                except Exception:
                    pass
            # ---- 回退: 旧的 Edge --app 方案 ----
            return self._course_edge_ensure(silent=silent)

    def _course_wv2_embed_hwnd_poll(self) -> None:
        """pywebview WinForms Form 显示后 -> 找窗口标题 "__kaoyan_wv2__" 且属于当前进程 -> SetParent 嵌入 host"""
        self._course_wv2_embed_ticks = int(getattr(self, "_course_wv2_embed_ticks", 0)) + 1
        if getattr(self, "course_wv2_window", None) is not None:
            try:
                if hasattr(self, "_course_wv2_embed_timer") and self._course_wv2_embed_timer is not None:
                    self._course_wv2_embed_timer.stop()
            except Exception:
                pass
            return
        if self._course_wv2_embed_ticks > 250:  # 20 秒超时
            try:
                if hasattr(self, "_course_wv2_embed_timer") and self._course_wv2_embed_timer is not None:
                    self._course_wv2_embed_timer.stop()
            except Exception:
                pass
            self.course_wv2_starting = False
            try:
                if getattr(self, "course_edge_hint", None) is not None:
                    self.course_edge_hint.setText(
                        "❌ WebView2 初始化成功但找不到窗口句柄 (20s 超时)\n\n"
                        "👉 点工具栏 “♻️重启” 再试；如果仍失败会自动退回 Edge 外置模式。"
                    )
            except Exception:
                pass
            return
        try:
            import ctypes
            from ctypes import wintypes as _wt
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            try:
                my_pid = int(kernel32.GetCurrentProcessId())
            except Exception:
                my_pid = 0
            title_expected = str(getattr(self, "course_wv2_expected_title", "") or "")
            found_ctx = []

            @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
            def _enum(hwnd, _lp):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                except Exception:
                    return True
                try:
                    _pid_out = _wt.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid_out))
                    wpid = int(_pid_out.value or 0)
                except Exception:
                    wpid = 0
                if my_pid and wpid != my_pid:
                    return True
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = str(buf.value or "")
                except Exception:
                    title = ""
                # 匹配: 标题精确相等是最好, 其次也接受最后一次的结果
                if title_expected and title == title_expected:
                    # 再筛掉被嵌入过的子窗口 (必须是顶级 GetParent==0 的)
                    try:
                        par = int(user32.GetParent(hwnd) or 0)
                    except Exception:
                        par = 0
                    if par == 0:
                        found_ctx.append(int(hwnd))
                        return False
                return True

            try:
                user32.EnumWindows(_enum, 0)
            except Exception:
                pass
            if not found_ctx:
                # fallback: 不要求标题精确, 找同进程里第一个 WindowsForms / Chrome_WidgetWin 顶级窗口 (标题不为空)
                found2 = []
                @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
                def _enum2(hwnd, _lp):
                    try:
                        if not user32.IsWindowVisible(hwnd):
                            return True
                        _pid_out = _wt.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid_out))
                        wpid = int(_pid_out.value or 0)
                        if my_pid and wpid != my_pid:
                            return True
                        par = int(user32.GetParent(hwnd) or 0)
                        if par != 0:
                            return True
                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls_buf, 255)
                        cls = str(cls_buf.value or "")
                        if ("WindowsForms" in cls) or ("Chrome_WidgetWin_" in cls):
                            found2.append(int(hwnd))
                            return False
                        return True
                    except Exception:
                        return True
            try:
                user32.EnumWindows(_enum2, 0)
            except Exception:
                pass
            if not found2:
                return
            found_ctx = [int(found2[0])]
            hwnd = int(found_ctx[0])
            # 嵌入
            self._course_wv2_embed_by_hwnd(hwnd)
            try:
                if hasattr(self, "_course_wv2_embed_timer") and self._course_wv2_embed_timer is not None:
                    self._course_wv2_embed_timer.stop()
            except Exception:
                pass
        except Exception:
            pass

    def _course_wv2_embed_by_hwnd(self, hwnd: int) -> None:
        """把找到的 pywebview WinForms 窗口 (WebView2 承载) 塞到 self.course_edge_host 里去"""
        if hwnd <= 0 or getattr(self, "course_edge_host", None) is None:
            return
        import ctypes
        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_POPUP = 0x80000000
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000
        WS_CLIPSIBLINGS = 0x04000000
        WS_CLIPCHILDREN = 0x02000000
        host = self.course_edge_host
        try:
            host.createWinId()
        except Exception:
            pass
        try:
            host_hwnd = int(host.winId())
        except Exception:
            host_hwnd = 0
        if not host_hwnd:
            return
        try:
            self.course_wv2_original_style = int(user32.GetWindowLongW(hwnd, GWL_STYLE) or 0)
            self.course_wv2_original_exstyle = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) or 0)
            self.course_wv2_original_parent = int(user32.GetParent(hwnd) or 0)
        except Exception:
            pass
        try:
            user32.SetLastError(0)
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = style & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_POPUP)
            style = style | WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, 0)
        except Exception:
            pass
        try:
            user32.SetParent(hwnd, host_hwnd)
        except Exception:
            pass
        try:
            w = max(100, int(host.width()))
            h = max(100, int(host.height()))
            user32.MoveWindow(hwnd, 0, 0, w, h, True)
        except Exception:
            pass
        self.course_wv2_hwnd = int(hwnd)
        self.course_wv2_window = getattr(self, "course_wv2_window_raw", None)
        self.course_wv2_starting = False
        # 内嵌窗口创建后立即按 host 尺寸对齐 + 隐藏提示
        try:
            if getattr(self, "course_edge_hint", None) is not None:
                self.course_edge_hint.setVisible(False)
        except Exception:
            pass
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(150, self._course_wv2_resize_to_host)
        except Exception:
            pass
        # 周期性对齐 (WinForms 初次 Show 有时会改尺寸)
        self._course_wv2_realign_tick = 0
        try:
            self._course_wv2_realign_timer = QTimer(self)
            self._course_wv2_realign_timer.setInterval(250)
            self._course_wv2_realign_timer.timeout.connect(self._course_wv2_realign_poll)
            self._course_wv2_realign_timer.start()
        except Exception:
            pass
        # 把子 HWND 也缓存下来 (后续最大化全屏 MoveWindow 会用到)
        try:
            self._course_wv2_child_hwnd = self._course_wv2_find_child_hwnd()
        except Exception:
            pass

    def _course_wv2_realign_poll(self) -> None:
        """首 3 秒做几次尺寸对齐，之后如果在放大态也跟着重算"""
        try:
            self._course_wv2_realign_tick = int(getattr(self, "_course_wv2_realign_tick", 0)) + 1
            need = False
            if self._course_wv2_realign_tick <= 12:
                need = True
            if getattr(self, "_course_maximized", False):
                need = True
            if getattr(self, "_course_pop_win", None) is not None:
                need = False
            if need:
                if getattr(self, "course_wv2_window", None) is not None:
                    self._course_wv2_resize_to_host()
            if self._course_wv2_realign_tick > 20 and not getattr(self, "_course_maximized", False):
                try:
                    if hasattr(self, "_course_wv2_realign_timer") and self._course_wv2_realign_timer is not None:
                        self._course_wv2_realign_timer.stop()
                except Exception:
                    pass
        except Exception:
            pass

    def _course_wv2_resize_to_host(self) -> None:
        """对 WebView2：调用 window.resize 对齐 host；对放大态：覆盖整个卡片矩形"""
        try:
            w = getattr(self, "course_wv2_window", None)
            if w is None:
                return
            host = getattr(self, "course_edge_host", None)
            if self._course_maximized:
                box = getattr(self, "_course_max_box", None)
                if box is None:
                    return
                content_rect = box.rect()
                width = max(200, int(content_rect.width() - 12 - 12))
                height = max(160, int(content_rect.height() - 30 - 12 - 36))
            elif host is not None:
                width = max(200, int(host.width()))
                height = max(160, int(host.height()))
            else:
                return
            try:
                w.resize(width, height)
            except Exception:
                pass
        except Exception:
            pass

    def _course_wv2_load(self, url: str) -> None:
        w = getattr(self, "course_wv2_window", None)
        if w is None:
            return
        try:
            w.load_url(url)
        except Exception:
            try:
                w.evaluate_js(f"location.href = {url!r};")
            except Exception:
                pass

    def _course_wv2_back(self):
        w = getattr(self, "course_wv2_window", None)
        if w is None: return
        try: w.evaluate_js("history.back();")
        except Exception: pass

    def _course_wv2_forward(self):
        w = getattr(self, "course_wv2_window", None)
        if w is None: return
        try: w.evaluate_js("history.forward();")
        except Exception: pass

    def _course_wv2_refresh(self):
        w = getattr(self, "course_wv2_window", None)
        if w is None: return
        try: w.evaluate_js("location.reload(true);")
        except Exception: pass

    def _course_wv2_get_url(self) -> Optional[str]:
        w = getattr(self, "course_wv2_window", None)
        if w is None: return None
        try:
            return str(w.get_current_url())
        except Exception:
            try:
                return str(w.evaluate_js("location.href;") or "") or None
            except Exception:
                return None

    def _course_wv2_kill(self) -> None:
        try:
            t = getattr(self, "_course_wv2_realign_timer", None)
            if t is not None:
                try: t.stop()
                except Exception: pass
        except Exception:
            pass
        w = getattr(self, "course_wv2_window", None)
        if w is None:
            return
        try:
            try:
                w.destroy()
            except Exception:
                pass
        except Exception:
            pass
        self.course_wv2_window = None
        try:
            if getattr(self, "course_edge_hint", None) is not None:
                self.course_edge_hint.setVisible(True)
        except Exception:
            pass

    def _course_wv2_restart(self) -> None:
        url = getattr(self, "course_edge_url", "") or self._course_default_home()
        self._course_wv2_kill()
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(400, lambda: self._course_wv2_ensure(silent=False) or self._course_edge_ensure(silent=False))
        except Exception:
            pass

    def _course_wv2_restart_or_edge_restart(self) -> None:
        """工具栏 ♻️重启 按钮：当前是什么内核就重启什么；都没启动就尝试 WebView2 优先，失败 Edge 兜底"""
        if getattr(self, "course_wv2_window", None) is not None or getattr(self, "course_wv2_starting", False):
            self._course_wv2_restart()
            return
        if int(getattr(self, "course_edge_hwnd", 0) or 0) or getattr(self, "course_edge_starting", False):
            self._course_edge_restart()
            return
        # 都没启动
        if not self._course_wv2_ensure(silent=False):
            self._course_edge_ensure(silent=False)

    # ==================== 视频纯净模式 (把页面 <video> 提取出来单独放大填满整个卡片) ====================
    def _course_toggle_pure_video_mode(self) -> None:
        """🎬 视频纯净模式: CDP/JS 注入查找 <video> -> 创建黑底 overlay 把视频单独提出来, 铺满整个浏览器区域 (Edge/WebView2 都支持)。"""
        # 已在纯净模式 -> 还原
        if bool(getattr(self, "_course_pure_video_on", False)):
            self._course_pure_video_restore()
            return
        # 检查浏览器是否已启动 (三种"可用"：真内嵌 WebView2 / Edge HWND 已嵌入 / Edge CDP 已连通)
        wv2_exists = bool(getattr(self, "course_wv2_window", None))
        edge_exists = bool(int(getattr(self, "course_edge_hwnd", 0) or 0))
        edge_starting = bool(getattr(self, "course_edge_starting", False))
        cdp_ready = bool(getattr(self, "_course_cdp_ws_url", ""))
        # 最后兜底：只要 CDP ensure 能立即连上，也算就绪
        if not wv2_exists and not edge_exists and not edge_starting and not cdp_ready:
            try:
                cdp_ready = bool(self._course_cdp_ensure(timeout_s=3.0))
            except Exception:
                cdp_ready = False
        if not wv2_exists and not edge_exists and not edge_starting and not cdp_ready:
            try:
                QMessageBox.information(
                    self, "🎬 请先启动浏览器",
                    "视频纯净模式需要先把浏览器启动起来并加载完页面。\n\n"
                    "👉 先点工具栏「🧩启动浏览器」或者切页让它自动启动，等视频画面出来了再点这个按钮。"
                )
            except Exception:
                pass
            return
        # 注入 JS
        js = r'''
(function () {
    const OVERLAY_ID = "__kaoyan_pure_video_overlay__";
    if (document.getElementById(OVERLAY_ID)) {
        return { ok: false, reason: "already_on" };
    }
    // 找 video: 优先正在播放的, 其次 readyState>=2(有数据) 的, 其次第一个存在的
    const vs = Array.from(document.querySelectorAll("video"));
    if (!vs.length) return { ok: false, reason: "no_video" };
    let pick = vs.find(v => v && !v.paused && !v.ended && v.readyState >= 2)
             || vs.find(v => v && v.readyState >= 2)
             || vs[0];
    if (!pick) return { ok: false, reason: "no_video_ready" };
    // 记住原来的上下文 (方便还原)
    pick.__kaoyan_restore = {
        parentNode: pick.parentNode,
        nextSibling: pick.nextSibling,
        style: pick.getAttribute("style"),
        cssText: pick.style ? pick.style.cssText : "",
        className: pick.getAttribute("class"),
        controls: pick.hasAttribute("controls"),
        playsinline: pick.hasAttribute("playsinline"),
    };
    // 造一个黑色 fullscreen fixed overlay (z-index 拉满覆盖整页)
    const div = document.createElement("div");
    div.id = OVERLAY_ID;
    div.style.cssText = "position:fixed;inset:0;width:100%;height:100%;background:#000;z-index:2147483647;";
    div.setAttribute("data-kaoyan", "pure-video-overlay");
    // 插入 body 顶部 (避免被框架 overflow:hidden 裁剪)
    const host = document.body || document.documentElement;
    host.appendChild(div);
    // 把 video 搬进去, 并铺满整个 overlay
    div.appendChild(pick);
    const fit = window.__kaoyan_video_fit === "cover" ? "cover" : "contain";
    pick.setAttribute("playsinline", "");
    pick.setAttribute("webkit-playsinline", "");
    pick.style.cssText =
        "position:absolute;inset:0;width:100%!important;height:100%!important;max-width:100%!important;max-height:100%!important;"+
        "min-width:0!important;min-height:0!important;object-fit:" + fit + ";background:#000;border:0;margin:0;padding:0;outline:none;display:block;";
    try { pick.requestPointerLock = pick.requestPointerLock; } catch (e) {}
    // 页面内 ESC 还原: 绑定 keydown 一次
    window.__kaoyan_pure_video_on = true;
    if (!window.__kaoyan_pure_video_bound) {
        window.addEventListener("keydown", function (e) {
            if (!window.__kaoyan_pure_video_on) return;
            if (e.key === "Escape" || e.keyCode === 27) {
                window.__kaoyan_restore_pure_video && window.__kaoyan_restore_pure_video();
            }
        }, true);
        window.__kaoyan_pure_video_bound = true;
    }
    window.__kaoyan_restore_pure_video = function () {
        const d = document.getElementById(OVERLAY_ID);
        if (!d || !d.firstElementChild) {
            window.__kaoyan_pure_video_on = false;
            return { ok: true };
        }
        const v = d.firstElementChild;
        const ctx = v.__kaoyan_restore;
        if (ctx) {
            try {
                if (ctx.parentNode) {
                    if (ctx.nextSibling) ctx.parentNode.insertBefore(v, ctx.nextSibling);
                    else ctx.parentNode.appendChild(v);
                }
                if (ctx.style === null) v.removeAttribute("style");
                else if (typeof ctx.style === "string") v.setAttribute("style", ctx.style);
                else if (v.style && typeof ctx.cssText === "string") v.style.cssText = ctx.cssText;
                if (ctx.className === null) v.removeAttribute("class");
                else if (typeof ctx.className === "string") v.setAttribute("class", ctx.className);
                if (ctx.controls) v.setAttribute("controls", "");
                else v.removeAttribute("controls");
                if (ctx.playsinline) v.setAttribute("playsinline", "");
            } catch (err) {
                // 父节点被销毁了也别炸: 至少把 video 还回 body
                try { (document.body || document.documentElement).appendChild(v); } catch (_) {}
            }
        }
        try { d.parentNode && d.parentNode.removeChild(d); } catch (_) {}
        window.__kaoyan_pure_video_on = false;
        return { ok: true };
    };
    try {
        // 立即 play 一下防止被搬到 overlay 就暂停
        if (pick.paused) { const p = pick.play(); if (p && p.catch) p.catch(()=>{}); }
    } catch (e) {}
    return { ok: true, fit: fit };
})();
        '''
        try:
            raw = self._course_eval_js_in_browser(js) or {}
        except Exception as e:
            try:
                QMessageBox.warning(self, "视频纯净模式失败", f"JS 注入异常：{e}")
            except Exception:
                pass
            return
        ok = bool(raw and raw.get("ok"))
        reason = "" if not raw else (raw.get("reason") or "")
        if not ok:
            if reason == "no_video" or reason == "no_video_ready":
                try:
                    QMessageBox.information(
                        self, "当前页面没找到可播放的视频",
                        "🎬 视频纯净模式需要页面里已经有一个 <video> 播放器。\n\n"
                        "👉 打开一个 B 站视频页，让视频开始播放一次（哪怕暂停也行，只要画面加载出来），再按这个按钮。\n"
                        "   还没进视频播放页（比如 B 站首页/搜索页）是找不到 video 的。"
                    )
                except Exception:
                    pass
                return
            if reason == "already_on":
                self._course_pure_video_restore()
                return
            try:
                QMessageBox.warning(self, "视频纯净模式失败", f"JS 返回未知错误：{raw!r}")
            except Exception:
                pass
            return
        # 成功进入纯净模式 -> 记住状态 + 按钮变还原
        self._course_pure_video_on = True
        self.course_btn_pure_video.setText("📺 还原页面")
        self.course_btn_pure_video.setToolTip("当前是纯净视频模式，再点一次还原完整网页 (ESC 也可还原)")
        # ESC 快捷键还原（Qt 侧）
        try:
            from PyQt5.QtGui import QKeySequence
            from PyQt5.QtWidgets import QShortcut
            self._course_pure_video_shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
            self._course_pure_video_shortcut_esc.activated.connect(self._course_pure_video_restore)
        except Exception:
            pass
        # 刷新填充按钮显示
        self._course_refresh_video_fit_label()
        # 触发一次 ⛶ 放大（可选，用户体验更好：单独放大后就是整卡纯视频）
        try:
            if not self._course_maximized:
                self._course_toggle_maximize_in_card()
        except Exception:
            pass

    def _course_refresh_video_fit_label(self) -> None:
        if not hasattr(self, "course_btn_video_fit"):
            return
        cover = bool(getattr(self, "course_btn_video_fit", None) and self.course_btn_video_fit.isChecked())
        if cover:
            self.course_btn_video_fit.setText("🔲 铺满裁剪")
        else:
            self.course_btn_video_fit.setText("🔲 等比完整")

    def _course_toggle_video_fit_mode(self) -> None:
        """🔲 填充模式: contain ↔ cover，纯净模式下热切换 (实时 apply object-fit)。Edge CDP / WebView2 都支持。"""
        self._course_refresh_video_fit_label()
        cover = bool(self.course_btn_video_fit.isChecked())
        new_fit = "cover" if cover else "contain"
        if not bool(getattr(self, "_course_pure_video_on", False)):
            return
        js_set_fit = r'''
(function(){
    const fit = ''' + repr(new_fit) + r''';
    window.__kaoyan_video_fit = fit;
    const d = document.getElementById("__kaoyan_pure_video_overlay__");
    if (!d) return { ok: false };
    const v = d.querySelector("video");
    if (!v) return { ok: false };
    v.style.objectFit = fit;
    return { ok: true, fit: fit };
})();
        '''
        try:
            self._course_eval_js_in_browser(js_set_fit)
        except Exception:
            pass

    def _course_pure_video_restore(self) -> None:
        """从纯净模式回到完整页面: JS 还原 + 同步按钮/快捷键/放大状态。Edge CDP / WebView2 都支持。"""
        if bool(getattr(self, "_course_pure_video_on", False)):
            try:
                self._course_eval_js_in_browser(
                    "(window.__kaoyan_restore_pure_video && window.__kaoyan_restore_pure_video()) || {ok:true};"
                )
            except Exception:
                pass
        self._course_pure_video_on = False
        try:
            if getattr(self, "course_btn_pure_video", None) is not None:
                self.course_btn_pure_video.setText("🎬 视频纯净模式")
                self.course_btn_pure_video.setToolTip(
                    "把当前页面里正在播放的视频单独提取出来，黑底放大填满整个卡片区域，\n"
                    "不显示推荐/弹幕/评论等杂项。再点一次或按 ESC 可以还原。"
                )
        except Exception:
            pass
        try:
            if getattr(self, "_course_pure_video_shortcut_esc", None) is not None:
                self._course_pure_video_shortcut_esc.setParent(None)
        except Exception:
            pass
        self._course_pure_video_shortcut_esc = None
        # 如果当前是因为进入纯净模式自动放大的，还原时把放大也一起退了
        try:
            if self._course_maximized:
                self._course_toggle_maximize_in_card()
        except Exception:
            pass

    # ===== 旧 Edge --app 外置模式保留作回退 (只有 WebView2 初始化失败时才会走) =====
    def _course_edge_find_exe(self) -> Optional[str]:
        candidates_exe = ["msedge.exe", "chrome.exe", "brave.exe", "vivaldi.exe"]
        try:
            import winreg
            for exe in candidates_exe:
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + exe,
                        0, winreg.KEY_READ,
                    )
                    try:
                        val, _typ = winreg.QueryValueEx(key, None)
                        if val and str(val).strip():
                            return str(val).strip('"').strip()
                    finally:
                        winreg.CloseKey(key)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        except Exception:
            pass
        import os as _os
        prog_x86 = _os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
        prog = _os.environ.get("ProgramFiles") or r"C:\Program Files"
        local_app = _os.environ.get("LOCALAPPDATA") or _os.path.expandvars(r"%LOCALAPPDATA%")
        search_templates = [
            _os.path.join(prog, r"Microsoft\Edge\Application\msedge.exe"),
            _os.path.join(prog_x86, r"Microsoft\Edge\Application\msedge.exe"),
            _os.path.join(local_app, r"Microsoft\Edge\Application\msedge.exe"),
            _os.path.join(prog_x86, r"Google\Chrome\Application\chrome.exe"),
            _os.path.join(prog, r"Google\Chrome\Application\chrome.exe"),
            _os.path.join(local_app, r"Google\Chrome\Application\chrome.exe"),
            _os.path.join(prog_x86, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
            _os.path.join(local_app, r"Vivaldi\Application\vivaldi.exe"),
        ]
        for pth in search_templates:
            try:
                if pth and _os.path.isfile(pth):
                    return pth
            except Exception:
                pass
        try:
            import shutil as _shutil
            for exe in candidates_exe:
                w = _shutil.which(exe)
                if w: return str(w)
        except Exception:
            pass
        return None

    def _course_edge_restart(self) -> None:
        self._course_edge_kill(kill_proc=True)
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, lambda: self._course_edge_ensure(silent=False))
        except Exception:
            pass

    def _course_edge_kill(self, kill_proc: bool = True) -> None:
        try:
            if getattr(self, "course_edge_hint", None) is not None:
                try: self.course_edge_hint.setVisible(True)
                except Exception: pass
        except Exception:
            pass
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                try: user32.SetParent(hwnd, 0)
                except Exception: pass
                try:
                    if int(getattr(self, "course_edge_original_style", 0) or 0):
                        user32.SetWindowLongW(hwnd, -16, int(self.course_edge_original_style))
                    if int(getattr(self, "course_edge_original_exstyle", 0) or 0):
                        user32.SetWindowLongW(hwnd, -20, int(self.course_edge_original_exstyle))
                except Exception: pass
                try: user32.SendMessageW(hwnd, 0x0010, 0, 0)
                except Exception: pass
            except Exception:
                pass
            self.course_edge_hwnd = 0
            self.course_edge_original_parent = 0
        proc = getattr(self, "course_edge_proc", None)
        if kill_proc and proc is not None:
            try:
                if getattr(proc, "poll", lambda: None)() is None:
                    try: proc.terminate()
                    except Exception: pass
                    import time as _t
                    for _ in range(20):
                        if proc.poll() is not None: break
                        _t.sleep(0.05)
                    try:
                        if proc.poll() is None: proc.kill()
                    except Exception: pass
            except Exception:
                pass
        self.course_edge_proc = None
        self.course_edge_starting = False

    def _course_edge_ensure(self, silent: bool = False) -> bool:
        # ---------- 关键：必须「hwnd 存在 + proc 活着 + CDP 端口已分配」才算 ready ----------
        #   否则会出现 HWND 是上次探针残留、但当前 proc/cdp/port 都未初始化的假象
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        proc = getattr(self, "course_edge_proc", None)
        port = int(getattr(self, "course_edge_cdp_port", 0) or 0)
        proc_alive = (proc is not None and proc.poll() is None)
        if hwnd and proc_alive and port:
            return True
        if getattr(self, "course_edge_starting", False):
            return True
        # 如果有残留 HWND（proc 死了 / port 没了），先清掉旧标记，避免 hwnd 挡住重新启动
        if hwnd and (not proc_alive or not port):
            self.course_edge_hwnd = 0
        exe = self._course_edge_find_exe()
        if not exe:
            if not silent:
                try:
                    QMessageBox.warning(
                        self, "找不到 Edge / Chrome 浏览器",
                        "没在你系统里检测到 Microsoft Edge、Chrome、Brave、Vivaldi 任一浏览器。\n\n"
                        "👉 解决办法（任选其一）：\n"
                        "   1. 打开桌面上蓝绿色的 Microsoft Edge 图标一次\n"
                        "   2. 或安装 Microsoft Edge: https://www.microsoft.com/edge"
                    )
                except Exception:
                    pass
            return False
        self.course_edge_exe_path = exe
        start_url = getattr(self, "course_edge_url", "") or self._course_default_home()
        self.course_edge_url = start_url
        try:
            profile_dir = str(Path(__file__).resolve().parent / "image" / "edge_app_profile")
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            profile_dir = None
        # ---- 选一个可用的 CDP 调试端口 (9222~9320) ----
        port = self._course_edge_pick_free_port(9222, 9320)
        self.course_edge_cdp_port = port
        args = [exe]
        args.append("--app=" + str(start_url))
        args.append("--window-position=60,60")
        args.append("--window-size=900,600")
        if profile_dir:
            args.append("--user-data-dir=" + str(profile_dir))
        args.append("--no-default-browser-check")
        args.append("--no-first-run")
        args.append("--disable-features=RendererCodeIntegrity")
        args.append(f"--remote-debugging-port={port}")
        args.append("--remote-allow-origins=*")
        args.append("--disable-background-timer-throttling")
        args.append("--disable-renderer-backgrounding")
        import subprocess as _sp
        try:
            import os as _os
            si = _sp.STARTUPINFO()
            si.dwFlags = _sp.STARTF_USESHOWWINDOW
            proc = _sp.Popen(
                args, cwd=_os.path.dirname(exe) or None, shell=False, startupinfo=si,
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, stdin=_sp.DEVNULL,
            )
            self.course_edge_proc = proc
            self.course_edge_starting = True
        except Exception as e:
            if not silent:
                try: QMessageBox.warning(self, "Edge 启动失败", f"无法启动浏览器 {exe}:\n\n{e}")
                except Exception: pass
            self.course_edge_starting = False
            return False
        self._course_edge_poll_ticks = 0
        self._course_edge_poll_pid = int(proc.pid)
        try:
            from PyQt5.QtCore import QTimer
            self._course_edge_find_timer = QTimer(self)
            self._course_edge_find_timer.setInterval(100)
            self._course_edge_find_timer.timeout.connect(self._course_edge_find_hwnd_poll)
            self._course_edge_find_timer.start()
        except Exception:
            pass
        return True

    @staticmethod
    def _course_edge_pick_free_port(start: int, end: int) -> int:
        import socket
        for p in range(start, end + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                s.close()
                return p
            except Exception:
                continue
        return start  # 实在都占满就返回 start 让用户自行处理

    # ==================== Edge CDP (Chrome DevTools Protocol) —— 给外置 Edge 提供 JS 注入能力 ====================
    def _course_cdp_ensure(self, timeout_s: float = 40.0) -> bool:
        """拿到 Edge CDP 连接。返回 True 表示可调用 _course_cdp_eval；失败不会抛错，只返回 False。"""
        if getattr(self, "_course_cdp_ws_url", "") and getattr(self, "_course_cdp_target_id", ""):
            return True
        port = int(getattr(self, "course_edge_cdp_port", 0) or 0)
        if not port:
            return False
        import json, time, threading
        try:
            from urllib.request import urlopen
        except Exception:
            return False
        deadline = time.time() + timeout_s
        last_err = ""
        while time.time() < deadline:
            if int(getattr(self, "course_edge_hwnd", 0) or 0) == 0 and not getattr(self, "course_edge_starting", False):
                return False
            try:
                with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2.5) as resp:
                    targets = json.loads(resp.read().decode("utf-8", "ignore") or "[]")
                pages = [t for t in targets if isinstance(t, dict) and str(t.get("type", "")).lower() == "page"]
                if not pages:
                    last_err = "no page target"
                    time.sleep(0.25)
                    continue
                # 优先: 当前 host widget 内正在显示的那个 tab -> 取第一个 page 型 target (因为我们只开了 --app=url, 只有一个)
                target = pages[0]
                ws_url = str(target.get("webSocketDebuggerUrl") or "")
                tid = str(target.get("id") or "")
                if not ws_url or not tid:
                    last_err = "no ws url"
                    time.sleep(0.25)
                    continue
                self._course_cdp_ws_url = ws_url
                self._course_cdp_target_id = tid
                return True
            except Exception as e:
                last_err = repr(e)
                time.sleep(0.3)
        return False

    def _course_cdp_eval(self, expression: str, retries: int = 3):
        """Edge CDP 版 evaluate_js。语义尽量贴近 pywebview Window.evaluate_js: 返回 JS 对象/基本类型, 失败返回 None 或抛异常。"""
        if not getattr(self, "_course_cdp_ws_url", ""):
            if not self._course_cdp_ensure():
                raise RuntimeError("无法连接 Edge CDP (请先启动 Edge 并等嵌入成功)")
        ws_url = str(self._course_cdp_ws_url)
        tid = str(getattr(self, "_course_cdp_target_id", "") or "")
        exp_str = str(expression)
        # 让每个调用独立占一个 lock + 唯一 id，避免并发 eval 时 response 对不上号
        lock = getattr(self, "_course_cdp_lock", None)
        if lock is None:
            import threading as _thr
            lock = _thr.Lock()
            self._course_cdp_lock = lock
        import json, time
        try:
            import websocket  # pip install websocket-client
        except Exception:
            try:
                import pip._internal  # noqa: F401
            except Exception:
                pass
            # 给个最友好的提示: 尝试在子线程 pip 装
            try:
                import subprocess as _sp, sys as _sys
                _sp.run([_sys.executable, "-m", "pip", "install", "websocket-client",
                         "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                        check=False, timeout=120, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                import websocket  # type: ignore
            except Exception as e2:
                raise RuntimeError(
                    "缺少 websocket-client 且自动安装失败, 请手动执行:\n"
                    "  pip install websocket-client\n\n"
                    f"原始错误: {e2!r}"
                )
        last_err = None
        for attempt in range(max(1, int(retries))):
            try:
                with lock:
                    ws = websocket.create_connection(ws_url, timeout=15, enable_multithread=True)
                    try:
                        cid = getattr(self, "_course_cdp_seq", 1000) + 1
                        self._course_cdp_seq = cid
                        msg = {
                            "id": cid,
                            "method": "Runtime.evaluate",
                            "params": {
                                "expression": exp_str,
                                "objectGroup": "kaoyan",
                                "includeCommandLineAPI": True,
                                "silent": False,
                                "returnByValue": True,
                                "generatePreview": False,
                                "userGesture": True,
                                "awaitPromise": True,
                            },
                        }
                        # 注意：/json/list 里每个 page target 自带的 webSocketDebuggerUrl
                        #       就是直连该 page 的 WS 地址（形如 ws://127.0.0.1:{port}/devtools/page/<id>），
                        #       直接发 Runtime.evaluate 即可，顶层不允许加 targetId 等额外字段，
                        #       否则 CDP 服务会报错 "Message has property other than id/method/sessionId/params"。
                        ws.send(json.dumps(msg, ensure_ascii=False))
                        # CDP 消息分两层: 如果我们连的是 browser 端点, 那会被包装成 Target.targetCreated / 收到 Target.receivedMessageFromTarget
                        # 保险起见: 循环读若干条直到找到 {"id": cid} 或带 Target.* 包装
                        raw_text = None
                        t0 = time.time()
                        while time.time() - t0 < 12:
                            try:
                                chunk = ws.recv()
                            except Exception:
                                break
                            if not chunk or not isinstance(chunk, str):
                                continue
                            try:
                                obj = json.loads(chunk)
                            except Exception:
                                continue
                            # 情况 A: 直接连 page target -> {id:..., result:...}
                            if isinstance(obj, dict) and int(obj.get("id", -1)) == int(cid):
                                raw_text = chunk
                                break
                            # 情况 B: 连 browser 端点 + 带 targetId -> 包装在 Target.receivedMessageFromTarget
                            if isinstance(obj, dict) and obj.get("method") == "Target.receivedMessageFromTarget":
                                inner_s = str((obj.get("params") or {}).get("message") or "")
                                try:
                                    inner_obj = json.loads(inner_s)
                                except Exception:
                                    inner_obj = None
                                if isinstance(inner_obj, dict) and int(inner_obj.get("id", -1)) == int(cid):
                                    raw_text = inner_s
                                    break
                        if raw_text is None:
                            raise RuntimeError("CDP timeout: 未收到 Runtime.evaluate 响应")
                        resp = json.loads(raw_text)
                        err = resp.get("error")
                        if err:
                            raise RuntimeError(f"CDP error: {err!r}")
                        result = resp.get("result") or {}
                        exception = result.get("exceptionDetails")
                        if exception:
                            # 抛一下包含异常文字, 但不中断整个外部流程
                            txt = ""
                            try:
                                txt = str(exception.get("text") or "")
                                ex = exception.get("exception") or {}
                                val = ex.get("value") or ex.get("description") or ""
                                if val: txt += " | " + str(val)
                            except Exception:
                                pass
                            raise RuntimeError(f"JS runtime exception: {txt[:500]}")
                        remote = result.get("result") or {}
                        subtype = str(remote.get("subtype") or "")
                        vtype = str(remote.get("type") or "")
                        value = remote.get("value")
                        # undefined -> None
                        if vtype == "undefined":
                            return None
                        if value is not None or (remote.get("value") is None and vtype in ("boolean", "number", "string", "object")):
                            # null: remote.value 就是 Python None, 允许
                            return value
                        # 大对象走了 objectId, 但我们 returnByValue=True 理论不会走到这里, 兜底用 preview 或 description
                        return remote.get("description") or remote.get("className") or None
                    finally:
                        try: ws.close()
                        except Exception: pass
            except Exception as e:
                last_err = e
                # 连接失效时清空 ws_url，下次会自动重新连 /json/list 重取
                if ("ConnectionRefusedError" in repr(e) or "BadStatusLine" in repr(e)
                        or "WebSocketConnectionClosedException" in type(e).__name__
                        or (isinstance(e, RuntimeError) and "timeout" in repr(e).lower())):
                    try:
                        self._course_cdp_ws_url = ""
                        self._course_cdp_target_id = ""
                    except Exception:
                        pass
                if attempt + 1 < retries:
                    time.sleep(0.5 + 0.4 * attempt)
                    self._course_cdp_ensure(timeout_s=6.0)
                    continue
                break
        if last_err is not None:
            raise last_err
        return None

    # ==================== 统一 JS 注入入口（始终走 Edge CDP） ====================
    def _course_eval_js_in_browser(self, expression: str, timeout_ms: int = 8000):
        """统一 JS 注入入口: 优先 PyQtWebEngine runJavaScript, 回退 Edge CDP。"""
        # 路径 1: PyQtWebEngine (真嵌入, 同步返回)
        if self.course_webview is not None and getattr(self, "course_webview_loaded", False):
            return self._course_webview_eval_js(expression, timeout_ms)
        # 路径 2: Edge CDP (fallback)
        return self._course_cdp_eval(expression)

    def _course_webview_eval_js(self, expression: str, timeout_ms: int = 8000):
        """用 QWebEnginePage.runJavaScript 同步执行 JS, 返回 JS 对象。"""
        if self.course_webview is None:
            return None
        page = self.course_webview.page()
        if page is None:
            return None
        import json
        from PyQt5.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        result_holder = {"value": None, "done": False}

        def _cb(result):
            result_holder["value"] = result
            result_holder["done"] = True
            try: loop.quit()
            except Exception: pass

        try:
            # QWebEnginePage.runJavaScript 返回的是 JS 执行结果的字符串/对象
            page.runJavaScript(expression, _cb)
        except Exception:
            # 某些 PyQt5 版本的 runJavaScript 不支持回调, 改用带 worldId 的版本
            try:
                page.runJavaScript(expression, 0, _cb)
            except Exception as e:
                return None

        # 等待结果 (带超时)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        try:
            loop.exec_()
        except Exception:
            pass
        try: timer.stop()
        except Exception: pass
        if not result_holder["done"]:
            return None
        # 解析结果
        val = result_holder["value"]
        if val is None:
            return None
        # runJavaScript 返回的是 JS 对象的 repr, 尝试解析
        if isinstance(val, str):
            s = val.strip()
            if s == "undefined" or s == "null":
                return None
            if s == "true":
                return True
            if s == "false":
                return False
            try:
                return json.loads(s)
            except Exception:
                pass
            return val
        return val

    def _course_edge_find_hwnd_poll(self) -> None:
        self._course_edge_poll_ticks = int(getattr(self, "_course_edge_poll_ticks", 0)) + 1
        if self._course_edge_poll_ticks > 250:
            try:
                if hasattr(self, "_course_edge_find_timer"):
                    self._course_edge_find_timer.stop()
            except Exception:
                pass
            self.course_edge_starting = False
            try:
                if getattr(self, "course_edge_hint", None) is not None:
                    self.course_edge_hint.setText(
                        "❌ 启动 Edge 超时 (25s 没找到浏览器窗口)\n\n"
                        "点 “♻️重启Edge” 或在任务管理器里把 msedge.exe 结束再试。"
                    )
            except Exception:
                pass
            return
        try:
            import ctypes
            from ctypes import wintypes as _wt
            user32 = ctypes.windll.user32
            target_pid = int(getattr(self, "_course_edge_poll_pid", 0) or 0)
            # ---- 构建"我们自己这棵 msedge 进程树"的 pid 集合：target_pid + 所有后代 pid ----
            # Chromium 多进程架构：Popen 返回的是浏览器主进程 pid，但 Chrome_WidgetWin 窗口
            # 经常属于它 fork 出的某个 renderer/browser UI 子进程。所以必须把它所有
            # 子孙进程的 pid 也算进"目标家族"，避免 EnumWindows 时只匹配父 pid 漏掉窗口。
            family_pids = set([int(target_pid)]) if target_pid else set()
            try:
                import ctypes as _ct
                from ctypes import wintypes as _wt2
                TH32CS_SNAPPROCESS = 0x00000002
                kernel32 = _ct.windll.kernel32
                MAX_PATH = 260
                class _PE32(_ct.Structure):
                    _fields_ = [
                        ("dwSize", _wt2.DWORD), ("cntUsage", _wt2.DWORD),
                        ("th32ProcessID", _wt2.DWORD), ("th32DefaultHeapID", _ct.POINTER(_wt2.ULONG)),
                        ("th32ModuleID", _wt2.DWORD), ("cntThreads", _wt2.DWORD),
                        ("th32ParentProcessID", _wt2.DWORD), ("pcPriClassBase", _ct.c_long),
                        ("dwFlags", _wt2.DWORD), ("szExeFile", _ct.c_wchar * MAX_PATH),
                    ]
                snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
                if int(snap) not in (-1, None, 0xFFFFFFFF):
                    try:
                        pe = _PE32(); pe.dwSize = _ct.sizeof(_PE32)
                        entries = []
                        ok = kernel32.Process32FirstW(snap, _ct.byref(pe))
                        while ok:
                            entries.append((int(pe.th32ProcessID), int(pe.th32ParentProcessID), str(pe.szExeFile).lower()))
                            ok = kernel32.Process32NextW(snap, _ct.byref(pe))
                        # 最多扩展 8 层，避免极端情况死循环
                        for _ in range(8):
                            before = len(family_pids)
                            for (cpid, ppid, _n) in entries:
                                if ppid in family_pids:
                                    family_pids.add(int(cpid))
                            if len(family_pids) == before:
                                break
                    finally:
                        try: kernel32.CloseHandle(snap)
                        except Exception: pass
            except Exception:
                pass
            found_ctx = []
            @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
            def _enum(hwnd, _lparam):
                try:
                    if not user32.IsWindowVisible(hwnd): return True
                except Exception: return True
                try:
                    cls_buf = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(hwnd, cls_buf, 127)
                    cls = str(cls_buf.value or "")
                except Exception:
                    cls = ""
                if "Chrome_WidgetWin_1" not in cls and "Chrome_WidgetWin_0" not in cls:
                    return True
                try:
                    _pid_out = _wt.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(_pid_out))
                    wpid = int(_pid_out.value or 0)
                except Exception:
                    wpid = 0
                if wpid <= 0: return True
                matched = False
                # 1) 最优先: 主 pid 或它的任何子孙 pid (整棵 msedge 进程树)
                if wpid in family_pids:
                    matched = True
                if not matched and wpid == target_pid:
                    matched = True
                if not matched:
                    # 2) 兜底: 同类型 exe 的无主窗口 (如果没有任何别的 Edge 同时在跑就不会误命中)
                    try:
                        pname = (self._course_edge_get_process_name(wpid) or "").lower()
                        if pname in ("msedge.exe", "chrome.exe", "brave.exe", "vivaldi.exe"):
                            parent = int(user32.GetParent(hwnd) or 0)
                            if parent == 0:
                                owner = int(user32.GetWindow(hwnd, 4) or 0)
                                if owner == 0: matched = True
                    except Exception:
                        matched = False
                if matched:
                    found_ctx.append(int(hwnd))
                    return False
                return True
            try: user32.EnumWindows(_enum, 0)
            except Exception: pass
            if not found_ctx: return
            hwnd = int(found_ctx[0])
            try: self._course_edge_find_timer.stop()
            except Exception: pass
            self._course_edge_embed_hwnd(hwnd)
        except Exception:
            return

    def _course_edge_get_process_name(self, pid: int) -> Optional[str]:
        try:
            import ctypes
            from ctypes import wintypes as _wt
            TH32CS_SNAPPROCESS = 0x00000002
            kernel32 = ctypes.windll.kernel32
            MAX_PATH = 260
            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ("dwSize", _wt.DWORD), ("cntUsage", _wt.DWORD),
                    ("th32ProcessID", _wt.DWORD), ("th32DefaultHeapID", ctypes.POINTER(_wt.ULONG)),
                    ("th32ModuleID", _wt.DWORD), ("cntThreads", _wt.DWORD),
                    ("th32ParentProcessID", _wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", _wt.DWORD), ("szExeFile", ctypes.c_wchar * MAX_PATH),
                ]
            snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if int(snap) in (-1, None, 0xFFFFFFFF): return None
            try:
                pe = PROCESSENTRY32()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
                ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
                while ok:
                    if int(pe.th32ProcessID) == int(pid): return str(pe.szExeFile)
                    ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
                return None
            finally:
                try: kernel32.CloseHandle(snap)
                except Exception: pass
        except Exception:
            return None

    def _course_edge_embed_hwnd(self, hwnd: int) -> None:
        if hwnd <= 0 or getattr(self, "course_edge_host", None) is None: return
        import ctypes
        user32 = ctypes.windll.user32
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_CAPTION=0x00C00000; WS_THICKFRAME=0x00040000; WS_SYSMENU=0x00080000
        WS_MINIMIZEBOX=0x00020000; WS_MAXIMIZEBOX=0x00010000; WS_POPUP=0x80000000
        WS_CHILD=0x40000000; WS_VISIBLE=0x10000000
        WS_CLIPSIBLINGS=0x04000000; WS_CLIPCHILDREN=0x02000000
        host = self.course_edge_host
        try: host.createWinId()
        except Exception: pass
        try: host_hwnd = int(host.winId())
        except Exception: host_hwnd = 0
        if not host_hwnd: return
        try:
            self.course_edge_original_style = int(user32.GetWindowLongW(hwnd, GWL_STYLE) or 0)
            self.course_edge_original_exstyle = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) or 0)
            self.course_edge_original_parent = int(user32.GetParent(hwnd) or 0)
        except Exception: pass
        try:
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = style & ~(WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_POPUP)
            style = style | WS_CHILD|WS_VISIBLE|WS_CLIPSIBLINGS|WS_CLIPCHILDREN
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, 0)
        except Exception: pass
        try: user32.SetParent(hwnd, host_hwnd)
        except Exception: pass
        try:
            w = max(100, int(host.width())); h = max(100, int(host.height()))
            user32.MoveWindow(hwnd, 0, 0, w, h, True)
        except Exception: pass
        self.course_edge_hwnd = int(hwnd)
        self.course_edge_starting = False
        try:
            if self.course_edge_hint is not None:
                self.course_edge_hint.setVisible(False)
        except Exception: pass
        # ---- 关键：嵌入 HWND 成功后立刻把 CDP 也连上，否则纯净模式的 JS 没发注入 ----
        # 用 QTimer 稍等一下给 Edge 的 /json HTTP 接口准备好
        try:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(300, self._course_cdp_ensure)
        except Exception:
            try: self._course_cdp_ensure()
            except Exception: pass

    def _course_edge_resize_to_host(self) -> None:
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if not hwnd: return
        host = getattr(self, "course_edge_host", None)
        if host is None: return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            w = max(100, int(host.width())); h = max(100, int(host.height()))
            user32.MoveWindow(hwnd, 0, 0, w, h, True)
        except Exception: pass

    def _course_edge_send_keys(self, keys: str) -> None:
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if not hwnd: return
        try:
            import ctypes, time as _t
            user32 = ctypes.windll.user32
            try:
                qt_top = self.effectiveWinId() if hasattr(self, "effectiveWinId") else self.winId()
                try: user32.SetForegroundWindow(int(qt_top))
                except Exception: pass
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
            except Exception: pass
            KEYEVENTF_KEYUP = 0x0002
            VK_MENU=0x12; VK_CONTROL=0x11; VK_LEFT=0x25; VK_RIGHT=0x27
            VK_F5=0x74; VK_L=0x4C; VK_RETURN=0x0D
            def kd(vk): user32.keybd_event(vk, 0, 0, 0)
            def ku(vk): user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            seq_map = {
                "Alt+Left":  [(VK_MENU,True),(VK_LEFT,True),(VK_LEFT,False),(VK_MENU,False)],
                "Alt+Right": [(VK_MENU,True),(VK_RIGHT,True),(VK_RIGHT,False),(VK_MENU,False)],
                "F5":        [(VK_F5,True),(VK_F5,False)],
                "Ctrl+L":    [(VK_CONTROL,True),(VK_L,True),(VK_L,False),(VK_CONTROL,False)],
                "Return":    [(VK_RETURN,True),(VK_RETURN,False)],
                "Ctrl+V":    [(VK_CONTROL,True),(0x56,True),(0x56,False),(VK_CONTROL,False)],
                "F6":        [(0x75,True),(0x75,False)],
            }
            for (vk, down) in seq_map.get(keys, []):
                try:
                    kd(int(vk)) if down else ku(int(vk))
                    _t.sleep(0.01)
                except Exception: pass
        except Exception:
            pass

    def _course_edge_clipboard_load_url(self, url: str) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(str(url))
        except Exception:
            return
        import time as _t
        self._course_edge_send_keys("Ctrl+L"); _t.sleep(0.06)
        self._course_edge_send_keys("Ctrl+V"); _t.sleep(0.05)
        self._course_edge_send_keys("Return")

    # ==================== 统一入口 (WebView2 优先, 失败才 Edge --app) ====================
    def _course_default_home(self) -> str:
        return str(self.store.settings.get("course_home") or "https://www.bilibili.com")

    def _course_go_home(self):
        self._course_load(self._course_default_home())

    def _course_load(self, url: str):
        url = (url or "").strip()
        if not url: return
        if "://" not in url: url = "https://" + url
        self.course_addr.setText(url)
        self.course_edge_url = url
        if self.course_webview is not None:
            self.course_webview.setUrl(QUrl(url))
            self.course_edge_hint.setVisible(False)
            return
        # fallback
        if not int(getattr(self, "course_edge_hwnd", 0) or 0) and not getattr(self, "course_edge_starting", False):
            self._course_edge_ensure(silent=True)
            return
        if int(getattr(self, "course_edge_hwnd", 0) or 0):
            self._course_edge_clipboard_load_url(url)

    def _course_go_address(self): self._course_load(self.course_addr.text())

    def _course_go_back(self):
        if self.course_webview is not None:
            try: self.course_webview.back()
            except Exception: pass
        else:
            self._course_edge_send_keys("Alt+Left")

    def _course_go_forward(self):
        if self.course_webview is not None:
            try: self.course_webview.forward()
            except Exception: pass
        else:
            self._course_edge_send_keys("Alt+Right")

    def _course_refresh(self):
        if self.course_webview is not None:
            try: self.course_webview.reload()
            except Exception: pass
        else:
            self._course_edge_send_keys("F5")

    # ==================== 放大 (填充满整个 GroupBox) & 独立窗口 ====================
    def _course_toggle_maximize_in_card(self) -> None:
        """⛶ 按钮：整个“浏览器区域”方块内 100% 铺满，全屏=覆盖卡片内部全部区域（含工具栏下面的所有空间）"""
        if self._course_pop_win is not None:
            self._course_pop_win_close_then_restore(do_restore=True, maximize_next=True)
            return
        try:
            hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
            if hwnd <= 0: return
            import ctypes
            user32 = ctypes.windll.user32
            if not self._course_maximized:
                box = self.course_web_container.parent()
                if box is None: return
                self._course_max_box = box
                self._course_max_restore_container = self.course_web_container
                try: box.installEventFilter(self)
                except Exception: pass
                content_rect = box.rect()
                x = 12; y = 30 + 36
                w = content_rect.width() - 12 - 12
                h = content_rect.height() - 30 - 12 - 36
                try:
                    box.createWinId()
                    parent_hwnd = int(box.winId())
                    user32.SetParent(hwnd, parent_hwnd)
                except Exception: pass
                try:
                    user32.MoveWindow(hwnd, int(max(0, x)), int(max(0, y)),
                                      int(max(100, w)), int(max(100, h)), True)
                except Exception: pass
                self._course_maximized = True
                self.course_btn_maxarea.setText("✕")
                try:
                    from PyQt5.QtGui import QKeySequence
                    from PyQt5.QtWidgets import QShortcut
                    self._course_max_shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
                    self._course_max_shortcut_esc.activated.connect(self._course_toggle_maximize_in_card)
                except Exception: pass
            else:
                try:
                    if getattr(self, "_course_max_box", None) is not None:
                        self._course_max_box.removeEventFilter(self)
                except Exception: pass
                host = self.course_edge_host
                if host is not None:
                    try: host.createWinId(); host_hwnd = int(host.winId())
                    except Exception: host_hwnd = 0
                    if host_hwnd:
                        try: user32.SetParent(hwnd, host_hwnd)
                        except Exception: pass
                    w = max(100, int(host.width())); h = max(100, int(host.height()))
                    try: user32.MoveWindow(hwnd, 0, 0, w, h, True)
                    except Exception: pass
                self._course_max_box = None
                self._course_max_restore_container = None
                self._course_maximized = False
                self.course_btn_maxarea.setText("⛶")
                try:
                    if self._course_max_shortcut_esc is not None:
                        self._course_max_shortcut_esc.setParent(None)
                except Exception: pass
                self._course_max_shortcut_esc = None
        except Exception:
            pass

    def _course_wv2_find_child_hwnd(self) -> Optional[int]:
        """在我们自己进程内递归找 WebView2 的真实渲染 HWND (Chrome_WidgetWin_*)"""
        try:
            import ctypes
            from ctypes import wintypes as _wt
            user32 = ctypes.windll.user32
            host = getattr(self, "course_edge_host", None)
            if host is None: return None
            try: host.createWinId(); root = int(host.winId())
            except Exception: return None
            found = []
            @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
            def _enum_child(child, _lp):
                try:
                    cls_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(child, cls_buf, 255)
                    cls = str(cls_buf.value or "")
                except Exception:
                    cls = ""
                if "Chrome_WidgetWin_" in cls or "Microsoft.Web.WebView2" in cls:
                    found.append(int(child))
                    return False
                return True
            # 只枚举 host 为根的子树 (WebView2 应该就在里面)
            try:
                user32.EnumChildWindows(root, _enum_child, 0)
            except Exception:
                pass
            if found:
                return int(found[0])
        except Exception:
            pass
        return None

    def _course_relayout_maximized(self) -> None:
        if not self._course_maximized: return
        if getattr(self, "course_wv2_window", None) is not None:
            self._course_wv2_resize_to_host()
            # 同时重设父 HWND + MoveWindow，保证视频区域真的能铺满
            try:
                import ctypes
                user32 = ctypes.windll.user32
                box = getattr(self, "_course_max_box", None)
                if box is None: return
                child = getattr(self, "_course_wv2_child_hwnd", None)
                if child is None:
                    child = self._course_wv2_find_child_hwnd()
                    self._course_wv2_child_hwnd = child
                if child:
                    try: box.createWinId(); box_hwnd = int(box.winId())
                    except Exception: box_hwnd = 0
                    content_rect = box.rect()
                    width  = max(320, int(content_rect.width() - 12 - 12))
                    height = max(240, int(content_rect.height() - 30 - 12 - 36))
                    x = 12; y = 30 + 36
                    if box_hwnd:
                        try: user32.SetParent(int(child), int(box_hwnd))
                        except Exception: pass
                    try: user32.MoveWindow(int(child), int(x), int(y), int(width), int(height), True)
                    except Exception: pass
            except Exception:
                pass
            return
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if hwnd <= 0: return
        box = getattr(self, "_course_max_box", None)
        if box is None: return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            content_rect = box.rect()
            x = 12; y = 30 + 36
            w = content_rect.width() - 12 - 12
            h = content_rect.height() - 30 - 12 - 36
            user32.MoveWindow(hwnd, int(max(0, x)), int(max(0, y)),
                              int(max(100, w)), int(max(100, h)), True)
        except Exception:
            pass

    def _course_pop_out_browser(self) -> None:
        """🗔 独立窗口：当前始终是 Edge --app 模式，直接 SetParent(0) + 恢复边框，保持原进程/会话/视频进度不中断"""
        if self._course_maximized:
            self._course_toggle_maximize_in_card()
        if self._course_pop_win is not None:
            self._course_pop_win_close_then_restore(do_restore=True)
            return
        current_url = getattr(self, "course_edge_url", "") or self._course_default_home()
        real_url = current_url
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if hwnd <= 0:
            self.course_edge_url = real_url
            if not self._course_edge_ensure(silent=False): return
        self._course_pop_out_browser_edge_impl(real_url)

    def _course_pop_out_browser_edge_impl(self, real_url: str) -> None:
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if hwnd <= 0: return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            GWL_STYLE=-16; GWL_EXSTYLE=-20
            WS_POPUP=0x80000000; WS_CAPTION=0x00C00000; WS_THICKFRAME=0x00040000
            WS_SYSMENU=0x00080000; WS_MINIMIZEBOX=0x00020000; WS_MAXIMIZEBOX=0x00010000
            WS_VISIBLE=0x10000000
            WS_OVERLAPPEDWINDOW = WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX
            user32.SetParent(hwnd, 0)
            orig_style = int(getattr(self, "course_edge_original_style", 0) or 0)
            if orig_style:
                style = orig_style
            else:
                style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                style = style & ~0x40000000
                style = style | WS_POPUP | WS_OVERLAPPEDWINDOW | WS_VISIBLE
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            orig_ex = int(getattr(self, "course_edge_original_exstyle", 0) or 0)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, orig_ex)
            try: user32.MoveWindow(hwnd, 120, 100, 1280, 820, True)
            except Exception: pass
            try:
                SW_RESTORE = 9
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
            except Exception: pass
            dlg = QDialog(self)
            dlg.setWindowTitle("网课 · 独立浏览窗口 (点击归位/关闭对话框 → Edge 自动嵌回)")
            dlg.resize(420, 130)
            dlg.setModal(False)
            dlg_v = QVBoxLayout(dlg)
            dlg_v.setContentsMargins(14, 14, 14, 14)
            info = QLabel(
                "✅ Edge 浏览器已弹出为独立窗口。\n\n"
                "操作: 点下方「⇲ 立即归位」、关闭本对话框、按 ESC → Edge 自动嵌回主程序。"
            )
            info.setStyleSheet("color:#1e40af;font-weight:600;padding:2px;")
            btn_restore = QPushButton("⇲ 立即归位")
            btn_restore.setCursor(Qt.PointingHandCursor)
            btn_restore.setStyleSheet(
                "QPushButton{background:#2563eb;color:white;font-weight:800;"
                "border-radius:5px;padding:6px 10px;}"
                "QPushButton:hover{background:#3b82f6;}"
            )
            btn_restore.clicked.connect(lambda: self._course_pop_win_close_then_restore(do_restore=True))
            dlg_v.addWidget(info); dlg_v.addSpacing(6); dlg_v.addWidget(btn_restore)
            try:
                from PyQt5.QtGui import QKeySequence
                from PyQt5.QtWidgets import QShortcut
                self._course_pop_win_shortcut_esc = QShortcut(QKeySequence(Qt.Key_Escape), dlg)
                self._course_pop_win_shortcut_esc.activated.connect(
                    lambda: self._course_pop_win_close_then_restore(do_restore=True)
                )
            except Exception:
                pass
            try:
                dlg.finished.connect(lambda _r: self._course_pop_win_close_then_restore(do_restore=True))
            except Exception:
                pass
            self._course_pop_win = dlg
            self.course_btn_popout.setText("⇲ 归位")
            self.course_btn_popout.setToolTip("Edge 浏览器已独立窗口，点这里或关闭对话框归位")
            dlg.show(); dlg.raise_(); dlg.activateWindow()
        except Exception:
            pass

    def _course_pop_win_close_then_restore(self, do_restore: bool, maximize_next: bool = False) -> None:
        dlg = self._course_pop_win
        self._course_pop_win = None
        try:
            if self._course_pop_win_shortcut_esc is not None:
                self._course_pop_win_shortcut_esc.setParent(None)
        except Exception:
            pass
        self._course_pop_win_shortcut_esc = None
        self.course_btn_popout.setText("🗔")
        self.course_btn_popout.setToolTip("独立窗口：浏览器单独弹出一个新窗口 (关闭即归位)")
        hwnd = int(getattr(self, "course_edge_hwnd", 0) or 0)
        if do_restore and hwnd and getattr(self, "course_edge_host", None) is not None:
            try:
                host = self.course_edge_host
                try: host.createWinId()
                except Exception: pass
                host_hwnd = int(host.winId())
                import ctypes
                user32 = ctypes.windll.user32
                GWL_STYLE=-16; GWL_EXSTYLE=-20
                WS_CHILD=0x40000000; WS_VISIBLE=0x10000000
                WS_CAPTION=0x00C00000; WS_THICKFRAME=0x00040000; WS_SYSMENU=0x00080000
                WS_MINIMIZEBOX=0x00020000; WS_MAXIMIZEBOX=0x00010000; WS_POPUP=0x80000000
                WS_CLIPSIBLINGS=0x04000000; WS_CLIPCHILDREN=0x02000000
                style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                style = style & ~(WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX|WS_POPUP)
                style = style | WS_CHILD|WS_VISIBLE|WS_CLIPSIBLINGS|WS_CLIPCHILDREN
                user32.SetWindowLongW(hwnd, GWL_STYLE, style)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, 0)
                user32.SetParent(hwnd, host_hwnd)
                w = max(100, int(host.width())); h = max(100, int(host.height()))
                user32.MoveWindow(hwnd, 0, 0, w, h, True)
            except Exception:
                pass
        if getattr(self, "course_wv2_window", None) is not None:
            self._course_wv2_resize_to_host()
        if dlg is not None:
            try: dlg.blockSignals(True)
            except Exception: pass
            try: dlg.close()
            except Exception: pass
            try: dlg.setParent(None)
            except Exception: pass
            try: dlg.deleteLater()
            except Exception: pass
        if maximize_next:
            try:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(30, self._course_toggle_maximize_in_card)
            except Exception:
                pass

    def _course_on_enter(self):
        self._course_rebuild_pick_list()
        self._course_refresh_preview_header()
        # 优先使用 PyQtWebEngine (Qt 自带 Chromium, 真嵌入, 不需要外部浏览器)
        if self.course_webview is not None:
            # 显示 webview, 隐藏提示
            self.course_edge_hint.setVisible(False)
            # 如果 webview 还没加载过任何 URL, 加载默认首页
            if not self.course_webview_loaded:
                url = getattr(self, "course_edge_url", "") or self._course_default_home()
                self.course_edge_url = url
                self.course_webview.setUrl(QUrl(url))
            else:
                # 已加载过, 确保可见
                self.course_webview.show()
        elif not int(getattr(self, "course_edge_hwnd", 0) or 0) and not getattr(self, "course_edge_starting", False):
            # fallback: Edge 子进程方案
            if not getattr(self, "course_edge_url", ""):
                self.course_edge_url = self._course_default_home()
            self._course_edge_ensure(silent=True)

    # ---- WebEngine 信号回调 ----
    def _course_webview_on_url_changed(self, qurl):
        try:
            url = qurl.toString()
            if url and url.startswith("http"):
                self.course_addr.setText(url)
                self.course_edge_url = url
        except Exception:
            pass

    def _course_webview_on_load_finished(self, ok):
        self.course_webview_loaded = bool(ok)
        try:
            if self.course_edge_hint is not None:
                self.course_edge_hint.setVisible(False)
        except Exception:
            pass

    # ---- HTML5 播放提示 ----
    def _course_fix_html5_playback(self):
        try:
            QMessageBox.information(
                self, "🎬 浏览器: Qt WebEngine (Chromium 内核)",
                "现在网课学习区使用的是 Qt 自带的 Chromium 内核（PyQtWebEngine），\n"
                "B 站/腾讯课堂 HTML5 视频 100% 支持。\n\n"
                "如果仍出现「不支持 HTML5 播放器」：\n\n"
                "1) 点工具栏 ♻️ 刷新\n"
                "2) 重新在地址栏输入网址回车\n"
                "3) 点 🎬 视频纯净模式，把视频单独提取出来黑底放大填满整个区域"
            )
        except Exception:
            pass
        # 刷新当前页面
        if self.course_webview is not None:
            try:
                self.course_webview.reload()
            except Exception:
                pass


    def _course_build_markdown(self) -> QWidget:
        wrap = QWidget()
        outer = QHBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        # ---- 左: 笔记选择条 + 编辑区 ----
        left = QGroupBox("Markdown 笔记编辑")
        left.setStyleSheet(
            "QGroupBox {"
            "  background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #8b5cf6;"
            "  border-radius: 12px;"
            "  margin-top: 16px;"
            "  padding-top: 10px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin; left: 16px; padding: 2px 10px;"
            "  color: #6d28d9; font-size: 13px; font-weight: 700;"
            "  background: transparent;"
            "}"
        )
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 16, 12, 12)
        lv.setSpacing(8)

        # 第一行: 打开笔记(学科筛选+笔记列表)
        pick_row = QHBoxLayout()
        pick_row.setSpacing(6)
        self.course_pick_subject = QComboBox()
        self.course_pick_subject.addItems(["全部学科"] + list(NOTE_SUBJECTS))
        self.course_pick_subject.setFixedHeight(28)
        self.course_pick_subject.currentIndexChanged.connect(self._course_rebuild_pick_list)

        self.course_pick_note = QComboBox()
        self.course_pick_note.setFixedHeight(28)
        self.course_pick_note.setMinimumWidth(320)
        self.course_pick_note.setPlaceholderText("—— 选择已有笔记打开 ——")
        self.course_pick_note.currentIndexChanged.connect(self._course_on_pick_note_changed)

        btn_new = QPushButton("新笔记")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setFixedHeight(28)
        btn_new.clicked.connect(self._course_note_new)

        btn_delete = QPushButton("删除本笔记")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setFixedHeight(28)
        btn_delete.clicked.connect(self._course_note_delete_current)

        pick_row.addWidget(QLabel("筛选"))
        pick_row.addWidget(self.course_pick_subject)
        pick_row.addWidget(self.course_pick_note, 1)
        pick_row.addWidget(btn_new)
        pick_row.addWidget(btn_delete)
        lv.addLayout(pick_row)

        # 第二行: 保存条 - 学科(保存到哪科) | 标题 | 保存
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.course_note_subject = QComboBox()
        self.course_note_subject.addItems(list(NOTE_SUBJECTS))
        self.course_note_subject.setFixedHeight(28)
        self.course_note_title = QLineEdit()
        self.course_note_title.setPlaceholderText("笔记标题")
        self.course_note_title.setFixedHeight(28)

        btn_save = QPushButton("💾 保存到")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setFixedHeight(28)
        btn_save.setStyleSheet(
            "QPushButton { background: rgba(120,80,180,200); color: white;"
            " border-radius: 6px; font-weight: 700; padding: 0 14px; }"
            "QPushButton:hover { background: rgba(120,80,180,235); }"
        )
        btn_save.clicked.connect(self._course_note_save)
        meta_row.addWidget(QLabel("保存到学科"))
        meta_row.addWidget(self.course_note_subject)
        meta_row.addSpacing(6)
        meta_row.addWidget(QLabel("标题"))
        meta_row.addWidget(self.course_note_title, 1)
        meta_row.addWidget(btn_save)
        lv.addLayout(meta_row)

        # 标题/学科变动时, 预览卡的标题徽章 底部小字 同步刷新
        self.course_note_subject.currentIndexChanged.connect(
            lambda *_: self._course_refresh_preview_header()
        )
        self.course_note_title.textChanged.connect(
            lambda *_: self._course_refresh_preview_header()
        )

        # Markdown 编辑区 (不再包 Tab, 直接一个大编辑器)
        self.course_md_edit = QPlainTextEdit()
        self.course_md_edit.setPlaceholderText(
            "# 这里写 Markdown 笔记\n\n## 小标题\n- 列表\n- **加粗** 与 *斜体*\n\n```python\nprint('hello')\n```\n\n> 引用块\n\n写完自动在右侧预览，随时保存到 英语 / 数学 / 专业课。"
        )
        self.course_md_edit.setStyleSheet(
            "QPlainTextEdit {"
            " background: #ffffff; border-radius: 8px; padding: 12px;"
            " color: #0f172a; font-family: Consolas, 'Microsoft YaHei'; font-size: 13px;"
            " line-height: 170%; border: 1px solid #e2e8f0; }"
        )
        self.course_md_edit.textChanged.connect(self._course_refresh_preview)
        lv.addWidget(self.course_md_edit, 1)

        # 底部 meta 状态
        self.course_note_status = QLabel("当前：新笔记")
        self.course_note_status.setStyleSheet(
            "color: #64748b; font-size: 12px; font-weight: 600;"
        )
        lv.addWidget(self.course_note_status)

        outer.addWidget(left, 1)

        # ---- 右: Markdown 阅读预览 (直接整块当预览区, 原来的笔记库表删除) ----
        right = QGroupBox("📖 笔记阅读预览")
        right.setStyleSheet(
            "QGroupBox {"
            "  background: #ffffff;"
            "  border: 1px solid #e2e8f0;"
            "  border-top: 3px solid #10b981;"
            "  border-radius: 12px;"
            "  margin-top: 16px;"
            "  padding-top: 10px;"
            "}"
            "QGroupBox::title {"
            "  subcontrol-origin: margin; left: 16px; padding: 2px 10px;"
            "  color: #047857; font-size: 13px; font-weight: 700;"
            "  background: transparent;"
            "}"
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 16, 12, 12)
        rv.setSpacing(8)

        # 预览区顶栏: 预览标题 + 学科标签显示 + 空状态提示占位
        head = QHBoxLayout()
        self.course_preview_title = QLabel("标题")
        self.course_preview_title.setStyleSheet(
            "color: #0f172a; font-size: 17px; font-weight: 800; letter-spacing: 0.5px;"
        )
        self.course_preview_subject_tag = QLabel("学科：—")
        self.course_preview_subject_tag.setStyleSheet(
            "background: #dbeafe; color: #1d4ed8;"
            " padding: 4px 10px; border-radius: 10px; font-size: 12px; font-weight: 700;"
        )
        head.addWidget(self.course_preview_title, 1)
        head.addWidget(self.course_preview_subject_tag)
        rv.addLayout(head)

        self.course_md_preview = QTextBrowser()
        self.course_md_preview.setOpenExternalLinks(True)
        self.course_md_preview.setStyleSheet(
            "QTextBrowser {"
            " background: rgba(255,255,255,240); border-radius: 10px; padding: 18px 22px;"
            " color: #1f2937; font-family: 'Microsoft YaHei'; font-size: 14px;"
            " line-height: 200%; border: 1px solid rgba(180,140,80,100); }"
        )
        rv.addWidget(self.course_md_preview, 1)

        # 预览底部的小工具栏: 导出 HTML/文本等预留位置, 这里放"上一次保存信息"
        self.course_preview_footer = QLabel("")
        self.course_preview_footer.setStyleSheet(
            "color: rgba(15,43,33,180); font-size: 12px; font-weight: 600;"
        )
        rv.addWidget(self.course_preview_footer)

        outer.addWidget(right, 1)

        # 初始化状态
        self.course_current_note_id: Optional[str] = None
        self._course_md_last_preview: str = ""
        self._course_loading_note: bool = False  # 防止 currentIndexChanged 触发重入
        return wrap

    # ---- 打开笔记下拉筛选 ----
    def _course_rebuild_pick_list(self):
        if self._course_loading_note:
            return
        if not hasattr(self, "course_pick_note") or self.course_pick_note is None:
            return
        self.course_pick_note.blockSignals(True)
        self.course_pick_note.clear()
        filter_text = self.course_pick_subject.currentText()
        subject = None if filter_text == "全部学科" else filter_text
        notes = self.store.list_notes(subject)
        # 占位: 第一项"—— 选择已有笔记打开 ——"
        self.course_pick_note.addItem("—— 选择已有笔记打开 ——", None)
        for n in notes:
            label = f"[{n.get('subject','')}] {n.get('title','未命名')}   ·更新 {n.get('updated_at','')}"
            self.course_pick_note.addItem(label, str(n.get("id") or ""))
        self.course_pick_note.blockSignals(False)

    def _course_on_pick_note_changed(self, idx: int):
        if idx < 0 or self._course_loading_note:
            return
        nid = self.course_pick_note.itemData(idx)
        if not nid:
            return
        self._course_note_load(nid)

    def _course_refresh_preview_header(self):
        """根据当前输入区, 刷新预览顶栏的标题/学科/底部小字"""
        title = self.course_note_title.text().strip() or "未命名笔记"
        subj = self.course_note_subject.currentText()
        self.course_preview_title.setText(title)
        self.course_preview_subject_tag.setText(f"学科：{subj}")
        status = self.course_note_status.text() or ""
        # 挑出已保存的时间显示
        tail = ""
        if "已保存" in status and "保存于" in status:
            tail = status.split("保存于", 1)[-1].strip()
        elif "当前：" in status and "更新" in status:
            parts = status.split("更新", 1)
            if len(parts) == 2:
                tail = "已保存于 " + parts[-1].strip()
        if tail:
            self.course_preview_footer.setText(f"✔ {tail}")
        else:
            self.course_preview_footer.setText("✎ 正在编辑（尚未保存）")

    # ---- 笔记加载 / 新建 / 保存 / 删除 ----
    def _course_note_load(self, note_id: str):
        n = self.store.get_note(note_id)
        if n is None:
            return
        self._course_loading_note = True
        try:
            self.course_current_note_id = note_id
            subj = str(n.get("subject") or NOTE_SUBJECTS[0])
            if subj in NOTE_SUBJECTS:
                self.course_note_subject.setCurrentText(subj)
            self.course_note_title.setText(str(n.get("title") or ""))
            self.course_md_edit.blockSignals(True)
            self.course_md_edit.setPlainText(str(n.get("content") or ""))
            self.course_md_edit.blockSignals(False)
            self._course_md_last_preview = ""
            created = str(n.get("created_at") or "-")
            updated = str(n.get("updated_at") or "-")
            self.course_note_status.setText(
                f"当前：{subj} · {n.get('title') or '未命名'} · 创建 {created} · 更新 {updated}"
            )
            self._course_refresh_preview()
            # 把打开笔记同步到筛选下拉, 让用户一眼看到选的哪条
            if self.course_pick_subject.currentText() not in ("全部学科", subj):
                self.course_pick_subject.setCurrentText("全部学科")
            self._course_rebuild_pick_list()
            # 定位到该项
            for i in range(self.course_pick_note.count()):
                if self.course_pick_note.itemData(i) == note_id:
                    self.course_pick_note.setCurrentIndex(i)
                    break
        finally:
            self._course_loading_note = False

    def _course_note_new(self):
        self._course_loading_note = True
        try:
            self.course_current_note_id = None
            self.course_pick_note.blockSignals(True)
            if self.course_pick_note.count() > 0:
                self.course_pick_note.setCurrentIndex(0)
            self.course_pick_note.blockSignals(False)
            self.course_note_title.setText("")
            self.course_md_edit.blockSignals(True)
            self.course_md_edit.setPlainText("")
            self.course_md_edit.blockSignals(False)
            self.course_note_status.setText("当前：新笔记")
            self._course_refresh_preview()
        finally:
            self._course_loading_note = False

    def _course_note_save(self):
        subject = self.course_note_subject.currentText()
        title = self.course_note_title.text().strip() or "未命名笔记"
        content = self.course_md_edit.toPlainText()
        saved = self.store.upsert_note(
            subject=subject,
            title=title,
            content=content,
            note_id=self.course_current_note_id,
        )
        self.course_current_note_id = str(saved.get("id") or "")
        self.course_note_status.setText(
            f"已保存 ✔  {saved.get('subject')} · {saved.get('title')} · 保存于 {saved.get('updated_at')}"
        )
        self._course_loading_note = True
        try:
            # 如果当前筛选下拉里不含该学科, 切到"全部学科"再重建
            if self.course_pick_subject.currentText() not in ("全部学科", str(saved.get("subject"))):
                self.course_pick_subject.setCurrentText("全部学科")
            self._course_rebuild_pick_list()
            # 选中刚保存的那一条
            for i in range(self.course_pick_note.count()):
                if self.course_pick_note.itemData(i) == self.course_current_note_id:
                    self.course_pick_note.setCurrentIndex(i)
                    break
            self._course_refresh_preview_header()
        finally:
            self._course_loading_note = False

    def _course_note_delete_current(self):
        if not self.course_current_note_id:
            QMessageBox.information(self, "提示", "当前没有已保存的笔记可删除。请先选择或保存一篇笔记。")
            return
        n = self.store.get_note(self.course_current_note_id)
        title = (n or {}).get("title") or "该笔记"
        ret = QMessageBox.question(
            self, "删除笔记",
            f"确定要删除「{title}」吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        nid = self.course_current_note_id
        if self.store.delete_note(nid):
            self._course_note_new()
            self._course_rebuild_pick_list()

    # ---- Markdown 预览 (当前实时刷新 + 预览标题学科头同步) ----
    def _course_refresh_preview(self):
        md = self.course_md_edit.toPlainText() if hasattr(self, "course_md_edit") else ""
        if md == getattr(self, "_course_md_last_preview", None):
            # 内容没变 但标题/学科也可能变, 仍然要刷新头部
            self._course_refresh_preview_header()
            return
        self._course_md_last_preview = md
        # 先同步预览卡的标题/学科徽标/底部小字
        self._course_refresh_preview_header()
        # 再渲染正文
        try:
            self.course_md_preview.setMarkdown(md)
        except Exception:
            # 旧版 Qt 没有 setMarkdown 就降级
            self.course_md_preview.setPlainText(md)

    # ===== 导航选中态 =====
    def show_page(self, key: str):
        if not hasattr(self, "pages") or key not in self.pages:
            return
        # 切回主界面时，刷新每日语录 / 今日任务 (跨天自动重置) / 倒计时
        if key == "dashboard" and hasattr(self, "_refresh_dashboard"):
            try:
                self._refresh_dashboard()
            except Exception:
                pass
        if self.page_stack is None:
            return
        self.page_stack.setCurrentWidget(self.pages[key])
        # 重建 UI 后, _nav_buttons 里可能有已被 deleteLater 的旧按钮
        nav_btns = getattr(self, "_nav_buttons", [])
        live_btns = []
        for b in nav_btns:
            try:
                # 测试按钮是否还活着
                _ = b.property("page_key")
            except RuntimeError:
                continue  # 已被销毁, 跳过
            live_btns.append(b)
        # 替换为存活列表 (避免下次再遍历到死的)
        self._nav_buttons = live_btns
        for b in live_btns:
            try:
                is_sel = (b.property("page_key") == key)
                b.setProperty("selected", is_sel)
                # 动态属性变化需要重新应用 QSS
                b.style().unpolish(b)
                b.style().polish(b)
                b.update()
            except RuntimeError:
                continue

    # ===== 标题栏动作 (与上位机一致) =====
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ===== 主题切换 =====
    # 主题色定义 (与 ThemeDialog.PRESETS 对应)
    THEME_COLORS = {
        "light": dict(
            bg="#f8fafc", card="#ffffff", border="#e2e8f0",
            text="#0f172a", text2="#475569", text3="#64748b",
            title_bg="#ffffff", title_text="#1f2937", title_border="#e2e8f0",
            accent="#2563eb", accent_fg="#ffffff",
            nav_bg="#ffffff", nav_hover="#f1f5f9", nav_active="#dbeafe",
        ),
        "dark": dict(
            bg="#0f172a", card="#1e293b", border="#334155",
            # 文字改为牛奶色系 (柔和不刺眼, 暖色调)
            text="#f5f0e1",        # 主文字: 牛奶白
            text2="#e8e3d3",       # 次要: 偏暖奶白
            text3="#c9c2b0",       # 提示: 温润米色
            title_bg="#020617", title_text="#faf3e0", title_border="#1e293b",  # 标题: 浓牛奶色
            accent="#fbbf24", accent_fg="#0f172a",  # 强调色改为暖琥珀 (搭配牛奶色更和谐)
            nav_bg="#1e293b", nav_hover="#334155", nav_active="#3a2810",  # 选中: 暖琥珀深色
        ),
    }

    def _on_title_theme_toggled(self, checked: bool):
        """顶部小开关直接切换日/夜"""
        print(f"[MainWindow] _on_title_theme_toggled: {checked}")
        theme_id = "dark" if checked else "light"
        self._apply_theme(theme_id)

    def _open_theme_dialog(self):
        """打开完整主题设置弹窗 (含大滑动开关 + 主题预览)"""
        dlg = ThemeDialog(self.store, main_window=self, parent=self)
        dlg.exec_()

    # ----- 导航栏样式刷新 (按主题动态生成) -----
    NAV_ACCENTS = {
        "dashboard": "#f59e0b",  # amber
        "english":   "#ec4899",  # pink
        "math":      "#3b82f6",  # blue
        "major":     "#10b981",  # emerald
        "school":    "#eab308",  # yellow
        "course":    "#8b5cf6",  # violet
        "pdf":       "#06b6d4",  # cyan
        "focus":     "#ef4444",  # red
    }

    def _refresh_nav_styles(self, theme_id: str):
        """根据主题刷新: 导航栏容器 + 所有导航按钮 + 文字色 + 选中态"""
        c = self.THEME_COLORS.get(theme_id, self.THEME_COLORS["light"])
        # 1. 导航栏容器
        if hasattr(self, "nav_panel") and self.nav_panel is not None:
            try:
                self.nav_panel.setStyleSheet(
                    f"QWidget#navPanel {{"
                    f"  background: {c['nav_bg']};"
                    f"  border: 1px solid {c['border']};"
                    f"  border-radius: 16px;"
                    f"}}"
                )
            except Exception:
                pass
        # 2. 顶部标题 / 副标题 / 分隔线 / 底部
        for w in (self.nav_panel.findChildren(QWidget) if hasattr(self, "nav_panel") and self.nav_panel else []):
            try:
                obj = w.objectName()
                if obj == "navTitle":
                    w.setStyleSheet(
                        f"color: {c['text']}; font-size: 16px; font-weight: 800; background: transparent;"
                    )
                elif obj == "navSub":
                    w.setStyleSheet(
                        f"color: {c['text2']}; font-size: 11px; background: transparent;"
                    )
                elif w.property("nav_line"):
                    w.setStyleSheet(
                        f"background:{c['border']}; max-height:1px; min-height:1px; border: none;"
                    )
            except Exception:
                pass
        # 3. 每个导航按钮
        for b in getattr(self, "_nav_buttons", []):
            try:
                # 检查按钮还活着
                _ = b.property("page_key")
            except RuntimeError:
                continue
            try:
                page_key = b.property("page_key")
                selected = bool(b.property("selected"))
                accent = self.NAV_ACCENTS.get(page_key, c['accent'])
                # 按钮整体 QSS (含 hover / selected 态)
                b.setStyleSheet(
                    f"QPushButton#navBtn {{"
                    f"  background: transparent;"
                    f"  border: none;"
                    f"  border-radius: 10px;"
                    f"  padding: 0;"
                    f"  text-align: left;"
                    f"  color: {c['text']};"
                    f"}}"
                    f"QPushButton#navBtn:hover {{ background: {c['nav_hover']}; }}"
                    f"QPushButton#navBtn[selected='true'] {{ background: {c['nav_active']}; }}"
                )
                # 4. 按钮内子 label 单独 setStyleSheet (确保颜色正确)
                for lbl in b.findChildren(QLabel):
                    try:
                        if lbl.property("nav_dot"):
                            lbl.setStyleSheet(
                                f"background:{accent};border-radius:4px;"
                                "max-width:8px;min-width:8px;"
                                "max-height:8px;min-height:8px;"
                            )
                        elif lbl.property("nav_text"):
                            lbl.setStyleSheet(
                                f"background: transparent; color: {c['text']};"
                                f" font-size: 14px; font-weight: 700;"
                            )
                        elif lbl.property("nav_sub"):
                            lbl.setStyleSheet(
                                f"background: transparent; color: {c['text2']};"
                                f" font-size: 11px;"
                            )
                    except Exception:
                        pass
            except Exception:
                continue

    def _apply_theme(self, theme_id: str, animate: bool = True):
        """应用主题: 丝滑渐变 (遮罩色=目标色, 淡出→切换→淡入, 全程颜色一致)"""
        if theme_id not in self.THEME_COLORS:
            theme_id = "light"
        # 1. 改主变量
        prev_theme = self._current_theme
        self._current_theme = theme_id
        # 2. 落盘 (失败不影响主流程)
        try:
            self.store.settings["theme"] = theme_id
            self.store.save()
        except Exception as e:
            import traceback
            print(f"[MainWindow._apply_theme] store.save 失败: {e}")
            traceback.print_exc()
        # 3. 直接切换 (无动画)
        if not animate or prev_theme == theme_id:
            self._do_apply_theme(theme_id)
            return
        # 4. 丝滑切换: 遮罩色 = 目标主题背景色 (深→浅用浅遮罩, 浅→深用深遮罩)
        root = self.centralWidget()
        if root is None:
            self._do_apply_theme(theme_id)
            return
        try:
            # 移除上次残留遮罩
            old_overlay = getattr(self, "_theme_overlay", None)
            if old_overlay is not None:
                try:
                    old_overlay.deleteLater()
                except Exception:
                    pass
                self._theme_overlay = None
            # 目标色 = 目标主题背景
            target_bg = "#0f172a" if theme_id == "dark" else "#f8fafc"
            overlay = QFrame(root)
            overlay.setObjectName("themeOverlay")
            overlay.setAutoFillBackground(True)
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents)  # 不挡事件
            overlay.setStyleSheet(
                f"QFrame#themeOverlay {{ background-color: {target_bg}; border: none; }}"
            )
            # 透明度 effect
            eff = QGraphicsOpacityEffect(overlay)
            eff.setOpacity(0.0)
            overlay.setGraphicsEffect(eff)
            # 覆盖 root 全区域
            overlay.setGeometry(root.rect())
            overlay.raise_()
            overlay.show()
            self._theme_overlay = overlay
            # 动画 1: 淡入遮罩 0→1.0, 380ms, InOutQuart
            self._theme_anim_out = QPropertyAnimation(eff, b"opacity", self)
            self._theme_anim_out.setDuration(380)
            self._theme_anim_out.setStartValue(0.0)
            self._theme_anim_out.setEndValue(1.0)
            self._theme_anim_out.setEasingCurve(QEasingCurve.InOutQuart)
            self._theme_anim_out.finished.connect(
                lambda: self._apply_theme_mid(theme_id, overlay, eff)
            )
            self._theme_anim_out.start()
        except Exception as e:
            print(f"[MainWindow._apply_theme] 动画失败, 直接切换: {e}")
            self._do_apply_theme(theme_id)

    def _apply_theme_mid(self, theme_id: str, overlay, eff):
        """遮罩覆盖到 1.0 时: 改样式 (此时屏幕已被遮罩盖满, 用户无感知) → 再淡出遮罩"""
        # 改样式
        self._do_apply_theme(theme_id)
        # 动画 2: 淡出遮罩 1.0→0, 420ms, InOutQuart
        self._theme_anim_in = QPropertyAnimation(eff, b"opacity", self)
        self._theme_anim_in.setDuration(420)
        self._theme_anim_in.setStartValue(1.0)
        self._theme_anim_in.setEndValue(0.0)
        self._theme_anim_in.setEasingCurve(QEasingCurve.InOutQuart)
        self._theme_anim_in.finished.connect(lambda: self._remove_theme_overlay(overlay))
        self._theme_anim_in.start()

    def _remove_theme_overlay(self, overlay):
        """动画结束后清理遮罩"""
        try:
            overlay.deleteLater()
        except Exception:
            pass
        if getattr(self, "_theme_overlay", None) is overlay:
            self._theme_overlay = None

    def _do_apply_theme(self, theme_id: str):
        """真正执行主题样式切换 (无动画)"""
        # 移除 root 上的 QGraphicsOpacityEffect (避免 QPainter 警告)
        root = self.centralWidget()
        if root is not None:
            try:
                eff = root.graphicsEffect()
                if isinstance(eff, QGraphicsOpacityEffect):
                    root.setGraphicsEffect(None)
                    eff.deleteLater()
            except Exception:
                pass
        # 改子组件样式
        try:
            self._recolor_all(theme_id)
        except Exception as e:
            print(f"[MainWindow._do_apply_theme] recolor_all 失败: {e}")
        # root 背景色 (保留原 font-family)
        if root is not None:
            c = self.THEME_COLORS[theme_id]
            root_bg = "#0f172a" if theme_id == "dark" else "#f8fafc"
            existing = root.styleSheet() or ""
            if "font-family" in existing:
                import re as _re
                new_ss = _re.sub(
                    r"(QWidget#mainRoot\s*\{[^}]*?background:\s*)([^;}]+)",
                    rf"\g<1>{root_bg}",
                    existing,
                    flags=_re.IGNORECASE,
                )
                def _replace_color_in_qwidget_block(m):
                    block = m.group(0)
                    block = _re.sub(
                        r"(color:\s*)([^;}]+)",
                        rf"\g<1>{c.get('text', '#0f172a')}",
                        block,
                        flags=_re.IGNORECASE,
                    )
                    return block
                new_ss = _re.sub(
                    r"QWidget\s*\{[^}]*\}",
                    _replace_color_in_qwidget_block,
                    new_ss,
                )
                root.setStyleSheet(new_ss)
            else:
                root.setStyleSheet(
                    f"QWidget#mainRoot {{ background: {root_bg}; }}"
                    f"QWidget {{ color: {c.get('text', '#0f172a')};"
                    f" font-family: \"Microsoft YaHei UI\", \"Microsoft YaHei\", \"微软雅黑\";"
                    f" font-size: 13px; }}"
                )
        # AI 面板
        if hasattr(self, "ai_panel") and self.ai_panel is not None:
            try:
                self.ai_panel._apply_theme(theme_id)
            except Exception:
                pass
        # 导航栏 + 错题本表格 (按主题动态刷新)
        try:
            self._refresh_nav_styles(theme_id)
        except Exception as e:
            print(f"[MainWindow._do_apply_theme] _refresh_nav_styles 失败: {e}")
        try:
            if hasattr(self, "english_page") and self.english_page is not None:
                self.english_page._apply_theme(self.THEME_COLORS[theme_id])
        except Exception as e:
            print(f"[MainWindow._do_apply_theme] english_page._apply_theme 失败: {e}")

    # ===== 颜色映射: 浅色 <-> 深色 (只覆盖中性色与基础色) =====
    _COLOR_MAP_LIGHT_TO_DARK = {
        # 背景 (浅 -> 深)
        "#ffffff": "#1e293b",
        "#f8fafc": "#0f172a",
        "#fafafa": "#0f172a",
        "#f9fafb": "#0f172a",
        "#f1f5f9": "#334155",
        "#f3f4f6": "#1e293b",
        "#faf5ff": "#1e1b3a",
        "#eef2ff": "#1e1b3a",
        "#fef3c7": "#3f2d10",
        "#d1fae5": "#0d3a2c",
        "#fee2e2": "#3a1717",
        "#fef2f2": "#3a1717",
        "#f5f3ff": "#1e1b3a",
        # 边框 (浅 -> 深)
        "#e2e8f0": "#334155",
        "#cbd5e1": "#475569",
        "#e5e7eb": "#334155",
        "#d1d5db": "#475569",
        # 文字 (深 -> 浅)
        "#0f172a": "#f1f5f9",
        "#111827": "#f1f5f9",
        "#1f2937": "#e2e8f0",
        "#374151": "#cbd5e1",
        "#475569": "#cbd5e1",
        "#334155": "#94a3b8",
        "#64748b": "#94a3b8",
        "#94a3b8": "#64748b",
        # 蓝 (主色变深色版)
        "#2563eb": "#3b82f6",
        "#1d4ed8": "#2563eb",
        "#1e3a8a": "#bfdbfe",
        "#1e40af": "#93c5fd",
        "#3b82f6": "#60a5fa",
        "#60a5fa": "#3b82f6",
        "#bfdbfe": "#3b82f6",
        "#dbeafe": "#1e3a8a",
        # 紫
        "#6366f1": "#818cf8",
        "#8b5cf6": "#a78bfa",
        "#a855f7": "#c084fc",
        "#7c3aed": "#8b5cf6",
        # 状态色
        "#10b981": "#34d399",
        "#059669": "#10b981",
        "#065f46": "#6ee7b7",
        "#16a34a": "#22c55e",
        "#15803d": "#16a34a",
        "#dc2626": "#f87171",
        "#b91c1c": "#ef4444",
        "#991b1b": "#fca5a5",
        "#f59e0b": "#fbbf24",
        "#d97706": "#f59e0b",
        "#92400e": "#fcd34d",
    }
    # 深色 -> 浅色 (反向)
    _COLOR_MAP_DARK_TO_LIGHT = {v.lower(): k.lower() for k, v in _COLOR_MAP_LIGHT_TO_DARK.items()}

    def _recolor_all(self, theme_id: str):
        """递归遍历子组件, 对 setStyleSheet 过的做颜色替换 (light<->dark)"""
        import re as _re
        # 选对应方向的映射
        if theme_id == "dark":
            color_map = self._COLOR_MAP_LIGHT_TO_DARK
        else:
            color_map = self._COLOR_MAP_DARK_TO_LIGHT
        sorted_keys = sorted(color_map.keys(), key=len, reverse=True)
        pat = _re.compile(
            "(" + "|".join(_re.escape(k) for k in sorted_keys) + ")",
            _re.IGNORECASE,
        )

        def _sub(m):
            return color_map[m.group(1).lower()]

        def _walk(w):
            try:
                ss = w.styleSheet()
                if ss:
                    new_ss = pat.sub(_sub, ss)
                    if new_ss != ss:
                        w.setStyleSheet(new_ss)
            except Exception:
                pass
            for c in w.children():
                _walk(c)

        try:
            _walk(self)
        except Exception:
            pass

    def title_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def title_mouse_move(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            if self.isMaximized():
                self.showNormal()
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def title_mouse_release(self, event):
        self._drag_pos = None
        event.accept()


# ===========================================================
# main
# ===========================================================
def _install_crash_logger() -> None:
    """闪退/卡死兜底: 所有未捕获异常写进 image/crash.log, 也写 stderr"""
    import sys
    import traceback
    from datetime import datetime
    try:
        from pathlib import Path
        log_dir = Path(__file__).resolve().parent / "image"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "crash.log"
    except Exception:
        log_path = "crash.log"

    def _hook(etype, evalue, tb):
        try:
            lines = traceback.format_exception(etype, evalue, tb)
            text = "".join(lines)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(str(log_path), "a", encoding="utf-8") as f:
                f.write(f"\n=============== CRASH {stamp} ===============\n")
                f.write(text)
            # 也打到控制台
            print(text, file=sys.stderr)
            try:
                # 崩了也给个弹窗, 避免“一直卡在竖线没反应”
                from PyQt5.QtWidgets import QMessageBox
                from PyQt5.Qt import QApplication
                app_inst = QApplication.instance()
                if app_inst is None:
                    _ = QApplication(sys.argv)
                QMessageBox.critical(None, "程序崩溃", f"已写入错误日志到:\n{log_path}\n\n把下面内容发给我:\n\n{text[:2000]}")
            except Exception:
                pass
        except Exception:
            # logger 自己崩就别再抛了
            pass
        # 最后仍按默认方式退出
        sys.__excepthook__(etype, evalue, tb)

    sys.excepthook = _hook

    # threading 异常也抓 (pywebview 线程里崩默认会静默)
    try:
        import threading
        _orig_run = threading.Thread.run

        def _patched_run(self):
            try:
                _orig_run(self)
            except Exception:
                import sys as _sys2
                _hook(*_sys2.exc_info())
                raise
        threading.Thread.run = _patched_run  # type: ignore
    except Exception:
        pass


def main() -> None:
    _install_crash_logger()
    # ============= 启动前环境变量兜底 (彻底避免 "no Qt platform plugin could be initialized") =============
    # 在导入 QtWidgets / 创建 QApplication 之前设置:
    #   - PATH              : 加 PyQt5/Qt5/bin 与 qtwebengine 的 bin, 保证 DLL 被找到
    #   - QT_QPA_PLATFORM_PLUGIN_PATH : 精确指向 PyQt5/Qt5/plugins/platforms (qwindows.dll 所在)
    #   - QTWEBENGINEPROCESS_PATH     : QtWebEngineProcess.exe 绝对路径
    #   - QTWEBENGINE_CHROMIUM_FLAGS  : 关沙盒 + 自动播放 + 解码开关
    import os as _os
    _add_paths: list[str] = []
    try:
        import PyQt5 as _PyQt5
        _pyqt5_dir = _os.path.dirname(_PyQt5.__file__)
        _qt5_dir = _os.path.join(_pyqt5_dir, "Qt5")
        # PyPI 版标准结构:  Qt5/bin  Qt5/plugins/platforms  Qt5/resources
        _qt5_bin = _os.path.join(_qt5_dir, "bin")
        _qt5_platforms = _os.path.join(_qt5_dir, "plugins", "platforms")
        _qt5_translations = _os.path.join(_qt5_dir, "translations")
        # QtWebEngine 资源 & 可执行文件 (PyQtWebEngine-Qt5 提供)
        try:
            import PyQt5.QtWebEngineWidgets as _
            _qt5_web_bin = _os.path.join(_qt5_dir, "bin")
        except Exception:
            _qt5_web_bin = _qt5_bin
        _add_paths += [p for p in [_qt5_bin, _qt5_web_bin] if _os.path.isdir(p)]
        if _os.path.isdir(_qt5_platforms):
            _os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _qt5_platforms
        if _os.path.isdir(_qt5_translations):
            _os.environ.setdefault("QT_TRANSLATIONS_DIR", _qt5_translations)
        # QtWebEngineProcess.exe 可能在 PyQt5/Qt5/bin, 也可能在 PyQt5/Qt5/libexec (PyPI 5.15 一般是 bin)
        for _cand in [
            _os.path.join(_qt5_bin, "QtWebEngineProcess.exe"),
            _os.path.join(_qt5_dir, "libexec", "QtWebEngineProcess.exe"),
        ]:
            if _os.path.isfile(_cand):
                _os.environ["QTWEBENGINEPROCESS_PATH"] = _cand
                break
        # 资源 (QtWebEngineResources.pak / icudtl.dat) 搜索路径
        _qt5_res = _os.path.join(_qt5_dir, "resources")
        if _os.path.isdir(_qt5_res):
            _os.environ.setdefault("QTWEBENGINE_RESOURCES_DIR", _qt5_res)
        # 若是 Anaconda 式结构 (DLL 在 Anaconda3/Library/bin) 也加上 (作为兜底兼容)
        import site as _site
        for _sp in _site.getsitepackages():
            _lib_bin = _os.path.normpath(_os.path.join(_sp, "..", "..", "Library", "bin"))
            if _os.path.isdir(_lib_bin):
                _add_paths.append(_lib_bin)
            _lib_platforms = _os.path.normpath(
                _os.path.join(_sp, "..", "..", "Library", "plugins", "platforms")
            )
            if _os.path.isdir(_lib_platforms) and "QT_QPA_PLATFORM_PLUGIN_PATH" not in _os.environ:
                _os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _lib_platforms
    except Exception:
        pass
    if _add_paths:
        _cur_path = _os.environ.get("PATH", "")
        _os.environ["PATH"] = _os.pathsep.join(_add_paths + [_cur_path]) if _cur_path else _os.pathsep.join(_add_paths)
    # Chromium flags (Windows 兼容版, 移除 Linux 专属 VaapiVideoDecoder 等)
    _flags = (
        _os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        + " --no-sandbox --disable-gpu-sandbox"
        + " --autoplay-policy=no-user-gesture-required"
        + " --enable-features=PlatformHEVCDecoder,MediaFoundationVideoCapture,HardwareMediaKeyHandling,MediaSessionService,VideoPlaybackQuality"
        + " --ignore-gpu-blocklist"
    )
    _os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _flags
    # 强制 QtMultimedia 用 Windows Media Foundation 后端 (走系统已安装的解码器)
    _os.environ.setdefault("QT_MULTIMEDIA_BACKEND", "windowsmediafoundation")
    # GL / DPI / 共享上下文
    try:
        QApplication.setAttribute(Qt.AA_UseOpenGLES, True)
    except Exception:
        pass
    try:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    # ----- 启用 QWebEngine (Chromium) 硬件加速, 让视频能播 -----
    # 这两个环境变量必须在 QApplication() 之前设置
    try:
        import os as _os
        _os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            "--enable-features=VaapiVideoDecoder --use-gl=desktop --ignore-gpu-blocklist "
            "--enable-gpu-rasterization --enable-zero-copy --enable-accelerated-2d-canvas "
            "--autoplay-policy=no-user-gesture-required"
        )
        # Windows: 关闭 Edge WebView2 的硬件加速有时反而更稳, 但开 GL 可以解决白屏
        _os.environ["QT_OPENGL"] = "desktop"
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
