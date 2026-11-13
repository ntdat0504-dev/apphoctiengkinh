# -*- coding: utf-8 -*-
"""Lưu/đọc danh sách từ vựng đã lưu (bước 5) — tách khỏi mã giao diện.

Tệp dữ liệu: data/saved_vocabulary.json, chỉ chứa ID của đồ vật
({"saved_ids": ["qua_chuoi", ...]}). Thông tin hiển thị luôn lấy từ
data/sample_vocabulary.json để không lưu trùng nội dung.
"""
import json
import os


def load_saved_ids(path):
    """Đọc danh sách ID đã lưu. Tệp chưa tồn tại → danh sách rỗng, không lỗi.

    Trả về (ids, error): ids là list chuỗi không trùng, giữ thứ tự;
    error là thông báo dễ hiểu khi tệp lỗi (None nếu OK). Không bao giờ sập.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return [], None
    except json.JSONDecodeError as exc:
        return [], 'tệp từ đã lưu lỗi định dạng JSON (%s) — dùng danh sách mới.' % exc
    except (OSError, UnicodeDecodeError) as exc:
        return [], 'không đọc được tệp từ đã lưu (%s) — dùng danh sách mới.' % exc

    if isinstance(data, dict):
        raw = data.get('saved_ids')
    elif isinstance(data, list):  # chấp nhận cả dạng list thuần
        raw = data
    else:
        raw = None
    if not isinstance(raw, list):
        return [], 'dữ liệu từ đã lưu không đúng định dạng — dùng danh sách mới.'

    ids, seen = [], set()
    for value in raw:
        if isinstance(value, str) and value.strip() and value not in seen:
            seen.add(value)
            ids.append(value)
    return ids, None


def save_saved_ids(path, ids):
    """Ghi danh sách ID vào tệp (tạo thư mục đích nếu thiếu, không ghi đè dữ liệu mẫu).

    Trả về None nếu thành công, ngược lại trả về thông báo lỗi dễ hiểu.
    """
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        # dict.fromkeys: loại trùng nhưng giữ nguyên thứ tự
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'saved_ids': list(dict.fromkeys(ids))}, f, ensure_ascii=False, indent=2)
        return None
    except OSError as exc:
        return 'không ghi được tệp từ đã lưu (%s).' % exc
