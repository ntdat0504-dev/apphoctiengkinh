# -*- coding: utf-8 -*-
"""
Ứng dụng di động: BÉ HỌC TIẾNG KINH OFFLINE
Công nghệ: Python + Kivy thuần (100% Offline, phong cách Duolingo Candy UI)
Phiên bản hoàn chỉnh tối ưu cho Pydroid 3 & Android:
  - Khắc phục triệt để lỗi hiển thị, lỗi font chữ và tỷ lệ màn hình
  - Nạp dữ liệu an toàn chống lỗi KeyError: 0 (VocabularyDataLoader)
  - Hàng đợi phát âm thanh tuần tự (không chồng chéo âm thanh)
  - Đa luồng AI hỗ trợ TFLite và Top-K Matching thông minh
"""

import os
import json
import random
import threading
import unicodedata

from kivy.app import App
from kivy.lang import Builder
from kivy.properties import StringProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.camera import Camera
from kivy.core.audio import SoundLoader
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform

# ---------------------------------------------------------------------------
# CẤU HÌNH HIỂN THỊ TOÀN MÀN HÌNH (Khắc phục lỗi app bị co một góc trên Android)
# ---------------------------------------------------------------------------
try:
    Window.size = (400, 711) # Kích thước chuẩn dọc điện thoại
    Window.clearcolor = (1.0, 0.99, 0.96, 1.0)
except Exception:
    pass

# ---------------------------------------------------------------------------
# 1. NẠP THƯ VIỆN AI ĐA NỀN TẢNG (Tự động dò tìm trình thông dịch TFLite)
# ---------------------------------------------------------------------------
Interpreter = None
AI_BACKEND = None

for _mod_name, _label in (
    ('ai_edge_litert.interpreter', 'ai-edge-litert'),
    ('tflite_runtime.interpreter', 'tflite-runtime'),
    ('tensorflow.lite', 'tensorflow-lite'),
):
    try:
        _mod = __import__(_mod_name, fromlist=['Interpreter'])
        Interpreter = getattr(_mod, 'Interpreter')
        AI_BACKEND = _label
        break
    except Exception:
        continue

try:
    from plyer import tts as plyer_tts
    PLYER_TTS_AVAILABLE = True
except Exception:
    plyer_tts = None
    PLYER_TTS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    NUMPY_AVAILABLE = False

AI_READY = (Interpreter is not None) and PIL_AVAILABLE and NUMPY_AVAILABLE

# Nhập hàm lưu/đọc từ vựng cá nhân từ vocabulary_store (nếu có)
try:
    from vocabulary_store import load_saved_ids, save_saved_ids
except Exception:
    def load_saved_ids(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw = data.get('saved_ids') if isinstance(data, dict) else data
            if isinstance(raw, list):
                return [v for v in raw if isinstance(v, str)], None
            return [], None
        except Exception:
            return [], None

    def save_saved_ids(path, ids):
        try:
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'saved_ids': list(dict.fromkeys(ids))},
                          f, ensure_ascii=False, indent=2)
            return None
        except OSError as exc:
            return 'không ghi được tệp từ đã lưu (%s).' % exc

IS_ANDROID = (platform == 'android')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURED_IMAGE_NAME = 'captured_temp.png'
AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.wav', '.ogg')


def get_writable_dir():
    if IS_ANDROID:
        try:
            app = App.get_running_app()
            if app is not None and getattr(app, 'user_data_dir', None):
                return app.user_data_dir
        except Exception:
            pass
    return BASE_DIR


def get_vocabulary_json_path():
    return os.path.join(BASE_DIR, 'data', 'sample_vocabulary.json')


def get_model_path():
    return os.path.join(BASE_DIR, 'data', 'mobilenet_v2.tflite')


def get_saved_vocabulary_path():
    if IS_ANDROID:
        return os.path.join(get_writable_dir(), 'saved_vocabulary.json')
    return os.path.join(BASE_DIR, 'data', 'saved_vocabulary.json')


ETHNIC_LANGUAGES = {
    "H'Mông": 'mong',
    "Tày": 'tay',
    "Ê-đê": 'ede',
}
LANGUAGE_CYCLE = ["H'Mông", "Tày", "Ê-đê"]

AUDIO_ID_ALIASES = {
    'buffalo': 'con_trau', 'cow': 'con_bo', 'pig': 'con_heo',
    'chicken': 'con_ga', 'goat': 'con_de',
    'book': 'cuon_sach', 'notebook': 'cuon_vo', 'pen': 'cay_but_bi',
    'pencil': 'cay_but_chi', 'schoolbag': 'cai_cap_sach',
    'ruler': 'cay_thuoc_ke', 'chalk': 'vien_phan_trang', 'eraser': 'cuc_tay',
    'table': 'cai_ban', 'chair': 'cai_ghe', 'bed': 'cai_giuong',
    'fridge': 'cai_tu_lanh', 'pot': 'cai_noi', 'pan': 'cai_chao',
    'small_bowl': 'cai_chen', 'big_bowl': 'cai_to', 'phone': 'cai_dien_thoai',
    'tv': 'cai_ti_vi', 'desktop': 'cai_may_tinh_ban',
    'laptop': 'cai_may_tinh_xach_tay',
}


def find_audio_file(word_id, language_folder):
    if not word_id or not language_folder:
        return None
    folder = os.path.join(BASE_DIR, 'assets', 'audio', language_folder)
    candidates = [str(word_id), AUDIO_ID_ALIASES.get(str(word_id), '')]
    for candidate_id in candidates:
        if not candidate_id:
            continue
        for ext in AUDIO_EXTENSIONS:
            path = os.path.join(folder, candidate_id + ext)
            if os.path.isfile(path):
                return path
    return None


# ---------------------------------------------------------------------------
# 2. BẢNG ÁNH XẠ IMAGENET MỞ RỘNG (Bao phủ cả 1000-class và 1001-class offset)
# ---------------------------------------------------------------------------
IMAGENET_TO_APP_MAP = {
    7: 'chicken', 8: 'chicken', 9: 'chicken', 10: 'chicken',
    341: 'pig', 342: 'pig', 343: 'pig',
    344: 'buffalo', 345: 'cow', 346: 'buffalo', 347: 'cow',
    348: 'goat', 349: 'goat', 350: 'goat', 351: 'goat', 352: 'goat', 353: 'goat',
    418: 'pen', 419: 'pen', 563: 'pen', 564: 'pen', 749: 'pen', 750: 'pen',
    449: 'pencil', 450: 'pencil', 710: 'pencil', 711: 'pencil',
    767: 'eraser', 768: 'eraser', 769: 'ruler', 770: 'ruler', 818: 'ruler', 819: 'ruler',
    414: 'schoolbag', 415: 'schoolbag', 636: 'schoolbag', 637: 'schoolbag', 748: 'schoolbag',
    454: 'book', 455: 'book', 921: 'book', 922: 'book',
    500: 'notebook', 501: 'notebook', 549: 'notebook', 550: 'notebook',
    487: 'phone', 488: 'phone', 528: 'phone', 529: 'phone', 605: 'phone', 606: 'phone',
    620: 'laptop', 621: 'laptop', 681: 'laptop', 682: 'laptop',
    508: 'desktop', 509: 'desktop', 527: 'desktop', 528: 'desktop',
    664: 'desktop', 665: 'desktop', 673: 'desktop', 674: 'desktop', 782: 'desktop', 783: 'desktop',
    851: 'tv', 852: 'tv', 598: 'tv', 599: 'tv',
    526: 'table', 532: 'table', 533: 'table', 736: 'table',
    423: 'chair', 558: 'chair', 559: 'chair', 765: 'chair', 766: 'chair', 857: 'chair',
    403: 'bed', 404: 'bed', 516: 'bed', 831: 'bed', 832: 'bed',
    760: 'fridge', 762: 'fridge', 763: 'fridge',
    494: 'pot', 495: 'pot', 539: 'pot', 540: 'pot', 849: 'pot', 850: 'pot',
    567: 'pan', 568: 'pan', 906: 'pan', 907: 'pan',
    504: 'small_bowl', 505: 'small_bowl', 968: 'small_bowl', 969: 'small_bowl',
    659: 'big_bowl', 660: 'big_bowl', 809: 'big_bowl', 810: 'big_bowl', 923: 'big_bowl',
}

EMOJI_BY_ID = {
    'buffalo': '🐃', 'cow': '🐂', 'pig': '🐖', 'chicken': '🐔', 'goat': '🐐',
    'book': '📖', 'notebook': '📓', 'pen': '🖊️', 'pencil': '✏️',
    'schoolbag': '🎒', 'ruler': '📏', 'chalk': '🖍️', 'eraser': '🧽',
    'table': '🪑', 'chair': '🪑', 'bed': '🛏️', 'fridge': '🧊',
    'pot': '🍲', 'pan': '🍳', 'small_bowl': '🍚', 'big_bowl': '🥣',
    'phone': '📱', 'tv': '📺', 'desktop': '🖥️', 'laptop': '💻',
    'cay_thuoc': '💊',
}


def slugify(text):
    if not isinstance(text, str) or not text.strip():
        return ''
    nfkd = unicodedata.normalize('NFD', text.strip().lower())
    plain = ''.join(ch for ch in nfkd if not unicodedata.combining(ch))
    plain = plain.replace('đ', 'd')
    out = []
    for ch in plain:
        if ch.isalnum():
            out.append(ch)
        elif ch in (' ', '-', '_'):
            out.append('_')
    slug = ''.join(out)
    while '__' in slug:
        slug = slug.replace('__', '_')
    return slug.strip('_') or 'tu_chua_ro'


FALLBACK_VOCABULARY = [
    {'id': 'buffalo', 'vietnamese': 'con trâu', 'emoji': '🐃'},
    {'id': 'cow', 'vietnamese': 'con bò', 'emoji': '🐂'},
    {'id': 'pig', 'vietnamese': 'con heo (con lợn)', 'emoji': '🐖'},
    {'id': 'chicken', 'vietnamese': 'con gà', 'emoji': '🐔'},
    {'id': 'goat', 'vietnamese': 'con dê', 'emoji': '🐐'},
    {'id': 'book', 'vietnamese': 'cuốn sách', 'emoji': '📖'},
    {'id': 'notebook', 'vietnamese': 'cuốn vở', 'emoji': '📓'},
    {'id': 'pen', 'vietnamese': 'cây bút bi', 'emoji': '🖊️'},
    {'id': 'pencil', 'vietnamese': 'cây bút chì', 'emoji': '✏️'},
    {'id': 'schoolbag', 'vietnamese': 'cái cặp sách', 'emoji': '🎒'},
    {'id': 'ruler', 'vietnamese': 'cây thước kẻ', 'emoji': '📏'},
    {'id': 'chalk', 'vietnamese': 'viên phấn trắng', 'emoji': '🖍️'},
    {'id': 'eraser', 'vietnamese': 'cục tẩy (cục gôm)', 'emoji': '🧽'},
    {'id': 'table', 'vietnamese': 'cái bàn', 'emoji': '🪑'},
    {'id': 'chair', 'vietnamese': 'cái ghế', 'emoji': '🪑'},
    {'id': 'bed', 'vietnamese': 'cái giường', 'emoji': '🛏️'},
    {'id': 'fridge', 'vietnamese': 'cái tủ lạnh', 'emoji': '🧊'},
    {'id': 'pot', 'vietnamese': 'cái nồi', 'emoji': '🍲'},
    {'id': 'pan', 'vietnamese': 'cái chảo', 'emoji': '🍳'},
    {'id': 'small_bowl', 'vietnamese': 'cái chén (cái bát nhỏ)', 'emoji': '🍚'},
    {'id': 'big_bowl', 'vietnamese': 'cái tô (cái bát lớn)', 'emoji': '🥣'},
    {'id': 'phone', 'vietnamese': 'cái điện thoại', 'emoji': '📱'},
    {'id': 'tv', 'vietnamese': 'cái ti vi', 'emoji': '📺'},
    {'id': 'desktop', 'vietnamese': 'cái máy tính bàn', 'emoji': '🖥️'},
    {'id': 'laptop', 'vietnamese': 'cái máy tính xách tay (laptop)', 'emoji': '💻'},
    {'id': 'cay_thuoc', 'vietnamese': 'cây thuốc', 'emoji': '💊'},
]


class VocabularyDataLoader:
    VOCAB_CONTAINER_KEYS = (
        'tu_vung', 'vocabulary', 'vocab', 'words',
        'items', 'entries', 'data', 'danh_sach',
    )
    SKIP_KEYS = {'meta', 'nguon', 'ghi_chu', 'note', 'notes', 'info', 'version'}

    @classmethod
    def normalize_entry(cls, raw, index=0):
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = {'vietnamese': raw}
        elif isinstance(raw, bool):
            return None
        elif isinstance(raw, (int, float)):
            raw = {'vietnamese': str(raw)}
        elif isinstance(raw, list):
            if not raw:
                return None
            raw = {
                'id': raw[0] if len(raw) > 0 else None,
                'vietnamese': raw[1] if len(raw) > 1 else None,
            }
        if not isinstance(raw, dict):
            return None

        word_id = raw.get('id', raw.get('ID', raw.get('key', raw.get('slug'))))
        if isinstance(word_id, bool):
            word_id = None
        elif isinstance(word_id, (int, float)):
            word_id = str(word_id)
        if not isinstance(word_id, str) or not word_id.strip():
            word_id = slugify(
                raw.get('vietnamese') or raw.get('name') or raw.get('word') or ''
            )
        if not word_id:
            word_id = 'tu_%d' % index
        word_id = word_id.strip()

        vn_name = raw.get('vietnamese', raw.get('vn', raw.get('name', raw.get('word'))))
        if not isinstance(vn_name, str) or not vn_name.strip():
            vn_name = word_id.replace('_', ' ').capitalize()
        vn_name = vn_name.strip()

        emoji = raw.get('emoji')
        if not isinstance(emoji, str) or not emoji.strip():
            emoji = EMOJI_BY_ID.get(word_id, '📦')

        ethnic_words = {}
        for key in ('ethnic_words', 'ethnic_data', 'translations', 'translation'):
            value = raw.get(key)
            if isinstance(value, dict):
                for language, word in value.items():
                    if not isinstance(language, str):
                        continue
                    if isinstance(word, dict):
                        word = word.get('word', word.get('text', word.get('value')))
                    if isinstance(word, str) and word.strip():
                        ethnic_words[language.strip()] = word.strip()
        legacy_language = raw.get('ethnic_language')
        legacy_word = raw.get('ethnic_word')
        if (isinstance(legacy_language, str) and isinstance(legacy_word, str)
                and legacy_word.strip()):
            ethnic_words.setdefault(legacy_language.strip(), legacy_word.strip())
        ethnic_data = {lang: {'word': word} for lang, word in ethnic_words.items()}

        entry = {
            'id': word_id,
            'vietnamese': vn_name,
            'emoji': emoji,
            'ethnic_words': ethnic_words,
            'ethnic_data': ethnic_data,
            'translation_verified': bool(raw.get('translation_verified', bool(ethnic_words))),
        }
        category = raw.get('category')
        if isinstance(category, str) and category.strip():
            entry['category'] = category.strip()
        return entry

    @classmethod
    def extract_raw_list(cls, data):
        if isinstance(data, list):
            return data
        if isinstance(data, tuple):
            return list(data)
        if isinstance(data, dict):
            for key in cls.VOCAB_CONTAINER_KEYS:
                value = data.get(key)
                if isinstance(value, list):
                    return value
            if any(key in data for key in ('vietnamese', 'word', 'name', 'id')):
                return [data]
            mapping = {k: v for k, v in data.items() if k not in cls.SKIP_KEYS}
            if mapping:
                out = []
                for key, value in mapping.items():
                    if isinstance(value, dict):
                        entry = dict(value)
                        entry.setdefault('id', key)
                        out.append(entry)
                    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
                        out.append({'id': key, 'vietnamese': str(value)})
                if out:
                    return out
        return None

    @classmethod
    def fallback_list(cls):
        entries = []
        for raw in FALLBACK_VOCABULARY:
            entry = cls.normalize_entry(raw, len(entries))
            if isinstance(entry, dict):
                entries.append(entry)
        if not entries:
            entries = [{
                'id': 'buffalo', 'vietnamese': 'con trâu', 'emoji': '🐃',
                'ethnic_words': {}, 'ethnic_data': {}, 'translation_verified': False,
            }]
        return entries

    @classmethod
    def load(cls, json_path, merge_audio_backed=True):
        raw_list = None
        try:
            if os.path.isfile(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                raw_list = cls.extract_raw_list(data)
        except Exception:
            raw_list = None

        entries = []
        if isinstance(raw_list, list):
            for index, raw in enumerate(raw_list):
                entry = cls.normalize_entry(raw, index)
                if isinstance(entry, dict):
                    entries.append(entry)

        if not entries:
            entries = cls.fallback_list()

        unique_entries, seen_ids = [], set()
        for entry in entries:
            wid = entry.get('id')
            if wid and wid not in seen_ids:
                seen_ids.add(wid)
                unique_entries.append(entry)
        entries = unique_entries

        if merge_audio_backed:
            for raw in FALLBACK_VOCABULARY:
                wid = raw.get('id') if isinstance(raw, dict) else None
                if isinstance(wid, str) and wid and wid not in seen_ids:
                    entry = cls.normalize_entry(raw, len(entries))
                    if isinstance(entry, dict):
                        entries.append(entry)
                        seen_ids.add(wid)

        if not isinstance(entries, list) or len(entries) == 0:
            entries = cls.fallback_list()
        return entries


def find_word_by_id(vocab, word_id):
    if isinstance(vocab, list):
        for item in vocab:
            if isinstance(item, dict) and str(item.get('id', '')) == str(word_id):
                return item
    return None


def get_vietnamese(item):
    if isinstance(item, dict):
        name = item.get('vietnamese')
        if isinstance(name, str) and name.strip():
            return name
        wid = item.get('id')
        if isinstance(wid, str) and wid:
            return wid.replace('_', ' ').capitalize()
    return 'Không rõ'


def get_emoji(item):
    if isinstance(item, dict):
        emoji = item.get('emoji')
        if isinstance(emoji, str) and emoji.strip():
            return emoji
        wid = item.get('id')
        if isinstance(wid, str) and wid in EMOJI_BY_ID:
            return EMOJI_BY_ID[wid]
    return '📦'


def get_ethnic_display(item, language):
    if isinstance(item, dict):
        data = item.get('ethnic_words')
        if not isinstance(data, dict):
            nested = item.get('ethnic_data')
            if isinstance(nested, dict):
                data = {lang: val.get('word')
                        for lang, val in nested.items() if isinstance(val, dict)}
        if isinstance(data, dict):
            if isinstance(language, str):
                value = data.get(language)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for lang in sorted(data.keys()):
                value = data.get(lang)
                if isinstance(value, str) and value.strip():
                    return '(%s) %s' % (lang, value.strip())
    return 'Chưa có bản dịch'


class VocabCard(Button):
    vid = StringProperty('')
    emoji_text = StringProperty('📦')
    vn_text = StringProperty('')
    dt_text = StringProperty('Chưa có bản dịch')
    badge_text = StringProperty('CHƯA LƯU')


class SaveDialog(BoxLayout):
    vid = StringProperty('')
    emoji_text = StringProperty('📦')
    vn_text = StringProperty('')
    dt_text = StringProperty('Chưa có bản dịch')
    audio_text = StringProperty('')


KV = '''
<VocabCard>:
    vid: ''
    emoji_text: '📦'
    vn_text: ''
    dt_text: 'Chưa có bản dịch'
    badge_text: 'CHƯA LƯU'
    background_color: 0, 0, 0, 0
    size_hint: (1, None)
    height: dp(96)
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14,]
        Color:
            rgba: (0.88, 0.88, 0.92, 1)
        Line:
            rounded_rectangle: (*self.pos, *self.size, 14)
            width: 1
    BoxLayout:
        pos: self.parent.pos
        size: self.parent.size
        orientation: 'horizontal'
        padding: [10, 8, 10, 8]
        spacing: 8
        Label:
            text: root.emoji_text
            font_size: '30sp'
            size_hint_x: None
            width: dp(44)
        BoxLayout:
            orientation: 'vertical'
            spacing: 2
            Label:
                text: root.vn_text
                font_size: '14sp'
                bold: True
                color: (0.1, 0.1, 0.1, 1)
                halign: 'left'
                valign: 'middle'
                on_size: self.text_size = self.size
            Label:
                text: root.dt_text
                font_size: '11sp'
                color: (0.55, 0.45, 0.2, 1)
                halign: 'left'
                valign: 'middle'
                on_size: self.text_size = self.size
        Label:
            text: root.badge_text
            font_size: '10sp'
            bold: True
            color: (0.2, 0.65, 0.05, 1) if root.badge_text == 'ĐÃ LƯU ⭐' else (0.6, 0.6, 0.65, 1)
            size_hint_x: None
            width: dp(66)
            halign: 'right'
            valign: 'middle'
            on_size: self.text_size = self.size

<SaveDialog>:
    vid: ''
    emoji_text: '📦'
    vn_text: ''
    dt_text: 'Chưa có bản dịch'
    audio_text: ''
    orientation: 'vertical'
    padding: dp(14)
    spacing: dp(10)
    Label:
        text: root.emoji_text
        font_size: '42sp'
        size_hint_y: None
        height: dp(56)
    Label:
        text: root.vn_text
        font_size: '18sp'
        bold: True
        color: (0.1, 0.1, 0.1, 1)
    Label:
        text: root.dt_text
        font_size: '13sp'
        bold: True
        color: (0.85, 0.45, 0.05, 1)
    Label:
        text: root.audio_text
        font_size: '11sp'
        color: (0.5, 0.5, 0.55, 1)
    Button:
        id: save_btn
        text: '⭐ LƯU TỪ'
        bold: True
        size_hint_y: None
        height: dp(44)
        background_color: 0, 0, 0, 0
        canvas.before:
            Color:
                rgba: (0.68, 0.42, 0.92, 1)
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [10,]
    Button:
        id: close_btn
        text: 'ĐÓNG'
        bold: True
        size_hint_y: None
        height: dp(40)
        background_color: 0, 0, 0, 0
        canvas.before:
            Color:
                rgba: (0.8, 0.83, 0.87, 1)
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [10,]

<MainScreen>:
    name: 'main'
    on_pre_enter: root._sync_save_badge()
    canvas.before:
        Color:
            rgba: (1.0, 0.99, 0.96, 1.0)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        padding: 12
        spacing: 8

        BoxLayout:
            size_hint: (1, 0.08)
            orientation: 'horizontal'
            spacing: 10
            
            BoxLayout:
                orientation: 'vertical'
                size_hint: (0.6, 1)
                spacing: 2
                BoxLayout:
                    orientation: 'horizontal'
                    spacing: 4
                    Label:
                        text: '🎈'
                        font_size: '20sp'
                        size_hint_x: None
                        width: 25
                    Label:
                        text: 'BÉ HỌC TIẾNG KINH'
                        font_size: '15sp'
                        bold: True
                        color: (0.1, 0.1, 0.1, 1)
                        halign: 'left'
                        valign: 'middle'
                        on_size: self.text_size = self.size
                
                Label:
                    text: '🚫☁️ OFFLINE 100%'
                    font_size: '11sp'
                    color: (0.2, 0.65, 0.05, 1)
                    bold: True
                    halign: 'left'
                    valign: 'middle'
                    on_size: self.text_size = self.size

            AnchorLayout:
                size_hint: (0.4, 1)
                Button:
                    background_color: 0, 0, 0, 0
                    size_hint: (1, 0.85)
                    on_press: root.manager.current = 'library'
                    canvas.before:
                        Color:
                            rgba: (0.68, 0.42, 0.92, 1)
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [18,]
                    BoxLayout:
                        pos: self.parent.pos
                        size: self.parent.size
                        orientation: 'horizontal'
                        spacing: 4
                        halign: 'center'
                        valign: 'middle'
                        Label:
                            text: '📚'
                            font_size: '16sp'
                            size_hint_x: None
                            width: 24
                        Label:
                            text: 'Thư viện'
                            font_size: '13sp'
                            bold: True
                            color: (1, 1, 1, 1)

        BoxLayout:
            size_hint: (1, 0.11)
            orientation: 'horizontal'
            spacing: 10

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.select_direction('kinh')
                canvas.before:
                    Color:
                        rgba: (1, 1, 1, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [16,]
                    Color:
                        rgba: (0.98, 0.68, 0.12, 1)
                    Line:
                        rounded_rectangle: (*self.pos, *self.size, 16)
                        width: 2
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 4
                    spacing: 2
                    Label:
                        text: 'VN'
                        font_size: '16sp'
                        bold: True
                        color: (0.15, 0.15, 0.15, 1)
                    Label:
                        text: 'Tiếng Kinh'
                        font_size: '12sp'
                        bold: True
                        color: (0.25, 0.25, 0.25, 1)
                    AnchorLayout:
                        size_hint: (1, None)
                        height: 18
                        BoxLayout:
                            size_hint: (None, None)
                            size: (90, 16)
                            canvas.before:
                                Color:
                                    rgba: (1.0, 0.9, 0.7, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [6,]
                            Label:
                                text: 'Chiều đọc gốc'
                                font_size: '9.5sp'
                                color: (0.75, 0.4, 0.05, 1)
                                bold: True

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.select_direction('ethnic')
                canvas.before:
                    Color:
                        rgba: (1, 1, 1, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [16,]
                    Color:
                        rgba: (0.8, 0.8, 0.8, 1)
                    Line:
                        rounded_rectangle: (*self.pos, *self.size, 16)
                        width: 1
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 4
                    spacing: 2
                    Label:
                        text: '🏡'
                        font_size: '16sp'
                    Label:
                        text: 'Tiếng Dân Tộc'
                        font_size: '12sp'
                        bold: True
                        color: (0.25, 0.25, 0.25, 1)
                    AnchorLayout:
                        size_hint: (1, None)
                        height: 18
                        Button:
                            id: ethnic_lang_chip
                            background_color: 0, 0, 0, 0
                            size_hint: (None, None)
                            size: (115, 18)
                            on_press: root.cycle_ethnic_language()
                            canvas.before:
                                Color:
                                    rgba: (0.9, 0.94, 0.98, 1)
                                RoundedRectangle:
                                    pos: self.pos
                                    size: self.size
                                    radius: [6,]
                            BoxLayout:
                                pos: self.parent.pos
                                size: self.parent.size
                                Label:
                                    id: ethnic_lang_label
                                    text: "👗 Tiếng H'Mông ▼"
                                    font_size: '9.5sp'
                                    color: (0.1, 0.35, 0.65, 1)
                                    bold: True

        BoxLayout:
            id: camera_outer_layout
            size_hint: (1, 0.37)
            canvas.before:
                Color:
                    rgba: (0.07, 0.11, 0.18, 1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [20,]
                Color:
                    rgba: (1.0, 0.82, 0.15, 1)
                Line:
                    rounded_rectangle: (*self.pos, *self.size, 20)
                    width: 1.2
            FloatLayout:
                id: camera_container
                size_hint: (1, 1)
                
                BoxLayout:
                    size_hint: (None, None)
                    size: (150, 22)
                    pos_hint: {'x': 0.03, 'top': 0.93}
                    padding: [4, 2, 4, 2]
                    canvas.before:
                        Color:
                            rgba: (0.15, 0.2, 0.3, 0.9)
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [10,]
                    Label:
                        id: ai_status_label
                        text: '● TRẠNG THÁI: IDLE'
                        font_size: '9.5sp'
                        bold: True
                        color: (0.3, 0.9, 0.1, 1)

                BoxLayout:
                    id: camera_placeholder
                    orientation: 'vertical'
                    size_hint: (0.8, 0.6)
                    pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                    spacing: 6
                    Label:
                        text: '📷'
                        font_size: '36sp'
                    Label:
                        text: 'Đôi Mắt AI Đang Chờ'
                        font_size: '14sp'
                        bold: True
                        color: (1, 1, 1, 1)
                        halign: 'center'
                    Label:
                        id: camera_hint_label
                        text: 'Bấm "📸 Bật/Tắt" để bắt đầu'
                        font_size: '11.5sp'
                        color: (0.7, 0.75, 0.85, 1)
                        halign: 'center'

        BoxLayout:
            size_hint: (1, 0.21)
            padding: 8
            spacing: 10
            canvas.before:
                Color:
                    rgba: (1.0, 0.93, 0.73, 1)
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [18,]
            
            BoxLayout:
                size_hint: (0.28, 1)
                canvas.before:
                    Color:
                        rgba: (1, 1, 1, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [12,]
                Label:
                    id: vocab_emoji
                    text: '🐃'
                    font_size: '38sp'

            BoxLayout:
                orientation: 'vertical'
                size_hint: (0.72, 1)
                spacing: 2
                
                Label:
                    text: 'TỪ VỰNG AI NHẬN DIỆN'
                    font_size: '9.5sp'
                    color: (0.5, 0.4, 0.2, 1)
                    bold: True
                    halign: 'left'
                    valign: 'middle'
                    on_size: self.text_size = self.size

                Label:
                    id: vocab_vn_label
                    text: 'Con trâu'
                    font_size: '18sp'
                    bold: True
                    color: (0.1, 0.1, 0.1, 1)
                    halign: 'left'
                    valign: 'middle'
                    on_size: self.text_size = self.size

                Label:
                    id: vocab_ethnic_label
                    text: "H'Mông: tus twm"
                    font_size: '12sp'
                    bold: True
                    color: (0.95, 0.45, 0.05, 1)
                    halign: 'left'
                    valign: 'middle'
                    on_size: self.text_size = self.size

                BoxLayout:
                    size_hint: (1, 0.45)
                    spacing: 6
                    Button:
                        background_color: 0, 0, 0, 0
                        on_press: root.speak_word()
                        canvas.before:
                            Color:
                                rgba: (0.95, 0.24, 0.2, 1)
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [10,]
                        BoxLayout:
                            pos: self.parent.pos
                            size: self.parent.size
                            orientation: 'horizontal'
                            spacing: 4
                            halign: 'center'
                            valign: 'middle'
                            Label:
                                text: '🔊'
                                font_size: '13sp'
                                size_hint_x: None
                                width: 18
                            Label:
                                text: 'Nghe đọc'
                                font_size: '12sp'
                                bold: True
                                color: (1, 1, 1, 1)

                    Button:
                        background_color: 0, 0, 0, 0
                        on_press: root.toggle_save()
                        canvas.before:
                            Color:
                                rgba: (1.0, 0.98, 0.85, 1)
                            RoundedRectangle:
                                pos: self.pos
                                size: self.size
                                radius: [10,]
                            Color:
                                rgba: (0.9, 0.78, 0.2, 1)
                            Line:
                                rounded_rectangle: (*self.pos, *self.size, 10)
                                width: 1
                        BoxLayout:
                            pos: self.parent.pos
                            size: self.parent.size
                            orientation: 'horizontal'
                            spacing: 4
                            halign: 'center'
                            valign: 'middle'
                            Label:
                                text: '⭐'
                                font_size: '12sp'
                                size_hint_x: None
                                width: 16
                            Label:
                                id: save_btn_label
                                text: 'Lưu'
                                font_size: '11sp'
                                bold: True
                                color: (0.2, 0.2, 0.2, 1)

        BoxLayout:
            size_hint: (1, 0.12)
            spacing: 8

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.toggle_camera()
                canvas.before:
                    Color:
                        rgba: (0.34, 0.8, 0.04, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [14,]
                    Color:
                        rgba: (0.22, 0.58, 0.02, 1)
                    RoundedRectangle:
                        pos: (self.x, self.y - 3)
                        size: (self.width, 4)
                        radius: [0, 0, 10, 10]
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 2
                    spacing: 1
                    Label:
                        text: '📸'
                        font_size: '15sp'
                    Label:
                        text: 'Bật/Tắt'
                        font_size: '10.5sp'
                        bold: True
                        color: (1, 1, 1, 1)

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.capture_image()
                canvas.before:
                    Color:
                        rgba: (0.98, 0.75, 0.5, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [14,]
                    Color:
                        rgba: (0.82, 0.58, 0.32, 1)
                    RoundedRectangle:
                        pos: (self.x, self.y - 3)
                        size: (self.width, 4)
                        radius: [0, 0, 10, 10]
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 2
                    spacing: 1
                    Label:
                        text: '🎯'
                        font_size: '15sp'
                    Label:
                        text: 'Chụp ảnh'
                        font_size: '10.5sp'
                        bold: True
                        color: (0.25, 0.15, 0.05, 1)

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.run_ai_recognition()
                canvas.before:
                    Color:
                        rgba: (0.68, 0.85, 0.95, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [14,]
                    Color:
                        rgba: (0.45, 0.68, 0.82, 1)
                    RoundedRectangle:
                        pos: (self.x, self.y - 3)
                        size: (self.width, 4)
                        radius: [0, 0, 10, 10]
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 2
                    spacing: 1
                    Label:
                        text: '🔍'
                        font_size: '15sp'
                    Label:
                        text: 'Nhận diện'
                        font_size: '10.5sp'
                        bold: True
                        color: (0.05, 0.25, 0.38, 1)

            Button:
                background_color: 0, 0, 0, 0
                on_press: root.reset_app()
                canvas.before:
                    Color:
                        rgba: (0.8, 0.83, 0.87, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [14,]
                    Color:
                        rgba: (0.62, 0.66, 0.72, 1)
                    RoundedRectangle:
                        pos: (self.x, self.y - 3)
                        size: (self.width, 4)
                        radius: [0, 0, 10, 10]
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'vertical'
                    padding: 2
                    spacing: 1
                    Label:
                        text: '🔄'
                        font_size: '15sp'
                    Label:
                        text: 'Làm mới'
                        font_size: '10.5sp'
                        bold: True
                        color: (0.2, 0.22, 0.26, 1)

<LibraryScreen>:
    name: 'library'
    on_pre_enter: root.refresh_library()
    canvas.before:
        Color:
            rgba: (1.0, 0.99, 0.96, 1.0)
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        padding: 16
        spacing: 12
        BoxLayout:
            size_hint: (1, 0.08)
            orientation: 'horizontal'
            Button:
                background_color: 0, 0, 0, 0
                size_hint: (0.3, 1)
                on_press: root.manager.current = 'main'
                canvas.before:
                    Color:
                        rgba: (0.85, 0.85, 0.85, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [12,]
                BoxLayout:
                    pos: self.parent.pos
                    size: self.parent.size
                    orientation: 'horizontal'
                    spacing: 4
                    Label:
                        text: '↩️'
                        font_size: '14sp'
                    Label:
                        text: 'Quay lại'
                        font_size: '12sp'
                        bold: True
                        color: (0.2, 0.2, 0.2, 1)
            Label:
                text: '📚 TỪ VỰNG CỦA BÉ'
                font_size: '18sp'
                bold: True
                color: (0.15, 0.15, 0.2, 1)
                halign: 'center'
        Label:
            id: library_count_label
            text: 'Đang nạp dữ liệu...'
            font_size: '12sp'
            color: (0.45, 0.45, 0.5, 1)
            halign: 'center'
            size_hint_y: None
            height: dp(20)
        ScrollView:
            do_scroll_x: False
            do_scroll_y: True
            bar_width: dp(4)
            scroll_type: ['bars', 'content']
            GridLayout:
                id: library_grid
                cols: 1
                size_hint: (1, None)
                height: self.minimum_height
                spacing: dp(8)
                padding: [2, 0, 2, 16]
'''


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.vocabulary_list = []
        self.current_word = None
        self.camera_active = False
        self.camera_widget = None
        self.captured_image_path = None
        self.learning_direction = 'kinh'
        self.current_ethnic_language = "H'Mông"
        self._current_sound = None
        self._speak_queue = []
        self._scanning = False
        self._interpreter = None
        self._model_available = bool(AI_READY and os.path.isfile(get_model_path()))

        self.load_vocabulary()

    def load_vocabulary(self):
        self.vocabulary_list = VocabularyDataLoader.load(get_vocabulary_json_path())
        if not isinstance(self.vocabulary_list, list) or len(self.vocabulary_list) == 0:
            self.vocabulary_list = VocabularyDataLoader.fallback_list()

    def _safe_pick_random_word(self):
        vocab = self.vocabulary_list
        if isinstance(vocab, list) and len(vocab) > 0:
            for _ in range(5):
                item = random.choice(vocab)
                if isinstance(item, dict):
                    return item
        return None

    def select_direction(self, direction):
        if direction not in ('kinh', 'ethnic'):
            return
        self.learning_direction = direction
        if direction == 'kinh':
            self.ids.ai_status_label.text = '🧭 Chiều học: TIẾNG KINH → TIẾNG DÂN TỘC'
        else:
            self.ids.ai_status_label.text = '🧭 Chiều học: TIẾNG DÂN TỘC → TIẾNG KINH'

    def cycle_ethnic_language(self):
        try:
            index = LANGUAGE_CYCLE.index(self.current_ethnic_language)
        except ValueError:
            index = -1
        self.current_ethnic_language = LANGUAGE_CYCLE[(index + 1) % len(LANGUAGE_CYCLE)]
        self.ids.ethnic_lang_label.text = '👗 Tiếng %s ▼' % self.current_ethnic_language
        item = self.current_word
        if isinstance(item, dict):
            dt_word = get_ethnic_display(item, self.current_ethnic_language)
            self.ids.vocab_ethnic_label.text = 'Tiếng %s: %s' % (
                self.current_ethnic_language, dt_word)

    def toggle_camera(self):
        container = self.ids.camera_container
        placeholder = self.ids.camera_placeholder
        status_label = self.ids.ai_status_label

        if not self.camera_active:
            try:
                self.camera_widget = Camera(index=0, play=True, resolution=(640, 480))
                self.camera_widget.size_hint = (1, 1)
                if placeholder.parent is container:
                    container.remove_widget(placeholder)
                container.add_widget(self.camera_widget)
                self.camera_active = True
                status_label.text = '● TRẠNG THÁI: CAMERA_ON'
                self.ids.camera_hint_label.text = 'Đang xem qua camera...'
                print('Đã bật Camera thành công.')
            except Exception as exc:
                self.camera_widget = None
                self.camera_active = False
                status_label.text = '⚠️ LỖI CAMERA'
                self.ids.camera_hint_label.text = '⚠️ Không mở được camera\n(%s)' % exc
        else:
            if self.camera_widget is not None:
                try:
                    self.camera_widget.play = False
                    container.remove_widget(self.camera_widget)
                except Exception:
                    pass
                self.camera_widget = None
            if placeholder.parent is not container:
                container.add_widget(placeholder)
                self.ids.camera_hint_label.text = 'Bấm "📸 Bật/Tắt" để bắt đầu'
            self.camera_active = False
            status_label.text = '● TRẠNG THÁI: IDLE'

    def capture_image(self):
        if not self.camera_active or self.camera_widget is None:
            self.ids.ai_status_label.text = '📷 Hãy bấm Bật/Tắt camera trước'
            return
        try:
            if self.camera_widget.texture is None:
                self.ids.ai_status_label.text = '📷 Camera chưa sẵn sàng'
                return
            self.captured_image_path = os.path.join(get_writable_dir(), CAPTURED_IMAGE_NAME)
            self.camera_widget.export_to_png(self.captured_image_path)
            self.ids.ai_status_label.text = '● TRẠNG THÁI: CAPTURED'
            print('Đã chụp và lưu ảnh tại: %s' % self.captured_image_path)
        except Exception as exc:
            self.ids.ai_status_label.text = '⚠️ Lỗi chụp ảnh'
            print('Lỗi chụp ảnh: %s' % exc)

    def run_ai_recognition(self):
        status_label = self.ids.ai_status_label
        if self._scanning:
            status_label.text = '● TRẠNG THÁI: ĐANG QUÉT...'
            return

        if self.camera_active and self.camera_widget is not None and self.camera_widget.texture is not None:
            try:
                self.captured_image_path = os.path.join(get_writable_dir(), CAPTURED_IMAGE_NAME)
                self.camera_widget.export_to_png(self.captured_image_path)
            except Exception as exc:
                print('Không tự chụp được khung hình mới: %s' % exc)

        status_label.text = '● TRẠNG THÁI: ĐANG QUÉT...'
        self._model_available = bool(AI_READY and os.path.isfile(get_model_path()))
        has_photo = bool(self.captured_image_path) and os.path.isfile(self.captured_image_path)

        if AI_READY and self._model_available and has_photo:
            self._scanning = True
            Clock.schedule_once(lambda dt: self._start_inference_thread(), 0.25)
        else:
            Clock.schedule_once(self._finish_simulation_scan, 0.8)

    def _start_inference_thread(self):
        worker = threading.Thread(
            target=self._inference_worker,
            args=(self.captured_image_path,),
            daemon=True,
        )
        worker.start()

    def _finish_simulation_scan(self, dt):
        item = self._safe_pick_random_word()
        self._apply_result(item, 'MÔ PHỎNG — CHƯA CÓ THƯ VIỆN AI')

    def _inference_worker(self, image_path):
        result_word, note = self._run_real_inference(image_path)
        if not isinstance(result_word, dict):
            note = 'MÔ PHỎNG (%s)' % note
            Clock.schedule_once(
                lambda dt: self._apply_result(self._safe_pick_random_word(), note), 0)
        else:
            Clock.schedule_once(
                lambda dt: self._apply_result(result_word, note), 0)

    def _run_real_inference(self, image_path):
        try:
            if self._interpreter is None:
                self._interpreter = Interpreter(model_path=get_model_path())
                self._interpreter.allocate_tensors()
            input_detail = self._interpreter.get_input_details()[0]
            output_detail = self._interpreter.get_output_details()[0]
            in_h = int(input_detail['shape'][1])
            in_w = int(input_detail['shape'][2])

            image = Image.open(image_path).convert('RGB')
            w, h = image.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            image = image.crop((left, top, left + min_dim, top + min_dim)).resize((in_w, in_h))

            if input_detail['dtype'] == np.uint8:
                arr = np.asarray(image, dtype=np.uint8)
            else:
                arr = np.asarray(image, dtype=np.float32) / 127.5 - 1.0
            arr = np.expand_dims(arr, axis=0)

            self._interpreter.set_tensor(input_detail['index'], arr)
            self._interpreter.invoke()
            prediction = np.squeeze(self._interpreter.get_tensor(output_detail['index']))

            top_indices = [int(i) for i in np.argsort(prediction)[-5:][::-1]]
            for idx in top_indices:
                word_id = IMAGENET_TO_APP_MAP.get(idx) or IMAGENET_TO_APP_MAP.get(idx - 1)
                if word_id is not None:
                    word = find_word_by_id(self.vocabulary_list, word_id)
                    if isinstance(word, dict):
                        return word, 'AI THẬT (%s) — lớp #%d' % (AI_BACKEND, idx)

            return None, 'Top-5 chưa khớp từ vựng'
        except Exception as exc:
            return None, 'lỗi suy luận: %s' % exc

    def _apply_result(self, item, source_note):
        self._scanning = False
        status_label = self.ids.ai_status_label
        if not isinstance(item, dict):
            item = self._safe_pick_random_word()
        if not isinstance(item, dict):
            status_label.text = '⚠️ DANH SÁCH TRỐNG'
            return
        self.current_word = item
        vn_name = get_vietnamese(item)
        language = self.current_ethnic_language
        dt_word = get_ethnic_display(item, language)
        self.ids.vocab_emoji.text = get_emoji(item)
        self.ids.vocab_vn_label.text = vn_name
        self.ids.vocab_ethnic_label.text = 'Tiếng %s: %s' % (language, dt_word)
        self._sync_save_badge()
        status_label.text = '● KẾT QUẢ (%s)' % source_note

    def toggle_save(self):
        item = self.current_word
        if not isinstance(item, dict):
            self.ids.ai_status_label.text = '⭐ Chưa có từ để lưu'
            return
        app = App.get_running_app()
        if app is None:
            return
        now_saved = app.toggle_saved_word(item.get('id', ''))
        self.ids.save_btn_label.text = 'Đã Lưu' if now_saved else 'Lưu'

    def _sync_save_badge(self, *args):
        try:
            saved_ids, _ = load_saved_ids(get_saved_vocabulary_path())
            item = self.current_word
            current_id = str(item.get('id', '')) if isinstance(item, dict) else ''
            self.ids.save_btn_label.text = 'Đã Lưu' if current_id in saved_ids else 'Lưu'
        except Exception:
            pass

    def speak_word(self):
        item = self.current_word
        if not isinstance(item, dict):
            self.ids.ai_status_label.text = '🔊 Hãy nhận diện từ trước đã nhé!'
            return
        self._release_sound()
        if self.learning_direction == 'ethnic':
            self._speak_queue = ['ethnic', 'kinh']
        else:
            self._speak_queue = ['kinh', 'ethnic']
        self._speak_next_part()

    def _speak_next_part(self, *args):
        if not self._speak_queue:
            return
        part = self._speak_queue.pop(0)
        item = self.current_word
        if not isinstance(item, dict):
            return
        word_id = str(item.get('id', '') or '')
        vn_name = get_vietnamese(item)
        status_label = self.ids.ai_status_label

        played_audio_file = False
        if part == 'kinh':
            path = find_audio_file(word_id, 'kinh')
            if path:
                played_audio_file = self._play_sound_file(path, on_stop_callback=self._speak_next_part)
                if played_audio_file:
                    status_label.text = '🔊 Tiếng Kinh: %s' % vn_name
            if not played_audio_file:
                if self._tts_speak_vietnamese(vn_name):
                    status_label.text = '🗣 TTS đọc: %s' % vn_name
                    Clock.schedule_once(self._speak_next_part, 2.0)
                else:
                    status_label.text = '⚠️ Chưa có âm thanh tiếng Kinh'
                    Clock.schedule_once(self._speak_next_part, 1.0)
        else:
            language = self.current_ethnic_language
            path = find_audio_file(word_id, ETHNIC_LANGUAGES.get(language, ''))
            if path:
                played_audio_file = self._play_sound_file(path, on_stop_callback=self._speak_next_part)
                if played_audio_file:
                    status_label.text = '🔊 Tiếng %s (tệp offline)' % language
            if not played_audio_file:
                status_label.text = '⚠️ Chưa có tệp âm thanh tiếng %s' % language
                Clock.schedule_once(self._speak_next_part, 1.0)

    def _play_sound_file(self, path, on_stop_callback=None):
        if not path:
            return False
        self._release_sound()
        try:
            sound = SoundLoader.load(path)
        except Exception:
            return False
        if sound is None:
            return False
        try:
            if on_stop_callback:
                sound.bind(on_stop=lambda inst: Clock.schedule_once(lambda dt: on_stop_callback(), 0.15))
            sound.play()
            self._current_sound = sound
            return True
        except Exception:
            return False

    def _tts_speak_vietnamese(self, text):
        text = str(text or '').strip()
        if not text:
            return False
        try:
            if plyer_tts is not None:
                plyer_tts.speak(text)
                return True
        except Exception:
            pass
        return False

    def _release_sound(self):
        sound = self._current_sound
        self._current_sound = None
        if sound is not None:
            try:
                sound.unbind(on_stop=None)
            except Exception:
                pass
            try:
                sound.stop()
            except Exception:
                pass

    def reset_app(self):
        self._release_sound()
        self._speak_queue = []
        self._scanning = False
        if self.camera_active:
            self.toggle_camera()
        self.current_word = None
        self.captured_image_path = None
        self.ids.ai_status_label.text = '● TRẠNG THÁI: IDLE'
        self.ids.vocab_emoji.text = '🐃'
        self.ids.vocab_vn_label.text = 'Con trâu'
        self.ids.vocab_ethnic_label.text = "H'Mông: tus twm"
        self.ids.save_btn_label.text = 'Lưu'
        self.ids.camera_hint_label.text = 'Bấm "📸 Bật/Tắt" để bắt đầu'

    def release_resources(self):
        self._release_sound()
        self._speak_queue = []
        if self.camera_active:
            self.toggle_camera()


class LibraryScreen(Screen):
    def __init__(self, **kwargs):
        super(LibraryScreen, self).__init__(**kwargs)
        self._detail_popup = None

    def _get_vocabulary(self):
        app = App.get_running_app()
        vocab = getattr(app, 'vocabulary', None) if app is not None else None
        if not isinstance(vocab, list) or len(vocab) == 0:
            try:
                main_screen = self.manager.get_screen('main') if self.manager else None
                vocab = getattr(main_screen, 'vocabulary_list', None)
            except Exception:
                vocab = None
        if not isinstance(vocab, list) or len(vocab) == 0:
            vocab = VocabularyDataLoader.fallback_list()
        return vocab

    def _get_ethnic_language(self):
        try:
            main_screen = self.manager.get_screen('main') if self.manager else None
            language = getattr(main_screen, 'current_ethnic_language', None)
            if isinstance(language, str) and language:
                return language
        except Exception:
            pass
        return "H'Mông"

    def refresh_library(self, *args):
        grid = self.ids.library_grid
        count_label = self.ids.library_count_label
        grid.clear_widgets()

        vocab = self._get_vocabulary()
        if not isinstance(vocab, list) or len(vocab) == 0:
            count_label.text = '⚠️ Chưa nạp được dữ liệu từ vựng'
            grid.add_widget(self._make_message_label('Không có từ vựng nào.'))
            return

        saved_ids, load_error = load_saved_ids(get_saved_vocabulary_path())
        saved_set = set(saved_ids) if isinstance(saved_ids, list) else set()

        saved_words = [it for it in vocab
                       if isinstance(it, dict) and str(it.get('id', '')) in saved_set]
        sample_words = [it for it in vocab
                        if isinstance(it, dict) and str(it.get('id', '')) not in saved_set]
        count_label.text = '⭐ %d từ đã lưu • 🎒 %d từ để học' % (
            len(saved_words), len(sample_words))

        language = self._get_ethnic_language()

        grid.add_widget(self._make_header_label('⭐ TỪ BÉ ĐÃ LƯU (%d)' % len(saved_words)))
        if saved_words:
            self._add_card_rows(grid, saved_words, language, saved_set)
        else:
            grid.add_widget(self._make_message_label('Bé chưa lưu từ nào.'))

        grid.add_widget(self._make_header_label('🎒 KHO TỪ MẪU ĐỂ HỌC (%d)' % len(sample_words)))
        if sample_words:
            self._add_card_rows(grid, sample_words, language, saved_set)
        else:
            grid.add_widget(self._make_message_label('Bé đã lưu hết kho từ!'))

    def _add_card_rows(self, grid, words, language, saved_set):
        for index in range(0, len(words), 2):
            row = BoxLayout(orientation='horizontal',
                            size_hint_y=None, height=dp(96), spacing=dp(10))
            for item in words[index:index + 2]:
                row.add_widget(self._make_card(item, language, saved_set))
            if len(words[index:index + 2]) == 1:
                row.add_widget(BoxLayout())
            grid.add_widget(row)

    def _make_card(self, item, language, saved_set):
        word_id = str(item.get('id', ''))
        is_saved = word_id in saved_set
        card = VocabCard(
            vid=word_id,
            emoji_text=get_emoji(item),
            vn_text=get_vietnamese(item),
            dt_text=get_ethnic_display(item, language),
            badge_text='ĐÃ LƯU ⭐' if is_saved else 'CHƯA LƯU',
        )
        card.bind(on_press=lambda instance, wid=word_id: self.show_word_detail(wid))
        return card

    def _make_header_label(self, text):
        label = Label(text=text, size_hint_y=None, height=dp(28),
                      font_size='14sp', bold=True, color=(0.15, 0.15, 0.2, 1),
                      halign='left', valign='middle')
        label.bind(size=lambda inst, size: setattr(inst, 'text_size', size))
        return label

    def _make_message_label(self, text):
        label = Label(text=text, size_hint_y=None, height=dp(60),
                      font_size='12sp', color=(0.45, 0.45, 0.5, 1),
                      halign='center', valign='middle')
        label.bind(size=lambda inst, size: setattr(inst, 'text_size', size))
        return label

    def show_word_detail(self, word_id):
        word_id = str(word_id or '')
        item = find_word_by_id(self._get_vocabulary(), word_id)
        if not isinstance(item, dict):
            return
        saved_ids, _ = load_saved_ids(get_saved_vocabulary_path())
        is_saved = word_id in saved_ids
        language = self._get_ethnic_language()
        has_kinh_audio = bool(find_audio_file(word_id, 'kinh'))
        has_ethnic_audio = bool(find_audio_file(word_id, ETHNIC_LANGUAGES.get(language, '')))
        if has_kinh_audio and has_ethnic_audio:
            audio_note = '🔊 Có sẵn âm thanh Kinh + tiếng %s' % language
        elif has_kinh_audio or has_ethnic_audio:
            audio_note = '🔊 Có một phần tệp âm thanh'
        else:
            audio_note = '⚠️ Chưa có tệp âm thanh cho từ này'

        content = SaveDialog(
            vid=word_id,
            emoji_text=get_emoji(item),
            vn_text=get_vietnamese(item),
            dt_text='Tiếng %s: %s' % (language, get_ethnic_display(item, language)),
            audio_note=audio_note,
        )
        content.ids.save_btn.text = '⭐ BỎ LƯU' if is_saved else '⭐ LƯU TỪ'
        content.ids.save_btn.bind(on_press=lambda *args: self._save_from_dialog(word_id))
        content.ids.close_btn.bind(on_press=lambda *args: self._close_detail())
        self._detail_popup = Popup(
            title='📖 Chi tiết từ vựng',
            content=content,
            size_hint=(0.88, 0.66),
            auto_dismiss=True,
        )
        self._detail_popup.open()

    def _save_from_dialog(self, word_id):
        app = App.get_running_app()
        if app is not None:
            app.toggle_saved_word(word_id)
        self._close_detail()

    def _close_detail(self, *args):
        if self._detail_popup is not None:
            self._detail_popup.dismiss()
            self._detail_popup = None


class BeHocTiengKinhApp(App):
    title = 'Bé Học Tiếng Kinh & Dân Tộc'

    def __init__(self, **kwargs):
        super(BeHocTiengKinhApp, self).__init__(**kwargs)
        self.vocabulary = []
        self.main_screen = None
        self.library_screen = None

    def build(self):
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.CAMERA, Permission.RECORD_AUDIO])
            except Exception:
                pass
        Builder.load_string(KV)
        sm = ScreenManager()
        self.main_screen = MainScreen(name='main')
        self.library_screen = LibraryScreen(name='library')
        sm.add_widget(self.main_screen)
        sm.add_widget(self.library_screen)

        self.vocabulary = self.main_screen.vocabulary_list
        if not isinstance(self.vocabulary, list) or len(self.vocabulary) == 0:
            self.vocabulary = VocabularyDataLoader.fallback_list()
        return sm

    def toggle_saved_word(self, word_id):
        word_id = str(word_id or '').strip()
        if not word_id:
            return False
        saved_path = get_saved_vocabulary_path()
        saved_ids, load_error = load_saved_ids(saved_path)
        if word_id in saved_ids:
            saved_ids.remove(word_id)
            now_saved = False
        else:
            saved_ids.append(word_id)
            now_saved = True
        save_saved_ids(saved_path, saved_ids)
        if self.library_screen is not None:
            self.library_screen.refresh_library()
        if self.main_screen is not None:
            self.main_screen._sync_save_badge()
        return now_saved

    def on_stop(self):
        if self.main_screen is not None:
            self.main_screen.release_resources()

    def on_pause(self):
        if self.main_screen is not None:
            self.main_screen.release_resources()
        return True


if __name__ == '__main__':
    BeHocTiengKinhApp().run()